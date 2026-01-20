"""Process Chat Command - 최상위 유스케이스 엔트리.

Application Layer의 핵심 진입점.
메인 유스케이스로서 서브 서비스들(intent, answer, integrations, interaction)을 조율.

호출 순서:
1. queued 이벤트 발행
2. 파이프라인 실행 (LangGraph)
   - Intent → Route → [RAG/Character/Location] → Answer
3. done 이벤트 발행
4. 결과 반환

상태 모델:
- queued: 작업 대기
- running: 파이프라인 실행 중
- waiting_human: Human-in-the-Loop 대기 (interaction)
- completed: 완료
- failed: 실패

Clean Architecture:
- Infrastructure(Prometheus) 직접 의존 제거
- MetricsPort 추상화를 통한 메트릭 수집

LangGraph 네이티브 스트리밍:
- astream_events로 실시간 이벤트 스트리밍
- DynamicProgressTracker로 병렬 서브에이전트 Progress 계산
- Token v2로 복구 가능한 토큰 스트리밍
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Protocol

from chat_worker.application.services.progress_tracker import (
    DynamicProgressTracker,
    SUBAGENT_NODES,
    get_node_message,
    get_stage_for_node,
)

if TYPE_CHECKING:
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.metrics import MetricsPort
    from chat_worker.application.ports.telemetry import TelemetryConfigPort

logger = logging.getLogger(__name__)


# ============================================================
# Pipeline Protocol (Graph 인터페이스)
# ============================================================


class ChatPipelinePort(Protocol):
    """Chat 파이프라인 Port.

    LangGraph 구현을 추상화.
    테스트 시 Mock으로 교체 가능.
    """

    async def ainvoke(
        self,
        state: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """파이프라인 실행 (동기)."""
        ...

    def astream(
        self,
        state: dict[str, Any],
        config: dict[str, Any] | None = None,
        stream_mode: str | list[str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[tuple[str, Any] | Any]:
        """파이프라인 실행 (stream_mode 스트리밍).

        LangGraph 1.0+ 네이티브 스트리밍.

        Stream Modes:
        - "messages": LLM 토큰 스트리밍 (AIMessageChunk, metadata)
        - "updates": 노드 상태 업데이트 {node_name: state_update}
        - "values": 전체 상태 스냅샷

        복수 모드 사용 시 (stream_mode, data) 튜플 반환.

        Args:
            state: 초기 상태
            config: LangGraph config (thread_id 등)
            stream_mode: 스트리밍 모드 ("messages", "updates", "values")

        Yields:
            스트리밍 데이터 (모드에 따라 형식 다름)
        """
        ...

    def astream_events(
        self,
        state: dict[str, Any],
        config: dict[str, Any] | None = None,
        version: str = "v2",
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        """파이프라인 실행 (이벤트 스트리밍) - 레거시.

        LangGraph 1.0+ 이벤트 기반 스트리밍.
        stream_mode="messages"로 대체 권장.

        이벤트 타입:
        - on_chain_start/end: 노드 시작/완료
        - on_llm_stream: 토큰 스트리밍 (LangChain LLM 필요)
        - on_retriever_start/end: 검색 시작/완료

        Args:
            state: 초기 상태
            config: LangGraph config (thread_id 등)
            version: 이벤트 스키마 버전 (v2 권장)

        Yields:
            LangGraph 이벤트
        """
        ...


# ============================================================
# Request/Response DTOs
# ============================================================


@dataclass
class ProcessChatRequest:
    """Chat 처리 요청."""

    job_id: str
    session_id: str
    user_id: str
    message: str
    image_url: str | None = None
    user_location: dict[str, float] | None = None
    model: str | None = None


@dataclass
class ProcessChatResponse:
    """Chat 처리 응답."""

    job_id: str
    session_id: str
    status: str  # "completed" | "failed"
    intent: str | None
    answer: str | None
    error: str | None = None


# ============================================================
# Use Case (Main Entry Point)
# ============================================================


class ProcessChatCommand:
    """Chat 파이프라인 실행 Command.

    최상위 유스케이스로서:
    - 파이프라인 실행 조율 (LangGraph)
    - 시작/완료/실패 이벤트 발행 (ProgressNotifier)
    - 메트릭 수집 (MetricsPort)
    - 결과 포맷팅

    서브 서비스들:
    - intent/: IntentClassifier
    - answer/: AnswerGenerator
    - integrations/: CharacterService, LocationService
    - interaction/: HumanInputService

    ```
    ProcessChatCommand (여기)
          │
          └── ChatPipelinePort (LangGraph)
                    │
                    ├── IntentService
                    ├── AnswerService
                    ├── integrations/CharacterService
                    ├── integrations/LocationService
                    └── interaction/HumanInputService
    ```

    네이티브 스트리밍 모드:
    - astream_events로 실시간 이벤트 수신
    - on_chain_start/end: 노드 시작/완료 추적 → Progress 알림
    - on_llm_stream: 토큰 스트리밍 → Token v2 알림
    - DynamicProgressTracker로 병렬 서브에이전트 진행률 계산
    """

    def __init__(
        self,
        pipeline: ChatPipelinePort,
        progress_notifier: "ProgressNotifierPort",
        metrics: "MetricsPort | None" = None,
        telemetry: "TelemetryConfigPort | None" = None,
        provider: str = "openai",
        enable_native_streaming: bool = True,
    ):
        """초기화.

        Args:
            pipeline: Chat 파이프라인 (LangGraph)
            progress_notifier: 진행 상황 알림 Port
            metrics: 메트릭 수집 Port (선택)
            telemetry: Telemetry 설정 Port (선택, LangSmith 등)
            provider: LLM 프로바이더
            enable_native_streaming: 네이티브 스트리밍 활성화 (기본 True)

        Note:
            Event-First Architecture: 메시지 영속화는 done 이벤트에
            persistence 데이터를 포함하여 DB Consumer가 처리.
        """
        self._pipeline = pipeline
        self._progress_notifier = progress_notifier
        self._metrics = metrics
        self._telemetry = telemetry
        self._provider = provider
        self._enable_native_streaming = enable_native_streaming

    async def execute(self, request: ProcessChatRequest) -> ProcessChatResponse:
        """Chat 파이프라인 실행.

        상태 전이:
        queued → running → [waiting_human] → completed/failed

        네이티브 스트리밍 모드:
        - astream_events로 LangGraph 이벤트 실시간 수신
        - on_chain_start/end: 노드 진행률 추적
        - on_llm_stream: 토큰 스트리밍
        """
        log_ctx = {
            "job_id": request.job_id,
            "session_id": request.session_id,
            "user_id": request.user_id,
        }
        logger.info("ProcessChatCommand started", extra=log_ctx)

        start_time = time.perf_counter()
        intent = "unknown"
        status = "success"

        # Progress Tracker (요청별 로컬 인스턴스 - 동시성 안전)
        progress_tracker = DynamicProgressTracker()

        try:
            # 1. 작업 시작 이벤트 (queued → running)
            await self._progress_notifier.notify_stage(
                task_id=request.job_id,
                stage="queued",
                status="started",
                progress=0,
                message="작업이 시작되었습니다...",
            )

            # 2. 파이프라인 초기 상태
            # model: 프론트엔드가 지정한 모델 (Location Agent 등에서 사용)
            initial_state = {
                "job_id": request.job_id,
                "session_id": request.session_id,
                "user_id": request.user_id,
                "message": request.message,
                "image_url": request.image_url,
                "user_location": request.user_location,
                "llm_model": request.model,  # Location Agent에서 사용
                "llm_provider": self._provider,  # OpenAI or Google
            }

            # Telemetry + LangGraph config 생성
            # - Telemetry: run_name, tags, metadata (피처별 분석용)
            # - LangGraph: thread_id (멀티턴 대화 컨텍스트)
            config: dict[str, Any] = {"configurable": {}}
            if request.session_id:
                config["configurable"]["thread_id"] = request.session_id

            if self._telemetry:
                config = self._telemetry.get_run_config(
                    job_id=request.job_id,
                    session_id=request.session_id,
                    user_id=request.user_id,
                )

            # 3. 파이프라인 실행 (스트리밍 or 동기)
            if self._enable_native_streaming:
                result = await self._execute_streaming(
                    initial_state, config, request.job_id, progress_tracker
                )
            else:
                result = await self._pipeline.ainvoke(initial_state, config=config)

            intent = result.get("intent", "unknown")

            # Metrics: Intent 추적
            if self._metrics:
                self._metrics.track_intent(intent)

            answer = result.get("answer", "")

            # 4. 토큰 스트림 완료 처리
            if self._enable_native_streaming:
                await self._progress_notifier.finalize_token_stream(request.job_id)

            # 5. 작업 완료 이벤트 (running → completed)
            # Event-First Architecture: done 이벤트에 persistence 데이터 포함
            # DB Consumer가 이 이벤트를 소비하여 PostgreSQL에 저장
            now = datetime.now(timezone.utc)
            await self._progress_notifier.notify_stage(
                task_id=request.job_id,
                stage="done",
                status="completed",
                progress=100,
                result={
                    "intent": intent,
                    "answer": answer,
                    # Persistence data for DB Consumer
                    "persistence": {
                        "conversation_id": request.session_id,
                        "user_id": request.user_id,
                        "user_message": request.message,
                        "user_message_created_at": now.isoformat(),
                        "assistant_message": answer,
                        "assistant_message_created_at": now.isoformat(),
                        "intent": intent,
                        "metadata": result.get("metadata"),
                    },
                },
            )

            logger.info(
                "ProcessChatCommand completed",
                extra={**log_ctx, "intent": intent},
            )

            return ProcessChatResponse(
                job_id=request.job_id,
                session_id=request.session_id,
                status="completed",
                intent=intent,
                answer=answer,
            )

        except Exception as e:
            status = "error"
            logger.error(
                "ProcessChatCommand failed",
                extra={**log_ctx, "error": str(e)},
                exc_info=True,
            )

            # Metrics: 에러 추적
            if self._metrics:
                self._metrics.track_error(intent, type(e).__name__)

            # 작업 실패 이벤트 (running → failed)
            await self._progress_notifier.notify_stage(
                task_id=request.job_id,
                stage="done",
                status="failed",
                result={"error": str(e)},
            )

            return ProcessChatResponse(
                job_id=request.job_id,
                session_id=request.session_id,
                status="failed",
                intent=None,
                answer=None,
                error=str(e),
            )

        finally:
            # Metrics: 요청 시간 추적
            duration = time.perf_counter() - start_time
            if self._metrics:
                self._metrics.track_request(
                    intent=intent,
                    status=status,
                    provider=self._provider,
                    duration=duration,
                )
            # Token counter 정리
            self._progress_notifier.clear_token_counter(request.job_id)

    # ============================================================
    # Native Streaming Handlers (stream_mode 기반)
    # ============================================================

    async def _execute_streaming(
        self,
        state: dict[str, Any],
        config: dict[str, Any],
        job_id: str,
        progress_tracker: DynamicProgressTracker,
    ) -> dict[str, Any]:
        """stream_mode를 사용한 스트리밍 파이프라인 실행.

        LangGraph 1.0+ 권장 방식.
        - stream_mode="messages": LLM 토큰 스트리밍 (AIMessageChunk)
        - stream_mode="updates": 노드 상태 업데이트 (Progress 추적)

        참고: https://docs.langchain.com/oss/python/langgraph/streaming#messages

        Args:
            state: 초기 상태
            config: LangGraph config
            job_id: 작업 ID
            progress_tracker: 요청별 Progress Tracker (동시성 안전)

        Returns:
            최종 파이프라인 결과
        """
        final_result: dict[str, Any] = {}
        seen_nodes: set[str] = set()  # 노드 시작 추적

        # stream_mode=["messages", "updates"] 사용
        # 반환 형식: (stream_mode, data) 튜플
        async for stream_mode, data in self._pipeline.astream(
            state,
            config=config,
            stream_mode=["messages", "updates"],
        ):
            if stream_mode == "messages":
                # LLM 토큰 스트리밍
                await self._handle_message_chunk(data, job_id)

            elif stream_mode == "updates":
                # 노드 상태 업데이트
                final_result = await self._handle_node_update(
                    data, job_id, final_result, progress_tracker, seen_nodes
                )

        return final_result

    async def _handle_message_chunk(
        self,
        data: tuple[Any, dict[str, Any]],
        job_id: str,
    ) -> None:
        """messages 모드 청크 처리.

        LLM 토큰을 notify_token_v2로 전달.
        answer 노드는 자체적으로 토큰을 발행하므로 건너뜁니다.

        Note:
            현재 아키텍처에서는 모든 토큰 발행을 개별 노드에서 직접 처리합니다:
            - answer_node: notify_token_v2로 직접 토큰 발행 (웹 검색/LangChain 모두)
            - intent_node: 분류 결과만 반환 (토큰 스트리밍 불필요)
            - 기타 노드: 컨텍스트 수집만 수행 (토큰 스트리밍 불필요)

            따라서 ProcessChatCommand는 stream_mode="messages"에서 캡처되는
            LLM 응답을 토큰으로 발행하지 않습니다. 이를 통해:
            1. answer_node와의 토큰 중복 방지
            2. intent_node 분류 결과가 토큰으로 노출되는 것 방지

        Args:
            data: (AIMessageChunk, metadata) 튜플
            job_id: 작업 ID
        """
        # 모든 토큰 발행은 개별 노드에서 직접 처리하므로 여기서는 건너뜀
        # answer_node가 notify_token_v2로 직접 토큰을 발행함
        return

    async def _handle_node_update(
        self,
        data: dict[str, dict[str, Any]],
        job_id: str,
        current_result: dict[str, Any],
        progress_tracker: DynamicProgressTracker,
        seen_nodes: set[str],
    ) -> dict[str, Any]:
        """updates 모드 노드 업데이트 처리.

        노드 상태 변경을 Progress 알림으로 전달.

        Args:
            data: {node_name: state_update} 딕셔너리
            job_id: 작업 ID
            current_result: 현재까지 수집된 결과
            progress_tracker: 요청별 Progress Tracker
            seen_nodes: 이미 시작 알림을 보낸 노드들

        Returns:
            업데이트된 결과
        """
        for node_name, state_update in data.items():
            if node_name.startswith("__"):
                # 내부 노드 무시 (__start__, __end__ 등)
                continue

            # 노드 시작 알림 (첫 번째 업데이트)
            if node_name not in seen_nodes:
                seen_nodes.add(node_name)
                await self._notify_node_progress(node_name, job_id, "started", progress_tracker)

            # 노드 완료 알림
            await self._notify_node_progress(node_name, job_id, "completed", progress_tracker)

            # 결과 수집
            if isinstance(state_update, dict):
                if "intent" in state_update:
                    current_result["intent"] = state_update["intent"]
                if "answer" in state_update:
                    current_result["answer"] = state_update["answer"]

        return current_result

    async def _notify_node_progress(
        self,
        node: str,
        job_id: str,
        status: str,
        progress_tracker: DynamicProgressTracker,
    ) -> None:
        """노드 Progress 알림.

        Args:
            node: 노드 이름
            job_id: 작업 ID
            status: "started" 또는 "completed"
            progress_tracker: Progress Tracker
        """
        # 서브에이전트 추적
        if status == "started" and node in SUBAGENT_NODES:
            progress_tracker.on_subagent_start(node)
        elif status == "completed" and node in SUBAGENT_NODES:
            progress_tracker.on_subagent_end(node)

        # Phase 및 Progress 계산
        phase = progress_tracker.get_phase_for_node(node)
        progress = progress_tracker.calculate_progress(phase, status)

        # Stage 및 메시지
        stage = get_stage_for_node(node)
        message = get_node_message(node, status)

        await self._progress_notifier.notify_stage(
            task_id=job_id,
            stage=stage,
            status=status,
            progress=progress,
            message=message,
        )

        logger.debug(
            f"Node {status}",
            extra={"node": node, "phase": phase, "progress": progress},
        )

    async def _handle_chain_start(
        self,
        event: dict[str, Any],
        job_id: str,
        progress_tracker: DynamicProgressTracker,
    ) -> None:
        """on_chain_start 이벤트 처리.

        노드 시작 시 Progress 알림.
        서브에이전트는 DynamicProgressTracker로 추적.

        Args:
            event: LangGraph 이벤트
            job_id: 작업 ID
            progress_tracker: 요청별 Progress Tracker
        """
        metadata = event.get("metadata", {})
        node = metadata.get("langgraph_node", "")

        if not node:
            return

        # 서브에이전트 시작 추적
        if node in SUBAGENT_NODES:
            progress_tracker.on_subagent_start(node)

        # Phase 결정 및 Progress 계산
        phase = progress_tracker.get_phase_for_node(node)
        progress = progress_tracker.calculate_progress(phase, "started")

        # Stage 결정 (서브에이전트는 개별 stage명 사용)
        stage = get_stage_for_node(node)

        # UI 메시지 생성
        message = get_node_message(node, "started")

        await self._progress_notifier.notify_stage(
            task_id=job_id,
            stage=stage,
            status="started",
            progress=progress,
            message=message,
        )

        logger.debug(
            "Node started",
            extra={"node": node, "phase": phase, "progress": progress},
        )

    async def _handle_chain_end(
        self,
        event: dict[str, Any],
        job_id: str,
        current_result: dict[str, Any],
        progress_tracker: DynamicProgressTracker,
    ) -> dict[str, Any]:
        """on_chain_end 이벤트 처리.

        노드 완료 시 Progress 알림 및 결과 수집.
        서브에이전트 완료 시 DynamicProgressTracker 업데이트.

        Args:
            event: LangGraph 이벤트
            job_id: 작업 ID
            current_result: 현재까지 수집된 결과
            progress_tracker: 요청별 Progress Tracker

        Returns:
            업데이트된 결과 (최종 노드에서 결과 추출)
        """
        metadata = event.get("metadata", {})
        node = metadata.get("langgraph_node", "")

        if not node:
            return current_result

        # 서브에이전트 완료 추적
        if node in SUBAGENT_NODES:
            progress_tracker.on_subagent_end(node)

        # Phase 결정 및 Progress 계산
        phase = progress_tracker.get_phase_for_node(node)
        progress = progress_tracker.calculate_progress(phase, "completed")

        # Stage 결정 (서브에이전트는 개별 stage명 사용)
        stage = get_stage_for_node(node)

        # UI 메시지 생성
        message = get_node_message(node, "completed")

        await self._progress_notifier.notify_stage(
            task_id=job_id,
            stage=stage,
            status="completed",
            progress=progress,
            message=message,
        )

        logger.debug(
            "Node completed",
            extra={"node": node, "phase": phase, "progress": progress},
        )

        # 결과 수집 (answer 또는 aggregator 노드에서)
        output = event.get("data", {}).get("output", {})
        if isinstance(output, dict):
            # intent, answer 등 주요 필드 수집
            if "intent" in output:
                current_result["intent"] = output["intent"]
            if "answer" in output:
                current_result["answer"] = output["answer"]
            if "metadata" in output:
                current_result["metadata"] = output["metadata"]

        return current_result

    async def _handle_llm_stream(self, event: dict[str, Any], job_id: str) -> None:
        """on_llm_stream 이벤트 처리.

        LLM 토큰 스트리밍을 Token v2로 전달.
        """
        chunk = event.get("data", {}).get("chunk")
        if not chunk:
            return

        # AIMessageChunk에서 content 추출
        content = getattr(chunk, "content", None)
        if not content:
            return

        # 발생 노드 추출 (answer, summarize 등)
        metadata = event.get("metadata", {})
        node = metadata.get("langgraph_node", "")

        await self._progress_notifier.notify_token_v2(
            task_id=job_id,
            content=content,
            node=node,
        )
