"""완성도 점수의 확신도 집계 (app/orchestrator/score.py).

## 이 파일이 지키려는 것

`confidence` 는 "얼마나 통과했나"(review_pass_rate)와 다른 질문이다 —
"검증자가 자기 판정을 얼마나 확신했나"다. 둘이 독립적으로 움직여야
검증 자체가 흔들리고 있다는 신호를 놓치지 않는다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app.orchestrator.score import Score                        # noqa: E402


def test_confidence_is_unset_before_any_review():
    s = Score()
    assert s.detail()["confidence"] == "—"


def test_confidence_is_the_average_across_reviews():
    s = Score()
    s.reviews = 1
    s.confidence_total = 0.8
    assert s.detail()["confidence"] == 80

    s.reviews = 2
    s.confidence_total = 0.8 + 1.0
    assert s.detail()["confidence"] == 90


def test_confidence_and_pass_rate_move_independently():
    """검증자가 매번 통과시키면서도(100%) 매번 확신이 낮을 수 있다 —
    두 숫자가 하나로 뭉개지면 이 상황을 놓친다."""
    s = Score()
    s.reviews = 2
    s.passes = 2                    # 전부 통과
    s.confidence_total = 0.3 + 0.4  # 하지만 확신은 낮았다
    d = s.detail()
    assert d["review_pass_rate"] == 100
    assert d["confidence"] == 35
