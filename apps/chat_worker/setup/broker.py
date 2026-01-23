"""Taskiq Broker Configuration.

RabbitMQ Topology Operator가 Exchange/Queue를 미리 생성하므로
declare_exchange=False로 설정하여 기존 리소스를 재사용합니다.

운영 환경에서는 K8s Topology 매니페스트가 다음을 생성:
- Exchange: chat_tasks (direct)
- Queue: chat.process (DLX, TTL 설정 포함)
- Binding: chat_tasks → chat.process

분산 트레이싱 통합:
- aio-pika Instrumentation으로 MQ 메시지 추적
- OpenAI Instrumentation으로 LLM API 호출 추적
- Jaeger/Kiali에서 API → MQ → Worker → LLM 흐름 추적 가능
"""

from __future__ import annotations

import logging
import os

from aio_pika import ExchangeType
from taskiq_aio_pika import AioPikaBroker

from chat_worker.setup.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# OpenTelemetry 활성화 여부
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "true").lower() == "true"

# 운영 환경: Topology Operator가 미리 생성한 Exchange/Queue 사용
# 로컬 환경: declare_exchange=True로 자동 생성 (fallback)
_is_production = settings.environment in ("production", "staging", "dev")

broker = AioPikaBroker(
    url=settings.rabbitmq_url,
    declare_exchange=not _is_production,  # 운영 환경에서는 기존 사용
    exchange_name="chat_tasks",
    exchange_type=ExchangeType.DIRECT,
    routing_key="chat.process",
    queue_name=settings.rabbitmq_queue,  # chat.process
)


def _setup_aio_pika_tracing() -> None:
    """aio-pika 분산 추적 설정."""
    if not OTEL_ENABLED:
        logger.info("aio-pika tracing disabled (OTEL_ENABLED=false)")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.aio_pika import AioPikaInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        # TracerProvider 설정
        resource = Resource.create(
            {
                "service.name": "chat-worker",
                "service.version": os.getenv("SERVICE_VERSION", "1.0.0"),
                "deployment.environment": settings.environment,
                "messaging.system": "rabbitmq",
            }
        )

        provider = TracerProvider(resource=resource)
        endpoint = os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "http://jaeger-collector-clusterip.istio-system.svc.cluster.local:4318",
        )
        exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        # aio-pika Instrumentation
        AioPikaInstrumentor().instrument()
        logger.info(
            "aio-pika tracing enabled",
            extra={"endpoint": endpoint, "service_name": "chat-worker"},
        )

    except ImportError as e:
        logger.warning(f"aio-pika tracing not available: {e}")
    except Exception as e:
        logger.error(f"Failed to setup aio-pika tracing: {e}")


def _setup_openai_tracing() -> None:
    """OpenAI LLM API 분산 추적 설정.

    OpenAI API 호출을 Jaeger에서 추적할 수 있도록 합니다.
    - Chat Completions (streaming 포함)
    - Embeddings
    - 토큰 사용량 메트릭

    환경변수:
    - OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true: 프롬프트/응답 내용 캡처
    """
    if not OTEL_ENABLED:
        logger.info("OpenAI tracing disabled (OTEL_ENABLED=false)")
        return

    try:
        from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

        OpenAIInstrumentor().instrument()
        logger.info("OpenAI instrumentation enabled (LLM API calls will be traced)")

    except ImportError:
        logger.warning(
            "OpenAI instrumentation not available. "
            "Install: pip install opentelemetry-instrumentation-openai-v2"
        )
    except Exception as e:
        logger.error(f"Failed to setup OpenAI tracing: {e}")


def _setup_gemini_tracing() -> None:
    """Gemini (Google Generative AI) 분산 추적 설정.

    Gemini API 호출을 Jaeger에서 추적할 수 있도록 합니다.
    - generateContent (streaming 포함)
    - 토큰 사용량 메트릭
    """
    if not OTEL_ENABLED:
        logger.info("Gemini tracing disabled (OTEL_ENABLED=false)")
        return

    try:
        from opentelemetry.instrumentation.google_generativeai import (
            GoogleGenerativeAiInstrumentor,
        )

        GoogleGenerativeAiInstrumentor().instrument()
        logger.info("Gemini instrumentation enabled (LLM API calls will be traced)")

    except ImportError:
        logger.warning(
            "Gemini instrumentation not available. "
            "Install: pip install opentelemetry-instrumentation-google-generativeai"
        )
    except Exception as e:
        logger.error(f"Failed to setup Gemini tracing: {e}")


def _setup_langsmith_otel() -> None:
    """LangSmith OpenTelemetry 통합 설정.

    LangGraph 파이프라인 추적을 Jaeger로 내보냅니다.
    """
    if not OTEL_ENABLED:
        logger.info("LangSmith OTEL disabled (OTEL_ENABLED=false)")
        return

    try:
        from chat_worker.setup.langsmith import configure_langsmith_otel

        configure_langsmith_otel()

    except Exception as e:
        logger.warning(f"LangSmith OTEL setup skipped: {e}")


async def _check_redis_connectivity() -> None:
    """Redis 연결 확인 (fast-fail).

    워커 시작 시 Redis 연결 가능 여부를 확인합니다.
    Redis 불가 시 워커가 작업을 수신해도 이벤트 발행 불가이므로
    빠르게 실패하여 K8s가 적절히 재시작하도록 합니다.

    Raises:
        ConnectionError: Redis 연결 불가 시
    """
    from redis.asyncio import Redis as AsyncRedis

    redis_url = settings.redis_url
    streams_url = settings.redis_streams_url or redis_url

    for name, url in [("cache", redis_url), ("streams", streams_url)]:
        try:
            client = AsyncRedis.from_url(
                url,
                socket_connect_timeout=5.0,
                socket_timeout=5.0,
            )
            await client.ping()
            await client.close()
            logger.info(f"Redis ({name}) connectivity OK: {url}")
        except Exception as e:
            logger.error(
                f"Redis ({name}) connectivity FAILED: {url} - {e}",
                extra={"redis_name": name, "url": url, "error": str(e)},
            )
            raise ConnectionError(f"Redis ({name}) unavailable at {url}: {e}") from e


async def startup():
    """브로커 시작."""
    # 0. Redis 연결 확인 (fast-fail)
    await _check_redis_connectivity()

    # 1. OpenTelemetry aio-pika 트레이싱 설정 (MQ 메시지)
    _setup_aio_pika_tracing()

    # 2. OpenTelemetry LLM 트레이싱 설정 (LLM API 호출)
    _setup_openai_tracing()
    _setup_gemini_tracing()

    # 3. LangSmith OTEL 통합 (LangGraph 추적 → Jaeger)
    _setup_langsmith_otel()

    # 4. Trace context 전파 미들웨어 등록
    if OTEL_ENABLED:
        from chat_worker.setup.tracing_middleware import TracingMiddleware

        broker.add_middlewares(TracingMiddleware())
        logger.info("Tracing middleware registered (trace context propagation enabled)")

    # 5. 브로커 시작
    await broker.startup()
    logger.info("Taskiq broker started")


async def shutdown():
    """브로커 종료."""
    await broker.shutdown()
    logger.info("Taskiq broker stopped")
