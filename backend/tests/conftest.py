"""테스트가 **진짜 데이터에 쓰지 않게** 한다 (DAY 22).

## 무엇이 있었나

테스트는 `config.PROJECTS` 를 임시 폴더로 바꿔 파일은 격리했지만,
SQLite 색인의 경로는 `config.data_dir()` 에서 왔다. 그건 `DATA_DIR`
환경변수를 보고, 테스트는 그걸 건드리지 않았다.

그래서 **테스트가 만든 프로젝트 40여 개가 개발용 색인에 그대로 쌓였다.**
파일은 임시 폴더와 함께 사라지고 색인 행만 남아서, 화면의 프로젝트
목록에는 있는데 누르면 "없는 프로젝트"가 되는 항목이 줄줄이 생겼다.

색인만 더럽히는 게 아니다. `.credits.json`·`.secrets.json`·`.byok.json`·
`.staff.json` 이 전부 같은 폴더에 있으므로, 테스트가 지갑과 키 저장소도
건드릴 수 있었다.

## 그래서 전부 임시 폴더로 보낸다

한 곳에서 막는다. 개별 테스트가 따로 `DATA_DIR` 을 정하면 그 값이
이긴다 — monkeypatch 는 나중에 건 것이 이긴다.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path, monkeypatch):
    """모든 테스트의 데이터 폴더를 임시 폴더로.

    색인 연결은 스레드마다 캐시된다. 폴더를 바꾼 뒤 남아 있는 연결은
    **옛 파일**을 가리키므로 닫는다 — 안 닫으면 테스트가 여전히 개발용
    DB 에 쓴다.
    """
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_DIR", str(data))

    from app.database import index
    index.close()
    yield
    index.close()
