"""개발자 에이전트 — Tool Runner로 실제 파일을 쓴다.

권한이 좁다: src/ 에만 쓰고, tests/ 는 읽지도 못한다.
테스트를 볼 수 있으면 인수기준이 아니라 테스트에 맞춰 짜게 되고,
쓸 수 있으면 통과시키려고 테스트를 고친다. 둘 다 막는다.

대신 인수기준은 보여준다. 그게 계약서이기 때문이다.
"""
import json

from anthropic import beta_tool

import bus
import config
from agents import llm
from schemas import Criterion, QAVerdict, Task
from tools import fs

touched: set[str] = set()
ROLE = "DEV"


@beta_tool
def read_file(path: str) -> str:
    """src/ 안의 파일 내용을 읽는다. tests/ 는 읽을 수 없다.

    Args:
        path: 프로젝트 기준 상대경로. 예: src/app/main.py
    """
    try:
        bus.say("DEV", f"파일 읽는 중 — `{path}`", kind="tool")
        return fs.read(path, ROLE)
    except fs.Denied as e:
        return f"거부됨: {e}"


@beta_tool
def list_files() -> str:
    """src/ 에 현재 존재하는 파일 목록을 반환한다."""
    files = fs.listdir(ROLE)
    bus.say("DEV", f"파일 목록 확인 — {len(files)}개", kind="tool")
    return "\n".join(files) or "(비어 있음)"


@beta_tool
def write_file(path: str, content: str) -> str:
    """src/ 안에 파일을 쓴다. 기존 파일은 덮어쓴다.

    Args:
        path: 프로젝트 기준 상대경로. 반드시 src/ 로 시작해야 한다.
        content: 파일 전체 내용. 일부만 넣으면 나머지가 사라진다.
    """
    try:
        info = fs.write(path, content, ROLE)
    except fs.Denied as e:
        bus.say("DEV", f"쓰기 거부됨 — `{path}` ({e})", kind="error")
        return f"거부됨: {e}"
    touched.add(path)
    verb = "새로 만듦" if info["created"] else f"수정 ({info['old_lines']}→{info['new_lines']}줄)"
    bus.say("DEV", f"`{path}` {verb}", kind="tool")
    return f"ok: {path} ({info['new_lines']} lines)"


TOOLS = [read_file, list_files, write_file]


def implement(task: Task, criteria: list[Criterion],
              feedback: QAVerdict | None) -> tuple[str, list[str]]:
    """태스크 하나를 구현한다. (개발자의 마지막 발언, 건드린 파일 목록)."""
    touched.clear()

    relevant = [c for c in criteria if c.id in task.covers] or criteria
    prompt = (
        f"# 이번 태스크\n{task.model_dump_json(indent=2)}\n\n"
        f"# 이 태스크가 충족시켜야 하는 인수기준\n"
        f"{json.dumps([c.model_dump() for c in relevant], ensure_ascii=False, indent=2)}\n"
    )
    if feedback:
        bus.say("DEV", "반려 사유 반영해서 다시 작업합니다.")
        fixes = "\n".join(f"- {x}" for x in feedback.required_fixes)
        found = "\n".join(f"- {f.file}: {f.issue} ({f.why})" for f in feedback.findings)
        prompt += (f"\n# QA 반려 — 아래를 전부 해결해야 한다\n"
                   f"## 필수 수정\n{fixes}\n## 지적사항\n{found}\n")
    else:
        bus.say("DEV", f"'{task.title}' 착수합니다.")

    runner = llm.client().beta.messages.tool_runner(
        model=config.DEV_MODEL,
        max_tokens=config.DEV_MAX_TOKENS,
        system=[{"type": "text", "text": config.prompt("dev"),
                 "cache_control": {"type": "ephemeral"}}],
        thinking={"type": "adaptive"},
        output_config={"effort": "xhigh"},
        tools=TOOLS,
        messages=[{"role": "user", "content": prompt}],
    )

    messages = []
    for m in runner:
        messages.append(m)
        for block in m.content:
            if block.type == "text" and block.text.strip():
                bus.say("DEV", block.text.strip())

    llm.bill_messages("DEV", config.DEV_MODEL, messages)

    last_text = ""
    if messages:
        last_text = "".join(b.text for b in messages[-1].content if b.type == "text")
    return last_text.strip(), sorted(touched)
