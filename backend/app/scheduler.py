"""B6 — 예약 실행.

정해진 시각에 저장된 요구사항을 자동으로 착수시킨다.
cron 문자열 대신 `HH:MM` + 요일 선택. 개인용 도구에 cron 문법은 과하다.

## 안전 관련 결정

- **예약은 mock/실제 모드를 서버 설정 그대로 따른다.** 예약이 몰래 실제 모델을
  부르는 일이 없게, 서버가 mock이면 예약도 mock이다.
- **동시 실행 한도를 그대로 존중한다.** 한도에 걸리면 그 회차는 건너뛰고 기록만 남긴다.
- **1분 안에 두 번 발화하지 않는다.** 마지막 실행 시각을 분 단위로 기억한다.
- 실제 모드인데 키가 없으면 실행하지 않고 사유를 남긴다.
"""
import json
import threading
import time
import uuid
from datetime import datetime

from app import bus
from app import config

STORE = config.ROOT / "schedules.json"
CHECK_INTERVAL = 20          # 초

_lock = threading.RLock()
_items: dict[str, dict] = {}
_thread: threading.Thread | None = None
_stop = threading.Event()

# 실행 함수는 서버가 주입한다(순환 import 방지)
_runner = None


def configure(runner) -> None:
    """runner(requirement) -> slug 를 주입한다."""
    global _runner
    _runner = runner


def _load() -> None:
    if not STORE.exists():
        return
    try:
        data = json.loads(STORE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    with _lock:
        for it in data.get("schedules", []):
            if isinstance(it, dict) and it.get("id"):
                it.setdefault("last_run", None)
                it.setdefault("last_note", "")
                _items[it["id"]] = it


def _save() -> None:
    with _lock:
        data = {"schedules": list(_items.values())}
    STORE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add(requirement: str, at: str, days: list[int] | None = None,
        enabled: bool = True) -> dict:
    """at: 'HH:MM'. days: 0=월 … 6=일. 비우면 매일."""
    hh, mm = _parse_time(at)
    item = {"id": uuid.uuid4().hex[:8], "requirement": requirement.strip(),
            "at": f"{hh:02d}:{mm:02d}", "days": sorted(days or []),
            "enabled": bool(enabled), "created_at": time.time(),
            "last_run": None, "last_note": ""}
    if not item["requirement"]:
        raise ValueError("요구사항이 비어 있습니다")
    with _lock:
        _items[item["id"]] = item
    _save()
    return item


def _parse_time(at: str) -> tuple[int, int]:
    try:
        hh, mm = at.strip().split(":")
        h, m = int(hh), int(mm)
        if not (0 <= h < 24 and 0 <= m < 60):
            raise ValueError
        return h, m
    except Exception:
        raise ValueError(f"시각 형식이 잘못됐습니다: {at} (HH:MM 이어야 함)")


def update(sid: str, **fields) -> dict | None:
    with _lock:
        it = _items.get(sid)
        if not it:
            return None
        if "at" in fields:
            h, m = _parse_time(fields.pop("at"))
            it["at"] = f"{h:02d}:{m:02d}"
        if "days" in fields:
            it["days"] = sorted(fields.pop("days") or [])
        if "requirement" in fields:
            it["requirement"] = (fields.pop("requirement") or "").strip()
        if "enabled" in fields:
            it["enabled"] = bool(fields.pop("enabled"))
    _save()
    return it


def remove(sid: str) -> bool:
    with _lock:
        gone = _items.pop(sid, None) is not None
    if gone:
        _save()
    return gone


def listing() -> list[dict]:
    with _lock:
        return sorted(_items.values(), key=lambda i: (i["at"], i["created_at"]))


def _due(item: dict, now: datetime) -> bool:
    if not item.get("enabled"):
        return False
    if item["days"] and now.weekday() not in item["days"]:
        return False
    if item["at"] != now.strftime("%H:%M"):
        return False
    # 같은 분에 두 번 발화하지 않는다
    return item.get("last_run_minute") != now.strftime("%Y-%m-%d %H:%M")


def _fire(item: dict, now: datetime) -> None:
    item["last_run_minute"] = now.strftime("%Y-%m-%d %H:%M")
    item["last_run"] = time.time()
    try:
        slug = _runner(item["requirement"])
        item["last_note"] = f"착수됨 ({slug})"
        bus.say("SYSTEM", f"예약 실행 — \"{item['requirement'][:40]}\" 착수", kind="tool")
    except Exception as e:
        item["last_note"] = f"건너뜀: {e}"
        bus.say("SYSTEM", f"예약 실행 건너뜀 — {e}", kind="error")
    _save()


def _loop() -> None:
    while not _stop.wait(CHECK_INTERVAL):
        if _runner is None:
            continue
        now = datetime.now()
        with _lock:
            due = [i for i in _items.values() if _due(i, now)]
        for item in due:
            _fire(item, now)


def start() -> None:
    global _thread
    _load()
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="scheduler")
    _thread.start()


def stop() -> None:
    _stop.set()


def next_due(item: dict, now: datetime | None = None) -> str:
    """다음 실행 시각을 사람이 읽을 문장으로."""
    if not item.get("enabled"):
        return "꺼짐"
    names = ["월", "화", "수", "목", "금", "토", "일"]
    when = "매일" if not item["days"] else ", ".join(names[d] for d in item["days"])
    return f"{when} {item['at']}"
