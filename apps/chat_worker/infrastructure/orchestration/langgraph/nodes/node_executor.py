"""Node Executor - Policy 적용 노드 실행기.

NodePolicy + CircuitBreaker를 노드 실행에 적용합니다.

역할:
1. Circuit Breaker 상태 확인 (OPEN이면 즉시 실패)
2. Timeout 적용
3. Retry 로직
4. FailMode에 따른 실패 처리
5. 성공/실패 기록 (Circuit Breaker 업데이트)

Clean Architecture:
- CircuitBreakerRegistry: Port로 추상화 (DI 가능)
- NodePolicy: Infrastructure 내부 (변경 불필요)

사용 예:
    ```python
    from node_executor import with_policy, NodeExecutor

    # 데코레이터 방식
    @with_policy("character")
    async def character_node(state):
        ...

    # 또는 명시적 래핑
    executor = NodeExecutor.get_instance()
    result = await executor.execute(
        node_name="character",
        node_func=character_node,
        state=state,
    )
    ```
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from chat_worker.application.dto.node_result import NodeResult
from chat_worker.application.ports.circuit_breaker import CircuitBreakerRegistryPort
from chat_worker.domain.enums import FailMode
from chat_worker.infrastructure.orchestration.langgraph.policies.node_policy import (
    get_node_policy,
)
from chat_worker.infrastructure.resilience.circuit_breaker import (
    CircuitBreakerRegistry,
)
from chat_worker.infrastructure.telemetry import (
    get_tracer,
    set_span_attributes,
    OTEL_ENABLED,
)

if TYPE_CHECKING:
    from chat_worker.infrastructure.orchestration.langgraph.policies.node_policy import (
        NodePolicy,
    )

logger = logging.getLogger(__name__)

# 노드 함수 타입
NodeFunc = Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]


class NodeExecutor:
    """Policy 적용 노드 실행기 (싱글톤).

    NodePolicy와 CircuitBreaker를 적용하여 노드를 실행합니다.

    Clean Architecture:
    - CircuitBreakerRegistryPort로 DI 가능 (테스트 용이)
    - 기본값으로 CircuitBreakerRegistry 사용

    Attributes:
        _cb_registry: Circuit Breaker 레지스트리 (Port)
    """

    _instance: "NodeExecutor | None" = None
    _cb_registry: CircuitBreakerRegistryPort

    def __new__(cls) -> "NodeExecutor":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cb_registry = CircuitBreakerRegistry()
        return cls._instance

    @classmethod
    def get_instance(
        cls,
        cb_registry: CircuitBreakerRegistryPort | None = None,
    ) -> "NodeExecutor":
        """싱글톤 인스턴스 반환.

        Args:
            cb_registry: CircuitBreaker 레지스트리 (테스트 시 Mock 주입)

        Returns:
            NodeExecutor 인스턴스
        """
        instance = cls()
        if cb_registry is not None:
            instance._cb_registry = cb_registry
        return instance

    @classmethod
    def reset_instance(cls) -> None:
        """싱글톤 인스턴스 리셋 (테스트용)."""
        cls._instance = None

    async def execute(
        self,
        node_name: str,
        node_func: NodeFunc,
        state: dict[str, Any],
        fallback_func: NodeFunc | None = None,
    ) -> dict[str, Any]:
        """Policy를 적용하여 노드 실행.

        ADR P2: OpenTelemetry span으로 추적 속성 기록.

        Args:
            node_name: 노드 이름 (policy 조회용)
            node_func: 실행할 노드 함수
            state: 현재 LangGraph 상태
            fallback_func: FAIL_FALLBACK 시 대체 함수 (선택)

        Returns:
            업데이트된 상태 (+ node_results 추가)
        """
        policy = get_node_policy(node_name)
        cb = self._cb_registry.get(policy.name, threshold=policy.cb_threshold)

        job_id = state.get("job_id", "")
        start_time = time.time()

        # OpenTelemetry: span 시작 (활성화 시)
        span = None
        if OTEL_ENABLED:
            tracer = get_tracer()
            span = tracer.start_span(f"node:{node_name}")
            set_span_attributes(
                span,
                {
                    "node.name": node_name,
                    "node.policy.timeout_ms": policy.timeout_ms,
                    "node.policy.fail_mode": policy.fail_mode.value,
                    "job_id": job_id,
                    "intent": state.get("intent"),
                    "user_id": state.get("user_id"),
                },
            )

        # 1. Circuit Breaker 확인
        if not await cb.allow_request():
            logger.warning(
                "Node execution blocked by circuit breaker",
                extra={
                    "job_id": job_id,
                    "node": node_name,
                    "cb_state": cb.state.value,
                    "retry_after": cb.retry_after(),
                },
            )
            # OpenTelemetry: circuit open 기록
            if span:
                set_span_attributes(
                    span,
                    {
                        "node.status": "circuit_open",
                        "node.latency_ms": (time.time() - start_time) * 1000,
                    },
                )
                span.end()

            return await self._handle_failure(
                state=state,
                node_name=node_name,
                policy=policy,
                result=NodeResult.circuit_open(node_name),
                fallback_func=fallback_func,
            )

        # 2. Retry 루프
        last_error: Exception | None = None
        retry_count = 0

        for attempt in range(policy.max_retries + 1):
            retry_count = attempt
            try:
                # 3. Timeout 적용
                result_state = await asyncio.wait_for(
                    node_func(state),
                    timeout=policy.timeout_seconds,
                )

                # 4. 성공 기록
                latency_ms = (time.time() - start_time) * 1000
                await cb.record_success()

                logger.info(
                    "Node execution succeeded",
                    extra={
                        "job_id": job_id,
                        "node": node_name,
                        "latency_ms": latency_ms,
                        "retry_count": retry_count,
                    },
                )

                # node_results에 결과 추가
                node_result = NodeResult.success(
                    node_name=node_name,
                    data={},  # 실제 데이터는 state에 있음
                    latency_ms=latency_ms,
                    retry_count=retry_count,
                )

                # OpenTelemetry: 성공 기록
                if span:
                    set_span_attributes(
                        span,
                        {
                            "node.status": "success",
                            "node.latency_ms": latency_ms,
                            "node.retry_count": retry_count,
                        },
                    )
                    span.end()

                return self._append_node_result(result_state, node_result)

            except asyncio.TimeoutError:
                latency_ms = (time.time() - start_time) * 1000
                last_error = asyncio.TimeoutError(
                    f"Node {node_name} timed out after {latency_ms:.0f}ms"
                )
                logger.warning(
                    "Node execution timeout",
                    extra={
                        "job_id": job_id,
                        "node": node_name,
                        "attempt": attempt + 1,
                        "max_retries": policy.max_retries,
                        "timeout_ms": policy.timeout_ms,
                    },
                )
                # Timeout은 재시도하지 않음 (보통 서비스 과부하)
                break

            except Exception as e:
                last_error = e
                logger.warning(
                    "Node execution failed",
                    extra={
                        "job_id": job_id,
                        "node": node_name,
                        "attempt": attempt + 1,
                        "max_retries": policy.max_retries,
                        "error": str(e),
                    },
                )
                # 마지막 시도가 아니면 재시도
                if attempt < policy.max_retries:
                    await asyncio.sleep(0.1 * (attempt + 1))  # 백오프

        # 5. 최종 실패 처리
        latency_ms = (time.time() - start_time) * 1000
        await cb.record_failure()

        if isinstance(last_error, asyncio.TimeoutError):
            node_result = NodeResult.timeout(
                node_name=node_name,
                latency_ms=latency_ms,
                retry_count=retry_count,
            )
            status = "timeout"
        else:
            node_result = NodeResult.failed(
                node_name=node_name,
                error_message=str(last_error) if last_error else "Unknown error",
                latency_ms=latency_ms,
                retry_count=retry_count,
            )
            status = "failed"

        # OpenTelemetry: 실패 기록
        if span:
            set_span_attributes(
                span,
                {
                    "node.status": status,
                    "node.latency_ms": latency_ms,
                    "node.retry_count": retry_count,
                    "node.error": str(last_error) if last_error else None,
                },
            )
            span.end()

        return await self._handle_failure(
            state=state,
            node_name=node_name,
            policy=policy,
            result=node_result,
            fallback_func=fallback_func,
        )

    async def _handle_failure(
        self,
        state: dict[str, Any],
        node_name: str,
        policy: "NodePolicy",
        result: NodeResult,
        fallback_func: NodeFunc | None,
    ) -> dict[str, Any]:
        """FailMode에 따른 실패 처리.

        Args:
            state: 현재 상태
            node_name: 노드 이름
            policy: 노드 정책
            result: 실패 결과
            fallback_func: 대체 함수

        Returns:
            처리된 상태
        """
        job_id = state.get("job_id", "")

        if policy.fail_mode == FailMode.FAIL_OPEN:
            # 실패해도 진행 (선택적 노드)
            logger.info(
                "Node failure ignored (FAIL_OPEN)",
                extra={
                    "job_id": job_id,
                    "node": node_name,
                    "error": result.error_message,
                },
            )
            return self._append_node_result({}, result)

        elif policy.fail_mode == FailMode.FAIL_FALLBACK:
            # 대체 로직 실행
            if fallback_func:
                logger.info(
                    "Executing fallback function (FAIL_FALLBACK)",
                    extra={"job_id": job_id, "node": node_name},
                )
                try:
                    # fallback 함수 실제 실행
                    fallback_state = await fallback_func(state)
                    # fallback 성공 시 결과에 표시
                    result_with_fallback = NodeResult(
                        node_name=result.node_name,
                        status="fallback_success",
                        data=result.data,
                        error_message=result.error_message,
                        latency_ms=result.latency_ms,
                        retry_count=result.retry_count,
                    )
                    return self._append_node_result(fallback_state, result_with_fallback)
                except Exception as e:
                    # fallback도 실패하면 FAIL_OPEN처럼 처리
                    logger.warning(
                        "Fallback function also failed",
                        extra={
                            "job_id": job_id,
                            "node": node_name,
                            "fallback_error": str(e),
                        },
                    )
                    return self._append_node_result({}, result)
            else:
                # fallback 없으면 FAIL_OPEN과 동일
                logger.warning(
                    "No fallback function provided, treating as FAIL_OPEN",
                    extra={"job_id": job_id, "node": node_name},
                )
                return self._append_node_result({}, result)

        else:  # FAIL_CLOSE
            # 전체 실패
            logger.error(
                "Node failure causes pipeline failure (FAIL_CLOSE)",
                extra={
                    "job_id": job_id,
                    "node": node_name,
                    "error": result.error_message,
                },
            )
            result_state = {
                "pipeline_failed": True,
                "pipeline_error": f"Node {node_name} failed: {result.error_message}",
            }
            return self._append_node_result(result_state, result)

    def _append_node_result(
        self,
        state: dict[str, Any],
        result: NodeResult,
    ) -> dict[str, Any]:
        """node_results 리스트에 결과 추가.

        Args:
            state: 현재 상태
            result: 노드 결과

        Returns:
            node_results가 추가된 상태
        """
        node_results = state.get("node_results", [])
        node_results = [*node_results, result.to_dict()]
        return {**state, "node_results": node_results}


def with_policy(
    node_name: str,
    fallback_func: NodeFunc | None = None,
):
    """Policy 적용 데코레이터.

    노드 함수에 NodePolicy + CircuitBreaker를 적용합니다.

    Args:
        node_name: 노드 이름 (policy 조회용)
        fallback_func: FAIL_FALLBACK 시 대체 함수

    Returns:
        데코레이터

    Example:
        ```python
        @with_policy("character")
        async def character_node(state):
            # ... node logic
            return updated_state
        ```
    """

    def decorator(func: NodeFunc) -> NodeFunc:
        @functools.wraps(func)
        async def wrapper(state: dict[str, Any]) -> dict[str, Any]:
            executor = NodeExecutor.get_instance()
            return await executor.execute(
                node_name=node_name,
                node_func=func,
                state=state,
                fallback_func=fallback_func,
            )

        return wrapper

    return decorator


__all__ = [
    "NodeExecutor",
    "with_policy",
]
