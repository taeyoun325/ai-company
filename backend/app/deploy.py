"""배포 자세 (deployment posture) — 무엇을 허용할지 한 곳에서 정한다.

## 왜 이 파일이 생겼나

이 저장소에는 원래 **로컬 개발도구**가 있었다. 사용자의 컴퓨터에서,
사용자의 권한으로, 사용자의 폴더를 다루는 프로그램이었다. 그 전제에서는
`run_command` 로 임의 명령을 돌리고 화면을 캡처하는 것이 위험하긴 해도
**말이 됐다** — 사용자가 자기 컴퓨터에 자기 도구를 쓴 것이니까.

AI COMPANY 는 SaaS 다. 같은 코드가 **서버**에서 돌면 뜻이 완전히 달라진다:

  - `run_command` → 남의 서버에서 임의 명령 실행
  - `/api/workspace` → 서버의 아무 폴더나 열기
  - 화면 캡처 → 서버 화면(= 다른 사용자의 것일 수 있다)을 밖으로 내보내기
  - 생성된 코드의 pytest 실행 → **요구사항 한 줄로 RCE**

승인 게이트(`approvals.py`)는 "사용자가 자기 컴퓨터에서 승인한다"를
전제로 만들어졌다. SaaS 에서 그 승인은 남의 서버에 대한 승인이므로
아무것도 보장하지 않는다.

## 그래서 모드를 명시한다

`DEPLOY_MODE` 한 줄이 이 프로그램이 어디서 도는지를 정한다.

| 값 | 뜻 | 로컬 도구 기능 | 생성된 코드 실행 |
|---|---|---|---|
| `local` (기본) | 내 컴퓨터에서 내가 쓴다 | 허용 | 허용 |
| `saas` | 서버에서 남을 위해 돈다 | **차단** | 샌드박스일 때만 |

기본을 `local` 로 둔 이유: 지금 이 저장소를 돌리는 사람은 개발자이고,
기본값이 막혀 있으면 "왜 안 되지"로 시간을 쓴다. 대신 **배포용
`docker-compose.yml` 과 `.env.example` 에는 `saas` 를 적어둔다.**

## 샌드박스는 우리가 증명하지 않는다

`SANDBOXED=1` 은 "이 프로세스는 격리된 컨테이너 안에 있다"는 **운영자의
선언**이다. 우리가 확인할 방법은 없다. 그래서 이 값은 자물쇠가 아니라
서명이다 — 거짓으로 적으면 그 사람의 책임이 된다. 우리가 할 수 있는 건
거짓으로 적지 않으면 기본적으로 안전한 쪽에 서는 것뿐이다.
"""
from __future__ import annotations

import os

MODES = ("local", "saas")


def mode() -> str:
    m = os.getenv("DEPLOY_MODE", "local").strip().lower()
    return m if m in MODES else "local"


def is_saas() -> bool:
    return mode() == "saas"


def sandboxed() -> bool:
    """운영자가 '격리되어 있다'고 선언했는가. 우리가 확인할 수는 없다."""
    return os.getenv("SANDBOXED", "").strip().lower() in ("1", "true", "yes")


# ── 기능별 판단 ─────────────────────────────────────────────────────
def allow_local_tools() -> str | None:
    """사용자의 로컬 환경을 건드리는 기능(작업 폴더 열기·파일 편집·
    화면 캡처·임의 명령)을 허용하는가.

    막는 이유를 문자열로 돌려준다 — None 이면 허용. 화면과 API 가 같은
    문장을 쓰게 하려고 이유까지 여기서 만든다.
    """
    if is_saas():
        return ("서버 배포(DEPLOY_MODE=saas)에서는 로컬 환경에 접근하는 기능을 "
                "쓸 수 없습니다. 이 기능들은 '내 컴퓨터에서 내가 쓴다'를 전제로 "
                "만들어졌고, 서버에서는 같은 동작이 남의 서버를 건드리는 일이 "
                "됩니다.")
    return None


def allow_code_execution() -> str | None:
    """생성된 코드를 실행해도 되는가 (테스트 러너).

    SaaS 에서 이걸 열어두면 요구사항 한 줄로 임의 코드 실행이 된다.
    격리 선언(`SANDBOXED=1`)이 있을 때만 허용한다.
    """
    if is_saas() and not sandboxed():
        return ("서버 배포에서 생성된 코드를 실행하려면 격리된 컨테이너 안이어야 "
                "합니다. 컨테이너에서 실행 중이라면 SANDBOXED=1 을 설정하세요. "
                "설정하지 않으면 테스트는 실행되지 않고, 검증자는 '테스트 없음'을 "
                "근거로 판정합니다.")
    return None


def status() -> dict:
    """화면이 지금 어떤 자세인지 보여줄 수 있어야 한다.

    막혀 있다는 사실을 감추면, 사용자는 기능이 고장 났다고 생각한다.
    """
    local_block = allow_local_tools()
    exec_block = allow_code_execution()
    return {
        "mode": mode(),
        "sandboxed": sandboxed(),
        "local_tools": local_block is None,
        "local_tools_reason": local_block,
        "code_execution": exec_block is None,
        "code_execution_reason": exec_block,
    }
