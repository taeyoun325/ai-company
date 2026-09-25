"""완성도 점수 (지시서 §9).

## QA 통과율을 점수에서 뺀 이유

검증자가 관대할수록 점수가 오르는 순환논리가 된다. 남긴 두 항목은
검증자의 판단과 **독립**이다: 태스크 완료는 오케스트레이터가 세고,
테스트 통과는 파이썬이 실행한 결과다.

## 최종 점수는 인수기준으로 덮어쓴다

중간 점수는 진행률이고, 최종 점수는 **약속을 지켰는가**다. 태스크를 전부
끝냈는데 인수기준을 못 지켰다면 그건 100점이 아니다.
"""
from __future__ import annotations

from app import bus, lang
from app.orchestrator import runner

W_TASK, W_TEST = 0.70, 0.30


class Score:
    def __init__(self) -> None:
        self.total_tasks = 0
        self.done_tasks = 0
        self.tests = {"passed": 0, "failed": 0, "errors": 0}
        self.tests_pass = False
        self.tests_ran = False
        self.reviews = 0
        self.passes = 0
        self.reworks = 0
        self.replans = 0
        self.ac_total = 0
        self.ac_covered = 0                # 테스트가 붙은 인수기준 수
        self.ac_met: int | None = None     # 최종 검수 결과
        self.confidence_total = 0.0        # 판정마다의 확신도(0~1) 합

    # 재개(§18)에 들고 갈 칸. 멈췄다 이어간 실행이 반려 횟수·확신도를
    # 0 부터 다시 세면, 화면의 "확신도 95%" 가 재개 **이후** 판정 몇 개만의
    # 평균이 된다 — 앞에서 받은 낮은 확신도가 조용히 지워진다.
    _CARRY = ("reviews", "passes", "reworks", "replans", "confidence_total",
              "tests", "tests_pass", "tests_ran", "ac_covered")

    def carry(self) -> dict:
        return {k: getattr(self, k) for k in self._CARRY}

    def restore(self, saved: dict | None) -> None:
        for k in self._CARRY:
            if saved and k in saved:
                setattr(self, k, saved[k])

    def value(self) -> int:
        if self.ac_met is not None and self.ac_total:
            return round(100 * self.ac_met / self.ac_total)
        task = self.done_tasks / self.total_tasks if self.total_tasks else 0.0
        test = 1.0 if self.tests_pass else 0.0
        return round(100 * (W_TASK * task + W_TEST * test))

    def detail(self) -> dict:
        return {
            "tasks": f"{self.done_tasks}/{self.total_tasks}",
            "tests": (runner.summary_line({"skipped_run": not self.tests_ran,
                                           "timed_out": False, **self.tests})
                      # 번역한다 — DAY 26 화면 시험이 영어 점수판에서 찾았다.
                      if self.tests_ran else lang.t("test.notRun")),
            # 같은 것을 **데이터로**도 싣는다 (DAY 26). 위 문장은 실행의 언어로
            # 박제되므로, 한국어로 돌린 프로젝트를 영어 화면에서 보면 점수판에
            # "2통과·0실패"가 남았다. 점수판은 기록이 아니라 화면이다 — 숫자를
            # 받아 보는 사람의 언어로 적는다.
            "tests_state": "counts" if self.tests_ran else "not_run",
            "tests_passed": int(self.tests.get("passed", 0)),
            "tests_failed": int(self.tests.get("failed", 0)
                                + self.tests.get("errors", 0)),
            "ac_coverage": f"{self.ac_covered}/{self.ac_total}" if self.ac_total else "—",
            "review_pass_rate": (round(100 * self.passes / self.reviews)
                                 if self.reviews else 0),
            # 통과율과 다른 질문이다 — "얼마나 통과했나" 가 아니라 "검증자가
            # 자기 판정을 얼마나 확신했나"다. 둘이 같이 낮으면 검증
            # 자체가 흔들리고 있다는 뜻이다(§18 신뢰도).
            "confidence": (round(100 * self.confidence_total / self.reviews)
                          if self.reviews else "—"),
            "reworks": self.reworks,
            "replans": self.replans,
            "criteria": (f"{self.ac_met}/{self.ac_total}"
                         if self.ac_met is not None else "—"),
            "final": self.ac_met is not None,
        }

    def push(self) -> None:
        bus.state(score=self.value(), score_detail=self.detail())
