# Chat 서비스 구현 Phase 5: Setup & DI

> 설정 관리, 의존성 주입, 그리고 앱 라이프사이클

---

## 1. 왜 Setup Layer가 필요한가

Clean Architecture에서 Setup Layer는 **가장 바깥 원**입니다:

```
┌─────────────────────────────────────────┐
│              Setup Layer                 │  ← 여기
│  ┌───────────────────────────────┐      │
│  │        Presentation           │      │
│  │    ┌───────────────────┐      │      │
│  │    │   Infrastructure  │      │      │
│  │    │    ┌─────────┐    │      │      │
│  │    │    │  App    │    │      │      │
│  │    │    │ ┌─────┐ │    │      │      │
│  │    │    │ │Dom. │ │    │      │      │
│  │    │    │ └─────┘ │    │      │      │
│  │    │    └─────────┘    │      │      │
│  │    └───────────────────┘      │      │
│  └───────────────────────────────┘      │
└─────────────────────────────────────────┘
```

**Setup Layer의 책임:**

1. 환경 설정 로드 (Config)
2. 의존성 조립 (DI Container)
3. 앱 라이프사이클 관리 (Startup/Shutdown)

---

## 2. Config: Pydantic Settings

### 2.1 설정 클래스

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CHAT_",
        extra="ignore",
    )

    # 환경
    environment: Literal["dev", "staging", "prod"] = "dev"
    
    # LLM
    default_provider: Literal["openai", "anthropic", "gemini"]
    openai_api_key: str
    
    # Redis
    redis_streams_url: str
    redis_cache_url: str
```

**Pydantic Settings 선택 이유:**

| 대안 | 단점 |
|------|------|
| `os.environ` | 타입 검증 없음, 기본값 관리 어려움 |
| `python-dotenv` | 타입 검증 없음 |
| `dynaconf` | 과도한 기능, 복잡함 |
| **Pydantic** | ✓ 타입 검증, IDE 자동완성, 문서화 |

### 2.2 환경변수 우선순위

```
1. 환경변수 (CHAT_OPENAI_API_KEY)
2. .env 파일
3. 기본값
```

```bash
# Kubernetes Secret으로 주입
CHAT_OPENAI_API_KEY=sk-xxx
CHAT_REDIS_STREAMS_URL=redis://redis:6379/0
```

### 2.3 싱글톤 패턴

```python
@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤."""
    return Settings()
```

**`@lru_cache`의 효과:**

```
첫 호출: Settings() 생성, .env 파싱
이후 호출: 캐시된 인스턴스 반환 (O(1))
```

---

## 3. DI Container: Lazy Initialization

### 3.1 Container 클래스

```python
class Container:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._instances: dict = {}

    @property
    def llm(self) -> LLMPort:
        if "llm" not in self._instances:
            self._instances["llm"] = self._create_llm()
        return self._instances["llm"]
```

**Lazy Initialization의 장점:**

```
Eager (즉시 생성):
  Container.__init__():
    self.llm = OpenAIClient()  # 항상 생성
    self.redis = Redis()       # 항상 연결

Lazy (필요시 생성):
  Container.llm:  # 첫 접근 시에만 생성
```

- 테스트 시 불필요한 연결 회피
- 실패 지점 명확화
- 메모리 효율

### 3.2 Provider 기반 생성

```python
@property
def llm(self) -> LLMPort:
    if "llm" not in self._instances:
        provider = self._settings.default_provider
        
        if provider == "openai":
            client = OpenAILLMClient(
                model=self._settings.openai_model,
                api_key=self._settings.openai_api_key,
            )
        elif provider == "anthropic":
            client = AnthropicLLMClient(...)
        else:
            client = OpenAILLMClient(...)  # fallback
        
        self._instances["llm"] = client
    
    return self._instances["llm"]
```

**런타임 Provider 선택:**

```yaml
# dev.env
CHAT_DEFAULT_PROVIDER=openai

# prod.env  
CHAT_DEFAULT_PROVIDER=anthropic
```

### 3.3 그래프 의존성 조립

```python
@property
def chat_graph(self) -> CompiledStateGraph:
    if "chat_graph" not in self._instances:
        self._instances["chat_graph"] = create_chat_graph(
            llm=self.llm,               # LLMPort
            retriever=self.retriever,   # RetrieverPort
            event_publisher=self.event_publisher,  # EventPublisherPort
        )
    return self._instances["chat_graph"]
```

**의존성 그래프:**

```
chat_graph
    ├── llm (OpenAILLMClient)
    ├── retriever (LocalJSONRetriever)
    └── event_publisher (RedisEventPublisher)
            └── redis_streams (Redis)
```

---

## 4. App Factory: FastAPI Lifespan

### 4.1 Lifespan Context Manager

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 라이프사이클."""
    # Startup
    logger.info("Chat service starting...")
    container = get_container()
    
    yield  # 앱 실행 중
    
    # Shutdown
    logger.info("Chat service shutting down...")
    await container.close()
```

**Lifespan의 역할:**

```
서버 시작
    │
    ▼
┌─────────────┐
│   Startup   │  ← 리소스 초기화
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Running   │  ← 요청 처리
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Shutdown   │  ← 리소스 정리
└─────────────┘
```

### 4.2 App Factory 패턴

```python
def create_app() -> FastAPI:
    settings = get_settings()
    
    app = FastAPI(
        title="Eco² Chat API",
        docs_url="/docs" if settings.debug else None,
        lifespan=lifespan,
    )
    
    # CORS
    app.add_middleware(CORSMiddleware, ...)
    
    # 라우터
    app.include_router(chat_router, prefix="/api/v1")
    
    return app
```

**Factory 패턴의 장점:**

```
# 테스트에서
def test_api():
    app = create_app()  # 독립 인스턴스
    client = TestClient(app)
    
# 프로덕션에서
app = create_app()  # 단일 인스턴스
```

---

## 5. Worker Setup: Taskiq

### 5.1 Broker 설정

```python
from taskiq_aio_pika import AioPikaBroker

broker = AioPikaBroker(
    url=settings.rabbitmq_url,
    queue_name="chat_tasks",
    exchange_name="chat_exchange",
)
```

**RabbitMQ 선택 이유:**

| Broker | 장점 | 단점 |
|--------|------|------|
| Redis | 간단, 빠름 | 메시지 유실 가능 |
| **RabbitMQ** | 신뢰성, 기존 인프라 | 복잡함 |
| Kafka | 대용량, 리플레이 | 과도함 |

Eco² 프로젝트는 이미 RabbitMQ를 사용 중 (scan_worker).

### 5.2 Worker 실행

```bash
# Taskiq Worker 실행
taskiq worker chat_worker.main:broker \
    --workers 4 \
    --max-async-tasks 10
```

```python
# chat_worker/main.py
from chat_worker.setup.broker import broker
from chat_worker.tasks import process_chat  # 자동 등록

__all__ = ["broker"]
```

---

## 6. 디렉토리 구조

```
apps/chat/
├── setup/
│   ├── __init__.py
│   ├── config.py          # Settings
│   └── dependencies.py    # Container
├── main.py                # create_app()
└── ...

apps/chat_worker/
├── setup/
│   ├── __init__.py
│   ├── config.py          # Settings
│   └── broker.py          # Taskiq Broker
├── main.py                # Worker entry
└── tasks/
    └── process.py
```

---

## 7. 환경별 설정

### 7.1 Local (개발)

```bash
# .env.local
CHAT_ENVIRONMENT=dev
CHAT_DEBUG=true
CHAT_DEFAULT_PROVIDER=openai
CHAT_REDIS_STREAMS_URL=redis://localhost:6379/0
CHAT_RABBITMQ_URL=amqp://guest:guest@localhost:5672/
```

### 7.2 Production (K8s)

```yaml
# ConfigMap
CHAT_ENVIRONMENT: prod
CHAT_DEBUG: "false"
CHAT_DEFAULT_PROVIDER: anthropic

# Secret (External Secrets에서 주입)
CHAT_OPENAI_API_KEY: <from-vault>
CHAT_ANTHROPIC_API_KEY: <from-vault>
```

---

## 8. 다음 단계

Phase 6에서는:

1. **Dockerfile** - 멀티스테이지 빌드
2. **K8s Manifests** - Deployment, Service, ConfigMap
3. **ArgoCD Application** - GitOps 배포

---

**작성일**: 2026-01-13  
**Phase**: 5/6 (Setup & DI)

