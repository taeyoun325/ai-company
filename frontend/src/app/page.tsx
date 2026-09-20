"use client";

/**
 * 사무실 — 메인 화면 (지시서 §4 · §10 · §11).
 *
 * CEO 가 하는 일은 둘뿐이다: 일을 맡기거나(AUTO), 직원을 지목해
 * 직접 시키거나(MANUAL). 그래서 이 화면의 중심은 **입력창 하나와
 * 직원 다섯 명**이고, 나머지는 곁가지다.
 *
 * Mock 경고를 위쪽에 고정으로 띄운다. 접히거나 사라지면 아무도 안 본다.
 */
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ChatLog } from "@/components/ChatLog";
import { Office } from "@/components/Office";
import { ScorePanel, TaskBoard } from "@/components/TaskBoard";
import { Button, ErrorBox, Panel, Warning } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { CreditStatus, Employee, ProviderStatus } from "@/lib/types";
import { useLoader } from "@/lib/useLoader";
import { foldState, useStream } from "@/lib/useStream";

export default function OfficePage() {
  const router = useRouter();
  const [slug, setSlug] = useState<string | null>(null);
  // 실행 slug 를 같이 보낸다. 안 보내면 직원별 사용량이 전부 0 으로 와서,
  // 한창 일하는 중인데 사무실이 "아무도 일하지 않음"으로 보인다.
  const { data: state, error: loadError, reload } = useLoader(slug ?? "", () =>
    api.state(slug ?? undefined),
  );
  const employees: Employee[] = state?.employees ?? [];
  const providers: ProviderStatus | null = state?.providers ?? null;
  const wallet: CreditStatus | null = state?.credits ?? null;
  const [requirement, setRequirement] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [routing, setRouting] = useState<{ employee: string; why: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const stream = useStream(slug ?? undefined);
  const folded = foldState(stream.events);
  // 진행 중인가는 **계산 결과**다. 따로 상태로 들고 있으면 done 이벤트를
  // 놓쳤을 때 버튼이 영영 잠긴 채로 남는다.
  const running = slug !== null && folded.done === null;

  // 실행 중에는 직원별 사용량이 계속 바뀐다. 단계가 넘어갈 때만 다시
  // 읽는다 — 고정 간격 폴링은 아무 일도 없을 때까지 서버를 두드린다.
  useEffect(() => {
    if (slug) void reload();
  }, [slug, folded.phase, folded.done, reload]);

  const start = async () => {
    const text = requirement.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    setRouting(null);
    stream.clear();
    try {
      const r = await api.startRun(text);
      setSlug(r.slug);
    } catch (e) {
      setError(
        e instanceof ApiError && e.isBudget
          ? `${e.message} — 요금제 화면에서 충전하거나 요금제를 올리세요.`
          : e instanceof ApiError && e.isBusy
            ? `${e.message} (동시 실행 한도는 비용과 요청 한도를 함께 막는 장치입니다)`
            : e instanceof Error
              ? e.message
              : String(e),
      );
    } finally {
      setBusy(false);
    }
  };

  const askRouting = async () => {
    const text = requirement.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    try {
      setRouting(await api.route(text));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const openManual = async () => {
    const text = requirement.trim();
    if (!text || busy) return;
    setBusy(true);
    try {
      const r = await api.openManual(text);
      router.push(`/manual/${r.slug}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (!slug) return;
    try {
      await api.cancelRun(slug);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const allMock = providers?.all_mock ?? false;

  return (
    <div className="space-y-4">
      {allMock && (
        <Warning>
          <strong>지금은 Mock 직원이 일합니다.</strong> 산출물은 실제 AI 의 작업
          결과가 아니라 미리 짜인 대본입니다.{" "}
          <a href="/settings" className="underline">
            설정에서 API 키를 등록
          </a>
          하면 실제 직원이 일합니다.
        </Warning>
      )}
      {providers && !allMock && !providers.cross_check && (
        <Warning>
          <strong>교차검증이 성립하지 않습니다.</strong> 구현자와 검증자가 같은
          회사의 모델이거나, 검증자 쪽 키가 없습니다. 같은 모델은 같은 실수를
          함께 놓칩니다.
        </Warning>
      )}
      {(error || loadError) && <ErrorBox>{error ?? loadError}</ErrorBox>}

      <Panel
        title="무엇을 만들까요?"
        right={
          slug && (
            <span className="text-xs text-dim">
              프로젝트 <code>{slug}</code>
            </span>
          )
        }
      >
        <textarea
          value={requirement}
          onChange={(e) => setRequirement(e.target.value)}
          rows={3}
          placeholder="예) 사칙연산을 하는 계산기 모듈과 사용법 문서를 만들어주세요"
          className="w-full resize-y rounded-lg border border-line bg-panel2 px-3 py-2
            text-sm outline-none placeholder:text-dim focus:border-accent"
        />
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Button tone="primary" onClick={start} disabled={busy || running || !requirement.trim()}>
            AUTO 로 맡기기
          </Button>
          <Button onClick={openManual} disabled={busy || !requirement.trim()}>
            직접 지시하기 (MANUAL)
          </Button>
          <Button tone="ghost" onClick={askRouting} disabled={busy || !requirement.trim()}>
            누가 맡을지 먼저 보기
          </Button>
          {running && (
            <Button tone="danger" onClick={cancel} className="ml-auto">
              정지
            </Button>
          )}
        </div>
        {routing && (
          <p className="mt-2 text-xs text-muted">
            전략가의 판단:{" "}
            <strong style={{ color: `var(--${routing.employee}, var(--accent))` }}>
              {routing.employee}
            </strong>{" "}
            — {routing.why}
          </p>
        )}
      </Panel>

      <Panel
        title="사무실"
        right={
          folded.phase && (
            <span className="text-xs text-muted">
              {folded.phase}
              {folded.detail ? ` · ${folded.detail}` : ""}
            </span>
          )
        }
      >
        <Office
          employees={employees}
          phase={folded.phase}
          detail={folded.detail}
        />
      </Panel>

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <Panel title="작업 로그" className="flex max-h-[32rem] flex-col overflow-hidden">
          <div className="-m-4 flex min-h-0 flex-1 flex-col">
            <ChatLog
              events={stream.events}
              roster={stream.roster}
              connected={stream.connected}
              polling={stream.polling}
              className="h-[26rem]"
            />
          </div>
        </Panel>

        <div className="space-y-4">
          {wallet && (
            <Panel title="크레딧">
              <div className="flex items-end justify-between">
                <div>
                  <p className="text-2xl font-bold tabular-nums">
                    {wallet.balance.toFixed(0)}
                  </p>
                  <p className="text-[11px] text-dim">
                    남은 크레딧 · {wallet.plan_label} 요금제
                  </p>
                </div>
                <a href="/pricing" className="text-xs text-muted underline">
                  요금제
                </a>
              </div>
              {!wallet.prices_verified && (
                <p className="mt-2 text-[11px]" style={{ color: "var(--mock)" }}>
                  단가가 검증되지 않아 이 숫자는 추측입니다.
                </p>
              )}
            </Panel>
          )}
          <Panel title="완성도와 비용">
            <ScorePanel
              score={folded.score}
              detail={folded.scoreDetail}
              cost={folded.totals?.cost}
              round={folded.round}
            />
          </Panel>
          <Panel title="태스크">
            <TaskBoard tasks={folded.tasks} />
          </Panel>
          {folded.files.length > 0 && (
            <Panel title="산출물">
              <ul className="space-y-1 font-mono text-xs">
                {folded.files.map((f) => (
                  <li key={f} className="truncate text-muted" title={f}>
                    {f}
                  </li>
                ))}
              </ul>
              {slug && (
                <Button
                  className="mt-3 w-full"
                  onClick={() => router.push(`/projects/${slug}`)}
                >
                  프로젝트 상세 보기
                </Button>
              )}
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}
