"use client";

/**
 * 요금제와 크레딧 (지시서 §15 · §16 · DAY 19).
 *
 * ## 크레딧이 무엇인지 화면에서 말한다
 *
 * "900 크레딧"만 보여주면 그게 많은 건지 적은 건지 알 수 없다.
 * 1 크레딧이 몇 달러어치 원가인지, 그 요금제로 프로젝트를 몇 개쯤
 * 돌릴 수 있는지 같이 적는다. 다만 **그 환산은 아직 추정이다** —
 * 실제 모델로 프로젝트를 완주해본 적이 없다(STATUS.md). 추정이라고
 * 적지 않으면 사용자는 그 숫자를 약속으로 읽는다.
 *
 * ## 요금제마다 누구의 키로 도는지가 다르다
 *
 * 무료는 Mock 이라 실제 모델을 부르지 않고, 자체 키 요금제는 고객이
 * 자기 키로 직접 낸다. 이걸 화면에 적지 않으면 "무료로 진짜 AI 를 쓴다"
 * 고 믿게 되고, 그 오해는 결제 직전이 아니라 결제 직후에 깨진다.
 *
 * ## 결제는 여기 없다
 *
 * 결제 연동은 아직 없다. 이 화면이 성립시키는 것은 **잔액이 실제로 줄고
 * 실제로 막히는가** 하나다. 그래서 "충전"은 데모용이라고 화면에 적는다 —
 * 적지 않으면 결제가 붙은 줄 안다.
 */
import { useState } from "react";

import { Button, ErrorBox, MockBadge, Panel, Warning, money } from "@/components/ui";
import { api } from "@/lib/api";
import type { PlanRow } from "@/lib/types";
import { useLoader } from "@/lib/useLoader";

/**
 * 프로젝트 1건의 크레딧 추정치.
 *
 * 실측이 아니다. 모델 호출 20~40회 × 호출당 $0.03~0.15 라는 계산에서 나온
 * 폭이고, 실제 모델로 완주해본 적이 없으므로 **틀릴 수 있다.** 숫자 하나로
 * 적으면 약속처럼 보이므로 폭으로 적고, 화면에도 추정이라고 쓴다.
 */
const PER_PROJECT = { low: 100, high: 500 };

function projectsPerMonth(credits: number): string {
  if (credits <= 0) return "";
  const most = Math.floor(credits / PER_PROJECT.low);
  const least = Math.floor(credits / PER_PROJECT.high);
  if (most < 1) return "프로젝트 1건도 안 될 수 있음";
  if (least < 1) return `월 최대 ${most}건 (추정)`;
  return least === most
    ? `월 ${most}건 남짓 (추정)`
    : `월 ${least}~${most}건 (추정)`;
}

function SourceNote({ plan }: { plan: PlanRow }) {
  if (plan.source === "mock")
    return (
      <li className="flex items-center gap-1.5">
        <MockBadge /> 실제 모델을 부르지 않습니다
      </li>
    );
  if (plan.source === "byok")
    return (
      <li>
        모델 요금은 <strong>내 API 키로 직접</strong> 결제
      </li>
    );
  return <li>월 {plan.credits.toLocaleString()} 크레딧</li>;
}

export default function PricingPage() {
  const { data, error, reload } = useLoader("pricing", async () => {
    const [plans, credits] = await Promise.all([api.plans(), api.credits()]);
    return { plans, credits };
  });
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const plans = data?.plans.plans ?? {};
  const topups = data?.plans.topups ?? {};
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
            <span className="text-xs text-dim">{wallet.plan_label} 요금제</span>
          }
        >
          {wallet.source === "byok" ? (
            <div className="flex flex-wrap items-end gap-6">
              <div>
                <p className="text-3xl font-bold tabular-nums">
                  {money(wallet.byok_usd)}
                </p>
                <p className="text-[11px] text-dim">
                  내 API 키로 나간 금액 · 우리가 청구하지 않습니다
                </p>
              </div>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
                <dt className="text-dim">동시 실행</dt>
                <dd>{wallet.max_concurrent}건</dd>
                <dt className="text-dim">프로젝트당 상한</dt>
                <dd>{money(wallet.max_project_cost)}</dd>
              </dl>
            </div>
          ) : (
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
          )}

          {wallet.source === "mock" && (
            <p className="mt-3 flex items-center gap-2 text-sm">
              <MockBadge />
              <span className="text-muted">
                이 요금제는 <strong>실제 모델을 부르지 않습니다.</strong> 산출물은
                대본이 만든 것이고 AI 의 작업 결과가 아닙니다. 실제로 돌리려면
                유료 요금제로 바꾸거나, 자체 키 요금제에서 본인 API 키를
                등록하세요.
              </span>
            </p>
          )}

          {wallet.balance < 0 && (
            <p className="mt-3 text-sm" style={{ color: "var(--bad)" }}>
              잔액이 마이너스입니다. 초과분은 지워지지 않고 그대로 남습니다 —
              다음 달에 그만큼 덜 받습니다.
            </p>
          )}

          {wallet.charges_credits ? (
            <div className="mt-4 border-t border-line pt-3">
              <p className="text-xs text-muted">크레딧 충전</p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {Object.entries(topups).map(([name, t]) => (
                  <Button
                    key={name}
                    onClick={() => void act(() => api.topUp(t.credits))}
                    disabled={busy}
                  >
                    {t.label} · ${t.price_usd}
                  </Button>
                ))}
              </div>
              <p className="mt-2 text-[11px] text-dim">
                결제 연동은 없습니다. 잔액이 실제로 줄고 막히는지 확인하기 위한
                데모용 버튼입니다. 충전은 크레딧당 단가가 구독보다 비쌉니다 —
                많이 쓰면 요금제를 올리는 편이 쌉니다.
              </p>
            </div>
          ) : (
            <p className="mt-4 border-t border-line pt-3 text-[11px] text-dim">
              이 요금제는 크레딧을 쓰지 않습니다 — 충전할 것도 없습니다.
            </p>
          )}

          <p className="mt-2 text-[11px] text-dim">
            1 크레딧 = 원가 {money(wallet.credit_usd)}
            {wallet.prices_verified_on &&
              ` · 단가 대조일 ${wallet.prices_verified_on}`}
          </p>
        </Panel>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {Object.entries(plans).map(([name, p]) => {
          const current = wallet?.plan === name;
          const per = projectsPerMonth(p.credits);
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
                <SourceNote plan={p} />
                <li>동시 실행 {p.max_concurrent}건</li>
                <li>프로젝트당 최대 {money(p.max_project_cost)}</li>
                {per && <li className="text-dim">{per}</li>}
              </ul>
              {p.blurb && <p className="mt-2 text-[11px] text-dim">{p.blurb}</p>}
              <Button
                className="mt-3 w-full"
                tone={current ? "default" : "primary"}
                disabled={busy || current}
                onClick={() => void act(() => api.changePlan(name))}
              >
                {current ? "현재 요금제" : "이 요금제로"}
              </Button>
              {p.source === "byok" && !current && (
                <p className="mt-2 text-[11px] text-dim">
                  바꾸기 전에 설정 화면에서 본인 API 키를 먼저 등록하세요. 키가
                  없으면 실행이 거부됩니다 — 운영자 키로 대신 부르지 않습니다.
                </p>
              )}
            </Panel>
          );
        })}
      </div>

      <p className="text-[11px] text-dim">
        프로젝트당 크레딧은 <strong>추정</strong>입니다. 아직 실제 모델로
        프로젝트를 완주해본 적이 없습니다 — 실측 후 요금제가 조정될 수 있습니다.
      </p>
    </div>
  );
}
