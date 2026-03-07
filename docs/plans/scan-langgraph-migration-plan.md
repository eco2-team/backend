# Scan API LangGraph 마이그레이션 계획

> Stateless Reducer + Dependency Injection + LangGraph 기반 마이그레이션
> 
> **목표**: 기존 Celery 파이프라인을 LangGraph로 전환하면서 기존 인프라(Redis Streams, SSE Gateway) 유지

---

## 1. 현재 구조 vs 목표 구조

### 1.1 현재 구조 (Celery + gevent)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         현재 구조 (Celery Chain)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   scan-api                                                                   │
│     │                                                                        │
│     └── POST /scan → Celery Chain 발행 ────────▶ RabbitMQ                   │
│                                                       │                      │
│                                                       ▼                      │
│   scan-worker (Celery + gevent)                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  vision_task → rule_task → answer_task → reward_task                │   │
│   │       │                         │                                    │   │
│   │       ▼                         ▼                                    │   │
│   │  waste_pipeline/vision.py   waste_pipeline/answer.py                │   │
│   │       │                         │                                    │   │
│   │       ▼                         ▼                                    │   │
│   │  OpenAI API (하드코딩)      OpenAI API (하드코딩)                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                         │                                                    │
│                         ▼                                                    │
│   Redis Streams (XADD) → Event Router → Pub/Sub → SSE Gateway → Client     │
│                                                                              │
│   문제점:                                                                    │
│   • LLM 하드코딩 (OpenAI만 지원)                                            │
│   • 상태 관리 분산 (Redis State KV + 태스크 간 전달)                        │
│   • 테스트 어려움 (부작용 많음)                                              │
│   • gevent + asyncio 충돌 가능성                                            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 목표 구조 (LangGraph + DI + Stateless Reducer)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              목표 구조 (LangGraph + Stateless Reducer + DI)                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   scan-api (FastAPI + LangGraph)                                            │
│     │                                                                        │
│     ├── POST /scan                                                          │
│     │     │                                                                  │
│     │     └── BackgroundTask 또는 aio-pika → RabbitMQ (선택)               │
│     │                                                                        │
│     └── GET /scan/stream/{task_id}                                          │
│           │                                                                  │
│           └── graph.astream_events() → SSE 직접 또는 Redis Pub/Sub         │
│                                                                              │
│   scan-worker (asyncio + LangGraph) [선택적 분리]                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  StateGraph (ScanState)                                              │   │
│   │       │                                                              │   │
│   │       ▼                                                              │   │
│   │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │   │
│   │  │ vision   │─▶│  rule    │─▶│  answer  │─▶│  reward  │            │   │
│   │  │  node    │  │  node    │  │  node    │  │  node    │            │   │
│   │  └────┬─────┘  └──────────┘  └────┬─────┘  └──────────┘            │   │
│   │       │ (Stateless Reducer)       │                                 │   │
│   │       ▼                           ▼                                 │   │
│   │  LLMClient Port              LLMClient Port                        │   │
│   │       │ (DI)                      │ (DI)                           │   │
│   │       ▼                           ▼                                 │   │
│   │  ┌──────────┐              ┌──────────┐                            │   │
│   │  │ OpenAI   │              │ Anthropic│  ← 런타임 선택 가능        │   │
│   │  │ Adapter  │              │ Adapter  │                            │   │
│   │  └──────────┘              └──────────┘                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                         │                                                    │
│                         ▼                                                    │
│   EventPublisher Port → Redis Streams → Event Router → SSE Gateway         │
│         (DI)                                                                │
│                                                                              │
│   장점:                                                                      │
│   • LLM 추상화 (OpenAI, Anthropic, Gemini 지원)                             │
│   • Stateless Reducer (테스트 용이, 재현성)                                 │
│   • DI로 의존성 교체 가능 (Mock 테스트)                                      │
│   • Checkpointer로 상태 복구                                                │
│   • asyncio 네이티브 (충돌 없음)                                            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 디렉토리 구조

```
apps/scan/
├── domain/                                 # 핵심 도메인 (의존성 없음)
│   ├── __init__.py
│   ├── entities/
│   │   └── scan_task.py                    # ScanTask 엔티티
│   ├── value_objects/
│   │   ├── classification.py               # Classification VO
│   │   └── disposal_rule.py                # DisposalRule VO
│   └── enums/
│       ├── scan_status.py                  # ScanStatus Enum
│       └── pipeline_stage.py               # PipelineStage Enum
│
├── application/                            # 유스케이스 (Port 의존)
│   ├── __init__.py
│   │
│   ├── common/                             # 공통 Port/DTO
│   │   ├── ports/
│   │   │   ├── llm_client.py               # LLMClient Port (ABC)
│   │   │   ├── event_publisher.py          # EventPublisher Port (ABC)
│   │   │   └── result_cache.py             # ResultCache Port (ABC)
│   │   └── dto/
│   │       └── scan_state.py               # ScanState (TypedDict)
│   │
│   ├── pipeline/                           # LangGraph 파이프라인
│   │   ├── __init__.py
│   │   ├── graph.py                        # StateGraph 정의
│   │   ├── nodes/                          # Stateless Reducer 노드들
│   │   │   ├── __init__.py
│   │   │   ├── vision_node.py              # Vision 분석 노드
│   │   │   ├── rule_node.py                # Rule 검색 노드
│   │   │   ├── answer_node.py              # Answer 생성 노드
│   │   │   └── reward_node.py              # Reward 처리 노드
│   │   └── callbacks/                      # LangGraph Callback
│   │       ├── __init__.py
│   │       └── event_callback.py           # Redis Streams 이벤트 발행
│   │
│   ├── commands/                           # 유스케이스
│   │   ├── start_scan.py                   # StartScanCommand
│   │   └── cancel_scan.py                  # CancelScanCommand
│   │
│   └── queries/
│       ├── get_result.py                   # GetResultQuery
│       └── get_progress.py                 # GetProgressQuery
│
├── infrastructure/                         # Port 구현체
│   ├── __init__.py
│   │
│   ├── llm/                                # LLM Adapters (DI)
│   │   ├── __init__.py
│   │   ├── factory.py                      # LLMFactory
│   │   ├── openai_adapter.py               # OpenAI 구현체
│   │   ├── anthropic_adapter.py            # Anthropic 구현체
│   │   └── gemini_adapter.py               # Gemini 구현체
│   │
│   ├── waste_pipeline/                     # 기존 로직 (프롬프트, 데이터)
│   │   ├── __init__.py
│   │   ├── prompts/                        # 프롬프트 템플릿
│   │   │   ├── vision_prompt.py
│   │   │   └── answer_prompt.py
│   │   ├── schemas/                        # Pydantic 스키마
│   │   │   ├── classification_schema.py
│   │   │   └── answer_schema.py
│   │   └── data/                           # 정적 데이터
│   │       ├── item_class_list.yaml
│   │       ├── situation_tags.yaml
│   │       └── source/*.json
│   │
│   ├── persistence_redis/                  # Redis 관련
│   │   ├── __init__.py
│   │   ├── event_publisher_impl.py         # EventPublisher 구현
│   │   ├── result_cache_impl.py            # ResultCache 구현
│   │   └── checkpointer.py                 # LangGraph Checkpointer
│   │
│   └── character_client/                   # 캐릭터 서비스 연동
│       ├── __init__.py
│       └── grpc_client.py                  # gRPC 클라이언트
│
├── presentation/                           # 진입점
│   ├── __init__.py
│   ├── http/
│   │   └── controllers/
│   │       ├── scan_controller.py          # POST /scan, GET /scan/{id}
│   │       └── stream_controller.py        # GET /scan/stream/{id}
│   └── background/                         # 백그라운드 실행 (선택)
│       └── worker.py                       # aio-pika Consumer
│
├── setup/                                  # 설정 및 DI
│   ├── __init__.py
│   ├── config.py                           # Settings
│   ├── dependencies.py                     # DI Container
│   └── lifespan.py                         # FastAPI Lifespan
│
├── tests/
│   ├── unit/
│   │   ├── test_vision_node.py
│   │   ├── test_rule_node.py
│   │   └── test_answer_node.py
│   └── integration/
│       └── test_pipeline.py
│
├── Dockerfile
├── main.py
└── requirements.txt
```

---

## 3. 핵심 코드 구현

### 3.1 ScanState (Stateless Reducer 상태)

```python
# application/common/dto/scan_state.py
from typing import TypedDict, Annotated
from operator import add

def merge_dict(existing: dict | None, new: dict) -> dict:
    """딕셔너리 병합 Reducer."""
    if existing is None:
        return new
    return {**existing, **new}

class ScanState(TypedDict):
    """Scan 파이프라인 상태 - Stateless Reducer 패턴.
    
    모든 노드는 이 상태를 읽고, 업데이트만 반환.
    StateGraph가 Reducer를 사용해 상태 병합.
    """
    # 입력 (불변)
    task_id: str
    user_id: str
    image_url: str
    user_input: str | None
    model: str  # LLM-as-Parameter (DI)
    
    # 파이프라인 결과 (각 노드가 업데이트)
    classification_result: dict | None
    disposal_rules: dict | None
    final_answer: dict | None
    reward: dict | None
    
    # 메타데이터 (Reducer로 누적)
    stage_history: Annotated[list[str], add]
    latencies: Annotated[dict, merge_dict]
    
    # 진행 상태
    progress: int
    error: str | None
```

### 3.2 LLMClient Port (DI 인터페이스)

```python
# application/common/ports/llm_client.py
from abc import ABC, abstractmethod
from typing import Any, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

class LLMClient(ABC):
    """LLM 클라이언트 Port - DI 인터페이스.
    
    구현체: OpenAIAdapter, AnthropicAdapter, GeminiAdapter
    """
    
    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, Any]],
        response_schema: type[T] | None = None,
        **kwargs,
    ) -> T | str:
        """텍스트 완성 (Structured Output 지원)."""
        pass
    
    @abstractmethod
    async def complete_with_vision(
        self,
        messages: list[dict[str, Any]],
        image_url: str,
        response_schema: type[T] | None = None,
        **kwargs,
    ) -> T | str:
        """Vision API 호출."""
        pass
```

### 3.3 EventPublisher Port

```python
# application/common/ports/event_publisher.py
from abc import ABC, abstractmethod
from typing import Any

class EventPublisher(ABC):
    """이벤트 발행 Port - DI 인터페이스.
    
    구현체: RedisStreamsPublisher
    """
    
    @abstractmethod
    async def publish_stage_event(
        self,
        task_id: str,
        stage: str,
        status: str,
        progress: int,
        result: dict[str, Any] | None = None,
    ) -> None:
        """파이프라인 스테이지 이벤트 발행."""
        pass
```

### 3.4 Vision Node (Stateless Reducer)

```python
# application/pipeline/nodes/vision_node.py
import time
from typing import Callable

from apps.scan.application.common.dto.scan_state import ScanState
from apps.scan.application.common.ports.llm_client import LLMClient
from apps.scan.infrastructure.waste_pipeline.prompts.vision_prompt import build_vision_prompt
from apps.scan.infrastructure.waste_pipeline.schemas.classification_schema import ClassificationSchema


def create_vision_node(llm_client: LLMClient) -> Callable[[ScanState], dict]:
    """Vision 노드 생성 - DI로 LLMClient 주입.
    
    Args:
        llm_client: 주입된 LLM 클라이언트
    
    Returns:
        Stateless Reducer 노드 함수
    """
    
    async def vision_node(state: ScanState) -> dict:
        """Vision 분석 노드 - Stateless Reducer.
        
        • 상태를 읽기만 함 (수정 X)
        • 업데이트만 반환
        • 순수 함수 (동일 입력 → 동일 출력)
        """
        start = time.perf_counter()
        
        # 1. 상태에서 입력 읽기
        image_url = state["image_url"]
        user_input = state["user_input"] or "이 폐기물을 어떻게 분리배출해야 하나요?"
        
        # 2. 프롬프트 생성 (기존 waste_pipeline 로직 재사용)
        messages = build_vision_prompt(user_input)
        
        # 3. LLM 호출 (DI된 클라이언트 사용)
        try:
            result = await llm_client.complete_with_vision(
                messages=messages,
                image_url=image_url,
                response_schema=ClassificationSchema,
            )
            classification = result.model_dump()
            error = None
        except Exception as e:
            classification = None
            error = f"Vision analysis failed: {str(e)}"
        
        elapsed = time.perf_counter() - start
        
        # 4. 업데이트만 반환 (Stateless)
        return {
            "classification_result": classification,
            "stage_history": ["vision"],
            "latencies": {"vision_ms": elapsed * 1000},
            "progress": 25,
            "error": error,
        }
    
    return vision_node
```

### 3.5 Rule Node (Stateless Reducer)

```python
# application/pipeline/nodes/rule_node.py
import time
from apps.scan.application.common.dto.scan_state import ScanState
from apps.scan.infrastructure.waste_pipeline.rag import get_disposal_rules


async def rule_node(state: ScanState) -> dict:
    """Rule 검색 노드 - Stateless Reducer.
    
    LLM 호출 없음 → DI 불필요.
    기존 waste_pipeline/rag.py 재사용.
    """
    start = time.perf_counter()
    
    # 이전 노드 결과 읽기
    classification = state.get("classification_result")
    
    if classification is None:
        return {
            "disposal_rules": None,
            "stage_history": ["rule_skipped"],
            "latencies": {"rule_ms": 0},
            "progress": 50,
        }
    
    # 규정 검색 (기존 로직)
    try:
        rules = get_disposal_rules(classification)
        error = None
    except Exception as e:
        rules = None
        error = f"Rule retrieval failed: {str(e)}"
    
    elapsed = time.perf_counter() - start
    
    return {
        "disposal_rules": rules,
        "stage_history": ["rule"],
        "latencies": {"rule_ms": elapsed * 1000},
        "progress": 50,
        "error": error if error else state.get("error"),
    }
```

### 3.6 Answer Node (Stateless Reducer + DI)

```python
# application/pipeline/nodes/answer_node.py
import time
from typing import Callable

from apps.scan.application.common.dto.scan_state import ScanState
from apps.scan.application.common.ports.llm_client import LLMClient
from apps.scan.infrastructure.waste_pipeline.prompts.answer_prompt import build_answer_prompt
from apps.scan.infrastructure.waste_pipeline.schemas.answer_schema import AnswerSchema


def create_answer_node(llm_client: LLMClient) -> Callable[[ScanState], dict]:
    """Answer 노드 생성 - DI로 LLMClient 주입."""
    
    async def answer_node(state: ScanState) -> dict:
        """Answer 생성 노드 - Stateless Reducer."""
        start = time.perf_counter()
        
        classification = state.get("classification_result")
        rules = state.get("disposal_rules")
        
        if classification is None or rules is None:
            return {
                "final_answer": {
                    "disposal_steps": {},
                    "insufficiencies": ["분류 또는 규정 정보 없음"],
                    "user_answer": "죄송합니다. 분석에 실패했습니다.",
                },
                "stage_history": ["answer_fallback"],
                "latencies": {"answer_ms": 0},
                "progress": 75,
            }
        
        messages = build_answer_prompt(classification, rules)
        
        try:
            result = await llm_client.complete(
                messages=messages,
                response_schema=AnswerSchema,
            )
            answer = result.model_dump()
            error = None
        except Exception as e:
            answer = {
                "disposal_steps": {},
                "insufficiencies": [str(e)],
                "user_answer": "답변 생성에 실패했습니다.",
            }
            error = f"Answer generation failed: {str(e)}"
        
        elapsed = time.perf_counter() - start
        
        return {
            "final_answer": answer,
            "stage_history": ["answer"],
            "latencies": {"answer_ms": elapsed * 1000},
            "progress": 75,
            "error": error if error else state.get("error"),
        }
    
    return answer_node
```

### 3.7 Reward Node (Stateless Reducer)

```python
# application/pipeline/nodes/reward_node.py
import time
from typing import Callable

from apps.scan.application.common.dto.scan_state import ScanState
from apps.scan.infrastructure.character_client.grpc_client import CharacterClient


def create_reward_node(character_client: CharacterClient) -> Callable[[ScanState], dict]:
    """Reward 노드 생성 - DI로 CharacterClient 주입."""
    
    async def reward_node(state: ScanState) -> dict:
        """Reward 처리 노드 - Stateless Reducer."""
        start = time.perf_counter()
        
        classification = state.get("classification_result")
        rules = state.get("disposal_rules")
        answer = state.get("final_answer")
        
        # 보상 조건 체크
        if not _should_attempt_reward(classification, rules, answer):
            return {
                "reward": None,
                "stage_history": ["reward_skipped"],
                "latencies": {"reward_ms": 0},
                "progress": 100,
            }
        
        try:
            reward = await character_client.match_character(
                user_id=state["user_id"],
                classification=classification,
                disposal_rules_present=rules is not None,
            )
            
            if reward and reward.get("received"):
                # 비동기 저장 (Fire & Forget)
                await character_client.save_ownership_async(
                    user_id=state["user_id"],
                    character_id=reward.get("character_id"),
                )
        except Exception as e:
            reward = None
        
        elapsed = time.perf_counter() - start
        
        return {
            "reward": reward,
            "stage_history": ["reward"],
            "latencies": {"reward_ms": elapsed * 1000},
            "progress": 100,
        }
    
    return reward_node


def _should_attempt_reward(classification, rules, answer) -> bool:
    """보상 시도 조건 체크."""
    if not classification:
        return False
    if not rules:
        return False
    if answer and answer.get("insufficiencies"):
        return False
    return True
```

### 3.8 StateGraph 정의

```python
# application/pipeline/graph.py
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.redis import RedisSaver

from apps.scan.application.common.dto.scan_state import ScanState
from apps.scan.application.common.ports.llm_client import LLMClient
from apps.scan.application.pipeline.nodes.vision_node import create_vision_node
from apps.scan.application.pipeline.nodes.rule_node import rule_node
from apps.scan.application.pipeline.nodes.answer_node import create_answer_node
from apps.scan.application.pipeline.nodes.reward_node import create_reward_node
from apps.scan.infrastructure.character_client.grpc_client import CharacterClient


def create_scan_graph(
    llm_client: LLMClient,
    character_client: CharacterClient,
    checkpointer: RedisSaver | None = None,
) -> StateGraph:
    """Scan 파이프라인 그래프 생성.
    
    Args:
        llm_client: LLM 클라이언트 (DI)
        character_client: 캐릭터 서비스 클라이언트 (DI)
        checkpointer: 체크포인터 (상태 저장/복구)
    
    Returns:
        컴파일된 StateGraph
    """
    # Stateless Reducer 노드 생성 (DI 주입)
    vision_node = create_vision_node(llm_client)
    answer_node = create_answer_node(llm_client)
    reward_node = create_reward_node(character_client)
    
    # 그래프 구성
    builder = StateGraph(ScanState)
    
    # 노드 추가
    builder.add_node("vision", vision_node)
    builder.add_node("rule", rule_node)
    builder.add_node("answer", answer_node)
    builder.add_node("reward", reward_node)
    
    # 엣지 추가 (순차 실행)
    builder.add_edge(START, "vision")
    builder.add_edge("vision", "rule")
    builder.add_edge("rule", "answer")
    builder.add_edge("answer", "reward")
    builder.add_edge("reward", END)
    
    # 컴파일 (체크포인터 연결)
    return builder.compile(checkpointer=checkpointer)
```

### 3.9 Event Callback (Redis Streams 연동)

```python
# application/pipeline/callbacks/event_callback.py
from langchain_core.callbacks import BaseCallbackHandler
from apps.scan.application.common.ports.event_publisher import EventPublisher


class RedisStreamsEventCallback(BaseCallbackHandler):
    """LangGraph 이벤트를 Redis Streams로 발행하는 Callback.
    
    기존 SSE Gateway와 호환 유지.
    """
    
    PROGRESS_MAP = {
        "vision": 25,
        "rule": 50,
        "answer": 75,
        "reward": 100,
    }
    
    def __init__(self, event_publisher: EventPublisher, task_id: str):
        self.event_publisher = event_publisher
        self.task_id = task_id
    
    async def on_chain_start(self, serialized, inputs, **kwargs):
        """노드 시작."""
        node_name = kwargs.get("name", "unknown")
        if node_name in self.PROGRESS_MAP:
            await self.event_publisher.publish_stage_event(
                task_id=self.task_id,
                stage=node_name,
                status="started",
                progress=self.PROGRESS_MAP.get(node_name, 0) - 25,
            )
    
    async def on_chain_end(self, outputs, **kwargs):
        """노드 완료."""
        node_name = kwargs.get("name", "unknown")
        if node_name in self.PROGRESS_MAP:
            await self.event_publisher.publish_stage_event(
                task_id=self.task_id,
                stage=node_name,
                status="completed",
                progress=self.PROGRESS_MAP.get(node_name, 0),
                result=outputs if node_name == "reward" else None,
            )
```

### 3.10 LLM Factory (DI Container)

```python
# infrastructure/llm/factory.py
from apps.scan.application.common.ports.llm_client import LLMClient
from apps.scan.infrastructure.llm.openai_adapter import OpenAIAdapter
from apps.scan.infrastructure.llm.anthropic_adapter import AnthropicAdapter
from apps.scan.infrastructure.llm.gemini_adapter import GeminiAdapter


class LLMFactory:
    """LLM Factory - 모델명으로 적절한 Adapter 생성."""
    
    MODEL_MAPPING = {
        # OpenAI
        "gpt-4o": OpenAIAdapter,
        "gpt-4o-mini": OpenAIAdapter,
        "gpt-4-turbo": OpenAIAdapter,
        # Anthropic
        "claude-3-5-sonnet-20241022": AnthropicAdapter,
        "claude-3-opus-20240229": AnthropicAdapter,
        # Google
        "gemini-1.5-pro": GeminiAdapter,
        "gemini-1.5-flash": GeminiAdapter,
    }
    
    @classmethod
    def create(cls, model: str) -> LLMClient:
        """모델명으로 LLM 클라이언트 생성."""
        adapter_class = cls.MODEL_MAPPING.get(model)
        if adapter_class is None:
            raise ValueError(f"Unknown model: {model}")
        
        return adapter_class(model=model)
```

### 3.11 Dependencies (DI 설정)

```python
# setup/dependencies.py
from functools import lru_cache
import redis.asyncio as aioredis
from langgraph.checkpoint.redis import RedisSaver

from apps.scan.application.common.ports.llm_client import LLMClient
from apps.scan.application.common.ports.event_publisher import EventPublisher
from apps.scan.infrastructure.llm.factory import LLMFactory
from apps.scan.infrastructure.persistence_redis.event_publisher_impl import RedisStreamsPublisher
from apps.scan.infrastructure.character_client.grpc_client import CharacterClient
from apps.scan.application.pipeline.graph import create_scan_graph
from apps.scan.setup.config import get_settings

settings = get_settings()


@lru_cache
def get_redis_client():
    """Redis 클라이언트 (싱글톤)."""
    return aioredis.from_url(settings.redis_url)


@lru_cache
def get_checkpointer():
    """LangGraph Checkpointer (싱글톤)."""
    return RedisSaver(get_redis_client())


def get_llm_client(model: str) -> LLMClient:
    """LLM 클라이언트 생성 (요청별)."""
    return LLMFactory.create(model)


def get_event_publisher() -> EventPublisher:
    """이벤트 발행자."""
    return RedisStreamsPublisher(get_redis_client())


def get_character_client() -> CharacterClient:
    """캐릭터 서비스 클라이언트."""
    return CharacterClient(settings.character_grpc_url)


def get_scan_graph(model: str = "gpt-4o"):
    """Scan 그래프 생성 (요청별 LLM 선택)."""
    return create_scan_graph(
        llm_client=get_llm_client(model),
        character_client=get_character_client(),
        checkpointer=get_checkpointer(),
    )
```

### 3.12 HTTP Controller

```python
# presentation/http/controllers/scan_controller.py
from fastapi import APIRouter, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from uuid import uuid4
import json

from apps.scan.setup.dependencies import (
    get_scan_graph,
    get_event_publisher,
)
from apps.scan.application.pipeline.callbacks.event_callback import RedisStreamsEventCallback
from apps.scan.application.common.dto.scan_state import ScanState

router = APIRouter(prefix="/scan", tags=["scan"])


@router.post("")
async def create_scan(
    request: ScanRequest,
    background_tasks: BackgroundTasks,
    model: str = Query("gpt-4o", description="LLM 모델 선택"),
):
    """스캔 요청 생성.
    
    model 파라미터로 LLM 선택 (LLM-as-Parameter 패턴).
    """
    task_id = str(uuid4())
    
    # 초기 상태 (Stateless Reducer 입력)
    initial_state: ScanState = {
        "task_id": task_id,
        "user_id": request.user_id,
        "image_url": request.image_url,
        "user_input": request.user_input,
        "model": model,
        "classification_result": None,
        "disposal_rules": None,
        "final_answer": None,
        "reward": None,
        "stage_history": [],
        "latencies": {},
        "progress": 0,
        "error": None,
    }
    
    # 백그라운드 실행
    background_tasks.add_task(
        run_scan_pipeline,
        task_id=task_id,
        initial_state=initial_state,
        model=model,
    )
    
    return {
        "task_id": task_id,
        "stream_url": f"/api/v1/scan/stream/{task_id}",
        "result_url": f"/api/v1/scan/result/{task_id}",
    }


async def run_scan_pipeline(task_id: str, initial_state: ScanState, model: str):
    """백그라운드에서 파이프라인 실행."""
    graph = get_scan_graph(model)
    event_publisher = get_event_publisher()
    
    # Callback으로 이벤트 발행
    callback = RedisStreamsEventCallback(event_publisher, task_id)
    
    config = {
        "configurable": {"thread_id": task_id},
        "callbacks": [callback],
    }
    
    await graph.ainvoke(initial_state, config=config)


@router.get("/stream/{task_id}")
async def stream_scan(task_id: str):
    """SSE 스트리밍 (LangGraph astream_events 사용).
    
    기존 SSE Gateway 대신 직접 스트리밍도 가능.
    """
    graph = get_scan_graph()
    
    async def sse_generator():
        config = {"configurable": {"thread_id": task_id}}
        
        async for event in graph.astream_events(
            None,  # 기존 체크포인트에서 재개
            config=config,
            version="v2"
        ):
            kind = event["event"]
            
            if kind == "on_chain_end":
                node_name = event.get("name")
                outputs = event["data"].get("output", {})
                
                sse_data = {
                    "step": node_name,
                    "status": "completed",
                    "progress": outputs.get("progress", 0),
                }
                yield f"event: stage\ndata: {json.dumps(sse_data)}\n\n"
            
            elif kind == "on_chain_end" and event.get("name") == "reward":
                # 최종 결과
                final = event["data"].get("output", {})
                yield f"event: done\ndata: {json.dumps(final)}\n\n"
    
    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
    )
```

---

## 4. 마이그레이션 단계

### Phase 1: 인프라 준비 (1일)

| 작업 | 설명 | 시간 |
|------|------|------|
| LangChain/LangGraph 의존성 추가 | `langchain`, `langgraph`, `langgraph-checkpoint-redis` | 0.5h |
| 디렉토리 구조 생성 | `apps/scan/` 폴더 구조 | 0.5h |
| Config 설정 | Settings, 환경변수 | 0.5h |
| Redis Checkpointer 설정 | LangGraph 상태 저장 | 0.5h |

### Phase 2: Port/Adapter 구현 (1일)

| 작업 | 설명 | 시간 |
|------|------|------|
| LLMClient Port | ABC 정의 | 0.5h |
| OpenAI Adapter | LangChain ChatOpenAI 래핑 | 1h |
| Anthropic Adapter | LangChain ChatAnthropic 래핑 | 1h |
| EventPublisher | Redis Streams 발행 | 1h |
| LLMFactory | 모델별 Adapter 생성 | 0.5h |

### Phase 3: Stateless Reducer 노드 구현 (1.5일)

| 작업 | 설명 | 시간 |
|------|------|------|
| ScanState 정의 | TypedDict + Reducer | 0.5h |
| vision_node | DI + Stateless | 2h |
| rule_node | 기존 로직 재사용 | 1h |
| answer_node | DI + Stateless | 2h |
| reward_node | DI + Stateless | 2h |

### Phase 4: StateGraph 구성 (0.5일)

| 작업 | 설명 | 시간 |
|------|------|------|
| graph.py | StateGraph 정의 | 1h |
| Event Callback | Redis Streams 연동 | 1h |
| Dependencies | DI Container | 1h |

### Phase 5: Presentation Layer (0.5일)

| 작업 | 설명 | 시간 |
|------|------|------|
| scan_controller.py | POST /scan, GET /result | 2h |
| stream_controller.py | GET /stream (선택) | 1h |

### Phase 6: 테스트 (1일)

| 작업 | 설명 | 시간 |
|------|------|------|
| Unit Tests | 각 노드 개별 테스트 | 2h |
| Integration Tests | 전체 파이프라인 | 2h |
| E2E Tests | 실제 API 테스트 | 2h |

### Phase 7: 배포 및 검증 (0.5일)

| 작업 | 설명 | 시간 |
|------|------|------|
| Canary 배포 | 10% 트래픽 | 1h |
| 모니터링 | 결과 비교 | 2h |
| 전체 전환 | 100% 트래픽 | 1h |

---

## 5. 테스트 전략

### 5.1 Unit Test (Stateless Reducer)

```python
# tests/unit/test_vision_node.py
import pytest
from unittest.mock import AsyncMock

from apps.scan.application.pipeline.nodes.vision_node import create_vision_node
from apps.scan.application.common.dto.scan_state import ScanState


@pytest.fixture
def mock_llm_client():
    """Mock LLM 클라이언트."""
    client = AsyncMock()
    client.complete_with_vision.return_value = MockClassification(
        major_category="재활용",
        middle_category="플라스틱",
        minor_category="PET",
    )
    return client


@pytest.mark.asyncio
async def test_vision_node_returns_update_only(mock_llm_client):
    """Vision 노드가 업데이트만 반환하는지 검증."""
    # Given
    node = create_vision_node(mock_llm_client)
    state: ScanState = {
        "task_id": "test-123",
        "user_id": "user-456",
        "image_url": "https://example.com/image.jpg",
        "user_input": "이것을 어떻게 버려야 하나요?",
        "model": "gpt-4o",
        "classification_result": None,
        "disposal_rules": None,
        "final_answer": None,
        "reward": None,
        "stage_history": [],
        "latencies": {},
        "progress": 0,
        "error": None,
    }
    
    # When
    update = await node(state)
    
    # Then
    assert "classification_result" in update
    assert update["progress"] == 25
    assert "vision" in update["stage_history"]
    
    # 원본 상태가 변경되지 않았는지 확인 (Stateless)
    assert state["classification_result"] is None
    assert state["progress"] == 0


@pytest.mark.asyncio
async def test_vision_node_error_handling(mock_llm_client):
    """Vision 노드 에러 핸들링 검증."""
    mock_llm_client.complete_with_vision.side_effect = TimeoutError("API timeout")
    node = create_vision_node(mock_llm_client)
    
    state = create_test_state()
    update = await node(state)
    
    assert update["classification_result"] is None
    assert "error" in update
    assert "timeout" in update["error"].lower()
```

### 5.2 Integration Test (전체 파이프라인)

```python
# tests/integration/test_pipeline.py
import pytest
from apps.scan.application.pipeline.graph import create_scan_graph
from apps.scan.infrastructure.llm.openai_adapter import OpenAIAdapter


@pytest.mark.asyncio
async def test_full_pipeline():
    """전체 파이프라인 통합 테스트."""
    # Given: 실제 LLM 클라이언트 (테스트 환경)
    llm_client = OpenAIAdapter(model="gpt-4o-mini")  # 비용 절감
    graph = create_scan_graph(llm_client, mock_character_client)
    
    initial_state = {
        "task_id": "test-integration",
        "user_id": "test-user",
        "image_url": "https://example.com/plastic.jpg",
        "user_input": "플라스틱 병 버리는 법",
        "model": "gpt-4o-mini",
        # ... 나머지 초기화
    }
    
    # When
    result = await graph.ainvoke(initial_state)
    
    # Then
    assert result["progress"] == 100
    assert result["classification_result"] is not None
    assert len(result["stage_history"]) == 4
```

---

## 6. 기존 인프라 호환성

### 6.1 유지되는 인프라

| 구성 요소 | 역할 | 변경 사항 |
|----------|------|----------|
| **Redis Streams** | 이벤트 내구성 | Event Callback으로 발행 |
| **Event Router** | Streams → Pub/Sub | 변경 없음 |
| **SSE Gateway** | 클라이언트 연결 | 변경 없음 |
| **Redis Cluster** | 캐시, Checkpointer | Checkpointer 추가 |

### 6.2 제거/대체되는 인프라

| 구성 요소 | 현재 역할 | 전환 후 |
|----------|----------|--------|
| **RabbitMQ** | Celery Broker | 선택적 유지 (분산 Worker) |
| **Celery** | 태스크 오케스트레이션 | LangGraph StateGraph로 대체 |
| **gevent pool** | 비동기 처리 | asyncio로 대체 |

---

## 7. 예상 일정

| Phase | 작업 | 기간 |
|-------|------|------|
| Phase 1 | 인프라 준비 | 1일 |
| Phase 2 | Port/Adapter 구현 | 1일 |
| Phase 3 | Stateless Reducer 노드 | 1.5일 |
| Phase 4 | StateGraph 구성 | 0.5일 |
| Phase 5 | Presentation Layer | 0.5일 |
| Phase 6 | 테스트 | 1일 |
| Phase 7 | 배포 및 검증 | 0.5일 |
| **총계** | | **6일** |

---

## 8. 리스크 및 완화 전략

| 리스크 | 완화 전략 |
|--------|----------|
| LangGraph 학습 곡선 | 문서화된 패턴 따르기, 점진적 도입 |
| 기존 SSE 호환성 | Event Callback으로 동일 형식 유지 |
| 성능 저하 | 벤치마크 후 조정, asyncio 최적화 |
| LLM Provider 장애 | Fallback Chain 구현 (OpenAI → Anthropic) |

---

## 9. 승인 후 진행

이 계획이 승인되면 Phase 1부터 순차적으로 진행합니다.

