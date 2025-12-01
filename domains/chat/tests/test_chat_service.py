from domains.chat.schemas.chat import ChatMessage
from domains.chat.services.chat import ChatService
from domains.chat.services.session_store import ChatSessionStore


def test_build_messages_uses_text_content_for_all_roles():
    session_store = ChatSessionStore(redis=None, ttl_seconds=300, max_history=6)
    service = ChatService(session_store=session_store)
    history = [
        ChatMessage(role="user", content="첫 번째 질문"),
        ChatMessage(role="assistant", content="첫 번째 답변"),
    ]

    messages = service._build_messages(history, "두 번째 질문")

    assert messages[0]["role"] == "system"
    assert messages[1]["content"][0]["type"] == "input_text"
    assert messages[2]["role"] == "assistant"
    assert messages[2]["content"][0]["type"] == "input_text"
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"][0]["text"] == "두 번째 질문"
