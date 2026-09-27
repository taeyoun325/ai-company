import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  // 이 폴더를 루트로 못박는다. 안 박으면 Next 가 상위로 거슬러 올라가
  // 홈 디렉터리의 package-lock.json 을 집어 경고를 낸다.
  turbopack: { root: path.resolve(__dirname) },

  // 화면 시험(e2e/serve.mjs)은 켜둔 개발 서버와 **다른 빌드 폴더**를 쓴다.
  // 두 dev 서버가 같은 `.next` 를 쓰면 서로의 캐시를 깬다 (DAY 26).
  distDir: process.env.NEXT_DIST_DIR || ".next",

  // 컨테이너 배포용 (DAY 16). 실행에 필요한 것만 추려 `.next/standalone` 에
  // 담아준다 — node_modules 전체를 이미지에 넣지 않아도 된다.
  output: "standalone",

  // `/api` 는 아래 rewrites 로 백엔드에 넘기는데, Next 는 넘기는 요청 본문을
  // **10MB 에서 자른다**(경고 한 줄만 남기고). 작업 지시에 붙이는 영상은
  // 20MB 까지 받으므로(backend/app/attachments.py) 잘린 영상이 끝없이
  // "올리는 중 100%" 에 멈춰 있었다 (DAY 28). 한 파일 20MB + 양식 머리를 넉넉히.
  experimental: {
    proxyClientMaxBodySize: "32mb",
  },

  async rewrites() {
    // 개발 중에는 프론트(3000)에서 /api 를 백엔드(8000)로 그대로 넘긴다.
    // CORS 설정을 따로 두지 않기 위해서다.
    //
    // **SSE 는 이 경로를 타지 않는다.** 이 rewrite 는 브라우저가 압축을
    // 요구하면 응답을 버퍼링해서, EventSource 가 `onopen` 까지만 받고
    // 이벤트를 하나도 못 받는다(실제로 겪었다 — 화면은 "연결됨"이라고
    // 표시한 채 작업 로그만 영영 비어 있었다). 그래서 `/api/stream` 만
    // 라우트 핸들러(src/app/api/stream/route.ts)가 가로채 흘려보낸다.
    // 라우트 핸들러가 rewrite 보다 우선한다.
    const backend = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
