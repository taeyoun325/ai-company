"""남의 글을 모델에게 보여줄 때 쓰는 울타리 (DAY 22).

## 왜 한 곳에 두나

프롬프트에 **우리가 쓰지 않은 글**이 들어가는 자리는 둘이다:

  1. 앞 직원이 만든 산출물 (`app/orchestrator/prompts.py`)
  2. 의뢰인이 올린 첨부 자료 (`app/attachments.py`)

둘 다 백틱 세 개로 감싸고 있었고, 둘 다 같은 구멍이 있었다 — **내용 안에
백틱 세 개가 있으면 거기서 울타리가 닫힌다.** 그 뒤의 글은 프롬프트의
평문이 되고, 하필 우리 프롬프트는 `# 할 일` 같은 절로 지시를 준다. 즉
남의 글이 **우리 프롬프트와 같은 모양의 지시**를 띨 수 있었다.

한 곳에서 고치지 않으면 다음에 또 한 곳만 고친다. 그래서 여기 둔다.

## 무엇을 막고 무엇을 못 막나

막는 것: 남의 글이 울타리를 **빠져나오는 것**. 마크다운 규칙상 더 짧은
백틱 묶음으로는 더 긴 울타리를 닫을 수 없다.

못 막는 것: 모델이 울타리 **안의 글을 읽고 설득되는 것**. 그건 이 자리의
문제가 아니다 — 진짜 방어는 권한 쪽이고, 설득당한 직원도 자기 구역 밖에는
못 쓴다(`app/tools/project_fs.py`).
"""
from __future__ import annotations

import re

MIN_FENCE = 3


def fence(text: str) -> str:
    """이 내용이 **끝낼 수 없는** 울타리 문자열."""
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    return "`" * max(MIN_FENCE, longest + 1)


def wrap(text: str) -> str:
    """내용을 울타리로 감싼다."""
    f = fence(text)
    return f"{f}\n{text}\n{f}"
