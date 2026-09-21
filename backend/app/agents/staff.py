"""인사 — 이름을 정하고, 채용하고, 내보낸다 (DAY 21).

## 직원 표와 무엇이 다른가

`roles.py` 는 **자리**를 정한다 — 무엇을 할 수 있고 어느 폴더에 쓸 수
있는지. 그건 제품의 구조라서 고객이 바꿀 수 있으면 안 된다. 작가에게
`src/` 쓰기를 허용하는 순간 권한 경계가 사라진다.

이 파일은 그 위에 얹는 **인사 기록**이다 — 자리에 앉은 사람의 이름과,
그 자리를 지금 쓰는지 여부. 테넌트마다 다르다.

## 왜 아무나 내보낼 수 없나

AUTO 는 기획 → 구현 → 교차검증 → 검수로 돈다. 이 중 하나라도 비면
그건 '직원이 적은 회사'가 아니라 **다른 제품**이다:

- 전략가를 내보내면 계획이 없다. 태스크가 없으니 시작할 것도 없다.
- 개발자를 내보내면 코드를 쓸 사람이 없다.
- 분석가를 내보내면 **교차검증이 사라진다.** 이게 제일 위험하다 —
  화면은 멀쩡히 돌고 산출물도 나오는데, 아무도 보지 않은 코드가
  '통과'로 나간다. 조용히 나빠지는 쪽이라 더 나쁘다.

그래서 세 자리는 고정이다. 작가·디자이너는 없어도 회사가 돈다 — 문서나
화면 명세가 필요 없는 프로젝트가 실제로 있다.

**내보낼 수 없다는 사실을 화면이 말해야 한다.** 버튼만 막아두면 사용자는
고장인 줄 안다.

## 이름은 고객의 것이다

기본 이름(한지수·박도현…)은 우리가 지은 것이고, 자기 회사 직원 이름을
붙이고 싶은 것은 당연하다. 다만 **자리의 권한은 이름과 무관하다** —
개발자를 '수석 아키텍트'라고 불러도 `src/` 밖에는 못 쓴다.
"""
from __future__ import annotations

import json
import threading

from app import config
from app.agents import roles

# 내보낼 수 없는 자리. 이유는 위 문서에 있다.
CORE = ("strategist", "developer", "analyst")

MAX_NAME = 24

_lock = threading.RLock()
_cache: dict[str, dict] | None = None


def store_path():
    return config.data_dir() / ".staff.json"


def _load() -> dict[str, dict]:
    global _cache
    if _cache is None:
        try:
            data = json.loads(store_path().read_text(encoding="utf-8"))
            _cache = data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            _cache = {}
    return _cache


def _save() -> None:
    try:
        store_path().write_text(
            json.dumps(_load(), ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        # 저장 실패가 실행을 막지는 않는다. 이름이 기본값으로 돌아갈 뿐이다.
        pass


def _row(owner: str, employee_id: str) -> dict:
    return _load().get(owner, {}).get(employee_id, {})


# ── 조회 ────────────────────────────────────────────────────────────
def name_of(owner: str, employee_id: str) -> str:
    """이 테넌트가 이 자리에 붙인 이름. 없으면 기본 이름."""
    custom = _row(owner, employee_id).get("name")
    if isinstance(custom, str) and custom.strip():
        return custom.strip()
    return roles.get(employee_id).name


def is_active(owner: str, employee_id: str) -> bool:
    """이 자리를 지금 쓰는가. 고정 자리는 언제나 참이다 —
    저장 파일이 손으로 고쳐져도 핵심 자리가 비지 않게 여기서 막는다."""
    if employee_id in CORE:
        return True
    value = _row(owner, employee_id).get("active")
    return True if value is None else bool(value)      # 기본은 채용 상태


def active_ids(owner: str) -> list[str]:
    return [i for i in roles.ids() if is_active(owner, i)]


def can_fire(employee_id: str) -> bool:
    return employee_id not in CORE


def fire_reason(employee_id: str) -> str:
    """왜 못 내보내는지. 화면이 이 문장을 그대로 보여준다."""
    if employee_id == "analyst":
        return ("교차검증을 맡는 자리입니다. 내보내면 아무도 보지 않은 "
                "코드가 '통과'로 나갑니다 — 화면은 멀쩡히 돌기 때문에 "
                "그 사실을 아무도 눈치채지 못합니다.")
    if employee_id == "strategist":
        return "계획을 세우는 자리입니다. 없으면 태스크가 만들어지지 않습니다."
    if employee_id == "developer":
        return "코드를 쓰는 유일한 자리입니다."
    return ""


# ── 변경 ────────────────────────────────────────────────────────────
def rename(owner: str, employee_id: str, name: str) -> None:
    if not roles.exists(employee_id):
        raise KeyError(f"없는 직원: {employee_id}")
    name = (name or "").strip()
    if len(name) > MAX_NAME:
        raise ValueError(f"이름은 {MAX_NAME}자까지입니다")
    with _lock:
        row = _load().setdefault(owner, {}).setdefault(employee_id, {})
        if name:
            row["name"] = name
        else:
            row.pop("name", None)        # 비우면 기본 이름으로 돌아간다
        _save()


def set_active(owner: str, employee_id: str, active: bool) -> None:
    if not roles.exists(employee_id):
        raise KeyError(f"없는 직원: {employee_id}")
    if not active and not can_fire(employee_id):
        raise ValueError(fire_reason(employee_id))
    with _lock:
        row = _load().setdefault(owner, {}).setdefault(employee_id, {})
        row["active"] = bool(active)
        _save()


def overlay(owner: str) -> dict[str, dict]:
    """화면에 내려보낼 인사 정보 한 벌."""
    return {
        i: {
            "name": name_of(owner, i),
            "default_name": roles.get(i).name,
            "active": is_active(owner, i),
            "can_fire": can_fire(i),
            "fire_reason": fire_reason(i),
        }
        for i in roles.ids()
    }


def reset() -> None:
    """테스트용."""
    global _cache
    with _lock:
        _cache = None
