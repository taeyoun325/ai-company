"use client";

/**
 * 설정 — API 키와 모델 (지시서 §7).
 *
 * ## 키를 되돌려주지 않는다
 *
 * 백엔드는 마스킹된 형태만 내려준다. 화면이 원문을 들고 있으면 그게
 * 브라우저 메모리·확장·스크린샷으로 샌다. 입력은 항상 새로 받는다.
 *
 * ## "저장" 과 "확인" 을 나눈다
 *
 * 키를 넣었다는 것과 그 키가 실제로 동작한다는 것은 다르다. 확인
 * 버튼은 실제로 모델 목록을 조회한다 — 키를 맨 마지막에 넣는 방침
 * 아래에서 이 버튼이 첫 실물 호출이 된다.
 *
 * ## 운영자 키와 내 키는 다른 패널이다 (DAY 19)
 *
 * 위쪽은 **이 서버를 운영하는 사람**의 키이고, 서버 배포(saas)에서는
 * 잠긴다 — 그 화면이 열려 있으면 로그인한 아무나 운영자 키를 덮어쓴다.
 * 아래 `ByokPanel` 은 **내 키**이고 저장소부터 다르다.
 */
import { useState } from "react";

import { ByokPanel } from "@/components/ByokPanel";
import { Button, ErrorBox, MockBadge, Panel, Screen, Skeleton, Warning }
  from "@/components/ui";
import { useLang } from "@/lib/i18n";
import { api } from "@/lib/api";
import type { ByokStatus, Employee, ProviderStatus, Settings } from "@/lib/types";
import { useLoader } from "@/lib/useLoader";

export default function SettingsPage() {
  const { t } = useLang();
  const { data, error: loadError, loading, reload: load } = useLoader("settings", async () => {
    const [s, st, b] = await Promise.all([
      api.settings(),
      api.state(),
      api.byok(),
    ]);
    return { settings: s, providers: st.providers, employees: st.employees, byok: b };
  });
  const settings: Settings | null = data?.settings ?? null;
  const providers: ProviderStatus | null = data?.providers ?? null;
  const employees: Employee[] = data?.employees ?? [];
  const byok: ByokStatus | null = data?.byok ?? null;
  const operatorLocked = settings ? !settings.operator_settings : false;

  const [draft, setDraft] = useState<Record<string, string>>({});
  const [remember, setRemember] = useState(false);
  const [checks, setChecks] = useState<Record<string, { ok: boolean; detail: string }>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    const filled = Object.fromEntries(
      Object.entries(draft).filter(([, v]) => v.trim() !== ""),
    );
    if (Object.keys(filled).length === 0) return;
    setBusy(true);
    try {
      await api.setKeys(filled, remember);
      setDraft({});
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const check = async (provider: string) => {
    setBusy(true);
    try {
      const r = await api.verifyKey(provider);
      setChecks((c) => ({ ...c, [provider]: { ok: r.ok, detail: r.detail } }));
    } catch (e) {
      setChecks((c) => ({
        ...c,
        [provider]: { ok: false, detail: e instanceof Error ? e.message : String(e) },
      }));
    } finally {
      setBusy(false);
    }
  };

  const setModel = async (id: string, model: string) => {
    try {
      await api.setEmployeeModel(id, model);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  // 키 이름(anthropic/gemini/openai)과 제공자 이름(claude/gemini/openai)이
  // 다르다. 화면에서 이어 붙여야 "키를 넣었는데 여전히 Mock" 이 안 생긴다.
  const KEY_OF: Record<string, string> = {
    claude: "anthropic",
    gemini: "gemini",
    openai: "openai",
  };

  return (
    <Screen>
    <div className="space-y-4">
      {(error || loadError) && <ErrorBox>{error ?? loadError}</ErrorBox>}

      {loading && !data && (
        <Panel title={t("set.operatorKeys")}>
          <Skeleton lines={4} />
        </Panel>
      )}

      {providers?.all_mock && (
        <Warning>
          {t("set.allMock")}
        </Warning>
      )}
      {providers && !providers.all_mock && !providers.cross_check && (
        <Warning>
          {t("set.noCross")}
        </Warning>
      )}

      <ByokPanel status={byok} reload={load} />

      <Panel title={t("set.operatorKeys")}>
        <p className="mb-3 text-xs text-dim">
          {operatorLocked
            ? t("set.operatorLocked")
            : t("set.operatorHint")}
        </p>
        <div className="space-y-3">
          {settings &&
            Object.entries(settings.keys).map(([name, k]) => (
              <div key={name} className="flex flex-wrap items-center gap-2">
                <label className="w-40 shrink-0 text-sm" htmlFor={`key-${name}`}>
                  {k.label}
                </label>
                <input
                  id={`key-${name}`}
                  type="password"
                  autoComplete="off"
                  value={draft[name] ?? ""}
                  onChange={(e) => setDraft((d) => ({ ...d, [name]: e.target.value }))}
                  disabled={operatorLocked}
                  placeholder={
                    operatorLocked
                      ? (k.set ? t("set.registeredEnv") : t("set.notRegistered"))
                      : (k.masked ?? t("set.notRegistered"))
                  }
                  className="min-w-0 flex-1 rounded-lg border border-line bg-panel2 px-3 py-1.5
                    font-mono text-sm outline-none focus:border-accent"
                />
                <Button
                  onClick={() => void check(name)}
                  disabled={!k.set || busy || operatorLocked}
                >
                  {t("set.check")}
                </Button>
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
          <Button tone="primary" onClick={save} disabled={busy || operatorLocked}>
            {t("set.save")}
          </Button>
          <label className="flex items-center gap-1.5 text-xs text-muted">
            <input
              type="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
            />
            {t("set.persist")}
          </label>
          {settings?.stored && (
            <Button tone="ghost" onClick={() => void api.forgetKeys().then(load)}>
              {t("set.forget")}
            </Button>
          )}
        </div>
      </Panel>

      <Panel title={t("set.providers")}>
        <ul className="space-y-2">
          {providers?.providers.map((p) => (
            <li
              key={p.name}
              className="flex flex-wrap items-center gap-2 rounded-lg bg-panel2 px-3 py-2 text-sm"
            >
              <span className="w-20 font-medium">{p.name}</span>
              <span className="text-xs text-muted">{p.model}</span>
              {p.mock ? (
                <MockBadge title={t("mock.badge")} />
              ) : (
                <span className="text-xs" style={{ color: "var(--ok)" }}>
                  {t("set.real")}
                </span>
              )}
              <span className="ml-auto text-[11px] text-dim">
                {settings?.keys[KEY_OF[p.name]]?.set ? t("set.keyYes") : t("set.keyNo")}
                {p.fallbacks.length > 0 &&
                  ` · ${t("set.fallback")} → ${p.fallbacks.join(", ")}`}
              </span>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel title={t("set.models")}>
        <p className="mb-3 text-xs text-dim">
          {t("set.modelsHint")}
        </p>
        <ul className="space-y-2">
          {employees.map((e) => {
            const catalog = settings?.catalog[e.provider]?.models ?? [];
            return (
              <li key={e.id} className="flex flex-wrap items-center gap-2 text-sm">
                <span
                  className="w-28 shrink-0 font-medium"
                  style={{ color: `var(--${e.id}, var(--fg))` }}
                >
                  {e.name}
                </span>
                <span className="w-16 shrink-0 text-xs text-dim">{e.role}</span>
                <select
                  value={e.model}
                  onChange={(ev) => void setModel(e.id, ev.target.value)}
                  className="min-w-0 flex-1 rounded-lg border border-line bg-panel2 px-2 py-1
                    text-sm outline-none focus:border-accent"
                >
                  {catalog.length === 0 && <option value={e.model}>{e.model}</option>}
                  {catalog.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label} ({m.tier})
                    </option>
                  ))}
                </select>
                {e.mock && <MockBadge title={t("mock.badge")} />}
              </li>
            );
          })}
        </ul>
      </Panel>
    </div>
    </Screen>
  );
}
