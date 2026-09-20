/**
 * SSE 전용 프록시 (지시서 §13).
 *
 * ## 왜 rewrite 로는 안 되나
 *
 * `next.config.ts` 의 `/api/:path*` rewrite 는 보통의 JSON 요청에는 잘
 * 동작하지만, **SSE 를 버퍼링한다.** 실제로 겪은 증상은 이렇다:
 *
 *   - `curl -N` 으로는 이벤트가 즉시 흘러나온다
 *   - 브라우저의 EventSource 는 `onopen` 까지만 오고 이벤트가 안 온다
 *
 * 연결은 열렸으므로 화면은 "연결됨"이라고 표시하고, 작업 로그만 영영
 * 비어 있다. 원인을 찾기 가장 어려운 종류의 고장이다.
 *
 * 그래서 이 경로만 라우트 핸들러로 가로채서 업스트림 응답 본문을
 * **그대로 흘려보낸다.** 라우트 핸들러가 rewrite 보다 우선한다.
 *
 * ## 압축을 끄는 이유
 *
 * 중간 단계가 gzip 을 하려면 일정량이 모일 때까지 기다린다. 그게 곧
 * 버퍼링이다. 업스트림에 `identity` 를 요구하고, 내려보낼 때도
 * `X-Accel-Buffering: no` 를 붙여 배포 환경의 역프록시에도 같은 말을 한다.
 */
import type { NextRequest } from "next/server";

// 이 경로는 절대 캐시되면 안 된다. 캐시된 SSE 는 '한 번 있었던 일'을
// 계속 다시 보여주는 화면이 된다.
export const dynamic = "force-dynamic";
export const revalidate = 0;
export const fetchCache = "force-no-store";

const BACKEND = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8000";

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const upstream = `${BACKEND}/api/stream${url.search}`;

  let res: Response;
  try {
    res = await fetch(upstream, {
      headers: {
        accept: "text/event-stream",
        // 압축을 요구하지 않는다. 압축은 모아야 하고, 모으면 실시간이 아니다.
        "accept-encoding": "identity",
        // 재연결 이어받기(§13). 이 헤더를 안 넘기면 끊긴 동안의 로그가 사라진다.
        ...(req.headers.get("last-event-id")
          ? { "last-event-id": req.headers.get("last-event-id") as string }
          : {}),
      },
      cache: "no-store",
      signal: req.signal,
    });
  } catch (e) {
    // 백엔드가 안 떠 있는 경우. 502 로 답해야 화면이 "연결 끊김"을 말할 수 있다.
    return new Response(`백엔드에 닿지 못했습니다: ${String(e)}`, { status: 502 });
  }

  if (!res.ok || !res.body) {
    return new Response(await res.text().catch(() => ""), { status: res.status });
  }

  return new Response(res.body, {
    status: res.status,
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
