"""키를 꽂는 날 돌릴 스크립트들이 그날 처음 돌지 않게 한다 (DAY 22).

## 왜 이 파일이 있나

`scripts/first_real_run.py` 는 "키를 꽂은 날 제일 먼저 돌리는 것"이라고
적혀 있다. 그런데 윈도우 기본 콘솔(cp949)에서는 그 스크립트가 찍는 `✓`
한 글자에 `UnicodeEncodeError` 로 죽는다. 하필 그날, 하필 제일 먼저.

`app/preflight.py` 의 `import os` 와 같은 종류다 — **그날에만 닿는 줄**은
그날까지 아무도 안 밟는다. 그래서 여기서 밟는다.
"""
import io
import re
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _source(name: str) -> str:
    return io.open(SCRIPTS / name, encoding="utf-8").read()


@pytest.mark.parametrize("name", ["first_real_run.py", "measure_costs.py"])
def test_scripts_survive_a_cp949_console(name):
    """출력 인코딩을 고쳐두지 않으면 첫 ✓ 에서 죽는다."""
    src = _source(name)
    assert "sys.stdout.reconfigure" in src, (
        f"{name} 이 출력 인코딩을 고정하지 않습니다 — 윈도우 콘솔에서 "
        f"✓ 한 글자에 죽습니다")


@pytest.mark.parametrize("name", ["first_real_run.py", "measure_costs.py"])
def test_scripts_compile(name):
    """문법 오류는 그날 아침에 발견할 것이 아니다."""
    compile(_source(name), str(SCRIPTS / name), "exec")


def test_measure_costs_percentile_is_right():
    """중앙값·p90 이 이 제품의 가격을 정한다. 라이브러리마다 답이 다른
    자리라 직접 세고, 직접 센 것은 직접 확인한다."""
    sys.path.insert(0, str(SCRIPTS))
    try:
        import measure_costs
    finally:
        sys.path.remove(str(SCRIPTS))

    p = measure_costs.percentile
    assert p([], 0.5) == 0.0
    assert p([2.0], 0.9) == 2.0
    assert p([1.0, 3.0], 0.5) == 2.0
    assert p([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5
    # p90 은 큰 쪽에 붙어야 한다 — 상한을 재는 값이기 때문이다.
    assert p([1.0] * 9 + [10.0], 0.9) > 1.0


def test_measure_costs_says_out_loud_that_mock_numbers_are_fake():
    """Mock 으로 잰 금액을 pricing.json 에 옮겨 적는 것이 이 스크립트로
    저지를 수 있는 제일 나쁜 실수다. 숫자 옆에 적어두는 것 말고는 막을
    방법이 없다."""
    src = _source("measure_costs.py")
    assert re.search(r"Mock.*가짜", src), "Mock 경고 문구가 없습니다"
