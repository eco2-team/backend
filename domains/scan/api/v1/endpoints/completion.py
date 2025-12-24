"""Scan Completion SSE Streaming Endpoint.

POST 요청에서 직접 SSE 스트림을 반환하는 Stateless 방식.
OpenAI/Anthropic 스트리밍 API 패턴과 동일.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from domains.scan.api.dependencies import CurrentUser, ScanServiceDep
from domains.scan.metrics import (
    SSE_CHAIN_DURATION,
    SSE_CONNECTIONS_ACTIVE,
    SSE_REQUESTS_TOTAL,
    SSE_STAGE_DURATION,
    SSE_TTFB,
)
from domains.scan.schemas.scan import ClassificationRequest

router = APIRouter(prefix="/scan", tags=["scan-completion"])

logger = logging.getLogger(__name__)


def _parse_celery_result(result: str | dict | None) -> dict:
    """Celery task-succeeded 이벤트의 result를 파싱.

    Celery는 result를 Python repr 형식(홑따옴표)으로 전달할 수 있어
    json.loads가 실패할 수 있음. 이 경우 ast.literal_eval 사용.
    """
    import ast
    import re

    if result is None:
        return {}

    if isinstance(result, dict):
        return result

    if not isinstance(result, str):
        return {}

    # 1. 먼저 json.loads 시도 (이미 JSON 형식인 경우)
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        pass

    # 2. Python repr 형식 → JSON 형식 변환 시도
    # 홑따옴표를 쌍따옴표로, None을 null로, True/False를 true/false로
    try:
        # Python literal → dict (가장 안전한 방법)
        return ast.literal_eval(result)
    except (ValueError, SyntaxError):
        pass

    # 3. 간단한 문자열 변환 시도 (fallback)
    try:
        converted = result
        # None → null
        converted = re.sub(r"\bNone\b", "null", converted)
        # True → true, False → false
        converted = re.sub(r"\bTrue\b", "true", converted)
        converted = re.sub(r"\bFalse\b", "false", converted)
        # 홑따옴표 → 쌍따옴표 (문자열 내부의 홑따옴표는 유지)
        converted = converted.replace("'", '"')
        return json.loads(converted)
    except (json.JSONDecodeError, Exception):
        logger.warning(
            "failed_to_parse_celery_result",
            extra={"result_preview": result[:200] if len(result) > 200 else result},
        )
        return {}


# Task 이름 → 단계 매핑 (4단계 Chain)
# prev_progress: started 상태일 때의 progress (이전 단계 완료 값)
TASK_STEP_MAP = {
    "scan.vision": {"step": "vision", "progress": 25, "prev_progress": 0},
    "scan.rule": {"step": "rule", "progress": 50, "prev_progress": 25},
    "scan.answer": {"step": "answer", "progress": 75, "prev_progress": 50},
    "scan.reward": {"step": "reward", "progress": 100, "prev_progress": 75},
}


@router.post(
    "/classify/completion",
    summary="Classify waste image with SSE streaming",
    response_class=StreamingResponse,
)
async def classify_completion(
    payload: ClassificationRequest,
    user: CurrentUser,
    service: ScanServiceDep,
) -> StreamingResponse:
    """이미지를 분석하여 폐기물을 분류합니다 (SSE 스트리밍).

    단일 POST 요청에서 SSE 스트림으로 진행상황과 최종 결과를 반환합니다.
    OpenAI/Anthropic streaming API와 동일한 패턴입니다.

    SSE Events:
        - started: 작업 시작 (task_id 포함)
        - progress: 각 단계 진행상황 (vision, rule, answer, reward)
        - completed: 최종 결과 포함
        - error: 에러 발생 시

    Example:
        ```
        data: {"status": "started", "task_id": "xxx"}
        data: {"step": "vision", "status": "completed", "progress": 25}
        data: {"step": "rule", "status": "completed", "progress": 50}
        data: {"step": "answer", "status": "completed", "progress": 75}
        data: {"step": "reward", "status": "completed", "progress": 100, "result": {...}}
        ```
    """
    return StreamingResponse(
        _completion_generator(payload, user, service),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx buffering 비활성화
        },
    )


async def _completion_generator(
    payload: ClassificationRequest,
    user: CurrentUser,
    service: ScanServiceDep,
) -> AsyncGenerator[str, None]:
    """SSE 스트림 생성기.

    1. Event Receiver 연결
    2. Task 시작 (chain.apply_async)
    3. Celery Events 수신하여 진행상황 스트리밍
    4. 최종 결과 전송 후 종료
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from uuid import uuid4

    from celery import chain

    from domains.scan.celery_app import celery_app
    from domains.scan.tasks.answer import answer_task
    from domains.scan.tasks.reward import scan_reward_task
    from domains.scan.tasks.rule import rule_task
    from domains.scan.tasks.vision import vision_task

    # 메트릭: 활성 연결 수 증가
    SSE_CONNECTIONS_ACTIVE.inc()
    chain_start_time = time.time()
    first_event_sent = False
    final_status = "success"

    # 스테이지별 시작 시간 추적
    stage_start_times: dict[str, float] = {}

    # 요청 검증
    image_url = str(payload.image_url) if payload.image_url else None
    if not image_url:
        SSE_CONNECTIONS_ACTIVE.dec()
        SSE_REQUESTS_TOTAL.labels(status="failed").inc()
        yield _format_sse({"status": "error", "error": "IMAGE_URL_REQUIRED"})
        return

    # Task ID 생성
    task_id = str(uuid4())
    user_id = str(user.user_id)

    logger.info(
        "completion_stream_started",
        extra={
            "event_type": "completion_started",
            "task_id": task_id,
            "user_id": user_id,
            "image_url": image_url,
        },
    )

    # 1. Celery Events 수신 준비
    event_queue: asyncio.Queue[dict | None] = asyncio.Queue()
    loop = asyncio.get_event_loop()
    receiver_ready = threading.Event()  # Event Receiver 연결 완료 신호

    # Chain task IDs 추적
    chain_task_ids: set[str] = {task_id}
    task_name_map: dict[str, str] = {}

    # 마지막으로 received된 task 추적 (다음 task-sent 시 이전 task 완료 처리용)
    last_received_task: dict = {"task_id": None, "task_name": None}

    def _send_sse_event(task_name: str, status: str, result: dict | str | None = None) -> None:
        """SSE 이벤트 전송."""
        nonlocal first_event_sent, stage_start_times

        step_info = TASK_STEP_MAP.get(task_name, {})
        if not step_info:
            return

        step_name = step_info["step"]

        # 스테이지별 시간 추적
        if status == "started":
            stage_start_times[step_name] = time.time()
        elif status == "completed" and step_name in stage_start_times:
            duration = time.time() - stage_start_times[step_name]
            SSE_STAGE_DURATION.labels(stage=step_name).observe(duration)
            logger.info(
                "stage_completed",
                extra={
                    "task_id": task_id,
                    "stage": step_name,
                    "duration_seconds": round(duration, 3),
                },
            )

        # progress 계산: completed면 해당 단계 완료 값, started면 이전 단계 완료 값
        progress = (
            step_info["progress"] if status == "completed" else step_info.get("prev_progress", 0)
        )

        sse_data: dict = {
            "step": step_info["step"],
            "status": status,
            "progress": progress,
        }

        # TTFB 메트릭 (첫 이벤트 전송 시간)
        if not first_event_sent:
            ttfb = time.time() - chain_start_time
            SSE_TTFB.observe(ttfb)
            first_event_sent = True

        # reward 완료 시 최종 결과 포함
        if task_name == "scan.reward" and status == "completed":
            # Celery result 파싱 (Python repr 또는 JSON)
            parsed_result = _parse_celery_result(result) if result else {}

            # 파싱 결과 로깅
            logger.info(
                "reward_result_parsed",
                extra={
                    "task_id": task_id,
                    "parsed_keys": list(parsed_result.keys()) if parsed_result else [],
                    "has_classification": "classification_result" in parsed_result,
                    "has_disposal": "disposal_rules" in parsed_result,
                    "has_answer": "final_answer" in parsed_result,
                },
            )

            # 결과가 없어도 기본 구조 반환
            sse_data["result"] = {
                "task_id": parsed_result.get("task_id") or task_id,
                "status": "completed",
                "message": "classification completed",
                "pipeline_result": {
                    "classification_result": parsed_result.get("classification_result"),
                    "disposal_rules": parsed_result.get("disposal_rules"),
                    "final_answer": parsed_result.get("final_answer"),
                },
                "reward": parsed_result.get("reward"),
                "error": None,
            }

        loop.call_soon_threadsafe(event_queue.put_nowait, sse_data)

        if task_name == "scan.reward" and status in ("completed", "failed"):
            loop.call_soon_threadsafe(event_queue.put_nowait, None)

    def _is_chain_task(event: dict) -> bool:
        """이벤트가 현재 chain의 task인지 확인."""
        event_task_id = event.get("uuid", "")
        root_id = event.get("root_id")
        parent_id = event.get("parent_id")

        is_chain = (
            root_id == task_id
            or event_task_id == task_id
            or event_task_id in chain_task_ids
            or parent_id in chain_task_ids
        )

        if is_chain:
            chain_task_ids.add(event_task_id)
            if event.get("name"):
                task_name_map[event_task_id] = event.get("name")

        return is_chain

    def on_task_started(event: dict) -> None:
        """task-started: Worker가 task 실행 시작 → 'started' 상태.

        Note: task-started에는 name이 없을 수 있음, root_id로 매칭 후 task_name_map에서 조회.
        """
        if not _is_chain_task(event):
            return

        event_task_id = event.get("uuid", "")
        task_name = event.get("name", "") or task_name_map.get(event_task_id, "")

        # task-started가 오면 이전 task는 완료된 것
        if last_received_task["task_name"] and last_received_task["task_id"] != event_task_id:
            _send_sse_event(last_received_task["task_name"], "completed")

        if task_name:
            _send_sse_event(task_name, "started")
            last_received_task["task_id"] = event_task_id
            last_received_task["task_name"] = task_name

    def on_task_received(event: dict) -> None:
        """task-received: Worker가 task를 받음 → name 매핑용."""
        if not _is_chain_task(event):
            return

        # task-received에는 name이 있으므로 매핑 저장
        event_task_id = event.get("uuid", "")
        task_name = event.get("name", "")
        if task_name:
            task_name_map[event_task_id] = task_name

    def on_task_sent(event: dict) -> None:
        """task-sent: task 전송 → name 매핑용."""
        if not _is_chain_task(event):
            return

        # task-sent에도 name이 있으므로 매핑 저장
        event_task_id = event.get("uuid", "")
        task_name = event.get("name", "")
        if task_name:
            task_name_map[event_task_id] = task_name

    def on_task_succeeded(event: dict) -> None:
        """task-succeeded: task 성공 (result 포함)."""
        if not _is_chain_task(event):
            return

        event_task_id = event.get("uuid", "")
        task_name = event.get("name", "") or task_name_map.get(event_task_id, "")

        # 디버그 로깅: result 확인
        raw_result = event.get("result")
        logger.info(
            "task_succeeded_result_debug",
            extra={
                "task_id": task_id,
                "event_task_id": event_task_id,
                "task_name": task_name,
                "result_type": type(raw_result).__name__,
                "result_preview": str(raw_result)[:200] if raw_result else None,
            },
        )

        # scan.reward는 task-result 커스텀 이벤트에서 처리
        # task-succeeded의 result는 str 타입으로 dict 파싱이 불안정함
        # task-result 이벤트는 dict로 직접 전달되어 안정적
        if task_name == "scan.reward":
            logger.debug(
                "skip_task_succeeded_for_reward",
                extra={"task_id": task_id, "event_task_id": event_task_id},
            )
            return

        if task_name:
            _send_sse_event(task_name, "completed", result=raw_result)

    def on_task_result(event: dict) -> None:
        """task-result: 커스텀 이벤트 - scan.reward 완료 결과."""
        # 이 이벤트는 scan.reward task에서 직접 발행함
        event_task_id = event.get("task_id", "")
        event_root_id = event.get("root_id", "")

        # 현재 chain의 task인지 확인
        if event_task_id != task_id and event_root_id != task_id:
            return

        raw_result = event.get("result")
        logger.info(
            "task_result_event_received",
            extra={
                "task_id": task_id,
                "event_task_id": event_task_id,
                "result_type": type(raw_result).__name__,
                "result_keys": list(raw_result.keys()) if isinstance(raw_result, dict) else None,
            },
        )

        # scan.reward 완료 처리
        _send_sse_event("scan.reward", "completed", result=raw_result)

    def on_task_failed(event: dict) -> None:
        """task-failed: task 실패."""
        if not _is_chain_task(event):
            return

        event_task_id = event.get("uuid", "")
        task_name = event.get("name", "") or task_name_map.get(event_task_id, "")

        if task_name:
            _send_sse_event(task_name, "failed")

    def run_event_receiver() -> None:
        """Celery Event Receiver (별도 스레드) - ReadyAwareReceiver 사용."""
        import socket
        from itertools import count

        from celery.events.receiver import EventReceiver

        class ReadyAwareReceiver(EventReceiver):
            """Consumer 준비 완료 시점을 정확히 알려주는 Receiver."""

            def __init__(self, *args, ready_event=None, **kwargs):
                super().__init__(*args, **kwargs)
                self.ready_event = ready_event

            def consume(self, limit=None, timeout=None, safety_interval=1, **kwargs):
                """Consumer context 진입 후 ready 신호를 보내는 consume."""
                elapsed = 0
                with self.consumer_context(**kwargs) as (conn, channel, consumers):
                    # Consumer가 설정된 후 ready 신호 (큐 바인딩 완료!)
                    logger.info("event_receiver_consumer_ready", extra={"task_id": task_id})
                    if self.ready_event:
                        self.ready_event.set()

                    for i in limit and range(limit) or count():
                        if self.should_stop:
                            break
                        self.on_iteration()
                        try:
                            conn.drain_events(timeout=safety_interval)
                        except socket.timeout:
                            conn.heartbeat_check()
                            elapsed += safety_interval
                            if timeout and elapsed >= timeout:
                                raise
                        except OSError:
                            if not self.should_stop:
                                raise
                        else:
                            yield
                            elapsed = 0

        try:
            logger.info("event_receiver_connecting", extra={"task_id": task_id})
            with celery_app.connection() as connection:
                logger.info("event_receiver_connected", extra={"task_id": task_id})

                def on_any_event(event: dict) -> None:
                    """모든 이벤트 로깅 (디버깅용)."""
                    logger.info(
                        "celery_event_received",
                        extra={
                            "task_id": task_id,
                            "event_type": event.get("type"),
                            "event_uuid": event.get("uuid"),
                            "event_name": event.get("name"),
                        },
                    )

                recv = ReadyAwareReceiver(
                    connection,
                    handlers={
                        "task-sent": on_task_sent,
                        "task-received": on_task_received,
                        "task-started": on_task_started,
                        "task-succeeded": on_task_succeeded,
                        "task-failed": on_task_failed,
                        "task-result": on_task_result,  # 커스텀 이벤트
                        "*": on_any_event,
                    },
                    ready_event=receiver_ready,
                )
                recv.capture(limit=None, timeout=120, wakeup=True)
        except Exception as e:
            logger.exception("event_receiver_error", extra={"task_id": task_id, "error": str(e)})
            receiver_ready.set()  # 에러 시에도 진행
            loop.call_soon_threadsafe(event_queue.put_nowait, None)

    # 2. Event Receiver 시작 (백그라운드)
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(run_event_receiver)

    # 연결 대기 (최대 5초) - ReadyAwareReceiver가 consumer 준비 후 set()
    if not receiver_ready.wait(timeout=5.0):
        logger.warning("event_receiver_connect_timeout", extra={"task_id": task_id})

    # Sleep 불필요! receiver_ready는 consumer가 실제로 준비된 후에만 set됨

    # 3. Started 이벤트 전송 및 Chain 시작
    yield _format_sse({"status": "started", "task_id": task_id})

    try:
        first_task = vision_task.s(task_id, user_id, image_url, payload.user_input).set(
            task_id=task_id
        )

        pipeline = chain(
            first_task,
            rule_task.s(),
            answer_task.s(),
            scan_reward_task.s(),
        )
        pipeline.apply_async()

        logger.info(
            "completion_chain_dispatched",
            extra={
                "event_type": "chain_dispatched",
                "task_id": task_id,
                "user_id": user_id,
            },
        )
    except Exception as e:
        logger.exception("completion_chain_failed", extra={"task_id": task_id})
        yield _format_sse({"status": "error", "error": str(e)})
        future.cancel()
        executor.shutdown(wait=False)
        return

    try:
        timeout = 120
        start_time = asyncio.get_event_loop().time()

        while True:
            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=1.0)

                if event is None:
                    logger.info("completion_stream_ended", extra={"task_id": task_id})
                    break

                yield _format_sse(event)

                if event.get("step") == "reward" and event.get("status") in ("completed", "failed"):
                    if event.get("status") == "failed":
                        final_status = "failed"
                    break

            except asyncio.TimeoutError:
                elapsed = asyncio.get_event_loop().time() - start_time

                if elapsed > timeout:
                    logger.warning("completion_stream_timeout", extra={"task_id": task_id})
                    yield _format_sse({"status": "timeout", "task_id": task_id})
                    final_status = "timeout"
                    break

                # Keep-alive
                yield ": keepalive\n\n"

    finally:
        # 메트릭 기록
        chain_duration = time.time() - chain_start_time
        SSE_CHAIN_DURATION.observe(chain_duration)
        SSE_REQUESTS_TOTAL.labels(status=final_status).inc()
        SSE_CONNECTIONS_ACTIVE.dec()

        logger.info(
            "completion_stream_finished",
            extra={
                "task_id": task_id,
                "status": final_status,
                "duration_seconds": round(chain_duration, 3),
            },
        )

        future.cancel()
        executor.shutdown(wait=False)


def _format_sse(data: dict) -> str:
    """SSE 형식으로 포맷팅."""
    return f"data: {json.dumps(data)}\n\n"
