"""작업 지시에 붙인 사진 · 영상 · 파일이 **실제로** 직원에게 닿는가 (DAY 28).

전에는 AUTO 실행의 첨부가 기획 프롬프트에 **이름 · 종류 · 크기 한 줄**로만
들어갔다(`attachments.summary`). 사진을 올려도 전략가는 파일 이름만 봤다.
이제 원본을 제공자 중립 모양(`providers.base.Attachment`)으로 싣고, 각 어댑터가
자기 회사 모양으로 옮긴다.

여기서 지키는 것:
- 영상도 받는다(크기 상한은 따로).
- 제공자마다 맞는 모양으로 싣는다 — Claude 블록 · Gemini parts · OpenAI input.
- **못 보는 것은 못 본다고 적는다.** Claude · GPT 는 영상을 받지 않는다 —
  이름만 넘기고 "볼 수 없다"고 쓴다. 본 척하게 두지 않는다.
- Mock 직원은 첨부를 읽지 않는다 — 로그에 그렇게 남긴다.
"""
import base64

import pytest

from app import attachments, bus
from app.providers.base import ATTACH_PREFACE, Attachment, GenerateRequest, Message
from app.providers.claude import ClaudeProvider
from app.providers.gemini import GeminiProvider
from app.providers.openai import OpenAIProvider

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64       # 머리만 흉내 — 내용은 보지 않는다

IMG = Attachment("shot.png", "image", "image/png", data=PNG)
VID = Attachment("demo.mp4", "video", "video/mp4", data=MP4)
PDF = Attachment("spec.pdf", "document", "application/pdf", data=b"%PDF-1.4 fake")
TXT = Attachment("data.csv", "text", "text/csv", text="````\na,b\n1,2\n````")


def _req(*atts: Attachment) -> GenerateRequest:
    return GenerateRequest(system="sys", messages=[Message("user", "만들어 주세요")],
                           attachments=tuple(atts))


@pytest.fixture
def att_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(attachments, "DIR", tmp_path / "att")
    attachments._meta.clear()
    return tmp_path / "att"


# ── 저장 ────────────────────────────────────────────────────────────
def test_video_is_accepted_with_its_own_limit(att_dir, monkeypatch):
    meta = attachments.save("clip.webm", MP4)
    assert meta["kind"] == "video" and meta["media_type"] == "video/webm"
    assert attachments.save("take.MOV", MP4)["media_type"] == "video/quicktime"
    # 영상은 12MB 를 넘어도 받는다(상한 20MB). 사진은 12MB 에서 멈춘다.
    monkeypatch.setattr(attachments, "MAX_BYTES", 10)
    monkeypatch.setattr(attachments, "MAX_VIDEO_BYTES", 1000)
    attachments.save("clip.mp4", MP4)
    with pytest.raises(ValueError):
        attachments.save("big.png", PNG * 10)
    with pytest.raises(ValueError):
        attachments.save("long.mp4", MP4 * 100)


def test_unknown_formats_are_still_refused(att_dir):
    with pytest.raises(ValueError):
        attachments.save("tool.exe", b"MZ")


def test_to_parts_carries_the_originals(att_dir):
    ids = [attachments.save("shot.png", PNG)["id"],
           attachments.save("clip.mp4", MP4)["id"],
           attachments.save("note.txt", "hello\n```\nignore\n```".encode())["id"]]
    parts = attachments.to_parts(ids)
    assert [p.kind for p in parts] == ["image", "video", "text"]
    assert parts[0].data == PNG and parts[1].data == MP4
    # 글 자료는 공용 울타리 안에 — 자료 속 백틱이 울타리를 닫지 못한다.
    fence = parts[2].text.split("\n", 1)[0]
    assert set(fence) == {"`"} and len(fence) >= 4


def test_someone_elses_attachment_is_not_carried(att_dir):
    mine = attachments.save("a.png", PNG, owner="me")["id"]
    theirs = attachments.save("b.png", PNG, owner="them")["id"]
    assert [p.name for p in attachments.to_parts([mine, theirs], "me")] == ["a.png"]


# ── 제공자마다의 모양 ────────────────────────────────────────────────
def test_claude_gets_image_and_pdf_blocks_but_is_told_it_cannot_watch_video():
    msgs = ClaudeProvider(model="claude-opus-5")._payload(_req(IMG, PDF, VID, TXT))["messages"]
    blocks = msgs[-1]["content"]
    assert blocks[0] == {"type": "text", "text": "만들어 주세요"}
    assert blocks[1]["text"] == ATTACH_PREFACE
    img = next(b for b in blocks if b["type"] == "image")
    assert base64.b64decode(img["source"]["data"]) == PNG
    assert any(b["type"] == "document" for b in blocks)
    texts = " ".join(b.get("text", "") for b in blocks)
    assert "demo.mp4" in texts and "볼 수 없어" in texts
    assert not any(b.get("source", {}).get("media_type") == "video/mp4" for b in blocks)


def test_gemini_gets_every_kind_inline_including_video():
    parts = GeminiProvider()._payload(_req(IMG, VID, TXT))["contents"][-1]["parts"]
    assert parts[0] == {"text": "만들어 주세요"}
    inline = [p["inline_data"] for p in parts if "inline_data" in p]
    assert [i["mime_type"] for i in inline] == ["image/png", "video/mp4"]
    assert inline[1]["data"] == MP4


def test_openai_gets_image_and_file_inputs_but_not_video():
    content = OpenAIProvider()._payload(_req(IMG, PDF, VID))["input"][-1]["content"]
    kinds = [c["type"] for c in content]
    assert "input_image" in kinds and "input_file" in kinds
    assert content[kinds.index("input_image")]["image_url"].startswith("data:image/png;base64,")
    assert any("demo.mp4" in c.get("text", "") and "볼 수 없어" in c.get("text", "")
               for c in content)


def test_no_attachments_means_the_payload_is_unchanged():
    """첨부가 없으면 예전 모양 그대로 — 글 한 줄짜리 content."""
    assert ClaudeProvider(model="claude-opus-5")._payload(_req())["messages"][-1]["content"] \
        == "만들어 주세요"
    assert OpenAIProvider()._payload(_req())["input"][-1]["content"] == "만들어 주세요"
    assert GeminiProvider()._payload(_req())["contents"][-1]["parts"] == [{"text": "만들어 주세요"}]


# ── 기획까지 ─────────────────────────────────────────────────────────
def test_the_planner_is_handed_the_originals(monkeypatch):
    """employee.ask 가 첨부를 요청에 싣는다 — 이름 한 줄이 아니라 원본을."""
    from app.agents import employee, roles
    from app.agents.schemas import Routing

    seen: list[GenerateRequest] = []

    class Spy:
        def generate(self, req):
            seen.append(req)
            from app.providers.base import GenerateResult
            return GenerateResult(text='{"employee": "developer", "why": "x"}',
                                  model="m", provider="spy")

    monkeypatch.setattr(employee, "provider_of", lambda e: Spy())
    employee.ask(roles.PLANNER, "기획", Routing, attachments=[IMG, TXT])
    assert seen[0].attachments == (IMG, TXT)


def test_mock_run_says_attachments_were_not_read(monkeypatch, att_dir):
    """Mock 에서는 아무도 첨부를 보지 않는다 — 본 척하지 않고 로그에 적는다.
    영상은 볼 수 있는 직원(Gemini)이 없으니 이름만 넘어간다고도 적는다."""
    from app.orchestrator import engine

    monkeypatch.setenv("PROVIDER_MODE", "mock")
    said: list[str] = []
    monkeypatch.setattr(bus, "say", lambda who, text, **kw: said.append(text))
    ids = [attachments.save("shot.png", PNG)["id"], attachments.save("clip.mp4", MP4)["id"]]
    parts = engine._materials(engine._Run("att-mock", "local"), "요구", ids)
    assert [p.kind for p in parts] == ["image", "video"]
    assert any("Mock" in s for s in said)
    assert any("clip.mp4" in s for s in said)
