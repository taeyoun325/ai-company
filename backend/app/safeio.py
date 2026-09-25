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
