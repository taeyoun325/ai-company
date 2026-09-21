"use client";

/**
 * 내 API 키 (BYOK · DAY 19).
 *
 * ## 운영자 키 패널과 나란히 있지만 다른 것이다
 *
 * 위쪽 "API 키" 패널은 **이 서버를 운영하는 사람**의 키다. 서버 배포에서는
 * 아예 잠긴다. 이 패널은 **내 키**이고, 저장소도 라우트도 따로다. 화면에서
 * 둘을 섞어 보여주면 사용자는 자기 키를 운영자 칸에 넣는다.
 *
 * ## 넣었다는 것과 동작한다는 것은 다르다
 *
 * 저장과 확인을 나눈다. 확인 버튼은 **내 키로** 실제 조회를 한 번 한다.
 * 요금제를 바꾸기 전에 키부터 확인하는 것이 정상적인 순서다.
 *
 * ## 원문은 돌아오지 않는다
 *
 * 서버는 마스킹된 형태만 내려준다. 입력은 항상 새로 받는다.
 */
import { useState } from "react";

import { Button, Panel, Warning } from "@/components/ui";
import { api } from "@/lib/api";
import type { ByokStatus } from "@/lib/types";

const LABEL: Record<string, string> = {
  anthropic: "Anthropic (Claude)",
  gemini: "Google (Gemini)",
  openai: "OpenAI (GPT)",
};

export function ByokPanel({
  status,
  reload,
}: {
  status: ByokStatus | null;
  reload: () => Promise<void> | void;
}) {
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [checks, setChecks] = useState<
    Record<string, { ok: boolean; detail: string }>
  >({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!status) return null;

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const save = () => {
    const filled = Object.fromEntries(
      Object.entries(draft).filter(([, v]) => v.trim() !== ""),
    );
    if (Object.keys(filled).length === 0) return;
    return run(async () => {
      await api.setByok(filled);
      setDraft({});
    });
  };

  const check = async (provider: string) => {
    setBusy(true);
    try {
      const r = await api.verifyByok(provider);
      setChecks((c) => ({ ...c, [provider]: { ok: r.ok, detail: r.detail } }));
    } catch (e) {
      setChecks((c) => ({
        ...c,
        [provider]: {
          ok: false,
          detail: e instanceof Error ? e.message : String(e),
        },
      }));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel
      title="내 API 키 (자체 키 요금제)"
      right={
        status.source === "byok" && (
          <span
            className="text-[11px]"
            style={{ color: status.ready ? "var(--ok)" : "var(--bad)" }}
          >
            {status.ready ? "사용 중" : "키가 모자랍니다"}
          </span>
        )
      }
    >
      {status.source === "byok" && !status.ready && (
        <Warning>
          자체 키 요금제인데 키가 모자랍니다 — 실행이 거부됩니다. 운영자 키로
          대신 호출하지 않습니다.
        </Warning>
      )}

      <p className="mb-3 text-xs text-dim">
        여기 넣은 키로 내 프로젝트가 돌아가고, <strong>모델 요금은 내
        계정으로 직접 청구됩니다.</strong> 크레딧은 차감되지 않습니다. 키는
        암호화해서 보관하고 화면에는 마스킹된 형태만 돌아옵니다.
      </p>

      {!status.kek_from_env && (
        <p className="mb-3 text-[11px]" style={{ color: "var(--bad)" }}>
          이 서버는 키 암호화 키(KEK)를 파일에 두고 있습니다. 서버 디스크를
          가져간 사람은 여기 넣은 키도 가져갑니다 — 운영자는 BYOK_SECRET 을
          환경변수로 넣어야 합니다.
        </p>
      )}

      {error && (
        <p className="mb-3 text-xs" style={{ color: "var(--bad)" }}>
          {error}
        </p>
      )}

      <div className="space-y-3">
        {Object.entries(status.keys).map(([name, k]) => (
          <div key={name} className="flex flex-wrap items-center gap-2">
            <label className="w-40 shrink-0 text-sm" htmlFor={`byok-${name}`}>
              {LABEL[name] ?? name}
            </label>
            <input
              id={`byok-${name}`}
              type="password"
              autoComplete="off"
              value={draft[name] ?? ""}
              onChange={(e) =>
                setDraft((d) => ({ ...d, [name]: e.target.value }))
              }
              placeholder={k.masked ?? "등록되지 않음"}
              className="min-w-0 flex-1 rounded-lg border border-line bg-panel2 px-3 py-1.5
                font-mono text-sm outline-none focus:border-accent"
            />
            <Button onClick={() => void check(name)} disabled={!k.set || busy}>
              확인
            </Button>
            {k.set && (
              <Button
                tone="ghost"
                disabled={busy}
                onClick={() => void run(() => api.clearByok(name))}
              >
                지우기
              </Button>
            )}
            {checks[name] && (
              <span
                className="w-full text-xs sm:w-auto"
                style={{ color: checks[name].ok ? "var(--ok)" : "var(--bad)" }}
              >
                {checks[name].detail}
              </span>
            )}
          </div>
        ))}
      </div>

      <div className="mt-3 flex items-center gap-3">
        <Button tone="primary" onClick={() => void save()} disabled={busy}>
          저장
        </Button>
        <span className="text-[11px] text-dim">
          구현자와 검증자는 <strong>서로 다른 회사</strong>여야 합니다 —
          Anthropic 과 Google 키가 둘 다 있어야 교차검증이 성립합니다.
        </span>
      </div>
    </Panel>
  );
}
