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
import { useEffect, useRef, useState } from "react";

import {
  Button, ErrorBox, MockBadge, Panel, Screen, Skeleton, SkeletonCards,
  Warning, money,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useLang, type Key } from "@/lib/i18n";
import type { PlanRow } from "@/lib/types";
import { T, revealFrom, stagger, withScope } from "@/lib/motion";
import { useLoader } from "@/lib/useLoader";

/**
 * 프로젝트 1건의 크레딧 추정치.
 *
 * 실측이 아니다. 모델 호출 20~40회 × 호출당 $0.03~0.15 라는 계산에서 나온
 * 폭이고, 실제 모델로 완주해본 적이 없으므로 **틀릴 수 있다.** 숫자 하나로
 * 적으면 약속처럼 보이므로 폭으로 적고, 화면에도 추정이라고 쓴다.
 */
const PER_PROJECT = { low: 100, high: 500 };

/**
 * 이 요금제로 프로젝트를 몇 건이나 할 수 있나.
 *
 * **잰 값이 있으면 잰 값을 쓴다.** 끝난 프로젝트들의 중앙값과 p90 이
 * 들어오면(backend: index.project_costs) 그걸로 계산하고, 없으면 위의
 * 추정 폭을 쓴다. 어느 쪽인지는 화면이 따로 말한다 — 없는 데이터를
 * 그럴듯한 숫자로 채우는 것이 제일 나쁜 거짓말이다.
 */
function projectsPerMonth(
  credits: number,
  t: (k: Key, v?: Record<string, string | number>) => string,
  measured?: { measured: boolean; median_usd: number; p90_usd: number },
  creditUsd = 0.01,
): string {
  if (credits <= 0) return "";
  const [low, high] = measured?.measured
    ? [measured.median_usd / creditUsd, measured.p90_usd / creditUsd]
    : [PER_PROJECT.low, PER_PROJECT.high];
  if (low <= 0 || high <= 0) return "";
  const most = Math.floor(credits / low);
  const least = Math.floor(credits / Math.max(high, low));
  if (most < 1) return t("price.lessThanOne");
  if (measured?.measured) {
    return least === most
      ? t("price.perMonthAbout", { n: most })
      : t("price.perMonthMeasured", { a: least, b: most });
  }
  if (least < 1) return t("price.perMonthMax", { n: most });
  return least === most
    ? t("price.perMonthAbout", { n: most })
    : t("price.perMonthEst", { a: least, b: most });
}

function SourceNote({ plan }: { plan: PlanRow }) {
  const { t } = useLang();
  if (plan.source === "mock")
    return (
      <li className="flex items-center gap-1.5">
        <MockBadge title={t("mock.badge")} /> {t("price.noRealCalls")}
      </li>
    );
  if (plan.source === "byok")
    return (
      <li>
        <Filled
          text={t("price.byokBilling")}
          strong={t("price.byokBilling.strong")}
        />
      </li>
    );
  return (
    <li>{t("price.creditsPerMonth", { n: plan.credits.toLocaleString() })}</li>
  );
}

export default function PricingPage() {
  const { t } = useLang();
  const { data, error, loading, reload } = useLoader("pricing", async () => {
    const [plans, credits] = await Promise.all([api.plans(), api.credits()]);
    return { plans, credits };
  });
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  // 요금제 카드만 순서대로 들어온다. 이 화면에서 사용자가 하는 일은
  // **비교**이고, 한꺼번에 나타나면 어디부터 볼지가 사라진다. 잔액 패널은
  // 건드리지 않는다 — 내 돈이 적힌 칸이 뒤늦게 나타나면 불안하다.
  useEffect(() => {
    const el = root.current;
    if (!el || !data) return;
    return withScope(el, () => {
      revealFrom(el.querySelectorAll("[data-reveal]"), {
        y: 12, delay: stagger(T.step),
      });
    });
  }, [data]);

  const plans = data?.plans.plans ?? {};
  const measured = data?.plans.per_project;
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
    <Screen>
    <div ref={root} className="space-y-4">
      {(error || failure) && <ErrorBox>{failure ?? error}</ErrorBox>}

      {/* 요금제는 돈을 쓰는 화면이다. 빈 화면을 보여주면 "요금제가
          없어졌나"로 읽힌다. */}
      {loading && !data && (
        <>
          <Panel title={t("price.myCredits")}>
            <Skeleton lines={3} />
          </Panel>
          <SkeletonCards n={4} />
        </>
      )}

      {wallet && !wallet.prices_verified && (
        <Warning>
          <strong>{t("price.unverified")}</strong> {t("price.unverifiedBody")}
        </Warning>
      )}

      {wallet && (
        <Panel
          title={t("price.myCredits")}
          right={
            <span className="text-xs text-dim">
              {wallet.plan_label} {t("price.planSuffix")}
            </span>
          }
        >
          {wallet.source === "none" ? (
            <p className="text-sm text-muted">
              {t("price.pickFirst")}
            </p>
          ) : wallet.source === "byok" ? (
            <div className="flex flex-wrap items-end gap-6">
              <div>
                <p className="text-3xl font-bold tabular-nums">
                  {money(wallet.byok_usd)}
                </p>
                <p className="text-[11px] text-dim">
                  {t("price.byokSpent")}
                </p>
              </div>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
                <dt className="text-dim">{t("price.concurrent")}</dt>
                <dd>{wallet.max_concurrent}</dd>
                <dt className="text-dim">{t("price.perProject")}</dt>
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
                  {t("price.left", { usd: money(wallet.balance_usd) })}
                </p>
              </div>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
                <dt className="text-dim">{t("price.granted")}</dt>
                <dd className="tabular-nums">{wallet.granted.toFixed(0)}</dd>
                <dt className="text-dim">{t("price.spent")}</dt>
                <dd className="tabular-nums">{wallet.spent.toFixed(1)}</dd>
                <dt className="text-dim">{t("price.concurrent")}</dt>
                <dd>{wallet.max_concurrent}</dd>
                <dt className="text-dim">{t("price.perProject")}</dt>
                <dd>{money(wallet.max_project_cost)}</dd>
              </dl>
            </div>
          )}

          {wallet.source === "none" && (
            <p className="mt-3 text-sm text-muted">
              <strong>{t("price.noPlan")}</strong> {t("price.noPlanBody")}
            </p>
          )}

          {wallet.source === "mock" && (
            <p className="mt-3 flex items-center gap-2 text-sm">
              <MockBadge title={t("mock.badge")} />
              <span className="text-muted">
                <strong>{t("price.mockPlan")}</strong> {t("price.mockPlanBody")}
              </span>
            </p>
          )}

          {wallet.balance < 0 && (
            <p className="mt-3 text-sm" style={{ color: "var(--bad)" }}>
              {t("price.negative")}
            </p>
          )}

          {wallet.charges_credits ? (
            <div className="mt-4 border-t border-line pt-3">
              <p className="text-xs text-muted">{t("price.topup")}</p>
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
                {t("price.topupNote")}
              </p>
            </div>
          ) : wallet.source === "none" ? null : (
            <p className="mt-4 border-t border-line pt-3 text-[11px] text-dim">
              {t("price.noTopup")}
            </p>
          )}

          <p className="mt-2 text-[11px] text-dim">
            {t("price.creditWorth", { usd: money(wallet.credit_usd) })}
            {wallet.prices_verified_on &&
              t("price.verifiedOn", { date: wallet.prices_verified_on })}
          </p>
        </Panel>
      )}

      {/* 요금제가 하나도 없으면 빈 화면이 아니라 이유를 보여준다 —
          서버의 요금표가 잘못됐다는 신호이고, 사용자는 기다릴 이유가 없다. */}
      {!loading && Object.keys(plans).length === 0 && (
        <Panel title={t("plans.title")}>
          <p className="text-sm text-muted">{t("price.noPlans")}</p>
        </Panel>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {Object.entries(plans).map(([name, p]) => {
          const current = wallet?.plan === name;
        const per = projectsPerMonth(
            p.credits, t, data?.plans.per_project, data?.plans.credit_usd,
          );
          return (
            <Panel
              key={name}
              title={p.label}
              data-reveal
              className={`transition-transform duration-200 hover:-translate-y-0.5 ${
                current ? "border-accent" : ""
              }`}
              right={
                current && (
                  <span className="text-[11px]" style={{ color: "var(--accent)" }}>
                    {t("price.inUse")}
                  </span>
                )
              }
            >
              <p className="text-2xl font-bold tabular-nums">
                {p.price_usd === 0 ? t("price.free") : `$${p.price_usd}`}
                {p.price_usd > 0 && (
                  <span className="text-xs font-normal text-dim">
                      {" "}
                      {t("plan.perMonth")}
                    </span>
                )}
              </p>
              <ul className="mt-3 space-y-1 text-xs text-muted">
                <SourceNote plan={p} />
                <li>{t("plan.concurrent", { n: p.max_concurrent })}</li>
                <li>{t("price.maxPerProject", { usd: money(p.max_project_cost) })}</li>
                {per && <li className="text-dim">{per}</li>}
              </ul>
              {p.blurb && <p className="mt-2 text-[11px] text-dim">{p.blurb}</p>}
              <Button
                className="mt-3 w-full"
                tone={current ? "default" : "primary"}
                disabled={busy || current}
                onClick={() => void act(() => api.changePlan(name))}
              >
                {current ? t("price.current") : t("price.choose")}
              </Button>
              {p.source === "byok" && !current && (
                <p className="mt-2 text-[11px] text-dim">
                  {t("price.byokFirst")}
                </p>
              )}
            </Panel>
          );
        })}
      </div>

      <p className="text-[11px] text-dim">
        {measured?.measured ? (
          <>
            <strong>
              {t("price.measured", { n: measured.samples })}
            </strong>{" "}
            {t("price.measuredBody", {
              median: money(measured.median_usd),
              p90: money(measured.p90_usd),
            })}
          </>
        ) : (
          <>
            <strong>{t("price.estimate")}</strong> {t("price.estimateBody")}
          </>
        )}
      </p>
    </div>
    </Screen>
  );
}

/** `{strong}` 자리에 굵은 조각을 끼운다. 번역문마다 위치가 다르다. */
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
