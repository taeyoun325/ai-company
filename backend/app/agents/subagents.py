"""보조 에이전트 — 메인이 필요하다고 판단할 때만 호출된다.

여기가 "Claude Code인데 에이전트가 추가된" 지점이다.
메인은 혼자서도 다 할 수 있고, 이들은 도구 하나(`call_agent`)로 불린다.

## 역할

- `planner`  (Claude) — 큰 작업을 쪼갠다. 파일을 읽을 수 있고 쓰지는 못한다.
- `reviewer` (Gemini) — **다른 회사 모델로** 교차검토. 읽기만 한다.
- `tester`   (Claude) — 테스트를 짜고 돌린다. 쓰기·실행 가능.

## reviewer 를 Gemini로 두는 이유

이전 설계에서 그대로 살아남은 판단이다: 같은 모델끼리 검토하면 학습 분포가 같아
같은 유형의 실수를 함께 놓친다. 다만 이제 고정 파이프라인이 아니라
**메인의 판단이나 사용자의 요청**으로 호출된다.

한계도 그대로다 — 모델이 다르다는 사실만으로 오류가 독립이 되지는 않는다.
같은 코드와 같은 기준을 보면 같은 오해를 할 수 있다.
실제로 값을 만드는 건 '증거 채널이 분리된다'는 쪽이다.
"""
import json

from app import bus
from app import config
from app import usage

MAX_TOKENS = 12000

ROLES = {
    "planner": {
        "label": "기획자",
        "provider": "claude",
        "writes": False,
        "desc": "큰 작업을 실행 가능한 단계로 쪼갠다",
        "system": (
            "당신은 기획자입니다. 코드를 쓰지 않고, 무엇을 어떤 순서로 해야 하는지만 정합니다.\n"
            "- 필요한 파일을 먼저 읽어 현재 상태를 파악하세요.\n"
            "- 단계는 3~7개. 각 단계는 파일 1~3개 규모로 쪼갭니다.\n"
            "- 각 단계에 '무엇이 되면 끝인지'를 기계가 판정 가능한 문장으로 적으세요.\n"
            "- 모르는 것은 추측하지 말고 '확인 필요'로 남기세요.\n"
            "답변은 번호 매긴 계획 하나로 끝내세요."),
    },
    "reviewer": {
        "label": "검증자",
        "provider": "gemini",
        "writes": False,
        "desc": "다른 회사 모델로 교차검토한다",
        "system": (
            "당신은 검증자입니다. 구현자와 다른 회사의 모델이며, 그게 당신이 여기 있는 이유입니다.\n"
            "같은 모델은 같은 실수를 함께 놓칩니다.\n\n"
            "규칙:\n"
            "- 근거는 코드입니다. 파일과 줄을 지목하세요.\n"
            "- 실제로 터질 결함만 지적합니다. 스타일 취향은 지적 사항이 아닙니다.\n"
            "- **지적할 것이 없으면 억지로 만들지 말고 '문제 없음'이라고 하세요.**\n"
            "  근거 없는 지적은 팀을 무한 루프에 빠뜨립니다.\n"
            "- 각 지적에 '어떤 입력에서 어떻게 잘못되는가'를 붙이세요. 못 붙이면 그건 지적거리가 아닙니다.\n"
            "답변은 짧게. 심각한 것부터."),
    },
    "tester": {
        "label": "테스터",
        "provider": "claude",
        "writes": True,
        "desc": "테스트를 작성하고 실행한다",
        "system": (
            "당신은 테스터입니다. 테스트를 쓰고 실제로 돌려서 결과를 보고합니다.\n"
            "- 기존 테스트 관례(프레임워크·폴더·이름)를 먼저 확인하고 따르세요.\n"
            "- 정상 경로 하나, 경계·예외 경로 하나 이상.\n"
            "- `assert result is not None` 처럼 아무것도 검증하지 않는 테스트는 쓰지 마세요.\n"
            "- 테스트를 쓴 뒤 반드시 실행해서 통과·실패를 확인하고, 그 결과를 보고하세요.\n"
            "- 구현을 고쳐 테스트를 통과시키지 마세요. 그건 메인 에이전트의 일입니다."),
    },
}


def _claude(role: str, task: str, context: str) -> str:
    from app.providers import anthropic_client as llm
    from app.tools import agent_tools

    spec = ROLES[role]
    tools = agent_tools.ALL_TOOLS if spec["writes"] else agent_tools.READ_TOOLS

    runner = llm.client().beta.messages.tool_runner(
        model=config.PM_MODEL,
        max_tokens=MAX_TOKENS,
        system=[{"type": "text", "text": spec["system"],
                 "cache_control": {"type": "ephemeral"}}],
        thinking={"type": "adaptive"},
        tools=tools,
        messages=[{"role": "user", "content": f"{context}\n\n# 요청\n{task}"}],
    )
    messages = []
    for m in runner:
        messages.append(m)
        for b in m.content:
            if b.type == "text" and b.text.strip():
                bus.say(role.upper(), b.text.strip())
    llm.bill_messages(role.upper(), config.PM_MODEL, messages)
    if not messages:
        return "(응답 없음)"
    return "".join(b.text for b in messages[-1].content if b.type == "text").strip()


def _gemini(role: str, task: str, context: str) -> str:
    from google.genai import types
    from app.providers import gemini_client

    spec = ROLES[role]
    resp = gemini_client.client().models.generate_content(
        model=config.QA_MODEL,
        contents=f"{context}\n\n# 요청\n{task}",
        config=types.GenerateContentConfig(
            system_instruction=spec["system"], temperature=0.2),
    )
    um = getattr(resp, "usage_metadata", None)
    if um:
        usage.record(role.upper(), config.QA_MODEL,
                     input_tokens=getattr(um, "prompt_token_count", 0) or 0,
                     output_tokens=(getattr(um, "candidates_token_count", 0) or 0)
                                   + (getattr(um, "thoughts_token_count", 0) or 0))
    text = (resp.text or "").strip()
    if text:
        bus.say(role.upper(), text)
    return text or "(응답 없음)"


def call(role: str, task: str, files: list[str] | None = None) -> str:
    """보조 에이전트를 부른다. 결과 텍스트를 메인에게 돌려준다."""
    if role not in ROLES:
        return f"알 수 없는 역할: {role}. 가능한 값: {', '.join(ROLES)}"

    spec = ROLES[role]
    bus.emit("subagent", role=role, label=spec["label"], state="start", task=task[:160])
    bus.say(role.upper(), f"호출됨 — {task[:120]}", kind="verdict")

    context = ""
    if files:
        from app import workspace
        parts = []
        for f in files[:12]:
            try:
                p = workspace.resolve(f)
                if p.is_file():
                    parts.append(f"### {f}\n```\n"
                                 f"{p.read_text(encoding='utf-8', errors='replace')[:30000]}\n```")
            except workspace.Denied:
                continue
        if parts:
            context = "# 참고 파일\n" + "\n\n".join(parts)

    try:
        if spec["provider"] == "gemini":
            out = _gemini(role, task, context)
        else:
            out = _claude(role, task, context)
    except Exception as e:
        out = f"{spec['label']} 호출 실패: {type(e).__name__}: {e}"
        bus.say(role.upper(), out, kind="error")
    finally:
        bus.emit("subagent", role=role, label=spec["label"], state="end")

    return out


def roster() -> list[dict]:
    return [{"id": k, "label": v["label"], "provider": v["provider"],
             "desc": v["desc"], "writes": v["writes"]} for k, v in ROLES.items()]
