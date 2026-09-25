"""프로젝트별 권한 조정 (DAY 25).

## 왜 생겼나

권한은 직원 표(`roles.py`)의 데이터다 — "누가 무엇을 할 수 있나"가 한
화면에 있어야 한다는 이유였고, 그건 여전히 맞다. 그런데 그 표는 **모든
프로젝트에 같다.** "이 프로젝트만 작가에게 src/ 를 보여주고 싶다" 같은
요청을 들어주려면 코드를 고쳐야 했고, 고치면 모든 고객의 모든 프로젝트가
바뀐다.

그래서 **프로젝트마다 기본 표 위에 덧씌우는 조정**을 둔다. 조정은
프로젝트 메타(`permissions`)에 살고, 파일 도구(`project_fs`)와
MANUAL 이 직원 표 대신 여기서 실효 권한을 읽는다.

## 무엇이든 바꿀 수 있지는 않다 — 바닥(floor)

"권한은 제품이 정한다"는 설계 의도를 버리지 않는다. 조정이 제품의 핵심
논리를 무너뜨리면 그건 권한 조정이 아니라 **다른 제품**이다. 그래서 세
층으로 나눈다:

| 층 | 예 | 처리 |
|---|---|---|
| 자유 | 작가가 src/ 를 읽는다 · 디자이너 docs/ 쓰기 | 그대로 허용 |
| 위험 | 구현자가 tests/ 를 **읽는다** | `acknowledge_risk` 가 있어야 허용 · 프로젝트에 표시 |
| 바닥 | 검증자 외의 누가 tests/ 에 **쓴다** | 거부 — 누구도 풀 수 없다 |

**tests/ 쓰기가 바닥인 이유**: 구현자가 판정 기준을 고칠 수 있으면
"통과"가 아무것도 보증하지 않는다. 그건 약해진 교차검증이 아니라 없는
교차검증이다.

**tests/ 읽기가 '위험'인 이유**: 보면 맞춰 짠다 — 그래서 기본은 막혀
있다. 하지만 사용자가 "테스트를 보고 맞춰도 된다, 이 프로젝트는 테스트가
곧 명세다"라고 판단하는 것은 사용자의 권리다. 대신 그 사실이 조용히
묻히지 않게 한다: 프로젝트에 `risks` 로 남고 화면이 계속 말한다.

그 밖의 바닥:

- 검증자는 산출물 구역(src/ docs/ design/)에 못 쓴다 — 자기가 쓴 것을
  자기가 검증하게 된다.
- 검증자의 읽기는 줄일 수 없다 — 못 보는 것을 검증하라는 것은 검증자가
  지어내라는 것이다.
- 전략가는 쓰지 않는다 — 계획 스키마에 파일이 없다. 권한만 주면 쓸 곳
  없는 권한이 화면에만 남는다.
- 모르는 구역·모르는 직원은 거부한다. 오타 하나가 조용히 무시되면
  사용자는 준 줄 안다.

## 실행 중에는 바꿀 수 없다

병렬로 도는 태스크는 쓰기 구역이 겹치지 않는 것끼리만 같이 돈다
(`engine._conflicts`). 도는 도중에 쓰기 구역이 바뀌면 이미 같이 돌고 있는
두 태스크가 같은 파일을 쓰게 될 수 있다. 멈춰 있거나(stopped · awaiting)
끝났을 때만 바꾼다 — API 가 막는다.
"""
from __future__ import annotations

from app.agents import roles

RISK_TESTS_VISIBLE = "tests_visible"


class PolicyError(ValueError):
    """바닥을 건드리는 조정. 누구도 풀 수 없다."""


class RiskNotAcknowledged(ValueError):
    """위험한 조정인데 `acknowledge_risk` 가 없다."""


def _clean_areas(value, *, who: str, what: str) -> tuple[str, ...]:
    from app import lang
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise PolicyError(lang.t("perm.badShape", who=who, what=what))
    out: list[str] = []
    for a in value:
        a = str(a).strip().strip("/")
        if a not in roles.AREAS:
            raise PolicyError(lang.t("perm.unknownArea", area=a,
                                     allowed=", ".join(roles.AREAS)))
        if a not in out:
            out.append(a)
    return tuple(out)


def normalize(overrides: dict | None) -> dict[str, dict[str, list[str]]]:
    """화면·API 가 보낸 조정을 검사 가능한 모양으로 편다.

    모양: `{직원 id: {"writes": [...], "reads": [...]}}`. 한쪽만 주면
    다른 쪽은 기본값 그대로다(빠진 키 = 조정 없음, 빈 배열 = 전부 뺌).
    """
    from app import lang
    out: dict[str, dict[str, list[str]]] = {}
    for eid, row in (overrides or {}).items():
        if not roles.exists(eid):
            raise PolicyError(lang.t("perm.unknownEmployee", id=eid))
        if not isinstance(row, dict):
            raise PolicyError(lang.t("perm.badShape", who=eid, what="row"))
        clean: dict[str, list[str]] = {}
        for key in ("writes", "reads"):
            if key in row and row[key] is not None:
                clean[key] = list(_clean_areas(row[key], who=eid, what=key))
        if clean:
            out[eid] = clean
    return out


def _merged(eid: str, overrides: dict) -> tuple[tuple[str, ...], tuple[str, ...]]:
    e = roles.get(eid)
    row = overrides.get(eid) or {}
    writes = tuple(row["writes"]) if "writes" in row else e.writes
    reads = tuple(row["reads"]) if "reads" in row else e.reads
    # 쓸 수 있는 곳은 읽을 수 있어야 한다. 덮어쓰기 전에 직전 판본을
    # 남기려면 읽어야 하고, 못 읽는 파일을 전문으로 다시 쓰라는 것은
    # 지우라는 것과 같다.
    reads = tuple(dict.fromkeys((*reads, *writes)))
    return writes, reads


def validate(overrides: dict | None, *, acknowledge_risk: bool = False
             ) -> tuple[dict, list[str]]:
    """조정을 검사하고 `(정리된 조정, 위험 목록)` 을 돌려준다.

    바닥을 건드리면 `PolicyError`, 위험한데 인정하지 않았으면
    `RiskNotAcknowledged`.
    """
    from app import lang
    clean = normalize(overrides)
    risks: list[str] = []
    for eid in clean:
        e = roles.get(eid)
        writes, reads = _merged(eid, clean)
        if roles.TESTS in writes and eid != roles.VERIFIER:
            raise PolicyError(lang.t("perm.floorTestsWrite",
                                     who=roles.display(eid)))
        if eid == roles.VERIFIER:
            if set(writes) - {roles.TESTS}:
                raise PolicyError(lang.t("perm.floorVerifierWrites"))
            if set(roles.AREAS) - set(reads):
                raise PolicyError(lang.t("perm.floorVerifierReads"))
        if e.kind == "plan" and writes:
            raise PolicyError(lang.t("perm.floorPlannerWrites"))
        if (roles.TESTS in reads and eid != roles.VERIFIER
                and roles.TESTS not in e.reads):
            if RISK_TESTS_VISIBLE not in risks:
                risks.append(RISK_TESTS_VISIBLE)
    if risks and not acknowledge_risk:
        raise RiskNotAcknowledged(lang.t("perm.riskNeedsAck"))
    return clean, risks


def overrides_of(slug: str | None) -> dict:
    if not slug:
        return {}
    from app.database import store
    try:
        return (store.meta(slug).get("permissions") or {}).get("overrides") or {}
    except Exception:                                          # noqa: BLE001
        return {}


def effective(slug: str | None, employee_id: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """이 프로젝트에서 이 직원이 실제로 쓸 수 있는 곳 · 읽을 수 있는 곳.

    메타에 저장된 조정을 **다시 검사하지 않는다** — 저장할 때 검사했다.
    대신 바닥 하나는 여기서도 겹쳐 지킨다: 검증자 외에는 tests/ 에 못
    쓴다. 누가 메타 파일을 손으로 고쳤어도 판정 기준은 안전해야 한다.
    """
    if not roles.exists(employee_id):
        return (), ()
    writes, reads = _merged(employee_id, overrides_of(slug))
    if employee_id != roles.VERIFIER:
        writes = tuple(a for a in writes if a != roles.TESTS)
    return writes, reads


def table(slug: str | None) -> list[dict]:
    """화면이 그릴 표 — 직원마다 기본 · 실효 · 잠긴 칸."""
    ov = overrides_of(slug)
    rows = []
    for e in roles.EMPLOYEES.values():
        writes, reads = effective(slug, e.id)
        locked_w = [a for a in roles.AREAS if _locked(e, a, write=True)]
        locked_r = [a for a in roles.AREAS if _locked(e, a, write=False)]
        rows.append({
            "id": e.id, "kind": e.kind,
            "base": {"writes": list(e.writes), "reads": list(e.reads)},
            "effective": {"writes": list(writes), "reads": list(reads)},
            "overridden": e.id in ov,
            "locked": {"writes": locked_w, "reads": locked_r},
            "risky": {"reads": ([roles.TESTS] if e.id != roles.VERIFIER
                                and roles.TESTS not in e.reads else [])},
        })
    return rows


def _locked(e, area: str, *, write: bool) -> bool:
    """이 칸을 사용자가 바꿀 수 없는가(바닥)."""
    if write:
        if e.kind == "plan":
            return True
        if area == roles.TESTS:
            return True                  # 검증자는 켜진 채, 나머지는 꺼진 채로 잠김
        if e.id == roles.VERIFIER:
            return True
        return False
    if e.id == roles.VERIFIER:
        return True                      # 검증자의 읽기는 줄일 수 없다
    return False


def describe(slug: str | None) -> dict:
    m = {}
    if slug:
        from app.database import store
        m = store.meta(slug).get("permissions") or {}
    return {"overrides": m.get("overrides") or {},
            "risks": m.get("risks") or [],
            "acknowledged_at": m.get("acknowledged_at"),
            "table": table(slug)}
