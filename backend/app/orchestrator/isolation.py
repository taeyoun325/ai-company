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
    """
    if not requested():
        return cmd, False, f"{ENV_FLAG}=0 — 네트워크를 끊지 않았습니다"
    ok, why = probe()
    if not ok:
        return cmd, False, why
    return ["unshare", *UNSHARE_ARGS, *cmd], True, why


def status() -> dict:
    """화면·점검이 볼 현황."""
    ok, why = probe()
    return {"requested": requested(), "available": ok, "detail": why,
            "effective": requested() and ok}
