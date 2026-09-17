"""검증자 에이전트 — Gemini. 두 가지 일을 한다: 테스트 작성, 그리고 판정.

테스트를 검증자가 쓰는 이유가 이 시스템에서 가장 중요한 결정이다.
구현자가 테스트를 쓰면 통과시키려고 테스트를 고칠 수 있다(assert True).
그래서 tests/ 는 QA만 쓰고, DEV는 읽지도 못한다.

일부러 다른 회사 모델을 쓴다. 다만 이것이 자동으로 오류 독립성을 주지는 않는다 —
같은 인수기준과 같은 코드를 보면 같은 오해를 할 수 있다. 실제로 효과가 있는 것은
'모델이 다르다'가 아니라 '증거 채널이 분리돼 있다'는 쪽이다.
DEV의 자기보고를 판정 근거에서 제거한 것이 그 분리다.
"""
import json

import bus
import config
import secrets_broker
import usage
from schemas import Criterion, QAVerdict, Task, TestSuite

_client = None


def client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=secrets_broker.require("gemini"))
    return _client


def reset_client() -> None:
    global _client
    _client = None


def list_models() -> list[str]:
    """실제로 쓸 수 있는 모델 ID를 조회한다.

    config.QA_MODEL 의 기본값은 추측이다. 설정 화면에서 이 목록으로 고르게 한다.
    """
    out = []
    for m in client().models.list():
        name = getattr(m, "name", "") or ""
        mid = name.split("/")[-1] if "/" in name else name
        actions = getattr(m, "supported_actions", None) or []
        if mid and (not actions or "generateContent" in actions):
            out.append(mid)
    return sorted(set(out))


def _call(system: str, contents: str, schema):
    from google.genai import types
    resp = client().models.generate_content(
        model=config.QA_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.2,
        ),
    )
    um = getattr(resp, "usage_metadata", None)
    if um:
        usage.record("QA", config.QA_MODEL,
                     input_tokens=getattr(um, "prompt_token_count", 0) or 0,
                     output_tokens=(getattr(um, "candidates_token_count", 0) or 0)
                                   + (getattr(um, "thoughts_token_count", 0) or 0),
                     cached_tokens=getattr(um, "cached_content_token_count", 0) or 0)
    return _parse(resp.text, schema)


def _parse(text: str, schema):
    try:
        return schema.model_validate_json(text)
    except Exception:
        cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        return schema.model_validate_json(cleaned.strip())


def write_tests(criteria: list[Criterion], tasks: list[Task]) -> TestSuite:
    """구현 전에, 인수기준만 보고 테스트를 먼저 쓴다."""
    bus.say("QA", "구현 전에 인수기준으로 테스트를 먼저 작성합니다.")
    plan_view = [{"id": t.id, "title": t.title, "files": t.files, "covers": t.covers}
                 for t in tasks]
    suite = _call(
        config.prompt("qa_tests"),
        f"# 인수기준\n{json.dumps([c.model_dump() for c in criteria], ensure_ascii=False, indent=2)}\n\n"
        f"# 계획된 태스크 (구현될 모듈 경로 참고용)\n"
        f"{json.dumps(plan_view, ensure_ascii=False, indent=2)}\n\n"
        f"각 인수기준을 검증하는 테스트를 작성하세요.",
        TestSuite,
    )
    bus.say("QA", suite.message_to_team)
    return suite


def review(task: Task, criteria: list[Criterion], files: dict[str, str],
           report: dict) -> QAVerdict:
    bus.say("QA", f"'{task.title}' 검토 시작합니다. 파일 {len(files)}개.")

    body = "\n\n".join(f"### {p}\n```\n{c}\n```" for p, c in files.items()) or "(파일 없음)"
    contents = (
        f"# 태스크\n{task.model_dump_json(indent=2)}\n\n"
        f"# 프로젝트 인수기준\n"
        f"{json.dumps([c.model_dump() for c in criteria], ensure_ascii=False, indent=2)}\n\n"
        f"# 테스트 실행 리포트\n```json\n{json.dumps(report, ensure_ascii=False, indent=2)}\n```\n\n"
        f"# 프로젝트 전체 코드 (src/ + tests/)\n{body}\n"
    )
    verdict = _call(config.prompt("qa"), contents, QAVerdict)

    icon = "통과" if verdict.verdict == "pass" else f"반려 ({verdict.severity})"
    bus.say("QA", f"**{icon}** — {verdict.message_to_dev}", kind="verdict")
    for f in verdict.findings:
        bus.say("QA", f"`{f.file}` · {f.issue}", kind="tool")
    return verdict
