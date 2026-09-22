"""소스가 저장소에 들어 있는가 (DAY 22).

## 왜 이 검사가 있나

`.gitignore` 첫 줄이 `projects/` 였다. 의도는 실행할 때마다 쌓이는 산출물
폴더(뿌리의 `projects/`)를 막는 것이었는데, 슬래시가 없으면 git 은 그
이름의 폴더를 **전부** 막는다. 그래서 `frontend/src/app/projects/` 의 화면
소스 두 개가 **한 번도 커밋되지 않았다.** 이 컴퓨터에서는 잘 돌아간다 —
파일이 여기 있으니까. 새로 받아 올린 사람은 그 화면 없이 빌드한다.

이런 종류의 고장은 "여기서는 되는데"로만 나타나서, 배포하는 날에야 보인다.
그래서 기계가 본다: **소스 폴더의 파일이 하나라도 무시되면 실패한다.**
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# 사람이 쓴 소스만 본다. 생성물(.next, node_modules)은 무시되는 것이 맞다.
SOURCE_DIRS = ("backend/app", "backend/tests", "frontend/src", "docs")
SOURCE_SUFFIX = {".py", ".ts", ".tsx", ".css", ".md", ".json", ".mjs"}


def _sources() -> list[Path]:
    out = []
    for rel in SOURCE_DIRS:
        base = ROOT / rel
        if not base.exists():
            continue
        for f in base.rglob("*"):
            if f.is_file() and f.suffix in SOURCE_SUFFIX:
                if "__pycache__" in f.parts or "node_modules" in f.parts:
                    continue
                out.append(f)
    return out


@pytest.mark.skipif(shutil.which("git") is None, reason="git 이 없다")
def test_no_source_file_is_ignored_by_git():
    files = _sources()
    assert files, "소스를 하나도 못 찾았습니다 — 검사가 아무것도 안 보고 있습니다"

    rel = [str(f.relative_to(ROOT)).replace("\\", "/") for f in files]
    # check-ignore 는 무시되는 경로만 돌려주고, 하나도 없으면 1 로 끝난다.
    # 바이트로 넘긴다. 텍스트 모드로 주면 윈도우에서 파이썬이 줄바꿈을
    # CRLF 로 바꿔 보내고, 경로 끝에 붙은 CR 이 결과를 흔든다.
    r = subprocess.run(["git", "check-ignore", "--stdin"],
                       cwd=ROOT, input="\n".join(rel).encode(),
                       capture_output=True, timeout=60)
    ignored = [ln for ln in r.stdout.decode("utf-8", "replace").splitlines()
                if ln.strip()]
    assert not ignored, (
        "이 소스 파일들이 .gitignore 에 걸려 저장소에 들어가지 않습니다. "
        "런타임 데이터용 패턴에 앞 슬래시가 빠졌는지 보세요 "
        "(`projects/` → `/projects/`):\n" + "\n".join(ignored))


@pytest.mark.skipif(shutil.which("git") is None, reason="git 이 없다")
def test_runtime_data_stays_ignored():
    """반대쪽도 본다. 앞 슬래시를 붙이다가 실수로 산출물을 커밋하게 되면,
    저장소가 남의 프로젝트 파일로 부풀고 그 안에 비밀이 섞일 수 있다."""
    r = subprocess.run(["git", "check-ignore", "--stdin"],
                       cwd=ROOT, input=b"projects\nlogs\nattachments\n.venv",
                       capture_output=True, timeout=60)
    got = set(r.stdout.decode("utf-8", "replace").split())
    for name in ("projects", "logs", ".venv"):
        assert name in got, f"{name} 이(가) 더 이상 무시되지 않습니다"
