"""생성된 코드를 실행하는 유일한 지점. 여기가 가장 위험한 곳이다.

방어 수단과, 그것이 막지 못하는 것을 정직하게 적어둔다.

막는 것:
  - API 키 유출: 환경변수를 세탁해서 넘긴다 (KEY/TOKEN/SECRET/PASSWORD 계열 제거)
  - 자동 로딩 우회: PYTHONNOUSERSITE로 usercustomize, -p no:cacheprovider,
    고정 pytest.ini(-c)로 프로젝트 내 설정 파일 무시, PYTHONDONTWRITEBYTECODE
  - 좀비 프로세스: 프로세스 그룹/작업 단위로 트리 전체 종료
  - 무한 루프: 타임아웃

부분적으로 막는 것:
  - 네트워크 송신. **리눅스에서는** 빈 네트워크 네임스페이스로 끊는다
    (app/orchestrator/isolation.py). 다른 OS 나 네임스페이스가 막힌 커널에서는
    끊지 못하며, 그 사실이 리포트의 `network_isolated` 로 나간다.
    막았다고 믿게 만드는 것이 안 막는 것보다 나쁘기 때문이다.

막지 못하는 것 (정직하게):
  - 홈 디렉터리 읽기. 프로세스는 사용자 권한을 그대로 갖는다.
  정말로 신뢰할 수 없는 요구사항을 돌릴 거라면 컨테이너 안에서 이 앱을 통째로 실행해라.
"""
import os
import re
import subprocess
import sys

from app import config
from app import deploy
from app.orchestrator import isolation
from app import secrets_broker

TIMEOUT = int(os.getenv("TEST_TIMEOUT", "120"))

# 이 조각이 이름에 들어가면 자식 프로세스에 넘기지 않는다
SECRET_HINTS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL",
                "ANTHROPIC", "GEMINI", "GOOGLE", "OPENAI", "AWS", "AZURE")

# 오케스트레이터가 소유하는 고정 설정. 프로젝트 안의 어떤 설정 파일도 무시된다.
PYTEST_INI = """[pytest]
testpaths = tests
pythonpath = src
addopts = -q --no-header -p no:cacheprovider
"""


def _clean_env() -> dict:
    env = {}
    for k, v in os.environ.items():
        if any(h in k.upper() for h in SECRET_HINTS):
            continue
        env[k] = v
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"        # usercustomize.py 자동 import 차단
    env["PYTHONUNBUFFERED"] = "1"
    env.pop("PYTHONSTARTUP", None)
    env.pop("PYTHONPATH", None)          # pytest.ini의 pythonpath만 쓰게 한다
    return env


def _popen_kwargs() -> dict:
    """프로세스 트리를 통째로 죽일 수 있도록 그룹을 만든다."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        if sys.platform == "win32":
            # taskkill /T 가 자식까지 정리한다. proc.kill()은 직계만 죽인다.
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=15)
        else:
            os.killpg(os.getpgid(proc.pid), 9)
    except Exception:
        pass
    try:
        proc.wait(timeout=10)
    except Exception:
        pass


_SUMMARY = re.compile(r"(\d+) (passed|failed|error|errors|skipped)")


def _parse(out: str, returncode: int, timed_out: bool,
           isolated: bool = False, isolation_detail: str = "") -> dict:
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    for n, kind in _SUMMARY.findall(out):
        key = "errors" if kind.startswith("error") else kind
        counts[key] = int(n)
    failures = re.findall(r"^(?:FAILED|ERROR) (.+)$", out, re.M)
    return {
        "ok": returncode == 0 and not timed_out,
        "timed_out": timed_out,
        "returncode": returncode,
        # 이 코드가 네트워크 없이 돌았는가. 검증자와 화면이 이 값을 본다 —
        # 조용히 실패해서 "격리된 줄 알았는데 아니었다"가 되지 않게 한다.
        "network_isolated": isolated,
        "isolation_detail": isolation_detail,
        **counts,
        "failed_tests": failures[:40],
        # 앞뒤를 모두 남긴다. 뒤에서만 자르면 실패 원인이 통째로 사라진다.
        # 만에 하나 출력에 키가 섞이면 가린다
        "output": secrets_broker.scrub(_clip(out)),
    }


def _clip(s: str, head: int = 2500, tail: int = 2500) -> str:
    if len(s) <= head + tail:
        return s
    return f"{s[:head]}\n\n... (중략 {len(s) - head - tail}자) ...\n\n{s[-tail:]}"


def blocked(reason: str) -> dict:  # noqa: D401
    """실행하지 않았다는 사실을 **실패로** 돌려준다.

    통과로 돌려주면 검증자가 "테스트 통과"를 근거로 승인한다. 돌리지
    않은 테스트는 통과한 테스트가 아니다.
    """
    return {"ok": False, "skipped_run": True, "timed_out": False,
            "returncode": -1, "passed": 0, "failed": 0, "errors": 0,
            "skipped": 0, "failed_tests": [], "blocked": True,
            "network_isolated": False, "isolation_detail": "실행하지 않았습니다",
            "output": reason}


def run(project_dir) -> dict:
    """프로젝트의 tests/ 를 실행하고 구조화된 리포트를 돌려준다.

    **여기가 이 프로그램에서 가장 위험한 지점이다.** 모델이 쓴 코드를
    실제로 실행한다. 로컬 도구였을 때는 "사용자가 자기 컴퓨터에서 자기
    도구를 돌린다"였지만, SaaS 에서는 "요구사항 한 줄로 우리 서버에서
    임의 코드 실행"이 된다. 그래서 배포 자세가 먼저 판단한다(app/deploy.py).
    """
    if (reason := deploy.allow_code_execution()) is not None:
        return blocked(reason)

    tests = project_dir / "tests"
    if not any(tests.glob("test_*.py")):
        return blocked("(테스트 파일 없음 — 실행 생략)") | {"blocked": False}

    ini = project_dir / "pytest.ini"      # 오케스트레이터가 매번 덮어쓴다
    ini.write_text(PYTEST_INI, encoding="utf-8")

    cmd, isolated, why = isolation.wrap(
        [sys.executable, "-I", "-m", "pytest", "-c", str(ini),
         "--rootdir", str(project_dir)])
    proc = subprocess.Popen(
        cmd,
        cwd=project_dir, env=_clean_env(), text=True, encoding="utf-8",
        errors="replace", stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        **_popen_kwargs(),
    )
    timed_out = False
    try:
        out, _ = proc.communicate(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(proc)
        out, _ = proc.communicate()
        out = (out or "") + f"\n\n[타임아웃 {TIMEOUT}초 — 프로세스 트리 강제 종료]"

    return _parse(out or "", proc.returncode or 0, timed_out, isolated, why)


ENTRY_CANDIDATES = ("main.py", "app.py", "__main__.py", "run.py", "cli.py")


def find_entry(project_dir) -> str | None:
    """실행해볼 만한 파이썬 진입점을 고른다."""
    src = project_dir / "src"
    if not src.exists():
        return None
    for name in ENTRY_CANDIDATES:
        if (src / name).exists():
            return f"src/{name}"
    pys = [f for f in sorted(src.glob("*.py")) if not f.name.startswith("_")]
    return f"src/{pys[0].name}" if len(pys) == 1 else None


def find_html(project_dir) -> str | None:
    src = project_dir / "src"
    if not src.exists():
        return None
    for name in ("index.html", "main.html"):
        if (src / name).exists():
            return f"src/{name}"
    htmls = sorted(src.rglob("*.html"))
    if htmls:
        return "src/" + str(htmls[0].relative_to(src)).replace("\\", "/")
    return None


def run_entry(project_dir, entry: str, timeout: int | None = None) -> dict:
    """진입점을 한 번 실행하고 출력을 돌려준다.

    pytest와 동일한 격리를 쓴다 — 환경 세탁, 격리 모드, 프로세스 트리 종료.
    stdin은 막는다. 입력을 기다리는 프로그램이 타임아웃까지 매달리지 않게.
    """
    limit = timeout or min(TIMEOUT, 30)
    cmd, isolated, why = isolation.wrap(
        [sys.executable, "-I", entry.replace("/", os.sep)])
    proc = subprocess.Popen(
        cmd,
        cwd=project_dir, env=_clean_env(), text=True, encoding="utf-8",
        errors="replace", stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        **_popen_kwargs(),
    )
    timed_out = False
    try:
        out, _ = proc.communicate(timeout=limit)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(proc)
        out, _ = proc.communicate()
        out = (out or "") + f"\n\n[타임아웃 {limit}초 — 프로세스 트리 강제 종료]"
    return {
        "entry": entry,
        "network_isolated": isolated,
        "isolation_detail": why,
        "ok": proc.returncode == 0 and not timed_out,
        "timed_out": timed_out,
        "returncode": proc.returncode or 0,
        "output": secrets_broker.scrub(_clip(out or "", 1500, 1500)) or "(출력 없음)",
    }


def summary_line(r: dict) -> str:
    """테스트 결과 한 줄.

    이 문장이 검증자의 판정 근거이자 화면의 점수다. 번역되지 않으면
    영어로 쓰는 사람은 "무엇이 통과했는지"를 읽을 수 없다.
    """
    from app import lang
    if r.get("blocked"):
        return lang.t("test.blocked")
    if r.get("skipped_run"):
        return lang.t("test.none")
    if r["timed_out"]:
        return lang.t("test.timeout", n=TIMEOUT)
    bad = r["failed"] + r["errors"]
    return lang.t("test.counts", passed=r["passed"], failed=bad)
