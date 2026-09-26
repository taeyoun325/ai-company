"""생성된 코드의 네트워크를 끊는다 (DAY 16).

## 지금까지 "막지 못한다"고 적어둔 것

`docs/security.md` §3 첫 항목은 이랬다:

> 생성된 코드가 로컬 파일을 읽어 **외부로 보내는 것을 막지 못한다.**
> subprocess 로는 불가능하다.

절반만 맞는 말이었다. **리눅스에서는 가능하다** — 사용자 네임스페이스와
네트워크 네임스페이스를 쓰면 권한 없이도 자식 프로세스에게 "루프백만
있는 빈 네트워크"를 줄 수 있다. `unshare --net --map-root-user` 가 그것이다.

## 왜 완전한 해결은 아닌가

- **리눅스에서만 된다.** 개발 머신(Windows·macOS)에서는 안 된다
- 커널이 비특권 사용자 네임스페이스를 막아둔 배포판도 있다
- 되더라도 디스크·메모리·CPU 는 여전히 제한되지 않는다

그래서 이것은 컨테이너 격리를 **대체하지 않는다.** 컨테이너 안에서
한 겹 더 좁히는 것이고, 컨테이너가 없는 환경에서는 한 겹이라도 얻는 것이다.

## 가장 중요한 부분: 되는지 안 되는지를 **보고한다**

막았다고 믿게 만드는 것이 안 막는 것보다 나쁘다. 그래서 테스트 리포트에
`network_isolated` 를 실어 보내고, 검증자와 화면이 그 사실을 본다.
조용히 실패해서 "격리된 줄 알았는데 아니었다"가 되지 않게 한다.
"""
from __future__ import annotations

import functools
import os
import shutil
import subprocess
import sys

# 이 조합이 하는 일:
#   --net              새 (빈) 네트워크 네임스페이스. 루프백만 남는다
#   --map-root-user    사용자 네임스페이스. 권한 없이도 위를 만들 수 있게 한다
#   --                 이후는 실행할 명령
UNSHARE_ARGS = ("--net", "--map-root-user", "--")

ENV_FLAG = "RUNNER_ISOLATE_NETWORK"


def requested() -> bool:
    """네트워크를 끊으라고 설정돼 있는가.

    기본값은 **켜짐**이다. 안전한 쪽이 기본이어야 하고, 안 되는 환경에서는
    어차피 자동으로 꺼지면서 그 사실이 보고된다.
    """
    return os.getenv(ENV_FLAG, "1").strip().lower() not in ("0", "false", "no")


@functools.lru_cache(maxsize=1)
def probe() -> tuple[bool, str]:
    """이 환경에서 실제로 되는가. (가능한가, 이유)

    `unshare` 가 존재하는지만 보지 않고 **실제로 한 번 돌려본다.** 커널이
    비특권 사용자 네임스페이스를 막아둔 배포판에서는 명령이 있어도 실패한다.
    존재 여부만 보고 "격리됐다"고 보고하면 그게 바로 거짓 보고다.

    결과를 캐시하는 이유: 테스트를 돌릴 때마다 프로세스를 하나 더 띄우면
    한 실행에 수십 번 반복된다.
    """
    if sys.platform != "linux":
        return False, f"리눅스가 아닙니다 ({sys.platform}) — 네임스페이스를 쓸 수 없습니다"
    if shutil.which("unshare") is None:
        return False, "unshare 명령이 없습니다 (util-linux 설치 필요)"
    try:
        r = subprocess.run(
            ["unshare", *UNSHARE_ARGS, "true"],
            capture_output=True, timeout=10, text=True)
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"unshare 실행 실패: {type(e).__name__}: {e}"
    if r.returncode != 0:
        detail = (r.stderr or r.stdout or "").strip().splitlines()
        why = detail[-1] if detail else f"종료 코드 {r.returncode}"
        return False, f"커널이 거부했습니다: {why}"
    return True, "네트워크 네임스페이스 격리"


def wrap(cmd: list[str]) -> tuple[list[str], bool, str]:
    """명령을 격리해서 감싼다. (명령, 격리됐는가, 설명)

    감싸지 못했으면 **원래 명령을 그대로** 돌려준다. 격리가 안 된다고
    테스트를 못 돌리게 하면, 개발 머신에서는 아무것도 검증할 수 없다.
    대신 두 번째 값이 False 로 나가고 그것이 리포트에 실린다.

    네트워크만 끊는다. 파일 시스템까지 가두려면 `sandbox()` 를 쓴다.
    """
    if not requested():
        return cmd, False, f"{ENV_FLAG}=0 — 네트워크를 끊지 않았습니다"
    ok, why = probe()
    if not ok:
        return cmd, False, why
    return ["unshare", *UNSHARE_ARGS, *cmd], True, why


# ── 파일 시스템까지 가두기 (DAY 27) ────────────────────────────────
#
# 네트워크만 끊어서는 부족하다는 것을 Cloud Run 에서 실제로 쟀다. 생성된
# 코드는 **서버와 같은 사용자**로 돈다. 그래서 네트워크가 끊겨 있어도:
#
#   - 계정 DB 에 세션 행을 써 넣어 **아무 계정이나 가져갈** 수 있고
#   - 지갑 잔액을 고치고, 다른 테넌트의 프로젝트를 읽고 고치고
#   - `/proc/<서버 pid>/environ` 으로 서버의 비밀 환경변수를 읽는다
#
# 빼낼 길도 있다 — 테스트 출력과 산출물이 **요청한 사람에게 돌아간다.**
#
# bubblewrap 으로 새 루트를 짠다. 보이는 것은 읽기 전용 시스템(/usr·/etc)과
# **자기 프로젝트 폴더 하나**뿐이다. 서버의 데이터·다른 프로젝트·버킷
# 마운트·홈은 아예 없다. PID 네임스페이스가 따로라 서버 프로세스도 안 보인다.
# 커널 기능은 unshare 와 같다(비특권 사용자 네임스페이스).
#
# 자원: 메모리·파일 크기·프로세스 수·CPU 시간을 prlimit 로 묶는다. 한 사용자의
# 코드가 인스턴스 메모리를 다 먹으면 **모든 사용자의 서버가** 같이 죽는다.
SANDBOX_MEM_MB = int(os.getenv("SANDBOX_MEM_MB", "1024"))
SANDBOX_FSIZE_MB = int(os.getenv("SANDBOX_FSIZE_MB", "64"))
SANDBOX_NPROC = int(os.getenv("SANDBOX_NPROC", "256"))

# 새 루트에 읽기 전용으로 들이는 것. /app·/home·/mnt·/tmp 는 **넣지 않는다.**
_SYSTEM_DIRS = ("/usr", "/etc")
_MAYBE_LINKS = ("/bin", "/sbin", "/lib", "/lib64")


def _root_args() -> list[str]:
    args: list[str] = []
    for d in _SYSTEM_DIRS:
        args += ["--ro-bind", d, d]
    for d in _MAYBE_LINKS:
        if os.path.islink(d):           # merged-/usr: /bin → usr/bin
            args += ["--symlink", os.readlink(d), d]
        elif os.path.isdir(d):
            args += ["--ro-bind", d, d]
    return args


def _bwrap_args(workdir: str) -> list[str]:
    return ["bwrap", "--unshare-all", "--die-with-parent", "--new-session",
            *_root_args(),
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--bind", workdir, workdir, "--chdir", workdir,
            "--setenv", "HOME", "/tmp", "--"]


def _limit_args(cpu_seconds: int) -> list[str]:
    if shutil.which("prlimit") is None:
        return []
    return ["prlimit", f"--as={SANDBOX_MEM_MB * 1024 * 1024}",
            f"--fsize={SANDBOX_FSIZE_MB * 1024 * 1024}",
            f"--nproc={SANDBOX_NPROC}", f"--cpu={max(1, cpu_seconds)}",
            "--nofile=512", "--"]


@functools.lru_cache(maxsize=1)
def probe_sandbox() -> tuple[bool, str]:
    """bubblewrap 이 **여기서 실제로** 새 루트를 짤 수 있는가."""
    if sys.platform != "linux":
        return False, f"리눅스가 아닙니다 ({sys.platform}) — 파일 시스템 격리를 쓸 수 없습니다"
    if shutil.which("bwrap") is None:
        return False, "bwrap 명령이 없습니다 (bubblewrap 설치 필요)"
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        try:
            r = subprocess.run([*_bwrap_args(d), "/bin/sh", "-c",
                                "test ! -e /app && echo ok > probe"],
                               capture_output=True, timeout=10, text=True)
        except (OSError, subprocess.SubprocessError) as e:
            return False, f"bwrap 실행 실패: {type(e).__name__}: {e}"
        written = os.path.exists(os.path.join(d, "probe"))
    if r.returncode != 0 or not written:
        detail = (r.stderr or r.stdout or "").strip().splitlines()
        return False, f"bwrap 이 거부됐습니다: {detail[-1] if detail else r.returncode}"
    return True, "bubblewrap — 네트워크·파일 시스템·프로세스 격리"


def sandbox_available() -> bool:
    return requested() and probe_sandbox()[0]


def sandbox(cmd: list[str], workdir, cpu_seconds: int = 120) -> tuple[list[str], dict]:
    """명령을 `workdir` 하나만 보이는 샌드박스에 넣는다. (명령, 리포트)

    bubblewrap 이 안 되면 네트워크만 끊는 `wrap()` 으로 내려간다 — 로컬
    개발 머신의 옛 동작 그대로다. **서버 배포(saas)에서는 그 내려감이
    일어나지 않는다**: `app/deploy.py` 가 bubblewrap 없이는 실행을 막는다.
    """
    if requested():
        ok, why = probe_sandbox()
        if ok:
            wd = os.path.abspath(str(workdir))
            return ([*_limit_args(cpu_seconds), *_bwrap_args(wd), *cmd],
                    {"network": True, "filesystem": True, "detail": why})
    out, net, why = wrap(cmd)
    return out, {"network": net, "filesystem": False, "detail": why}


def status() -> dict:
    """화면·점검이 볼 현황."""
    ok, why = probe()
    fs_ok, fs_why = probe_sandbox()
    return {"requested": requested(), "available": ok, "detail": why,
            "effective": requested() and ok,
            "filesystem": requested() and fs_ok, "filesystem_detail": fs_why}
