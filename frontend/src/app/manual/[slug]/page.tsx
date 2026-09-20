"use client";

/**
 * MANUAL 모드 화면 (지시서 §11).
 *
 * CEO 가 직원을 골라 직접 시킨다. 왼쪽에서 자리를 누르고, 아래에서
 * 지시를 적는다.
 *
 * ## 권한을 화면에 적어두는 이유
 *
 * 작가에게 `src/` 를 시키면 백엔드가 거부한다(§8). 그 사실을 지시하기
 * **전에** 알 수 있어야 한다. 거부된 뒤에 알게 되면, 사용자는 제품이
 * 고장 났다고 생각한다.
 */
import { use, useState } from "react";

import { ChatLog } from "@/components/ChatLog";
import { FileViewer } from "@/components/FileViewer";
import { Office } from "@/components/Office";
import { Button, ErrorBox, Panel, Warning } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { Employee, Verdict } from "@/lib/types";
import { useLoader } from "@/lib/useLoader";
import { useSlug } from "@/lib/useSlug";
import { foldState, useStream } from "@/lib/useStream";

export default function ManualPage({ params }: { params: Promise<{ slug: string }> }) {
  const slug = useSlug(use(params));
  const { data, error: loadError, reload } = useLoader(slug, () =>
    api.manualState(slug),
  );
  const employees: Employee[] = data?.employees ?? [];
  const files = data?.files ?? [];

  const [picked, setPicked] = useState<string | null>("developer");
  const [message, setMessage] = useState("");
  // 서버가 말하는 작업 중과, 이 화면이 방금 보낸 지시를 함께 본다.
  // 서버 것만 보면 응답이 돌아오기 전까지 버튼이 열려 있어 두 번 눌린다.
  const [sending, setSending] = useState<string | null>(null);
  const busy = sending ?? data?.busy ?? null;
  const [error, setError] = useState<string | null>(null);
  const [verdict, setVerdict] = useState<Verdict | null>(null);

  const stream = useStream(slug);
  const folded = foldState(stream.events);

  const employee = employees.find((e) => e.id === picked) ?? null;
  const allMock = employees.length > 0 && employees.every((e) => e.mock);

  const send = async () => {
    const text = message.trim();
    if (!text || !picked || busy) return;
    setSending(picked);
    setError(null);
    try {
      await api.instruct(slug, picked, text);
      setMessage("");
      await reload();
    } catch (e) {
      setError(
        e instanceof ApiError && e.isBudget
          ? `${e.message}`
          : e instanceof Error
            ? e.message
            : String(e),
      );
    } finally {
      setSending(null);
    }
  };

  const verify = async () => {
    if (busy) return;
    setSending("analyst");
    setError(null);
    try {
      const b = await api.verifyManual(slug);
      setVerdict(b.verdict);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(null);
    }
  };

  return (
    <div className="space-y-4">
      {allMock && (
        <Warning>
          <strong>Mock 직원입니다.</strong> 지시는 실제로 전달되지만 답은 대본입니다.
        </Warning>
      )}
      {(error || loadError) && <ErrorBox>{error ?? loadError}</ErrorBox>}

      <Panel
        title="직원을 고르세요"
        right={
          <Button onClick={verify} disabled={!!busy}>
            지금 검증하기
          </Button>
        }
      >
        <Office
          employees={employees}
          busy={busy}
          picked={picked}
          onPick={(id) => setPicked(id)}
        />
      </Panel>

      <Panel
        title={
          employee ? `${employee.name}(${employee.role})에게 지시` : "직원을 고르세요"
        }
      >
        {employee && (
          <p className="mb-2 text-xs text-dim">
            쓸 수 있는 폴더:{" "}
            <strong className="text-muted">
              {employee.writes.length
                ? employee.writes.map((w) => `${w}/`).join(", ")
                : "없음 (글로만 답합니다)"}
            </strong>
            {" · "}읽기: {employee.reads.map((r) => `${r}/`).join(", ")}
          </p>
        )}
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          rows={3}
          disabled={!!busy}
          placeholder="예) div 에 0 나눗셈 예외 처리를 넣어주세요"
          className="w-full resize-y rounded-lg border border-line bg-panel2 px-3 py-2
            text-sm outline-none placeholder:text-dim focus:border-accent
            disabled:opacity-50"
        />
        <div className="mt-2 flex items-center gap-2">
          <Button tone="primary" onClick={send} disabled={!!busy || !message.trim() || !picked}>
            {busy ? "작업 중…" : "지시하기"}
          </Button>
          <span className="text-xs text-dim">
            {folded.phase && `${folded.phase} · ${folded.detail}`}
          </span>
        </div>
      </Panel>

      {verdict && (
        <Panel title="검증 결과">
          <p
            className="text-sm font-semibold"
            style={{ color: verdict.verdict === "pass" ? "var(--ok)" : "var(--bad)" }}
          >
            {verdict.verdict === "pass" ? "통과" : `반려 (${verdict.severity})`}
          </p>
          <p className="mt-1 text-sm text-muted">{verdict.message_to_team}</p>
          {verdict.findings.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs">
              {verdict.findings.map((f, i) => (
                <li key={i}>
                  <code className="text-muted">{f.file}</code> — {f.issue}
                  <span className="block text-dim">{f.why}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
        <Panel title="산출물">
          <FileViewer slug={slug} files={files} />
        </Panel>
        <Panel title="작업 로그" className="flex max-h-[30rem] flex-col overflow-hidden">
          <div className="-m-4 flex min-h-0 flex-1 flex-col">
            <ChatLog
              events={stream.events}
              roster={stream.roster}
              connected={stream.connected}
              polling={stream.polling}
              className="h-[24rem]"
            />
          </div>
        </Panel>
      </div>
    </div>
  );
}
