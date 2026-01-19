"""ProcessChatCommand 단위 테스트."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

import pytest

from chat_worker.application.commands.process_chat import (
    ProcessChatCommand,
    ProcessChatRequest,
    ProcessChatResponse,
)


class MockPipeline:
    """Mock LangGraph Pipeline."""

    def __init__(self, result: dict[str, Any] | None = None):
        self._result = result or {
            "job_id": "job-123",
            "message": "테스트",
            "intent": "waste",
            "answer": "페트병은 라벨을 제거해주세요.",
        }
        self.ainvoke = AsyncMock(return_value=self._result)

    async def astream(
        self,
        state: dict[str, Any],
        config: dict[str, Any] | None = None,
        stream_mode: str | list[str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[tuple[str, Any]]:
        """Mock astream for stream_mode based streaming.

        stream_mode=["messages", "updates"] 시:
        - "messages": (AIMessageChunk, metadata) 튜플
        - "updates": {node_name: state_update} 딕셔너리
        """
        answer = self._result.get("answer", "")

        # Intent node update
        yield ("updates", {"intent": {"intent": self._result.get("intent", "unknown")}})

        # Answer node - token streaming
        for char in answer[:5]:  # Simulate first 5 chars as tokens
            yield ("messages", (MockChunk(char), {"langgraph_node": "answer"}))

        # Answer node update (completed)
        yield ("updates", {"answer": {"answer": answer}})

    async def astream_events(
        self,
        state: dict[str, Any],
        config: dict[str, Any] | None = None,
        version: str = "v2",
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        """Mock astream_events for legacy native streaming."""
        # Simulate intent node start/end
        yield {
            "event": "on_chain_start",
            "metadata": {"langgraph_node": "intent"},
        }
        yield {
            "event": "on_chain_end",
            "metadata": {"langgraph_node": "intent"},
            "data": {"output": {"intent": self._result.get("intent", "unknown")}},
        }

        # Simulate answer node with LLM streaming
        yield {
            "event": "on_chain_start",
            "metadata": {"langgraph_node": "answer"},
        }
        # Simulate on_llm_stream tokens
        answer = self._result.get("answer", "")
        for char in answer[:5]:  # Simulate first 5 chars as tokens
            yield {
                "event": "on_llm_stream",
                "metadata": {"langgraph_node": "answer"},
                "data": {"chunk": MockChunk(char)},
            }
        yield {
            "event": "on_chain_end",
            "metadata": {"langgraph_node": "answer"},
            "data": {"output": {"answer": answer}},
        }


class MockChunk:
    """Mock AIMessageChunk for token streaming."""

    def __init__(self, content: str):
        self.content = content


class MockProgressNotifier:
    """Mock ProgressNotifier."""

    def __init__(self):
        self.events: list[dict] = []
        self.tokens: list[dict] = []

    async def notify_stage(
        self,
        task_id: str,
        stage: str,
        status: str,
        progress: int | None = None,
        result: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> str:
        self.events.append(
            {
                "task_id": task_id,
                "stage": stage,
                "status": status,
                "progress": progress,
                "result": result,
                "message": message,
            }
        )
        return "event-id"

    async def notify_token(self, task_id: str, content: str) -> str:
        return "event-id"

    async def notify_token_v2(self, task_id: str, content: str, node: str | None = None) -> str:
        self.tokens.append({"task_id": task_id, "content": content, "node": node})
        return "event-id"

    async def finalize_token_stream(self, task_id: str) -> None:
        pass

    def clear_token_counter(self, task_id: str) -> None:
        pass

    async def notify_needs_input(
        self,
        task_id: str,
        input_type: str,
        message: str,
        timeout: int = 60,
    ) -> str:
        return "event-id"


class TestProcessChatCommand:
    """ProcessChatCommand 테스트 스위트."""

    @pytest.fixture
    def mock_pipeline(self) -> MockPipeline:
        """Mock Pipeline."""
        return MockPipeline()

    @pytest.fixture
    def mock_notifier(self) -> MockProgressNotifier:
        """Mock Notifier."""
        return MockProgressNotifier()

    @pytest.fixture
    def command(
        self,
        mock_pipeline: MockPipeline,
        mock_notifier: MockProgressNotifier,
    ) -> ProcessChatCommand:
        """테스트용 Command (레거시 ainvoke 모드)."""
        return ProcessChatCommand(
            pipeline=mock_pipeline,
            progress_notifier=mock_notifier,
            enable_native_streaming=False,  # 기존 테스트는 ainvoke 모드
        )

    @pytest.fixture
    def streaming_command(
        self,
        mock_pipeline: MockPipeline,
        mock_notifier: MockProgressNotifier,
    ) -> ProcessChatCommand:
        """테스트용 Command (네이티브 스트리밍 모드)."""
        return ProcessChatCommand(
            pipeline=mock_pipeline,
            progress_notifier=mock_notifier,
            enable_native_streaming=True,
        )

    @pytest.fixture
    def sample_request(self) -> ProcessChatRequest:
        """샘플 요청."""
        return ProcessChatRequest(
            job_id="job-123",
            session_id="session-1",
            user_id="user-1",
            message="페트병 어떻게 버려?",
        )

    # ==========================================================
    # Basic Execution Tests
    # ==========================================================

    @pytest.mark.anyio
    async def test_execute_success(
        self,
        command: ProcessChatCommand,
        mock_pipeline: MockPipeline,
        sample_request: ProcessChatRequest,
    ):
        """성공 실행."""
        result = await command.execute(sample_request)

        assert result is not None
        assert isinstance(result, ProcessChatResponse)
        assert result.status == "completed"
        mock_pipeline.ainvoke.assert_called_once()

    @pytest.mark.anyio
    async def test_execute_passes_initial_state(
        self,
        command: ProcessChatCommand,
        mock_pipeline: MockPipeline,
    ):
        """초기 상태 전달."""
        request = ProcessChatRequest(
            job_id="job-456",
            session_id="session-2",
            user_id="user-2",
            message="테스트 메시지",
            user_location={"latitude": 37.5, "longitude": 127.0},
        )

        await command.execute(request)

        call_args = mock_pipeline.ainvoke.call_args[0][0]
        assert call_args["job_id"] == "job-456"
        assert call_args["session_id"] == "session-2"
        assert call_args["message"] == "테스트 메시지"
        assert call_args["user_location"]["latitude"] == 37.5

    @pytest.mark.anyio
    async def test_execute_uses_thread_id_for_checkpointing(
        self,
        command: ProcessChatCommand,
        mock_pipeline: MockPipeline,
        sample_request: ProcessChatRequest,
    ):
        """체크포인팅용 thread_id 전달."""
        await command.execute(sample_request)

        call_kwargs = mock_pipeline.ainvoke.call_args.kwargs
        assert "config" in call_kwargs
        assert call_kwargs["config"]["configurable"]["thread_id"] == "session-1"

    # ==========================================================
    # Event Publishing Tests
    # ==========================================================

    @pytest.mark.anyio
    async def test_execute_publishes_started_event(
        self,
        command: ProcessChatCommand,
        mock_notifier: MockProgressNotifier,
        sample_request: ProcessChatRequest,
    ):
        """시작 이벤트 발행."""
        await command.execute(sample_request)

        started_events = [e for e in mock_notifier.events if e["status"] == "started"]
        assert len(started_events) >= 1

    @pytest.mark.anyio
    async def test_execute_publishes_completed_event(
        self,
        command: ProcessChatCommand,
        mock_notifier: MockProgressNotifier,
        sample_request: ProcessChatRequest,
    ):
        """완료 이벤트 발행."""
        await command.execute(sample_request)

        completed_events = [e for e in mock_notifier.events if e["status"] == "completed"]
        assert len(completed_events) >= 1

    @pytest.mark.anyio
    async def test_execute_publishes_failed_event_on_error(
        self,
        mock_notifier: MockProgressNotifier,
    ):
        """에러 시 실패 이벤트 발행."""
        mock_pipeline = MockPipeline()
        mock_pipeline.ainvoke = AsyncMock(side_effect=Exception("Pipeline Error"))
        command = ProcessChatCommand(
            pipeline=mock_pipeline,
            progress_notifier=mock_notifier,
            enable_native_streaming=False,  # ainvoke 모드로 테스트
        )

        request = ProcessChatRequest(
            job_id="job-def",
            session_id="session-1",
            user_id="user-1",
            message="테스트",
        )

        result = await command.execute(request)

        assert result.status == "failed"
        assert result.error is not None
        failed_events = [e for e in mock_notifier.events if e["status"] == "failed"]
        assert len(failed_events) >= 1

    # ==========================================================
    # Result Handling Tests
    # ==========================================================

    @pytest.mark.anyio
    async def test_execute_returns_result(
        self,
        mock_notifier: MockProgressNotifier,
    ):
        """결과 반환."""
        mock_pipeline = MockPipeline(
            result={
                "job_id": "job-xyz",
                "intent": "character",
                "answer": "플라스틱 캐릭터 정보입니다.",
            }
        )
        command = ProcessChatCommand(
            pipeline=mock_pipeline,
            progress_notifier=mock_notifier,
            enable_native_streaming=False,  # ainvoke 모드로 테스트
        )

        request = ProcessChatRequest(
            job_id="job-xyz",
            session_id="session-1",
            user_id="user-1",
            message="플라스틱 캐릭터 뭐야?",
        )

        result = await command.execute(request)

        assert result.intent == "character"
        assert "플라스틱" in result.answer

    # ==========================================================
    # Input Handling Tests
    # ==========================================================

    @pytest.mark.anyio
    async def test_execute_without_location(
        self,
        command: ProcessChatCommand,
        mock_pipeline: MockPipeline,
    ):
        """위치 정보 없이 실행."""
        request = ProcessChatRequest(
            job_id="job-1",
            session_id="session-1",
            user_id="user-1",
            message="안녕",
        )

        await command.execute(request)

        call_args = mock_pipeline.ainvoke.call_args[0][0]
        assert call_args.get("user_location") is None

    @pytest.mark.anyio
    async def test_execute_with_location(
        self,
        command: ProcessChatCommand,
        mock_pipeline: MockPipeline,
    ):
        """위치 정보 포함 실행."""
        request = ProcessChatRequest(
            job_id="job-2",
            session_id="session-1",
            user_id="user-1",
            message="근처 재활용 센터",
            user_location={"latitude": 37.5665, "longitude": 126.9780},
        )

        await command.execute(request)

        call_args = mock_pipeline.ainvoke.call_args[0][0]
        assert call_args["user_location"]["latitude"] == 37.5665

    @pytest.mark.anyio
    async def test_execute_with_image(
        self,
        command: ProcessChatCommand,
        mock_pipeline: MockPipeline,
    ):
        """이미지 포함 실행."""
        request = ProcessChatRequest(
            job_id="job-3",
            session_id="session-1",
            user_id="user-1",
            message="이게 뭐야?",
            image_url="https://example.com/image.jpg",
        )

        await command.execute(request)

        call_args = mock_pipeline.ainvoke.call_args[0][0]
        assert call_args["image_url"] == "https://example.com/image.jpg"

    # ==========================================================
    # Native Streaming Tests
    # ==========================================================

    @pytest.mark.anyio
    async def test_streaming_execute_success(
        self,
        streaming_command: ProcessChatCommand,
        sample_request: ProcessChatRequest,
    ):
        """네이티브 스트리밍 성공 실행."""
        result = await streaming_command.execute(sample_request)

        assert result is not None
        assert isinstance(result, ProcessChatResponse)
        assert result.status == "completed"
        assert result.answer == "페트병은 라벨을 제거해주세요."

    @pytest.mark.anyio
    async def test_streaming_collects_intent_from_events(
        self,
        streaming_command: ProcessChatCommand,
        sample_request: ProcessChatRequest,
    ):
        """스트리밍에서 intent 수집."""
        result = await streaming_command.execute(sample_request)

        assert result.intent == "waste"

    @pytest.mark.anyio
    async def test_streaming_skips_answer_node_tokens(
        self,
        streaming_command: ProcessChatCommand,
        mock_notifier: MockProgressNotifier,
        sample_request: ProcessChatRequest,
    ):
        """스트리밍에서 answer 노드 토큰 건너뛰기.

        answer_node가 자체적으로 토큰을 발행하므로
        ProcessChatCommand._handle_message_chunk()는 answer 노드 토큰을 건너뜁니다.
        실제 answer_node 테스트는 answer_node.py 단위 테스트에서 수행.
        """
        await streaming_command.execute(sample_request)

        # ProcessChatCommand는 answer 노드 토큰을 건너뜀 (중복 방지)
        # 실제 토큰은 answer_node에서 직접 발행됨
        answer_tokens = [t for t in mock_notifier.tokens if t["node"] == "answer"]
        assert len(answer_tokens) == 0

    @pytest.mark.anyio
    async def test_streaming_notifies_stage_events(
        self,
        streaming_command: ProcessChatCommand,
        mock_notifier: MockProgressNotifier,
        sample_request: ProcessChatRequest,
    ):
        """스트리밍에서 단계 이벤트 알림."""
        await streaming_command.execute(sample_request)

        # queued, intent started/completed, answer started/completed, done
        stages = [e["stage"] for e in mock_notifier.events]
        assert "queued" in stages
        assert "intent" in stages
        assert "answer" in stages
        assert "done" in stages

    @pytest.mark.anyio
    async def test_streaming_calculates_progress(
        self,
        streaming_command: ProcessChatCommand,
        mock_notifier: MockProgressNotifier,
        sample_request: ProcessChatRequest,
    ):
        """스트리밍에서 진행률 계산."""
        await streaming_command.execute(sample_request)

        # 진행률이 0에서 시작해서 100으로 끝나야 함
        progresses = [e["progress"] for e in mock_notifier.events if e["progress"] is not None]
        assert 0 in progresses
        assert 100 in progresses
