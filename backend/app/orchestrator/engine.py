"""상태머신 — 누가 다음에 말할지는 LLM 이 아니라 여기가 정한다 (지시서 §9 · §10).

## 왜 코드가 정하는가

LLM 라우터는 디버깅이 지옥이다. "왜 저 직원을 불렀나"에 답할 수 없고,
무한 루프에 빠지면 멈출 방법이 없다. 순서·정지조건·예산은 전부 파이썬이
쥔다. 모델은 **각 칸을 채우는 일**만 한다.

AUTO(§10)에서 모델이 고르는 것은 딱 하나다: 태스크별 담당 직원.
그것도 `assignable()` 안에서만 고를 수 있고, 벗어나면 오케스트레이터가
기본 담당자로 되돌린다. "모델이 정한다"와 "모델이 고른 것을 검사 없이
따른다"는 다르다.

## 흐름

    PLAN ─▶ [승인] ─▶ WRITE_TESTS ─▶ ┌─ IMPLEMENT ─▶ TEST ─▶ REVIEW ─▶ [승인] ─┐ ─▶ FINALIZE ─▶ DONE
                                    │   (의존성이 풀린 태스크는 **동시에** 돈다) │
                                    └──────── 반려면 되돌아간다 ──────────────┘

정지 조건(OR): 태스크 전부 완료 / 라운드 상한 / 비용 상한 / 재기획 상한.
`[승인]` 은 CEO 가 켰을 때만 선다(`gates.py`).

## 태스크는 동시에 돈다 (DAY 25)

그 전까지는 `_topo()` 가 순서만 정하고 한 번에 하나씩 돌았다. 직원 다섯
중 실제로 일하는 사람은 늘 한 명이었다. 이제 **의존성이 풀린 태스크들을
동시에** 돌린다 — 개발자가 끝낸 뒤 작가와 디자이너가 함께 일한다.

같이 돌릴 수 없는 조합이 있다. **쓰기 구역이 겹치는 두 태스크**다. 둘이
같은 파일을 쓰면 나중에 쓴 쪽이 이기고, 되돌리기(§18 자동 롤백)가 남의
시도까지 지운다. 그래서 같은 직원의 태스크 둘, 또는 실효 쓰기 구역이
겹치는 두 직원(프로젝트별로 권한을 넓혔을 때)은 같이 돌지 않는다
(`_conflicts`). 기본 표에서는 직원마다 쓰기 구역이 달라서 파일 충돌이
구조적으로 불가능하다.

pytest 는 한 번에 하나만 돈다(`_Run.test_lock`). 같은 폴더에 설정 파일을
쓰고 같은 파일을 읽는 두 프로세스가 겹칠 이유가 없다.

## 비용은 호출 *전에* 검사한다

사후 감지는 상한이 아니라 부고다. 개발자 한 번이 예산을 통째로 넘길 수
있으므로, 다음 호출의 **최악 비용**을 더해서 넘으면 그 자리에서 멈춘다.
태스크가 동시에 돌면 "다음 호출"이 여럿이다 — 이미 나가 있는 호출의 최악
비용도 함께 더한다(`_Run.hold`).

## 실행 하나가 스레드 여럿

`bus` · `usage` · `project_fs` 가 스레드 로컬로 현재 실행을 찾고,
`tenant` · `lang` 은 컨텍스트 변수다. 태스크를 도는 줄(lane)마다 넷을
**다시 세운다** (`_lane`). 하나라도 빠뜨리면 그 줄의 비용이 어느 실행에도
안 잡히거나(usage), 운영자 키로 나가거나(tenant), 한국어로 나온다(lang).
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import os
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import contextmanager

from app import bus, config, lang, safeio, tenant, usage
from app.agents import employee, roles
from app.agents.schemas import (Criterion, FinalReport, Plan, Routing, Task,
                                TestSuite, Verdict, WorkResult)
from app.database import index, store
from app.usage import credits
from app.orchestrator import difficulty, gates, guard, prompts, runner
from app.orchestrator.score import Score
from app.tools import project_fs as pfs

MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT", "3"))
# 한 실행 안에서 동시에 도는 태스크 수의 하드 상한. 요금제가
# `max_parallel_tasks` 로 더 낮출 수 있다. 1 이면 DAY 24 까지의 동작이다.
MAX_PARALLEL_TASKS = int(os.getenv("MAX_PARALLEL_TASKS", "3"))
# 승인 결정을 확인하는 간격(초). 도는 태스크가 있으면 그 사이에 본다.
DECISION_POLL = float(os.getenv("DECISION_POLL", "0.5"))

_runs: dict[str, threading.Thread] = {}
_runs_lock = threading.RLock()
_cancelled: set[str] = set()


class Stop(Exception):
    """계획된 중단. 예산·라운드·재기획 상한에 닿았을 때."""


class Park(Exception):
    """승인을 기다리며 쉰다. 실패가 아니다 — 결정이 오면 이어간다."""


class _Halted(Exception):
    """다른 줄이 멈췄다. 이 줄은 조용히 접는다 (오류로 세지 않는다)."""


# ── 실행 관리 ───────────────────────────────────────────────────────
def _reap() -> None:
    with _runs_lock:
        for slug in [s for s, t in _runs.items() if not t.is_alive()]:
            _runs.pop(slug, None)
            _cancelled.discard(slug)


def running_slugs() -> list[str]:
    _reap()
    with _runs_lock:
        return sorted(_runs)


def is_running(slug: str | None = None) -> bool:
    _reap()
    with _runs_lock:
        return slug in _runs if slug else bool(_runs)


# ── 살아 있다는 신호 (DAY 22) ───────────────────────────────────────
#
# ## 왜 필요한가
#
# `new_project()` 는 status 를 `running` 으로 쓰고, 그걸 끝으로 바꾸는 것은
# **실행 스레드뿐**이다. 프로세스가 죽으면 되돌릴 사람이 없다. 그 프로젝트는
# 목록에서 영원히 "진행 중"으로 남고, 화면은 오지 않는 로그를 기다린다.
#
# 서버를 다시 켜는 일은 드물지 않다 — 배포, 재시작, 죽음. 그때마다 좀비가
# 하나씩 쌓인다.
#
# ## 왜 시각을 쓰나
#
# "이 프로세스가 살아 있나"는 **다른 프로세스에서 확인할 수 없다.** pid 는
# 재사용되고, 컨테이너가 바뀌면 의미도 없다. 대신 **최근에 무언가 했는가**를
# 본다 — 실행 중에는 주기적으로 시각을 찍고, 그게 오래되면 죽은 것으로 친다.
#
# 간격보다 넉넉하게 잡는다. 모델 호출 하나가 몇 분씩 걸리므로, 박자가 조금
# 늦었다고 살아 있는 실행을 죽었다고 하면 그게 더 나쁘다.
BEAT_EVERY = 20.0          # 초. 실행 중에 이 간격으로 찍는다
BEAT_STALE = 180.0         # 초. 이보다 오래됐으면 죽은 것으로 본다

_beater: threading.Thread | None = None


def _beat_once() -> None:
    for slug in running_slugs():
        try:
            store.save_meta(slug, {"beat": time.time()})
        except Exception:                                      # noqa: BLE001
            # 박자를 못 찍는다고 실행을 멈추지는 않는다. 다음에 찍힌다.
            pass


def _beat_loop() -> None:
    while True:
        time.sleep(BEAT_EVERY)
        if not running_slugs():
            return
        _beat_once()


def _start_beating() -> None:
    """실행이 있는 동안만 도는 스레드 하나. 실행마다 두지 않는다."""
    global _beater
    if _beater is not None and _beater.is_alive():
        return
    _beater = threading.Thread(target=_beat_loop, daemon=True, name="beat")
    _beater.start()


def sweep_stale_runs() -> list[str]:
    """기동 시 한 번. 아무도 돌리고 있지 않은 '진행 중'을 끝낸다.

    **지우지 않고 중단으로 표시한다.** 그때까지 만든 산출물은 그대로 있고,
    사용자는 무슨 일이 있었는지 알아야 한다 — 조용히 사라지면 자기가 뭘
    잘못했는지 찾게 된다.

    `awaiting`(승인 대기)은 건드리지 않는다. 그건 죽은 실행이 아니라
    사람을 기다리는 실행이다 — 스레드가 없는 것이 정상이다.
    """
    stopped = []
    now = time.time()
    for row in store.list_projects():
        if row.get("status") != "running":
            continue
        slug = row.get("slug")
        if not slug or slug in running_slugs():
            continue
        beat = float(row.get("beat") or row.get("created_at") or 0)
        if now - beat < BEAT_STALE:
            continue          # 다른 인스턴스가 돌리는 중일 수 있다
        store.save_meta(slug, {
            "status": "stopped",
            # 이 문장은 프로젝트 화면의 "중단 사유"에 그대로 뜬다.
            # 기동 시에는 요청이 없어 언어를 알 수 없으므로 기본값으로
            # 남는다 — 화면이 다시 번역할 수는 없다(기록이기 때문이다).
            "stopped_reason": lang.t("stop.restarted"),
        })
        stopped.append(slug)
    return stopped


def cancel(slug: str) -> bool:
    """CEO 의 정지 버튼 (§18).

    스레드를 강제로 죽이지 않는다 — 파일을 반쯤 쓴 상태로 끊기면 산출물이
    깨진다. 대신 표시만 해두고, 다음 단계 경계에서 스스로 멈춘다.

    승인을 기다리며 쉬는 실행(`awaiting`)에는 스레드가 없다. 그건 여기서
    바로 `stopped` 로 바꾼다. 열려 있던 승인은 그대로 둔다 — 재개하면
    체크포인트에서, 그 사이 내려진 결정부터 이어간다.
    """
    _reap()
    with _runs_lock:
        if slug in _runs:
            _cancelled.add(slug)
            alive = True
        else:
            alive = False
            m = store.meta(slug)
            if m.get("status") != "awaiting":
                return False
            store.save_meta(slug, {"status": "stopped",
                                   "stopped_reason": lang.t("stop.byCeo")})
    prev = bus.current()
    bus.bind(slug)
    try:
        bus.say("SYSTEM", lang.t("log.stopRequested"), kind="error")
        if not alive:
            bus.emit("projects", list=store.list_projects())
            bus.emit("done", ok=False, summary=lang.t("stop.byCeo"),
                     unmet=[], score=store.meta(slug).get("score", 0))
    finally:
        if prev is None:
            bus.release()
        else:
            bus.bind(prev)
    return True


def _check_cancelled(slug: str) -> None:
    with _runs_lock:
        if slug in _cancelled:
            raise Stop(lang.t("stop.byCeo"))


def _admit(owner: str) -> None:
    """좌석·잔액 검사. 새로 시작하든 멈춘 걸 이어서 돌리든 같은 문을 지난다.

    동시 실행 수를 제한하는 이유: 각 실행이 모델을 호출하므로 무제한이면
    비용과 요청 한도가 동시에 터진다.
    """
    _reap()
    # **요금제부터 본다.** 좌석 검사보다 먼저여야 한다 — 요금제를 고르지
    # 않은 계정은 좌석이 0 이라, 순서가 바뀌면 "요금제를 고르세요" 대신
    # "동시 실행 한도(0)에 도달했습니다"라는 말이 나간다. 같은 거절이지만
    # 사용자가 할 일이 전혀 다르다.
    tenant.require_runnable(owner)

    # 동시 실행 한도는 요금제가 정한다 (§16). 환경변수 MAX_CONCURRENT 는
    # 그 위의 하드 상한이다 — 요금제를 잘못 적어도 서버가 무너지지 않게.
    seats = min(MAX_CONCURRENT,
                int(credits.plan(credits.wallet(owner).plan)
                    .get("max_concurrent", MAX_CONCURRENT)))
    # 좌석은 **인스턴스를 넘어** 센다 (DAY 22). 프로세스 안의 스레드 수로
    # 세면 두 대로 띄우는 순간 한도가 인스턴스마다 따로 세져, 2좌석을 산
    # 사람이 4개를 돌릴 수 있다. 색인은 인스턴스가 공유한다.
    #
    # 이 프로세스의 것도 함께 본다 — 방금 시작해 아직 박자를 못 찍은
    # 실행이 색인에 'running' 으로 올라가기 전 찰나가 있기 때문이다.
    with _runs_lock:
        here = len(_runs)
    live = max(here, index.running_count(owner, time.time() - BEAT_STALE))
    if live >= seats:
        raise RuntimeError(lang.t("run.concurrent", n=seats))

    # 잔액을 **시작 전에** 본다 (§15). 0 이 된 다음에 막으면 이미 쓴 것이다.
    # 다만 프로젝트 상한 전액이 아니라 **한 번 부를 돈**만 요구한다.
    # 전액을 요구하면 무료 요금제(월 한도 == 프로젝트 상한)는 한 달에
    # 한 번만 시작할 수 있게 되는데, 그건 상한이 아니라 횟수 제한이다.
    credits.reserve(owner, employee.max_worst_case())


def _spawn(requirement: str, slug: str, attachment_ids: list[str],
           owner: str, checkpoint: dict | None = None) -> None:
    # 요청의 언어를 **여기서** 집는다. 실행 스레드는 요청 컨텍스트를
    # 물려받지 못하므로, 안 집으면 영어로 요청한 사람이 한국어 산출물을
    # 받는다 (DAY 21).
    t = threading.Thread(
        target=_run,
        args=(requirement, slug, attachment_ids, owner, lang.current(), checkpoint),
        daemon=True, name=f"run:{slug}")
    with _runs_lock:
        _runs[slug] = t
    store.save_meta(slug, {"beat": time.time(), "status": "running",
                           "stopped_reason": None})
    _start_beating()
    t.start()


def start(requirement: str, attachment_ids: list[str] | None = None,
          owner: str = "local", *, gate_list: list[str] | None = None,
          permissions: dict | None = None) -> str:
    """새 실행을 시작하고 프로젝트 slug 를 돌려준다 (AUTO, §10).

    `gate_list` — CEO 가 멈춰 서서 보겠다는 지점(`gates.py`).
    `permissions` — 이 프로젝트만의 권한 조정. **이미 검사된** 값이어야
    한다(`permissions.validate` 의 결과) — 검사는 요청을 받은 쪽이 한다.
    """
    gl = gates.normalize(gate_list)
    _admit(owner)
    slug = store.new_project(requirement, owner=owner)
    extra: dict = {"gates": gl}
    if permissions:
        extra["permissions"] = permissions
    store.save_meta(slug, extra)
    _spawn(requirement, slug, attachment_ids or [], owner)
    return slug


class NotResumable(RuntimeError):
    """`stopped`·`awaiting` 가 아닌 프로젝트는 이어서 돌릴 게 없거나 이미 돌고 있다."""


RESUMABLE = ("stopped", "awaiting")


def resume(slug: str, owner: str = "local") -> str:
    """멈춘 실행을 이어서 돈다 (§18 체크포인트).

    처음부터 다시 계획하지 않는다 — 마지막으로 저장된 체크포인트
    (`_persist` 가 태스크마다 남긴 done · rounds · plan)를 그대로
    이어받는다. 계획이 서기도 전에 멈췄다면(예산 상한을 PLAN 에서
    맞았다면) 되돌릴 계획이 없으므로 처음부터 다시 계획한다 — 그래도
    **같은 프로젝트**로 이어지는 것이 새 프로젝트를 또 만드는 것보다
    낫다. 대화 이력과 이미 쓴 비용이 한 slug 에 남는다.

    `stopped` 와 `awaiting`(승인 대기) 만 재개할 수 있다. `running` 은 이미
    돌고 있고, `done` 은 이어갈 것이 없다 — 둘 다 재개가 아니라 다른 요청이다.

    확인과 등록을 **한 잠금 안에서** 한다. 승인 버튼과 재개 버튼이 거의
    동시에 눌리면(또는 승인이 두 건 연달아 오면) 둘 다 "멈춰 있다"를 보고
    실행을 두 개 띄울 수 있다 — 같은 폴더를 두 스레드가 쓴다.
    """
    with _runs_lock:
        _reap()
        m = store.meta(slug)
        if not m:
            raise KeyError(slug)
        if m.get("status") not in RESUMABLE or slug in _runs:
            raise NotResumable(lang.t("resume.notStopped",
                                      status=m.get("status", "?")))
        _admit(owner)
        requirement = str(m.get("requirement", ""))
        checkpoint = m.get("checkpoint") or {}
        _spawn(requirement, slug, [], owner, checkpoint=checkpoint)
    return slug


def decide(slug: str, approval_id: str, decision: str, comment: str = "",
           owner: str = "local", by: str = "") -> dict:
    """CEO 의 승인 결정 (DAY 25 · HITL).

    결정을 기록하고, 실행이 쉬고 있으면(`awaiting`) 깨운다. 돌고 있으면
    실행이 스스로 본다(`_apply_task_decisions`).

    기록과 "살아 있나" 확인을 `_park` 와 **같은 잠금** 안에서 한다. 실행이
    막 쉬려는 순간에 결정이 들어오면, 둘 중 하나는 반드시 상대를 본다 —
    실행이 먼저 잠그면 결정을 보고 쉬지 않고, 결정이 먼저 잠그면 실행이
    이미 쉬었으므로 여기서 깨운다.
    """
    with _runs_lock:
        _reap()
        rec = gates.decide(slug, approval_id, decision, comment, by=by)
        alive = slug in _runs
    out = {"approval": rec, "resumed": False, "note": None}
    # 보류는 결정이 아니다 — 깨울 이유가 없다.
    if decision == "hold" or alive \
            or store.meta(slug).get("status") != "awaiting":
        return out
    try:
        resume(slug, owner=owner)
        out["resumed"] = True
    except NotResumable:
        pass                                   # 다른 결정이 먼저 깨웠다
    except (tenant.NoPlan, tenant.KeysMissing, credits.InsufficientCredits,
            RuntimeError) as e:
        # 결정은 남았다. 좌석·잔액 때문에 지금 못 깨우면, 재개 버튼이
        # 나중에 같은 결정으로 이어간다.
        out["note"] = str(e)
    return out


# ── 보조 ────────────────────────────────────────────────────────────
def _topo(tasks: list[Task]) -> list[Task]:
    """의존성 순서로 정렬. 순환이 있으면 남은 걸 그냥 뒤에 붙인다.

    순환을 오류로 올리지 않는 이유: 계획을 세운 것도 모델이다. 모델이 만든
    순환 하나 때문에 실행 전체를 버리는 것보다, 순서를 포기하고 진행한 뒤
    검증자에게 판정을 맡기는 편이 낫다.
    """
    done: set[str] = set()
    out: list[Task] = []
    pending = list(tasks)
    while pending:
        ready = [t for t in pending if all(d in done for d in t.deps)]
        if not ready:
            bus.say("SYSTEM", lang.t("log.cycle"), kind="error")
            out.extend(pending)
            break
        for t in ready:
            out.append(t)
            done.add(t.id)
            pending.remove(t)
    return out


def _sig(task: Task) -> str:
    """태스크의 '의미' 지문.

    done 을 `task.id` 로만 관리하면, 재기획에서 전략가가 같은 id 로 다른
    태스크를 정의했을 때 이미 끝났다고 착각하고 건너뛴다. 그래서 id 가
    아니라 지문으로 기억한다.
    """
    raw = f"{task.id}|{task.title}|{task.done_when}|{sorted(task.covers)}|{task.assignee}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _assignee(task: Task, *, quiet: bool = False) -> str:
    """담당자를 검사한다 (§10).

    모델이 없는 직원이나 맡길 수 없는 직원(기획자·검증자)을 적을 수 있다.
    그대로 따르면 KeyError 로 실행이 죽거나, 검증자가 자기 코드를 검증하게
    된다. 벗어나면 되돌린다 — **고르게 하되 검사 없이 따르지는 않는다.**
    """
    if task.assignee in roles.assignable():
        return task.assignee
    fallback = roles.assignable()[0]
    if not quiet:
        bus.say("SYSTEM",
                lang.t("log.badAssignee", task=task.title, who=task.assignee,
                       fallback=roles.display_name(fallback)), kind="error")
    return fallback


def _conflicts(a_who: str, b_who: str) -> bool:
    """두 직원의 태스크를 동시에 돌리면 안 되는가.

    같은 직원이면 안 된다 — 한 사람이 두 일을 동시에 하면 두 시도가 같은
    파일을 쓴다. 다른 직원이라도 **실효** 쓰기 구역이 겹치면 안 된다
    (프로젝트별로 권한을 넓혔을 수 있다).
    """
    if a_who == b_who:
        return True
    wa = set(pfs.areas(a_who, write=True))
    wb = set(pfs.areas(b_who, write=True))
    return bool(wa & wb)


def _apply(result: WorkResult, employee_id: str, *,
           round: int = 0, reason: str = "") -> list[str]:
    """직원이 낸 파일을 실제로 쓴다.

    권한 위반은 실행을 죽이지 않는다 — 그 파일만 거부하고 사실을 남긴다.
    한 파일의 경로가 틀렸다고 나머지 산출물까지 버릴 이유가 없고,
    거부 사실이 로그에 남아야 검증자와 CEO 가 판단할 수 있다.

    `round` 와 `reason` 은 파일 이력에 함께 남는다 — 나중에 이 파일을
    짚고 "몇 라운드에서 어떤 지적을 받고 고쳤나"를 따라갈 수 있어야 한다.
    """
    written: list[str] = []
    for f in result.files:
        try:
            info = pfs.write(f.path, f.content, employee_id,
                             round=round, reason=reason)
        except pfs.Denied as e:
            bus.say(employee_id, lang.t("log.denied", path=f.path, why=e),
                    kind="error")
            continue
        written.append(f.path)
        bus.say(employee_id,
                lang.t("log.created", path=f.path) if info["created"]
                else lang.t("log.updated", path=f.path, n=info["new_lines"]),
                kind="tool")
    return written


def route(requirement: str) -> Routing:
    """AUTO 라우팅 한 번 (§10). MANUAL 화면이 '누가 맡을까'를 물을 때도 쓴다."""
    roster = [roles.get(i).info() for i in roles.assignable()]
    r = employee.ask(roles.PLANNER, prompts.route(requirement, roster), Routing)
    if r.employee not in roles.assignable():
        r = Routing(employee=roles.assignable()[0],
                    why=lang.t("log.badAssigneeFallback", who=r.employee))
    return r


def parallel_limit(owner: str) -> int:
    """이 실행에서 동시에 돌릴 태스크 수. 요금제가 낮출 수 있다."""
    try:
        per_plan = int(credits.plan(credits.wallet(owner).plan)
                       .get("max_parallel_tasks", MAX_PARALLEL_TASKS))
    except Exception:                                          # noqa: BLE001
        per_plan = MAX_PARALLEL_TASKS
    return max(1, min(MAX_PARALLEL_TASKS, per_plan))


# ── 실행 하나의 공유 상태 ───────────────────────────────────────────
PROGRESS_FILE = ".progress.json"


class _Run:
    """한 실행 안에서 줄(lane)들이 함께 보는 상태.

    전부 `lock` 아래에서 읽고 쓴다. 파이썬의 `+=` 는 원자적이지 않다 —
    두 줄이 동시에 `score.reworks += 1` 을 하면 하나가 사라진다.
    """

    def __init__(self, slug: str, owner: str):
        self.slug = slug
        self.owner = owner
        self.lock = threading.RLock()
        self.test_lock = threading.Lock()
        self.halt = threading.Event()
        self.score = Score()
        self.plan: Plan | None = None
        self.criteria: list[Criterion] = []
        self.done: set[str] = set()
        self.rounds = 0
        self.inflight = 0.0
        self.report: dict = {}
        self.rows: list[dict] = []
        self.stage: str | None = None
        self.running: dict[str, Task] = {}          # sig -> task
        # 계획이 바뀔 때마다 올린다 — 본 줄이 순서(`_topo`)를 다시 짠다.
        self.plan_version = 0
        self.awaiting: dict[str, str] = {}          # sig -> approval id
        # sig -> {"rework": n, "feedback": Verdict dump | None,
        #         "baseline": {path: 내용 | None}}
        self.progress: dict[str, dict] = {}
        # 이 실행이 시작할 때 이미 청구돼 있던 원가. 끝날 때 **늘어난 만큼만**
        # 청구한다 — 재개한 실행이 앞 실행의 원가를 다시 청구하지 않게.
        self.billed = 0.0

    # ── 예산 ────────────────────────────────────────────────────
    @contextmanager
    def hold(self, worst: float, *, bump: bool):
        """호출 하나를 예산에 올려두고 부른다. `bump` 면 라운드를 센다.

        예약은 **검사와 같은 잠금 안에서** 건다. 검사만 잠그고 예약을
        나중에 하면, 두 줄이 동시에 검사를 통과한 뒤 둘 다 부른다.
        """
        with self.lock:
            if bump:
                self.rounds += 1
            try:
                guard.check_spend(
                    self.slug, self.owner, worst, rounds=self.rounds,
                    unbilled=max(0.0, usage.total_cost(self.slug) - self.billed),
                    inflight=self.inflight)
            except guard.SpendLimit as e:
                raise Stop(str(e)) from e
            self.inflight += worst
            rounds = self.rounds
        try:
            yield rounds
        finally:
            with self.lock:
                self.inflight = max(0.0, self.inflight - worst)

    # ── 진행 기록 ───────────────────────────────────────────────
    def prog(self, sig: str) -> dict:
        with self.lock:
            return self.progress.setdefault(
                sig, {"rework": 0, "feedback": None, "baseline": {}})

    def save_progress(self) -> None:
        """반려 횟수·반려 사유·시작 전 내용을 파일에 남긴다.

        메타(`.meta.json`)에 넣지 않는 이유: 시작 전 내용은 파일 원문이라
        클 수 있고, 메타는 단계마다 다시 쓰이며 색인도 매번 읽는다.
        쉬었다가(승인 대기) 재개해도 반려가 쌓여 포기할 때 **처음 상태로**
        되돌릴 수 있어야 한다 — 메모리에만 두면 재개한 실행은 되돌릴 곳을
        모른다.
        """
        # 잠금을 쥔 채 쓴다. 두 줄이 동시에 같은 파일을 이름 바꾸기로
        # 덮으면 윈도우에서는 한쪽이 PermissionError 로 실패한다.
        with self.lock:
            try:
                safeio.write_json(store.dir_of(self.slug) / PROGRESS_FILE,
                                  self.progress)
            except (OSError, TypeError, ValueError):
                pass                # 기록 실패가 실행을 멈추지는 않는다

    def load_progress(self) -> None:
        try:
            raw = json.loads((store.dir_of(self.slug) / PROGRESS_FILE)
                             .read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        with self.lock:
            self.progress = raw if isinstance(raw, dict) else {}


# ── 본체 ────────────────────────────────────────────────────────────
def _run(requirement: str, slug: str, attachment_ids: list[str],
         owner: str = "local", language: str = "ko",
         checkpoint: dict | None = None) -> None:
    """실행 스레드의 입구. 테넌트 자세를 **이 스레드에서 다시 세운다.**

    컨텍스트 변수는 새 스레드로 따라오지 않는다. 여기서 세우지 않으면
    실행 전체가 운영자 키로 돌아간다 — 무료 사용자가 우리 키를 태우고,
    BYOK 고객의 요금을 우리가 낸다. 둘 다 조용히 일어난다.
    """
    with tenant.bind(owner), lang.bind(language):
        _run_bound(requirement, slug, attachment_ids, owner, checkpoint)


def _run_bound(requirement: str, slug: str, attachment_ids: list[str],
               owner: str = "local", checkpoint: dict | None = None) -> None:
    # 이 스레드의 컨텍스트를 묶는다. 이후 bus/usage/pfs 호출은 전부 이 실행 소유다.
    bus.bind(slug)
    pfs.use(slug)
    m = store.meta(slug)
    if checkpoint is None:
        # 재개면 이전 실행의 로그를 지우지 않는다 — 지금까지 무슨 일이
        # 있었는지가 재개 이후의 로그와 이어져야 "왜 여기서부터 다시
        # 도나"를 사람이 읽을 수 있다.
        bus.reset(slug)
        usage.bind(slug)
    else:
        # `bind()` 는 0부터 다시 센다 — 재개에는 그걸 쓰면 안 된다.
        # 프로세스가 그대로면 메모리에 남은 값도 있겠지만, 서버가 그 사이
        # 재시작됐을 수 있으므로 **디스크에 남은 값**에서 시작한다.
        usage.seed(slug, m.get("usage") or {})

    run = _Run(slug, owner)
    run.billed = usage.total_cost(slug)
    any_mock = any(employee.is_mock(e) for e in roles.EMPLOYEES.values())
    store.save_meta(slug, {"mock": any_mock})
    bus.state(project={"slug": slug, "name": m.get("name", ""),
                       "requirement": requirement, "mock": any_mock})
    bus.emit("projects", list=store.list_projects())

    if checkpoint:
        run.rounds = int(checkpoint.get("rounds", 0))
        run.done = set(checkpoint.get("done", []))
        if checkpoint.get("plan"):
            run.plan = Plan.model_validate(checkpoint["plan"])
        # 옛 체크포인트(DAY 24)에는 stage 가 없다 — 계획이 있으면 테스트까지
        # 쓴 뒤 태스크를 돌던 중이었다.
        run.stage = checkpoint.get("stage") or ("tasks" if run.plan else None)
        run.score.restore(checkpoint.get("score"))
        run.score.ac_covered = int(checkpoint.get("ac_covered",
                                                  run.score.ac_covered))
        run.load_progress()

    if checkpoint is None:
        bus.say("USER", requirement)
    else:
        bus.say("SYSTEM", lang.t("log.resumed", n=len(run.done)), kind="tool")
    if any_mock:
        bus.say("SYSTEM", lang.t("log.mock"), kind="error")
    attachments_note = ""
    if attachment_ids:
        from app import attachments
        attachments_note = attachments.summary(attachment_ids)
        bus.say("USER", lang.t("log.attached", what=attachments_note),
                kind="tool")
        store.save_meta(slug, {"attachments": attachments_note})

    try:
        if run.plan is None:
            _plan(run, requirement, attachments_note)
        if run.stage == "planned":
            _plan_gate(run)
            _write_tests(run)
        else:
            # 재개 — 이미 있는 계획을 그대로 쓴다. PLAN·WRITE_TESTS 를
            # 다시 돌리면 검증자가 이미 쓴 테스트를 또 쓰거나, 전략가가
            # 이미 끝난 태스크를 다른 계획으로 다시 쪼갤 수 있다.
            run.criteria = run.plan.acceptance_criteria
            run.score.total_tasks = len(run.plan.tasks)
            run.score.ac_total = len(run.criteria)
            run.score.done_tasks = len(run.done & {_sig(t) for t in run.plan.tasks})
            _board(run)
            run.score.push()
            _plan_gate(run)

        _schedule(run)
        _finalize(run)

    except Park:
        pass                     # `_park` 가 이미 기록했다. 결정이 깨운다.
    except Stop as e:
        _fail(run, str(e))
    except employee.EmployeeFailed as e:
        _fail(run, lang.t("stop.employeeFailed", why=e))
    except Exception as e:                       # noqa: BLE001
        _fail(run, f"{type(e).__name__}: {e}")
    finally:
        # 실제로 쓴 만큼만 깎는다 (§15). 예약해두고 돌려주는 방식이 아닌
        # 이유: 실행이 죽으면 돌려줄 사람이 없다. Mock 은 원가가 0 이므로
        # 저절로 0 이 깎인다 — 따로 분기하지 않는다.
        #
        # **이 실행이 늘린 만큼만** 깎는다 (DAY 25에 고침). 재개한 실행은
        # 디스크에서 앞 실행의 사용량을 이어받는다(`usage.seed`). 누적을
        # 통째로 깎으면 앞 실행이 끝날 때 이미 깎은 돈을 또 깎는다 —
        # 재개할 때마다 한 번씩.
        total = usage.total_cost(slug)
        left = credits.charge(owner, max(0.0, total - run.billed))
        store.save_meta(slug, {"credits": round(credits.usd_to_credits(total), 3),
                               "credits_left": left})
        bus.state(credits=left, credits_used=credits.usd_to_credits(total))
        with _runs_lock:
            # 쉬러 들어간 실행(`_park`)은 이미 자리를 비웠고, 그 사이 결정이
            # 들어와 **새 스레드**가 같은 slug 로 자리를 잡았을 수 있다.
            # 남의 자리를 지우지 않는다.
            if _runs.get(slug) is threading.current_thread():
                _runs.pop(slug, None)
                _cancelled.discard(slug)
        pfs.release()


def _plan(run: _Run, requirement: str, attachments_note: str) -> None:
    """1) 기획."""
    bus.phase("PLAN", lang.t("phase.plan"))
    run.score.push()
    _check_cancelled(run.slug)
    with run.hold(employee.worst_case_cost(roles.PLANNER), bump=True):
        plan = employee.ask(roles.PLANNER,
                            prompts.plan(requirement, attachments_note), Plan)
    _adopt_plan(run, plan)
    if not plan.tasks:
        raise Stop(lang.t("stop.noTasks"))
    run.stage = "planned"
    _persist(run)


def _adopt_plan(run: _Run, plan: Plan) -> None:
    employee.say(roles.get(roles.PLANNER), plan.message_to_team)
    bus.handoff(roles.PLANNER, roles.VERIFIER, "PLAN",
                task_titles=[t.title for t in plan.tasks],
                criteria=[c.text for c in plan.acceptance_criteria])
    with run.lock:
        run.plan = plan
        run.criteria = plan.acceptance_criteria
        run.score.total_tasks = len(plan.tasks)
        run.score.ac_total = len(run.criteria)
    m = store.meta(run.slug)
    store.save_meta(run.slug, {"name": plan.project_name,
                               "criteria": [c.model_dump() for c in run.criteria]})
    bus.state(project={"slug": run.slug, "name": plan.project_name,
                       "requirement": m.get("requirement", ""),
                       "mock": m.get("mock", False)})
    _board(run)
    run.score.push()


def _plan_gate(run: _Run) -> None:
    """계획 승인 게이트 (DAY 25). 켜져 있지 않으면 그냥 지나간다.

    같은 계획은 한 번만 묻는다 — 재개할 때마다 같은 계획을 다시 승인하라고
    하지 않는다. 계획 지문(`plan_hash`)으로 기억한다.
    """
    while "plan" in gates.of(run.slug):
        h = gates.plan_hash(run.plan)
        rec = gates.find_plan(run.slug, h)
        if rec is None:
            rec = gates.open_gate(
                run.slug, "plan", title=run.plan.project_name, plan_hash=h,
                detail={"tasks": [{"id": t.id, "title": t.title,
                                   "assignee": t.assignee, "deps": t.deps}
                                  for t in run.plan.tasks],
                        "criteria": [c.model_dump() for c in run.criteria],
                        "message": run.plan.message_to_team})
        status = rec.get("status")
        if status == "pending":
            if _park(run, "plan"):
                raise Park()
            continue
        gates.mark_applied(run.slug, rec["id"])
        if status == "approved":
            return
        if status == "stopped":
            raise Stop(lang.t("stop.gate"))
        if status == "discarded":
            raise Stop(lang.t("stop.planDiscarded"))
        _revise_plan(run, rec.get("comment") or "")


def _revise_plan(run: _Run, comment: str) -> None:
    """CEO 가 계획을 반려했다 — 전략가가 의견을 받아 고친다."""
    with run.lock:
        run.score.replans += 1
        over = run.score.replans > config.MAX_REPLANS
    if over:
        raise Stop(lang.t("stop.replans", n=config.MAX_REPLANS,
                          task=run.plan.project_name))
    bus.phase("REPLAN", lang.t("phase.revise"))
    _check_cancelled(run.slug)
    with run.hold(employee.worst_case_cost(roles.PLANNER), bump=True):
        plan = employee.ask(roles.PLANNER,
                            prompts.revise_plan(run.plan, comment), Plan)
    if not plan.tasks:
        raise Stop(lang.t("stop.noTasks"))
    _adopt_plan(run, plan)
    _persist(run)


def _write_tests(run: _Run) -> None:
    """2) 검증자가 테스트를 **먼저** 쓴다.

    구현자는 이 파일들을 읽지도 못한다. 보면 맞춰 짜기 때문이다.
    """
    bus.phase("WRITE_TESTS", lang.t("phase.write_tests"))
    _check_cancelled(run.slug)
    with run.hold(employee.worst_case_cost(roles.VERIFIER), bump=True) as rounds:
        suite: TestSuite = employee.ask(
            roles.VERIFIER, prompts.write_tests(run.criteria, run.plan.tasks),
            TestSuite)
    employee.say(roles.get(roles.VERIFIER), suite.message_to_team)
    covered: set[str] = set()
    for tf in suite.files:
        path = tf.path if tf.path.startswith("tests/") else f"tests/{tf.path}"
        try:
            pfs.write(path, tf.content, roles.VERIFIER, round=rounds)
        except pfs.Denied as e:
            bus.say(roles.VERIFIER,
                    lang.t("log.testDenied", path=path, why=e),
                    kind="error")
            continue
        covered.update(tf.covers)
        bus.say(roles.VERIFIER,
                lang.t("log.testWritten", path=path,
                       covers=", ".join(tf.covers) or lang.t("log.unspecified")),
                kind="tool")
    run.score.ac_covered = len(covered & {c.id for c in run.criteria})
    if suite.uncovered:
        bus.say(roles.VERIFIER,
                lang.t("log.uncovered", ids=", ".join(suite.uncovered)),
                kind="verdict")
    bus.handoff(roles.VERIFIER, "IMPLEMENT", "WRITE_TESTS",
                covered=sorted(covered), uncovered=suite.uncovered)
    bus.state(files=store.files_of(run.slug))
    run.score.push()
    run.stage = "tasks"
    _persist(run)


def _board(run: _Run) -> list[dict]:
    with run.lock:
        plan = run.plan
        if plan is None:
            return []
        running = {t.id for t in run.running.values()}
        rows = []
        for t in plan.tasks:
            s = _sig(t)
            status = ("done" if s in run.done
                      else "awaiting" if s in run.awaiting
                      else "doing" if t.id in running else "todo")
            rows.append({"id": t.id, "title": t.title,
                         "assignee": _assignee(t, quiet=True), "status": status})
        active = [{"task": t.id, "title": t.title,
                   "assignee": _assignee(t, quiet=True)}
                  for t in run.running.values()]
        run.rows = rows
    bus.state(tasks=rows, active=active)
    return rows


def _run_tests(run: _Run) -> dict:
    """pytest 는 한 번에 하나만 돈다 — 같은 폴더에 설정 파일을 쓰는
    두 프로세스가 겹칠 이유가 없다."""
    with run.test_lock:
        bus.say("SYSTEM", lang.t("log.pytest"), kind="tool")
        r = runner.run(pfs.root())
    with run.lock:
        run.score.tests_ran = not r.get("skipped_run")
        run.score.tests_pass = r["ok"]
        run.score.tests = {k: r.get(k, 0) for k in ("passed", "failed", "errors")}
        run.report = r
    head = (lang.t("test.passed") if r["ok"]
            else lang.t("test.failed", detail=runner.summary_line(r)))
    detail = "\n".join(r["failed_tests"][:5])
    bus.say("SYSTEM", head + (f"\n```\n{detail}\n```" if detail else ""), kind="tool")
    return r


def _boundary(run: _Run) -> None:
    """단계 경계에서 멈출 이유가 있는지 본다."""
    _check_cancelled(run.slug)
    if run.halt.is_set():
        raise _Halted()


def _lane(run: _Run, task: Task):
    """태스크 하나를 도는 줄. **이 스레드에서** 실행 범위를 다시 세운다.

    `tenant` · `lang` 은 `contextvars.copy_context()` 로 제출할 때 따라왔다.
    `bus` · `usage` · `project_fs` 는 스레드 로컬이라 여기서 묶는다.
    """
    bus.bind(run.slug)
    usage.attach(run.slug)
    pfs.use(run.slug)
    try:
        return _work(run, task)
    finally:
        bus.release()
        pfs.release()
        # 줄 스레드는 실행이 끝나면 사라진다. 스레드마다 열린 색인 연결을
        # 남겨두지 않는다.
        index.close()


def _ceo_verdict(comment: str) -> Verdict:
    """CEO 의 반려를 담당자가 읽는 모양(반려 사유)으로 옮긴다."""
    return Verdict(message_to_team=comment, verdict="fail", severity="major",
                   findings=[], required_fixes=[comment], confidence=1.0)


def _work(run: _Run, task: Task) -> tuple[str, Verdict]:
    """태스크 하나의 구현 → 테스트 → 검토 → (반려면) 다시.

    돌려주는 값: `("pass", 판정)` 또는 `("abandon", 마지막 판정)`.
    완료로 칠지(승인 게이트)·포기하면 무엇을 할지(재기획)는 **본 줄이**
    정한다 — 계획을 바꾸는 일은 다른 줄이 돌고 있지 않을 때만 한다.
    """
    slug = run.slug
    who = _assignee(task)
    sig = _sig(task)
    prog = run.prog(sig)
    feedback = Verdict.model_validate(prog["feedback"]) if prog["feedback"] else None
    baseline: dict[str, str | None] = prog["baseline"]

    while True:
        _boundary(run)
        bus.phase("IMPLEMENT", f"{roles.get(who).name} · {task.title}",
                  owner=who, lane=task.id)
        with run.hold(employee.worst_case_cost(who), bump=True) as rounds:
            bus.state(round=rounds)
            # 작은 태스크·첫 시도면 더 싼 모델로 내려간다(§ 난이도 라우팅).
            # 기본 모델의 최악 비용으로 이미 예산을 잡았으므로 여기서 고르는
            # 모델은 그보다 비쌀 수 없다.
            routed_model = difficulty.pick_model(
                roles.get(who), task, is_retry=feedback is not None)
            with run.lock:
                criteria = list(run.criteria)
            work: WorkResult = employee.ask(
                who, prompts.implement(task, criteria, pfs.snapshot(who), feedback),
                WorkResult, model=routed_model)
        # 이 태스크가 건드리는 각 파일의 **시작 전** 내용. 처음 손대는
        # 순간에만 채운다 — 재시도마다 다시 읽으면 반려된 중간 상태가
        # "시작 전"으로 뒤바뀐다. 반려가 쌓여 태스크를 포기하면 여기로
        # 되돌린다(§18 자동 롤백).
        with run.lock:
            for fw in work.files:
                baseline.setdefault(fw.path, pfs.raw_read(fw.path))
        run.save_progress()
        employee.say(roles.get(who), work.message_to_team)
        # 반려를 받고 다시 쓰는 것이면 그 사유를 이력에 남긴다.
        _apply(work, who, round=rounds,
               reason=(feedback.message_to_team if feedback else ""))
        bus.state(files=store.files_of(slug))
        # 검증자의 **프롬프트**에는 여전히 안 넘긴다(교차검증 오염
        # 방지) — 이건 사람이 로그로 보는 감사 기록이지, 다음 모델 호출에
        # 들어가는 입력이 아니다.
        bus.handoff(who, roles.VERIFIER, "IMPLEMENT", task_id=task.id,
                    files=[fw.path for fw in work.files],
                    summary=work.summary, self_check=work.self_check)

        bus.phase("TEST", task.title, lane=task.id)
        report = _run_tests(run)
        run.score.push()

        bus.phase("REVIEW", task.title, lane=task.id)
        _boundary(run)
        with run.hold(employee.worst_case_cost(roles.VERIFIER), bump=False):
            # 변경분이 아니라 전체를 보여준다. 부분만 보면 회귀를 놓친다.
            # 담당자의 설명(work.summary)은 **넘기지 않는다** — 자기 합리화에
            # 오염되지 않아야 교차검증이 성립한다.
            verdict: Verdict = employee.ask(
                roles.VERIFIER,
                prompts.review(task, criteria, pfs.snapshot(roles.VERIFIER), report),
                Verdict)
        with run.lock:
            run.score.reviews += 1
            run.score.confidence_total += verdict.confidence
        icon = (lang.t("verdict.pass") if verdict.verdict == "pass"
                else lang.t("verdict.fail", severity=verdict.severity))
        # 판정 말풍선에 확신도를 **같이** 싣는다 (DAY 25). 따로 오는 handoff
        # 이벤트와 짝지으면, 태스크가 동시에 돌 때 다른 줄의 판정과 섞인다.
        bus.emit("message", agent=roles.VERIFIER, kind="verdict",
                 text=f"**{icon}** — {verdict.message_to_team}",
                 confidence=verdict.confidence, task_id=task.id)
        for f in verdict.findings:
            bus.say(roles.VERIFIER, f"`{f.file}` · {f.issue}", kind="tool")
        bus.handoff(
            roles.VERIFIER, (roles.PLANNER if verdict.verdict == "pass" else who),
            "REVIEW", task_id=task.id, verdict=verdict.verdict,
            severity=verdict.severity,
            findings=[f.model_dump() for f in verdict.findings],
            required_fixes=verdict.required_fixes,
            confidence=verdict.confidence)

        if verdict.verdict == "pass":
            with run.lock:
                run.score.passes += 1
            return "pass", verdict

        with run.lock:
            run.score.reworks += 1
            prog["rework"] += 1
            prog["feedback"] = verdict.model_dump()
            give_up = prog["rework"] >= config.MAX_REWORK
        run.score.push()
        run.save_progress()
        feedback = verdict
        if give_up:
            return "abandon", verdict


def _schedule(run: _Run) -> None:
    """3) 태스크 루프 — 의존성이 풀린 것을 **동시에** 돌린다.

    본 줄(이 함수)은 직원을 부르지 않는다. 고르고, 나눠주고, 결과를 받아
    완료·승인 대기·포기를 가른다. 계획을 바꾸는 일(재기획)은 **다른 줄이
    하나도 돌고 있지 않을 때만** 한다 — 도는 중인 태스크의 계획을 바꾸면
    그 줄은 없는 태스크를 하고 있게 된다.
    """
    slug = run.slug
    limit = parallel_limit(run.owner)
    with run.lock:
        queue = _topo(run.plan.tasks)
        # 재개 — 승인을 기다리던 태스크를 다시 집는다.
        pending_ids = {a.get("sig"): a["id"] for a in gates.pending(slug)
                       if a.get("gate") == "task"}
        live = {_sig(t) for t in run.plan.tasks}
        run.awaiting = {s: aid for s, aid in pending_ids.items() if s in live}
    seen_version = run.plan_version
    futures: dict[Future, str] = {}
    abandoned: list[tuple[Task, Verdict]] = []
    error: BaseException | None = None
    relax = False
    pool = ThreadPoolExecutor(max_workers=limit, thread_name_prefix=f"lane:{slug}")
    try:
        while True:
            # ① 승인 결정을 반영한다.
            abandoned.extend(_apply_task_decisions(run))
            if run.plan_version != seen_version:        # 폐기로 계획이 줄었다
                with run.lock:
                    queue = _topo(run.plan.tasks)
                    seen_version = run.plan_version
            try:
                _check_cancelled(slug)
            except Stop as e:
                error = error or e
                run.halt.set()

            # ② 새 줄을 띄운다 — 멈출 이유가 없고, 재기획을 기다리지 않을 때만.
            if error is None and not abandoned:
                for t in _eligible(run, queue, relax=relax):
                    if len(futures) >= limit:
                        break
                    s = _sig(t)
                    with run.lock:
                        run.running[s] = t
                    ctx = contextvars.copy_context()
                    futures[pool.submit(ctx.run, _lane, run, t)] = s
                    relax = False
                _board(run)

            # ③ 도는 줄이 없으면 다음 할 일을 정한다.
            if not futures:
                if error is not None:
                    raise error
                if abandoned:
                    queue = _replan(run, abandoned)
                    seen_version = run.plan_version
                    abandoned = []
                    continue
                with run.lock:
                    todo = [t for t in queue if _sig(t) not in run.done
                            and _sig(t) not in run.awaiting]
                    waiting = bool(run.awaiting)
                if not todo and not waiting:
                    return                              # 전부 끝났다
                if waiting:
                    # 할 수 있는 것은 다 했다. 사람을 기다린다.
                    _persist(run)
                    if _park(run, "task"):
                        raise Park()
                    continue                            # 그 사이 결정이 왔다
                # 남은 것이 있는데 아무것도 못 띄웠다 — 의존성 순환이다.
                # 순서를 포기하고 하나씩 돈다(`_topo` 와 같은 판단).
                relax = True
                continue

            # ④ 끝난 줄을 거둔다.
            finished, _ = wait(list(futures), timeout=DECISION_POLL,
                               return_when=FIRST_COMPLETED)
            for fut in finished:
                s = futures.pop(fut)
                with run.lock:
                    task = run.running.pop(s, None)
                try:
                    outcome, verdict = fut.result()
                except _Halted:
                    continue
                except BaseException as e:             # noqa: BLE001
                    # 한 줄이 쓰러지면 나머지 줄도 다음 경계에서 접는다.
                    # 도는 중인 호출은 끝까지 기다린다 — 반쯤 쓴 파일을
                    # 남기지 않기 위해서다(`cancel()` 과 같은 이유).
                    error = error or e
                    run.halt.set()
                    continue
                if task is None:
                    continue
                if outcome == "abandon":
                    abandoned.append((task, verdict))
                    continue
                _accept_or_gate(run, task, verdict)
            _board(run)
    finally:
        run.halt.set()
        pool.shutdown(wait=True)
        with run.lock:
            run.running.clear()


def _eligible(run: _Run, queue: list[Task], *, relax: bool) -> list[Task]:
    """지금 띄울 수 있는 태스크. `queue` 순서(= 의존성 순서)대로 고른다."""
    with run.lock:
        ids = {t.id for t in run.plan.tasks}
        done_ids = {t.id for t in run.plan.tasks if _sig(t) in run.done}
        busy = [_assignee(t, quiet=True) for t in run.running.values()]
        out: list[Task] = []
        for t in queue:
            s = _sig(t)
            if s in run.done or s in run.awaiting or s in run.running:
                continue
            # 계획에 없는 id 를 의존성으로 적었으면 무시한다 — 영영 안 풀리는
            # 의존성은 순환과 같은 결과(아무것도 못 함)를 낸다.
            deps = [d for d in t.deps if d in ids and d != t.id]
            if not relax and not all(d in done_ids for d in deps):
                continue
            who = _assignee(t, quiet=True)
            if any(_conflicts(who, b) for b in busy):
                continue
            out.append(t)
            busy.append(who)
            if relax:
                break                      # 순환이면 하나씩만
        return out


def _accept_or_gate(run: _Run, task: Task, verdict: Verdict) -> None:
    """검증자가 통과시킨 태스크 — 완료로 칠지, 사람에게 물을지."""
    s = _sig(task)
    who = _assignee(task, quiet=True)
    reason = gates.task_reason(gates.of(run.slug), who, verdict.confidence)
    if reason is None:
        _mark_done(run, s)
        return
    prog = run.prog(s)
    rec = gates.open_gate(
        run.slug, "task", title=task.title, sig=s, task_id=task.id,
        detail={"assignee": who, "reason": reason,
                "confidence": verdict.confidence,
                "threshold": gates.CONFIDENCE_GATE,
                "message": verdict.message_to_team,
                "files": sorted(prog.get("baseline") or {}),
                "findings": [f.model_dump() for f in verdict.findings],
                "rework": prog.get("rework", 0)})
    with run.lock:
        run.awaiting[s] = rec["id"]
    _persist(run)


def _mark_done(run: _Run, sig: str) -> None:
    with run.lock:
        run.done.add(sig)
        run.awaiting.pop(sig, None)
        run.progress.pop(sig, None)
        run.score.done_tasks = len(run.done & {_sig(t) for t in run.plan.tasks})
    _board(run)
    run.score.push()
    run.save_progress()
    _persist(run)


def _apply_task_decisions(run: _Run) -> list[tuple[Task, Verdict]]:
    """CEO 의 태스크 결정을 반영한다. 포기로 이어진 것을 돌려준다."""
    decided = gates.take_decided(run.slug, "task")
    if not decided:
        return []
    with run.lock:
        by_sig = {_sig(t): t for t in run.plan.tasks}
    abandoned: list[tuple[Task, Verdict]] = []
    for rec in decided:
        s = rec.get("sig")
        with run.lock:
            run.awaiting.pop(s, None)
        task = by_sig.get(s)
        if task is None:
            continue                           # 그 사이 계획이 바뀌었다
        status = rec.get("status")
        if status == "approved":
            _mark_done(run, s)
        elif status == "stopped":
            raise Stop(lang.t("stop.gate"))
        elif status == "discarded":
            _discard_task(run, task)
        else:
            v = _ceo_verdict(rec.get("comment") or "")
            prog = run.prog(s)
            with run.lock:
                prog["rework"] += 1
                prog["feedback"] = v.model_dump()
                run.score.reworks += 1
                give_up = prog["rework"] >= config.MAX_REWORK
            run.save_progress()
            if give_up:
                abandoned.append((task, v))
    _board(run)
    run.score.push()
    _persist(run)
    return abandoned


def _discard_task(run: _Run, task: Task) -> None:
    """대표가 태스크를 **폐기**했다 — 흔적을 되돌리고 계획에서 뺀다.

    나머지는 계속 돈다. 이 태스크에 기대던 태스크는 의존성이 사라진 채로
    돈다(`_eligible` 은 계획에 없는 id 를 무시한다). 이 태스크가 덮던
    인수기준은 최종 검수에서 미충족으로 드러난다 — 버린 것을 채운 척하지
    않는다.
    """
    s = _sig(task)
    prog = run.prog(s)
    restored = pfs.restore_files(prog.get("baseline") or {})
    bus.say("SYSTEM", lang.t("log.discarded", task=task.title,
                             files=", ".join(restored) or "-"), kind="error")
    if restored:
        bus.state(files=store.files_of(run.slug))
    with run.lock:
        run.progress.pop(s, None)
        run.plan = run.plan.model_copy(update={
            "tasks": [t for t in run.plan.tasks if _sig(t) != s]})
        run.plan_version += 1
        run.score.total_tasks = len(run.plan.tasks)
        live = {_sig(t) for t in run.plan.tasks}
        run.score.done_tasks = len(run.done & live)
    run.save_progress()


def _replan(run: _Run, abandoned: list[tuple[Task, Verdict]]) -> list[Task]:
    """반려가 쌓여 포기한 태스크 — 되돌리고, 계획을 다시 세운다.

    여러 태스크를 한꺼번에 포기했으면 **전부** 되돌리고 재기획 횟수도
    각각 센다(한 번에 여럿이 막혔다는 것은 더 나쁜 신호다). 재기획 자체는
    첫 태스크를 두고 한 번만 한다 — 같은 옛 계획을 두고 여러 번 물으면
    서로 다른 새 계획이 겹친다.
    """
    for task, verdict in abandoned:
        s = _sig(task)
        prog = run.prog(s)
        # 이 태스크는 포기한다 — 반려된 시도의 흔적을 남기지 않는다.
        restored = pfs.restore_files(prog.get("baseline") or {})
        if restored:
            bus.say("SYSTEM", lang.t(
                "log.rollback", task=task.title, n=prog.get("rework", 0),
                files=", ".join(restored)), kind="error")
            bus.state(files=store.files_of(run.slug))
        with run.lock:
            run.progress.pop(s, None)
            run.score.replans += 1
            over = run.score.replans > config.MAX_REPLANS
        run.save_progress()
        if over:
            raise Stop(lang.t("stop.replans", n=config.MAX_REPLANS,
                              task=task.title))
    task, verdict = abandoned[0]
    bus.phase("REPLAN", task.title)
    _check_cancelled(run.slug)
    with run.hold(employee.worst_case_cost(roles.PLANNER), bump=True):
        plan = employee.ask(roles.PLANNER,
                            prompts.replan(run.plan, task, verdict), Plan)
    employee.say(roles.get(roles.PLANNER), plan.message_to_team)
    with run.lock:
        run.plan = plan
        run.plan_version += 1
        run.score.total_tasks = len(plan.tasks)
        live = {_sig(t) for t in plan.tasks}
        run.awaiting = {s: a for s, a in run.awaiting.items() if s in live}
        run.score.done_tasks = len(run.done & live)
    _board(run)
    run.score.push()
    _persist(run)
    # 재기획한 계획도 계획이다 — 계획 승인을 켜뒀으면 다시 묻는다.
    _plan_gate(run)
    with run.lock:
        return _topo(run.plan.tasks)


def _finalize(run: _Run) -> None:
    """4) 최종 검수."""
    slug = run.slug
    bus.phase("FINALIZE", lang.t("phase.finalize"))
    _check_cancelled(slug)
    with run.hold(employee.worst_case_cost(roles.PLANNER), bump=True):
        final: FinalReport = employee.ask(
            roles.PLANNER,
            prompts.finalize(run.criteria, pfs.snapshot("SYSTEM"), run.report),
            FinalReport)
    employee.say(roles.get(roles.PLANNER), final.message_to_team)
    bus.handoff(roles.PLANNER, "SYSTEM", "FINALIZE",
                met=final.met_criteria, unmet=final.unmet_criteria)
    ids = {c.id for c in run.criteria}
    run.score.ac_met = len(set(final.met_criteria) & ids)
    run.score.push()

    _persist(run, status="done", report=final)
    bus.emit("projects", list=store.list_projects())
    bus.emit("done", ok=not final.unmet_criteria, summary=final.summary,
             unmet=final.unmet_criteria, score=run.score.value())


def _park(run: _Run, gate: str) -> bool:
    """승인을 기다리며 쉰다. 쉬었으면 True, 그 사이 결정이 왔으면 False.

    확인과 자리 비우기를 `decide()` 와 **같은 잠금** 안에서 한다 — 그
    이유는 `decide()` 에 적었다.

    `gate` 는 지금 무엇을 기다리는가다. 그 종류의 결정만 본다 — 계획 승인을
    기다리는데 태스크 결정이 와 있다고 쉬지 않으면, 계획 게이트는 그
    결정을 반영할 수 없으니 쉬지도 못하고 나아가지도 못한 채 돈다.
    """
    slug = run.slug
    with _runs_lock:
        if gates.has_unapplied_decisions(slug, gate):
            return False
        _persist(run, status="awaiting")
        store.save_meta(slug, {"stopped_reason": None,
                               "awaiting_since": time.time()})
        if _runs.get(slug) is threading.current_thread():
            _runs.pop(slug, None)
            _cancelled.discard(slug)
    n = len(gates.pending(slug))
    bus.say("SYSTEM", lang.t("log.parked", n=n), kind="verdict")
    bus.emit("projects", list=store.list_projects())
    bus.emit("awaiting", approvals=gates.pending(slug))
    return True


def _persist(run: _Run, status: str = "running",
             report: FinalReport | None = None) -> None:
    slug = run.slug
    with run.lock:
        plan = run.plan
        patch = {
            "status": status,
            "score": run.score.value(),
            "score_detail": run.score.detail(),
            "tasks": list(run.rows),
            "usage": usage.agents_of(slug),
            "cost": round(usage.total_cost(slug), 4),
            "cache_ok": usage.cache_working(slug),
            "criteria": [c.model_dump() for c in plan.acceptance_criteria] if plan else [],
            "files": store.files_of(slug),
            # 재개(§18)를 위한 체크포인트. `resume()` 이 이것만으로 처음부터
            # 다시 계획하지 않고 이어갈 수 있다 — done 은 이미 끝낸 태스크,
            # rounds 는 상한 검사가 이어서 세야 할 값, plan 은 다시 물을
            # 필요가 없는 계획, stage 는 테스트를 이미 썼는가다.
            "checkpoint": {
                "stage": run.stage,
                "done": sorted(run.done),
                "rounds": run.rounds,
                "plan": plan.model_dump() if plan else None,
                "ac_covered": run.score.ac_covered,
                "score": run.score.carry(),
            },
        }
    if report is not None:
        patch["report"] = report.model_dump()
    store.save_meta(slug, patch)


def _fail(run: _Run, msg: str) -> None:
    slug = run.slug
    bus.say("SYSTEM", lang.t("log.stopped", why=msg), kind="error")
    _persist(run, status="stopped")
    store.save_meta(slug, {"stopped_reason": msg})
    # 열려 있던 승인은 닫지 않는다. 멈춘 동안 내린 결정도 기록되고,
    # 재개하면 그 결정부터 반영한다 — 닫아버리면 이미 검증까지 통과한
    # 태스크를 재개 후에 처음부터 다시 만든다(돈을 두 번 쓴다).
    bus.emit("projects", list=store.list_projects())
    bus.emit("done", ok=False, summary=msg, unmet=[], score=run.score.value())
