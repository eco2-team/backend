from domains._shared.schemas.waste import WasteClassificationResult
from domains.chat.services.chat import ChatService


def test_render_answer_prefers_user_answer():
    service = ChatService()
    result = WasteClassificationResult(
        classification_result={},
        disposal_rules={},
        final_answer={"user_answer": "직접 답변", "answer": "백업 답변"},
    )

    text = service._render_answer(result, "질문")

    assert text == "직접 답변"


def test_render_answer_falls_back_when_missing():
    service = ChatService()
    result = WasteClassificationResult(
        classification_result={},
        disposal_rules={},
        final_answer={},
    )

    text = service._render_answer(result, "원문 질문")
    assert text == service._fallback_answer("원문 질문")
