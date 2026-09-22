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
import io
import re
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


# ── 랜딩이 정적으로 남아 있는가 (DAY 22) ───────────────────────────
LAYOUT = ROOT / "frontend" / "src" / "app" / "layout.tsx"

# 루트 레이아웃에서 이것들을 부르면 **앱 전체**가 요청마다 서버 렌더가 된다.
DYNAMIC_APIS = ("headers(", "cookies(", "connection(")


def test_the_root_layout_stays_statically_renderable():
    """DAY 22 에 실제로 저질렀다가 되돌린 일이다.

    링크 미리보기 문구를 언어별로 내보내려고 루트 레이아웃에서
    `headers()` 로 `Accept-Language` 를 읽었다. 그러자 `next build` 의
    프리렌더가 이렇게 바뀌었다:

        before: ○ / · /pricing · /projects · /settings · /reset · /verify
        after:  ƒ 전부 (server-rendered on demand)

    랜딩은 이 제품의 **유일한 공개 페이지**이고 판매 창구다. 얻는 것은
    설명 한 줄, 잃는 것은 그 페이지를 CDN 에 얹는 것이었다.

    빌드를 돌려 확인하는 것이 제일 정확하지만 그건 1분이 든다. 여기서는
    **원인**을 막는다 — 루트 레이아웃에서 요청을 읽지 않는가.
    """
    if not LAYOUT.exists():                                    # pragma: no cover
        pytest.skip("layout.tsx 가 없다")
    src = io.open(LAYOUT, encoding="utf-8").read()
    # 주석 속 설명("headers() 로 ...")까지 잡으면 검사가 못 쓰게 된다.
    code = re.sub(r"//.*$", "", src, flags=re.M)
    code = re.sub(r"/\*(?:.|\n)*?\*/", "", code)
    used = [api for api in DYNAMIC_APIS if api in code]
    assert not used, (
        f"루트 레이아웃이 {used} 를 부릅니다. 그러면 앱 전체가 요청마다 "
        f"서버 렌더가 되고, 랜딩을 CDN 에 얹을 수 없습니다. "
        f"정말 필요하면 그 라우트에서만 부르세요.")
