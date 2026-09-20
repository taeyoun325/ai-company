"use client";

/**
 * 요금제와 크레딧 (지시서 §15 · §16).
 *
 * ## 크레딧이 무엇인지 화면에서 말한다
 *
 * "1,200 크레딧"만 보여주면 그게 많은 건지 적은 건지 알 수 없다.
 * 1 크레딧이 몇 달러어치 원가인지, 그 요금제로 프로젝트를 몇 개쯤
 * 돌릴 수 있는지 같이 적는다.
 *
 * ## 결제는 여기 없다
 *
 * 결제 연동은 이 제품의 범위 밖이다. 이 화면이 성립시키는 것은
 * **잔액이 실제로 줄고 실제로 막히는가** 하나다. 그래서 "충전"은
 * 데모용이라고 화면에 적는다 — 적지 않으면 결제가 붙은 줄 안다.
 */
import { useState } from "react";

import { Button, ErrorBox, Panel, Warning, money } from "@/components/ui";
import { api } from "@/lib/api";
import { useLoader } from "@/lib/useLoader";

export default function PricingPage() {
  const { data, error, reload } = useLoader("pricing", async () => {
    const [plans, credits] = await Promise.all([api.plans(), api.credits()]);
    return { plans, credits };
  });
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const plans = data?.plans.plans ?? {};
  const wallet = data?.credits;

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setFailure(null);
    try {
      await fn();
      await reload();
    } catch (e) {
      setFailure(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      {(error || failure) && <ErrorBox>{failure ?? error}</ErrorBox>}

      {wallet && !wallet.prices_verified && (
        <Warning>
          <strong>단가가 검증되지 않았습니다.</strong> 잔액과 비용은 추측입니다.
        </Warning>
      )}

      {wallet && (
        <Panel
          title="내 크레딧"
          right={
            <span className="text-xs text-dim">
              {wallet.plan_label} 요금제
            </span>
          }
        >
          <div className="flex flex-wrap items-end gap-6">
            <div>
              <p className="text-3xl font-bold tabular-nums">
                {wallet.balance.toFixed(1)}
              </p>
              <p className="text-[11px] text-dim">
                남은 크레딧 · 원가로 {money(wallet.balance_usd)}
              </p>
            </div>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
              <dt className="text-dim">받은 크레딧</dt>
              <dd className="tabular-nums">{wallet.granted.toFixed(0)}</dd>
              <dt className="text-dim">쓴 크레딧</dt>
              <dd className="tabular-nums">{wallet.spent.toFixed(1)}</dd>
              <dt className="text-dim">동시 실행</dt>
              <dd>{wallet.max_concurrent}건</dd>
              <dt className="text-dim">프로젝트당 상한</dt>
              <dd>{money(wallet.max_project_cost)}</dd>
            </dl>
          </div>

          {wallet.balance < 0 && (
            <p className="mt-3 text-sm" style={{ color: "var(--bad)" }}>
              잔액이 마이너스입니다. 초과분은 지워지지 않고 그대로 남습니다 —
              다음 달에 그만큼 덜 받습니다.
            </p>
          )}

          <div className="mt-3 flex items-center gap-2">
            <Button onClick={() => void act(() => api.topUp(500))} disabled={busy}>
              500 크레딧 충전
            </Button>
            <span className="text-[11px] text-dim">
              결제 연동은 없습니다. 잔액이 실제로 줄고 막히는지 확인하기 위한
              데모용 버튼입니다.
            </span>
          </div>

          <p className="mt-2 text-[11px] text-dim">
            1 크레딧 = 원가 {money(wallet.credit_usd)}
            {wallet.prices_verified_on &&
              ` · 단가 대조일 ${wallet.prices_verified_on}`}
          </p>
        </Panel>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        {Object.entries(plans).map(([name, p]) => {
          const current = wallet?.plan === name;
          return (
            <Panel
              key={name}
              title={p.label}
              className={current ? "border-accent" : ""}
              right={
                current && (
                  <span className="text-[11px]" style={{ color: "var(--accent)" }}>
                    사용 중
                  </span>
                )
              }
            >
              <p className="text-2xl font-bold tabular-nums">
                {p.price_usd === 0 ? "무료" : `$${p.price_usd}`}
                {p.price_usd > 0 && (
                  <span className="text-xs font-normal text-dim"> / 월</span>
                )}
              </p>
              <ul className="mt-3 space-y-1 text-xs text-muted">
                <li>월 {p.credits.toLocaleString()} 크레딧</li>
                <li>동시 실행 {p.max_concurrent}건</li>
                <li>프로젝트당 최대 {money(p.max_project_cost)}</li>
                <li className="text-dim">
                  계산기 한 개 규모(약 10 크레딧)로 치면 월{" "}
                  {Math.floor(p.credits / 10)}개 남짓
                </li>
              </ul>
              <Button
                className="mt-3 w-full"
                tone={current ? "default" : "primary"}
                disabled={busy || current}
                onClick={() => void act(() => api.changePlan(name))}
              >
                {current ? "현재 요금제" : "이 요금제로"}
              </Button>
            </Panel>
          );
        })}
      </div>
    </div>
  );
}
