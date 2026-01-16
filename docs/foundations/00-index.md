# Concurrency Foundations for Eco²

> 비동기 I/O와 동시성 향상을 위한 기초 지식 모음
> 공식 문서와 논문 기반의 신뢰할 수 있는 자료만 수집

---

## 이코에코 기술 스택

| 기술 | 버전 | 역할 | 공식 문서 |
|------|------|------|-----------|
| **Python** | 3.11 | 런타임 | [docs.python.org](https://docs.python.org/3.11/) |
| **FastAPI** | 0.109.0 | ASGI 웹 프레임워크 | [fastapi.tiangolo.com](https://fastapi.tiangolo.com/) |
| **Uvicorn** | 0.27.0 | ASGI 서버 | [uvicorn.org](https://www.uvicorn.org/) |
| **Celery** | 5.6.0 | 분산 태스크 큐 | [docs.celeryq.dev](https://docs.celeryq.dev/) |
| **RabbitMQ** | 4.0 | 메시지 브로커 (AMQP) | [rabbitmq.com](https://www.rabbitmq.com/documentation.html) |
| **Gevent** | 24.2.1 | Greenlet 기반 동시성 | [gevent.org](https://www.gevent.org/) |
| **aio-pika** | 9.3.1 | 비동기 AMQP 클라이언트 | [aio-pika.readthedocs.io](https://aio-pika.readthedocs.io/) |
| **asyncpg** | 0.29.0 | 비동기 PostgreSQL | [magicstack.github.io/asyncpg](https://magicstack.github.io/asyncpg/) |
| **aioredis** | 2.0.1 | 비동기 Redis | [aioredis.readthedocs.io](https://aioredis.readthedocs.io/) |

---

## 문서 목록

### 1. [Python asyncio](./01-python-asyncio.md)

Python의 비동기 I/O 프레임워크에 대한 기초 지식.

**공식 자료:**
- [asyncio 공식 문서](https://docs.python.org/3.11/library/asyncio.html)
- [PEP 3156 - Asynchronous I/O Support Rebooted](https://peps.python.org/pep-3156/)
- [PEP 492 - Coroutines with async and await syntax](https://peps.python.org/pep-0492/)
- [PEP 525 - Asynchronous Generators](https://peps.python.org/pep-0525/)
- [PEP 530 - Asynchronous Comprehensions](https://peps.python.org/pep-0530/)

**핵심 내용:**
- Event Loop 구조와 동작 원리
- Coroutine, Task, Future의 관계
- async/await 문법의 설계 철학

---

### 2. [Python GIL](./02-python-gil.md)

Global Interpreter Lock의 이해와 Python 3.13+ free-threading.

**공식 자료:**
- [GIL 공식 정의](https://docs.python.org/3.11/glossary.html#term-global-interpreter-lock)
- [C API: Thread State and GIL](https://docs.python.org/3.11/c-api/init.html#thread-state-and-the-global-interpreter-lock)
- [PEP 703 - Making the Global Interpreter Lock Optional](https://peps.python.org/pep-0703/)

**학술 자료:**
- [OMP4Py: A Pure Python Implementation of OpenMP](https://arxiv.org/abs/2411.14887) (arXiv, 2024)

**핵심 내용:**
- GIL의 정의와 존재 이유
- I/O-bound vs CPU-bound 작업에서의 영향
- Python 3.13 free-threading 모드

---

### 3. [AMQP Protocol](./03-amqp-protocol.md)

Advanced Message Queuing Protocol의 표준 스펙과 RabbitMQ 구현.

**공식 자료:**
- [AMQP 0-9-1 Complete Reference](https://www.rabbitmq.com/amqp-0-9-1-reference.html)
- [AMQP Concepts](https://www.rabbitmq.com/tutorials/amqp-concepts.html)
- [RabbitMQ Documentation](https://www.rabbitmq.com/documentation.html)
- [aio-pika Documentation](https://aio-pika.readthedocs.io/)
- [OASIS AMQP 1.0 Specification](https://www.amqp.org/specification/1.0/amqp-org-download) (ISO/IEC 19464:2014)

**핵심 내용:**
- Exchange, Queue, Binding의 관계
- Channel Multiplexing과 QoS
- 비동기 AMQP 클라이언트 패턴

---

### 4. [Concurrency Patterns](./04-concurrency-patterns.md)

이코에코 스택에서의 동시성 패턴과 최적화 전략.

**공식 자료:**
- [Celery Concurrency](https://docs.celeryq.dev/en/stable/userguide/concurrency/index.html)
- [Uvicorn Settings](https://www.uvicorn.org/settings/)
- [FastAPI Concurrency and async/await](https://fastapi.tiangolo.com/async/)

**핵심 내용:**
- Celery Worker Pool 종류 (prefork, eventlet, gevent)
- Uvicorn workers vs asyncio 관계
- FastAPI async def vs def 차이

---

### 5. [Event Loop Fundamentals](./05-event-loop-fundamentals.md) 🆕

Event Loop의 근원 개념과 OS 수준 I/O Multiplexing.

**공식 자료:**
- [Python select module](https://docs.python.org/3/library/select.html)
- [libev - high performance event loop](http://software.schmorp.de/pkg/libev.html)
- [libuv - cross-platform async I/O](https://libuv.org/)
- [Gevent Introduction](https://www.gevent.org/intro.html)

**핵심 내용:**
- OS 수준 I/O Multiplexing (select, poll, epoll, kqueue)
- asyncio Event Loop vs Gevent Event Loop (libev/libuv)
- 왜 서로 다른 Event Loop는 충돌하는가
- Monkey Patching의 동작 원리

---

### 6. [Concurrency Models](./06-concurrency-models.md)

동시성 모델 비교: Process, Thread, Greenlet, Coroutine.

**공식 자료:**
- [Python multiprocessing](https://docs.python.org/3.11/library/multiprocessing.html)
- [Python threading](https://docs.python.org/3.11/library/threading.html)
- [Greenlet Documentation](https://greenlet.readthedocs.io/)
- [Gevent Documentation](https://www.gevent.org/)

**핵심 내용:**
- Concurrency vs Parallelism 명확한 구분
- 4가지 동시성 모델 비교 (Process, Thread, Greenlet, Coroutine)
- Context Switch 비용 비교
- 메모리 공유 특성과 선택 기준

---

### 7. [Redis Streams](./07-redis-streams.md) 🆕

Redis Streams: Kafka 스타일 로그 기반 메시지 브로커.

**공식 자료:**
- [Redis Streams Introduction](https://redis.io/docs/latest/develop/data-types/streams/)
- [antirez: Streams Design](http://antirez.com/news/114)
- [The Log - Jay Kreps](https://engineering.linkedin.com/distributed-systems/log-what-every-software-engineer-should-know-about-real-time-datas-unifying)

**핵심 내용:**
- Append-only Log 구조와 Entry ID
- XADD, XREAD, XREADGROUP 명령어
- Consumer Group 패턴
- Kafka vs Redis Streams vs RabbitMQ 비교

---

### 8. [Server-Sent Events](./08-server-sent-events.md) 🆕

SSE: HTTP 기반 서버→클라이언트 실시간 스트리밍.

**공식 자료:**
- [HTML Standard - Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [MDN - EventSource](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)
- [FastAPI StreamingResponse](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)

**핵심 내용:**
- SSE vs WebSocket vs Polling 비교
- SSE 프로토콜 형식 (event, data, id)
- 인프라 고려사항 (Nginx, Istio, ALB)
- 연결 수명 관리와 모니터링

---

### 9. [MapReduce](./09-mapreduce.md) 🆕

Google MapReduce 논문 상세 분석: 대규모 클러스터에서의 단순화된 데이터 처리.

**핵심 논문:**
- [MapReduce: Simplified Data Processing on Large Clusters](https://research.google/pubs/pub62/) (OSDI 2004, Jeffrey Dean, Sanjay Ghemawat)

**핵심 내용:**
- Map/Reduce 프로그래밍 모델과 수식
- Master-Worker 실행 아키텍처
- Shuffle Phase와 데이터 파티셔닝
- Fault Tolerance (Worker 장애, Stragglers)
- Combiner, Locality 최적화
- Hadoop, Spark 등 후속 연구와의 관계

---

### 10. [NUMA](./10-numa.md) 🆕

Non-Uniform Memory Access 아키텍처: 멀티프로세서 시스템의 메모리 접근 최적화.

**핵심 논문:**
- [An Analysis of Linux Scalability to Many Cores](https://www.usenix.org/conference/osdi10/analysis-linux-scalability-many-cores) (OSDI 2010)
- [The Scalable Commutativity Rule](https://dl.acm.org/doi/10.1145/2517349.2522712) (SOSP 2013)

**핵심 내용:**
- UMA vs NUMA 아키텍처 비교
- 노드 구조, 인터커넥트 (QPI, Infinity Fabric)
- Cache Coherence 프로토콜 (MESI, MOESI)
- False Sharing 문제와 해결
- NUMA-aware 프로그래밍 (numactl, libnuma)
- Redis, PostgreSQL, K8s 환경에서의 NUMA 최적화

---

### 11. [KEDA](./11-keda.md)

Kubernetes Event-Driven Autoscaling: 이벤트 기반 워크로드를 위한 세밀한 오토스케일링.

**공식 자료:**
- [KEDA Documentation](https://keda.sh/docs/)
- [KEDA Scalers](https://keda.sh/docs/scalers/)
- [Kubernetes HPA](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/)

**핵심 내용:**
- HPA의 한계와 KEDA의 등장 배경
- KEDA 아키텍처 (Operator, Metrics Server, ScaledObject)
- External Metrics API와 메트릭 제공 방식
- RabbitMQ Scaler 상세 (QueueLength, MessageRate)
- 스케일링 알고리즘과 수식
- Scale-to-Zero, Stabilization Window
- 운영 고려사항 (콜드 스타트, 메트릭 지연)

---

### 12. [Consensus Algorithms](./12-consensus-algorithms.md)

분산 합의 알고리즘: Paxos, Raft, Redis Sentinel (Quorum), RabbitMQ Quorum Queue.

**핵심 논문:**
- [The Part-Time Parliament](https://lamport.azurewebsites.net/pubs/lamport-paxos.pdf) (Leslie Lamport, ACM TOCS 1998)
- [Paxos Made Simple](https://lamport.azurewebsites.net/pubs/paxos-simple.pdf) (Leslie Lamport, 2001)
- [In Search of an Understandable Consensus Algorithm](https://raft.github.io/raft.pdf) (USENIX ATC 2014, Diego Ongaro)

**공식 자료:**
- [Redis Sentinel Documentation](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/)
- [RabbitMQ Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues)

**핵심 내용:**
- Paxos 2-Phase Protocol (Prepare, Accept)
- Raft Leader Election, Log Replication
- Quorum (과반수 동의) 원칙과 Split-Brain 방지
- Redis Sentinel SDOWN/ODOWN 장애 감지
- Eco² Redis Sentinel 3노드 HA 구성

---

### 13. [Sharding & Routing](./13-sharding-and-routing.md)

분산 데이터 파티셔닝과 라우팅: Consistent Hashing, Consumer Groups, Fanout.

**핵심 논문:**
- [Consistent Hashing and Random Trees](https://www.cs.princeton.edu/courses/archive/fall09/cos518/papers/chash.pdf) (Karger et al., MIT 1997)
- [Dynamo: Amazon's Highly Available Key-value Store](https://www.allthingsdistributed.com/files/amazon-dynamo-sosp2007.pdf) (SOSP 2007)
- [The Tail at Scale](https://research.google/pubs/pub40801/) (Jeff Dean, Google 2013)

**공식 자료:**
- [Redis Streams Consumer Groups](https://redis.io/docs/latest/develop/data-types/streams/)
- [Istio Destination Rule - consistentHash](https://istio.io/latest/docs/reference/config/networking/destination-rule/)
- [Envoy Ring Hash LB](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/load_balancing/load_balancers#ring-hash)

**핵심 내용:**
- Consistent Hashing (해시 링, Virtual Nodes)
- Redis Streams Consumer Groups vs Kafka 비교
- Istio/Envoy Consistent Hash Routing
- Pub/Sub Fanout 패턴과 Tail Latency

---

### 14. [FLP Impossibility](./14-flp-impossibility.md) 🆕

분산 합의의 불가능성: 비동기 시스템에서 합의의 이론적 한계와 실제 적용.

**핵심 논문:**
- [Impossibility of Distributed Consensus with One Faulty Process](https://groups.csail.mit.edu/tds/papers/Lynch/jacm85.pdf) (Fischer, Lynch, Paterson, JACM 1985)

**핵심 내용:**
- FLP 정리: 비동기 + 1개 장애 → 결정론적 합의 불가능
- Bivalence Argument (증명 핵심)
- 우회 전략: 부분 동기, 랜덤화, 장애 감지기
- CAP 정리와의 관계
- 실제 시스템(Paxos, Raft)이 FLP를 우회하는 방법
- **"비동기 분산 ≠ FLP"**: 중앙 조정자(Redis) 사용 시 해당 안 함
- Eco² SSE 이벤트 버스가 FLP 직격 대상이 아닌 이유

---

### 15. [Dependency Injection 비교: Dishka vs Dependency-Injector](./15-dependency-injection-comparison.md) 🆕

Python DI 라이브러리 비교 분석: 타입 기반 자동 와이어링 vs 명시적 컨테이너 패턴.

**공식 자료:**
- [Dishka Documentation](https://dishka.readthedocs.io/)
- [Dishka GitHub](https://github.com/reagento/dishka)
- [Dependency-Injector Documentation](https://python-dependency-injector.ets-labs.org/)
- [Dependency-Injector GitHub](https://github.com/ets-labs/python-dependency-injector)

**핵심 내용:**
- Auto-wiring vs Explicit Configuration 철학 비교
- 스코프 기반 라이프사이클 관리
- Async 지원 수준 비교
- FastAPI 통합 패턴
- 현재 프로젝트 DI 패턴 분석 및 마이그레이션 권장안

---

### 16. [FastAPI Clean Example 분석](./16-fastapi-clean-example-analysis.md) 🆕

fastapi-clean-example 프로젝트 상세 분석: Clean Architecture, CQRS, Gateway 패턴 및 근원 기술.

**참조 프로젝트:**
- [ivan-borovets/fastapi-clean-example](https://github.com/ivan-borovets/fastapi-clean-example)

**근원 기술 (Foundational Concepts):**
- Clean Architecture (Robert C. Martin, 2012)
- Hexagonal Architecture / Ports & Adapters (Alistair Cockburn, 2005)
- Domain-Driven Design (Eric Evans, 2003)
- CQRS (Greg Young, 2010)
- PoEAA Patterns (Martin Fowler, 2002) - Repository, Data Mapper, Unit of Work, Gateway
- SOLID Principles - 특히 Dependency Inversion Principle

**핵심 내용:**
- 4-Layer Architecture (Domain, Application, Infrastructure, Presentation)
- CQRS 패턴: Commands vs Queries
- Gateway 패턴: Port와 Adapter 명명 규칙
- Use Case (Interactor/QueryService) 구조
- Port의 3단계 구조 (Domain, Application, Infrastructure 내부)
- Port-Adapter 매핑 및 의존성 흐름
- 우리 프로젝트 적용 방안

---

### 17. [OAuth2.0 리팩토링 비교 분석](./17-oauth-refactoring-comparison.md) 🆕

기존 구현(`domains/auth/`)과 Clean Architecture 리팩토링(`apps/auth/`) 기능별 비교.

**핵심 내용:**
- 아키텍처 개요 비교 (Mermaid 다이어그램)
- OAuth Authorize 플로우 비교 (Sequence Diagram)
- OAuth Callback 플로우 비교 (Sequence Diagram)
- 파일 매핑 테이블 (기존 → 리팩토링)
- 의존성 주입 비교 (암시적 vs 명시적)
- 마이그레이션 체크리스트

---

### 18. [FastAPI Lifespan](./18-fastapi-lifespan.md) 🆕

FastAPI 애플리케이션 생명주기 관리: Startup, Shutdown, 상태 공유.

**공식 자료:**
- [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/)
- [Starlette Lifespan](https://www.starlette.io/lifespan/)
- [Python contextlib](https://docs.python.org/3/library/contextlib.html)
- [PEP 525 - Asynchronous Generators](https://peps.python.org/pep-0525/)

**핵심 내용:**
- `@asynccontextmanager`와 `yield`의 의미
- Startup/Shutdown 코드 실행 순서
- 캐시 워밍업 (Cold Start 해결)
- 백그라운드 Consumer 관리
- 다중 리소스 관리 패턴
- 레거시 `@app.on_event` vs 현재 `lifespan` 비교
- 테스트에서의 Lifespan 처리

---

### 19. [LLM Gateway & Unified Interface Pattern](./19-model-agnostic-agent-architecture.md) 🆕

AI 에이전트 시스템에서 LLM 모델 선택을 에이전트 로직과 분리하는 아키텍처 패턴.

> ⚠️ 공식 용어 없음. 실제 사용 용어: LLM Gateway, AI Gateway, LLM Router, Unified LLM Interface

**공식 자료:**
- [LiteLLM](https://github.com/BerriAI/litellm) - 100+ LLM을 OpenAI 형식으로 통합
- [Cloudflare AI Gateway](https://developers.cloudflare.com/ai-gateway/)
- [Cursor Cloud Agents API](https://cursor.com/docs/cloud-agent/api/endpoints)
- [당근 GenAI 플랫폼](https://medium.com/daangn/당근의-genai-플랫폼-ee2ac8953046)

**핵심 내용:**
- 전통적 AI 에이전트 구조의 문제점 (모델 하드코딩)
- Frontend Model Selection 패턴 (Cursor 방식)
- Gateway Model Routing 패턴 (당근 방식)
- Agent-Level Model Configuration 패턴 (CrewAI 방식)
- Dynamic Model Selection 패턴 (LangGraph 방식)
- 인터페이스 정의 및 모델 라우터 구현
- Auto Mode 구현 방법

---

### 20. [Dependency Injection for LLM (모델 주입 패턴)](./20-llm-as-parameter-pattern.md) 🆕

LLM 모델을 함수의 파라미터로 전달하여 에이전트 로직과 모델 선택을 분리하는 설계 패턴.

> ⚠️ 공식 용어 없음. 기존 DI/Strategy 패턴의 LLM 적용.

**공식 자료:**
- [Dependency Injection - Martin Fowler](https://martinfowler.com/articles/injection.html)
- [Strategy Pattern - Refactoring Guru](https://refactoring.guru/design-patterns/strategy)
- [LangChain Agent Documentation](https://python.langchain.com/docs/modules/agents/)
- [CrewAI Multi-Agent Systems](https://docs.crewai.com/)

**핵심 내용:**
- 의존성 역전 원칙 (Dependency Inversion) 적용
- 모델 하드코딩 vs 파라미터 주입 비교
- Cursor IDE, LangChain, CrewAI, 당근 LLM Router 구현 사례
- 패턴 장점: 유연성, 테스트 용이성, 비용 최적화, 장애 격리, A/B 테스트
- 구현 가이드: 인터페이스 정의 → Provider 구현 → Factory 패턴 → Agent 적용
- Auto Mode (자동 모델 선택) 구현
- 안티패턴 및 권장 패턴

---

### 24. [Multi-Agent Prompt Patterns](./24-multi-agent-prompt-patterns.md) 🆕

멀티 에이전트 시스템에서의 프롬프트 설계 패턴: 2025년 최신 연구 동향.

**참고 자료:**
- [ai-agent-papers (GitHub)](https://github.com/masamasa59/ai-agent-papers) - AI Agent 논문 모음 (격주 업데이트)
- [ChatDev (arxiv 2307.07924)](https://arxiv.org/abs/2307.07924) - 청화대 OpenBMB
- [MetaGPT (arxiv 2308.00352)](https://arxiv.org/abs/2308.00352) - DeepWisdom

**핵심 내용:**
- 프롬프트 패턴 분류 (통합/분리/하이브리드)
- 2025년 주요 논문 분석 (Local Prompt Optimization, Evolving Orchestration, Mem0, SEW)
- 선행 연구 (ChatDev, MetaGPT, AgentCoder)
- 패턴 선택 가이드
- Eco² chat_worker 적용 사례

---

### 27. [RAG 품질 평가 전략: LLM-as-a-Judge](./27-rag-evaluation-strategy.md) 🆕

RAG 시스템의 품질을 LLM Judge로 평가하기 위한 이론적 토대와 실전 설계 원칙.

**핵심 논문/자료:**
- [RAGAS: Automated Evaluation of RAG](https://arxiv.org/abs/2309.15217) (arXiv 2023)
- [TREC 2024 RAG Track - AutoNuggetizer](https://trec-rag.github.io/)
- [ConsJudge: Judge as a Judge](https://arxiv.org/) (2025)
- [Anthropic - Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) (2024)
- [Anthropic - Multi-agent Research System](https://www.anthropic.com/engineering/built-multi-agent-research-system) (2025)
- [TruLens RAG Triad](https://www.trulens.org/trulens_eval/core_concepts_rag_triad/)
- [Snowflake - Eval-guided optimization of LLM judges](https://www.snowflake.com/engineering-blog/) (2025)

**핵심 내용:**
- 4가지 핵심 기둥: 정량화(RAGAS/TREC), 근거 기반(Citation), 맥락 관리(Just-in-Time), 신뢰성(ConsJudge)
- Faithfulness, Groundedness, Context Relevance 지표 정의
- Nugget 기반 Completeness 측정
- Citation/Evidence 강제 전략
- Judge Consistency 확보 방안
- 실전 JSON 스키마 및 프롬프트 템플릿

---

## 권장 학습 순서

```
┌─────────────────────────────────────────────────────────────┐
│                    학습 경로                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Step 1: 근원 개념 (NEW)                                     │
│  ─────────────────────                                      │
│  ┌─────────────────┐     ┌─────────────────┐               │
│  │ 05-event-loop   │     │ 06-concurrency  │               │
│  │ I/O Multiplexing│ ──▶ │ 모델 비교       │               │
│  │ epoll/kqueue    │     │ Process/Thread  │               │
│  │ asyncio vs libev│     │ Greenlet/Coro   │               │
│  └─────────────────┘     └─────────────────┘               │
│                                                             │
│  Step 2: 언어 기초                                          │
│  ─────────────────                                          │
│  ┌─────────────────┐     ┌─────────────────┐               │
│  │ 01-asyncio.md   │     │ 02-gil.md       │               │
│  │ Event Loop      │ ──▶ │ GIL 이해        │               │
│  │ Coroutine       │     │ I/O vs CPU      │               │
│  └─────────────────┘     └─────────────────┘               │
│                                                             │
│  Step 3: 프로토콜                                           │
│  ────────────────                                           │
│  ┌─────────────────┐                                        │
│  │ 03-amqp.md      │                                        │
│  │ AMQP 0-9-1      │                                        │
│  │ Channel, QoS    │                                        │
│  └─────────────────┘                                        │
│                                                             │
│  Step 4: 적용                                               │
│  ───────────                                                │
│  ┌─────────────────┐                                        │
│  │ 04-concurrency  │                                        │
│  │ Celery/Uvicorn  │                                        │
│  │ FastAPI async   │                                        │
│  └─────────────────┘                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 빠른 경로 (실무 중심)

이미 asyncio/Celery 경험이 있다면:

```
05-event-loop → 06-concurrency-models → 04-concurrency-patterns
```

### 전체 경로 (개념 이해 중심)

처음부터 체계적으로 배우려면:

```
05-event-loop → 06-concurrency-models → 01-asyncio → 02-gil → 03-amqp → 04-concurrency
```

---

## 기존 자료와의 관계

이 디렉토리는 **기초 개념**에 집중합니다.

실전 패턴과 아키텍처는 [`docs/blogs/async/`](../blogs/async/)를 참고하세요:

| 이 디렉토리 (기초) | blogs/async (실전) |
|-------------------|-------------------|
| 05-event-loop-fundamentals | 18-gevent-asyncio-eventloop-conflict.md |
| 06-concurrency-models | 16-celery-gevent-pool-migration.md |
| 07-redis-streams | 24-redis-streams-sse-migration.md |
| 08-server-sent-events | 23-sse-bottleneck-analysis-50vu.md |
| 09-mapreduce | 분산 태스크 처리 패턴 (Celery Chain) |
| 10-numa | 25-redis-3node-cluster-provisioning.md |
| 11-keda | Worker 오토스케일링 (ScaledObject) |
| 12-consensus-algorithms | workloads/redis/README.md (Redis HA) |
| 13-sharding-and-routing | SSE-Gateway Fanout + Istio Routing |
| 14-flp-impossibility | 분산 합의 이론의 기초 (CAP, 타임아웃) |
| 01-asyncio 동작 원리 | 15-system-rpm-analysis-before-asyncio.md |
| 02-GIL 이해 | 17-worker-pool-db-optimization.md |
| 03-AMQP 프로토콜 스펙 | 09-celery-chain-events-part2.md |
| 04-Concurrency 패턴 | 12-batch-processing-idempotency.md |

---

## 참고: 이코에코 비동기 구조

```
┌─────────────────────────────────────────────────────────────┐
│                    Eco² Async Architecture                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Client Request                                             │
│       │                                                     │
│       ▼                                                     │
│  ┌─────────────┐                                            │
│  │   Uvicorn   │  ASGI Server (asyncio event loop)         │
│  │   Workers   │  → 05-event-loop-fundamentals.md          │
│  └──────┬──────┘                                            │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────┐                                            │
│  │   FastAPI   │  async def endpoints                      │
│  │   Router    │  → 01-python-asyncio.md                   │
│  └──────┬──────┘                                            │
│         │                                                   │
│    ┌────┴────┬────────────┐                                 │
│    │         │            │                                 │
│    ▼         ▼            ▼                                 │
│ ┌──────┐ ┌──────┐   ┌───────────┐                          │
│ │asyncpg│ │aioredis│  │ aio-pika │                          │
│ │  DB   │ │ Cache │  │   AMQP   │                          │
│ └──────┘ └──────┘   └─────┬─────┘                          │
│                           │                                 │
│                           ▼                                 │
│                    ┌───────────┐                            │
│                    │ RabbitMQ  │  → 03-amqp-protocol.md    │
│                    └─────┬─────┘                            │
│                          │                                  │
│                          ▼                                  │
│                   ┌────────────┐                            │
│                   │   Celery   │  Worker Pool              │
│                   │   Worker   │  (gevent)                 │
│                   └────────────┘  → 06-concurrency-models  │
│                          │                                  │
│                          │  gevent greenlet               │
│                          │  → 05-event-loop-fundamentals   │
│                          ▼                                  │
│                   ┌────────────┐                            │
│                   │  libev     │  Event Loop (C)           │
│                   │  (epoll)   │                            │
│                   └────────────┘                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 버전 정보

- 작성일: 2025-12-24
- Python 버전: 3.11
- Celery 버전: 5.6.0
- 대상: Eco² Backend Team

## 변경 이력

| 날짜 | 내용 |
|------|------|
| 2024-12-24 | 최초 작성 (01-04) |
| 2025-12-24 | Event Loop/Concurrency Models 문서 추가 (05-06) |
| 2025-12-25 | Redis Streams/SSE 문서 추가 (07-08) |
| 2025-12-26 | MapReduce/NUMA 논문 분석 문서 추가 (09-10) |
| 2025-12-26 | KEDA 이벤트 기반 오토스케일링 문서 추가 (11) |
| 2025-12-27 | Consensus Algorithms (Raft, Redis Sentinel) 문서 추가 (12) |
| 2025-12-27 | Sharding & Routing (Consistent Hashing, Fanout) 문서 추가 (13) |
| 2025-12-28 | FLP Impossibility (분산 합의 불가능성) 문서 추가 (14) |
| 2025-12-28 | FLP 문서에 "비동기 분산 ≠ FLP" 분석 섹션 추가 (14) |
|| 2025-12-30 | Dishka vs Dependency-Injector 비교 문서 추가 (15) |
|| 2025-12-30 | FastAPI Clean Example 분석 문서 추가 (16) |
|| 2025-12-31 | OAuth2.0 리팩토링 비교 분석 문서 추가 (17) |
|| 2026-01-04 | FastAPI Lifespan 애플리케이션 생명주기 문서 추가 (18) |
|| 2026-01-05 | LLM Gateway & Unified Interface Pattern 문서 추가 (19) |
|| 2026-01-05 | Dependency Injection for LLM 문서 추가 (20) |
|| 2026-01-14 | Multi-Agent Prompt Patterns 문서 추가 (24) |
|| 2026-01-15 | RAG 품질 평가 전략 (LLM-as-a-Judge) 문서 추가 (27) |