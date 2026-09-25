"""파일을 **잘리지 않게** 쓴다 (DAY 22).

## 무엇이 문제였나

저장이 전부 `write_text()` 한 줄이었다. 그 한 줄은 이렇게 동작한다:

1. 파일을 열면서 **내용을 0으로 자른다**
2. 새 내용을 쓴다

1과 2 사이에 프로세스가 죽으면 **빈 파일**이 남는다. 디스크가 차 있거나
2 중간에 죽으면 반쯤 쓰인 JSON 이 남고, 그건 다음에 읽을 때 깨진다.

이게 걸리는 파일들이 하필 중요한 것들이다 — 지갑(`.credits.json`),
프로젝트 메타(`.meta.json`), MANUAL 대화, 고객 키, 인사 기록.
"서버가 죽었더니 잔액이 0이 됐다"는 사고는 여기서 난다.

## 어떻게 고치나

옆에 임시 파일로 다 쓰고 나서 **이름을 바꿔 덮는다.** `os.replace` 는
같은 파일 시스템 안에서 원자적이다 — 성공하면 새 파일, 실패하면 옛 파일이고
**중간 상태는 없다.**

`flush` + `fsync` 를 먼저 하는 이유: 이름만 바꾸고 내용이 아직 디스크에
안 닿았으면, 전원이 나갔을 때 이름은 새 것인데 내용은 빈 파일이 된다.

## 남은 위험

디렉터리 항목 자체의 내구성(`fsync` 를 디렉터리에도 거는 것)은 하지
않는다. 윈도우에서는 그럴 수 없고, 거기까지 필요한 수준의 내구성이라면
파일이 아니라 데이터베이스를 써야 한다 — 실제로 프로젝트 색인은 이미
SQLite 다.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

# 윈도우에서 이름 바꾸기가 막힐 때 다시 해보는 횟수와 간격(초).
REPLACE_TRIES = 20
REPLACE_WAIT = 0.01


def _replace(src: str, dst: Path) -> None:
    """`os.replace` — 윈도우에서는 잠깐 막혀도 다시 한다 (DAY 25).

    윈도우는 **다른 스레드가 읽으려고 열어 둔 파일**을 덮어쓰는 이름 바꾸기를
    `PermissionError`(WinError 5)로 거절한다. 리눅스는 그냥 된다. 태스크가
    동시에 돌고(병렬 실행) 사무실 화면이 메타를 자주 읽기 시작하자, 메타를
    읽는 순간과 쓰는 순간이 겹쳐 실행 하나가 "PermissionError" 로 멈췄다 —
    시험을 여러 번 돌리다 한 번 잡혔다. 읽는 쪽은 금방 닫으므로, 아주 잠깐
    기다렸다 다시 하면 된다. 끝내 안 되면 그대로 올린다.
    """
    for attempt in range(REPLACE_TRIES):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if sys.platform != "win32" or attempt == REPLACE_TRIES - 1:
                raise
            time.sleep(REPLACE_WAIT * (attempt + 1))


def write_text(path: Path | str, text: str, *, encoding: str = "utf-8") -> None:
    """원자적으로 쓴다. 실패하면 **옛 내용이 그대로 남는다.**"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        # 같은 폴더에 만든다 — 다른 파일 시스템으로 넘어가면 os.replace 가
        # 원자적이지 않다(복사가 된다).
        fd, tmp = tempfile.mkstemp(dir=str(path.parent),
                                   prefix=f".{path.name}.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        _replace(tmp, path)
        tmp = None
    finally:
        if tmp is not None:
            # 실패했으면 임시 파일을 남기지 않는다. 남기면 폴더가
            # 쓰레기로 찬다.
            try:
                os.unlink(tmp)
            except OSError:
                pass


def write_json(path: Path | str, data: object, *, indent: int = 2) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=indent))


# ── 프로세스를 넘는 잠금 (DAY 26) ──────────────────────────────────
#
# ## 왜 필요한가
#
# 원자적 쓰기는 "잘리지 않음"만 보장한다. **읽고-고치고-쓰기**는 여전히
# 두 프로세스 사이에서 섞인다 — A 가 읽고, B 가 읽고, A 가 쓰고, B 가
# 쓰면 A 의 갱신이 사라진다. 스레드 잠금(`threading.Lock`)은 프로세스를
# 못 넘는다. 서버를 두 대로 띄우면 승인 결정과 "쉬러 들어가는 실행"이
# 서로를 못 본 채 지나가, 결정이 기록돼 있는데 아무도 실행을 깨우지 않았다.
#
# ## 왜 운영체제 잠금인가
#
# `O_CREAT | O_EXCL` 로 잠금 파일을 만드는 방식은 잡은 프로세스가 죽으면
# 파일이 남는다 — 오래됐는지 시각으로 짐작해야 하고, 짐작은 틀린다.
# `fcntl.flock` · `msvcrt.locking` 은 프로세스가 죽으면 **운영체제가 푼다.**
#
# 잠금 파일은 따로 둔다(`.<이름>.lock`). 데이터 파일 자체를 잠그면 원자적
# 쓰기(이름 바꾸기)가 그 파일을 갈아치우는 순간 잠금이 엉뚱한 파일에 남는다.
LOCK_TIMEOUT = float(os.getenv("FILE_LOCK_TIMEOUT", "15"))

if sys.platform == "win32":                                    # pragma: no cover - 플랫폼별
    import msvcrt

    def _try_lock(fd: int) -> bool:
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


class LockTimeout(TimeoutError):
    """다른 프로세스가 너무 오래 쥐고 있다."""


class file_lock:
    """`path` 옆의 잠금 파일을 **프로세스를 넘어** 배타적으로 잡는다.

    스레드 잠금과 **함께** 쓴다 — 스레드 잠금을 먼저 잡고 이것을 잡는다.
    같은 프로세스의 스레드들은 스레드 잠금에서 줄을 서므로, 잠금 파일을
    두고 헛돌며 기다리는 것은 다른 프로세스뿐이다.
    """

    def __init__(self, path: Path | str, timeout: float | None = None):
        path = Path(path)
        self.lock = path.with_name(f".{path.name}.lock")
        self.timeout = LOCK_TIMEOUT if timeout is None else timeout
        self.fd: int | None = None

    def __enter__(self) -> "file_lock":
        self.lock.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.lock, os.O_RDWR | os.O_CREAT, 0o644)
        deadline = time.monotonic() + self.timeout
        wait = 0.001
        while not _try_lock(fd):
            if time.monotonic() > deadline:
                os.close(fd)
                raise LockTimeout(f"lock busy: {self.lock}")
            time.sleep(wait)
            wait = min(wait * 2, 0.05)
        self.fd = fd
        return self

    def __exit__(self, *exc) -> bool:
        fd, self.fd = self.fd, None
        if fd is not None:
            try:
                _unlock(fd)
            finally:
                os.close(fd)
        return False
