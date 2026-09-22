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
import { useErrorText, useLang } from "@/lib/i18n";
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
  const { t } = useLang();
  const errText = useErrorText();
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
      setError(errText(e));
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
          detail: errText(e),
        },
      }));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel
      title={t("byok.title")}
      right={
        status.source === "byok" && (
          <span
            className="text-[11px]"
            style={{ color: status.ready ? "var(--ok)" : "var(--bad)" }}
          >
            {status.ready ? t("byok.inUse") : t("byok.short")}
          </span>
        )
      }
    >
      {status.source === "byok" && !status.ready && (
        <Warning>
          {t("byok.warn")}
        </Warning>
      )}

      <p className="mb-3 text-xs text-dim">
        <Filled text={t("byok.body")} strong={t("byok.body.strong")} />
      </p>

      {!status.kek_from_env && (
        <p className="mb-3 text-[11px]" style={{ color: "var(--bad)" }}>
          {t("byok.kekWarn")}
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
              placeholder={k.masked ?? t("set.notRegistered")}
              className="min-w-0 flex-1 rounded-lg border border-line bg-panel2 px-3 py-1.5
                font-mono text-sm outline-none focus:border-accent"
            />
            <Button onClick={() => void check(name)} disabled={!k.set || busy}>
              {t("set.check")}
            </Button>
            {k.set && (
              <Button
                tone="ghost"
                disabled={busy}
                onClick={() => void run(() => api.clearByok(name))}
              >
                {t("byok.clear")}
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
          {t("set.save")}
        </Button>
        <span className="text-[11px] text-dim">
          <Filled text={t("byok.crossNote")}
                  strong={t("byok.crossNote.strong")} />
        </span>
      </div>
    </Panel>
  );
}

/**
 * `{strong}` 자리에 굵은 조각을 끼운다. 번역문마다 강조할 조각의
 * **위치가 다르다** — 문장을 앞뒤로 쪼개 두면 언어마다 어순이 어긋난다.
 */
function Filled({ text, strong }: { text: string; strong: string }) {
  const [before, after = ""] = text.split("{strong}");
  return (
    <>
      {before}
      <strong className="text-fg">{strong}</strong>
      {after}
    </>
  );
}
