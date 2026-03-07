# Cursor에서 Claude Code로 마이그레이션하기

**작성일**: 2025-01-16
**태그**: `#tooling` `#claude-code` `#cursor` `#skills` `#ai-coding`

---

## 한 줄 요약

Cursor IDE에서 Claude Code CLI로 전환하면서, 프로젝트에 특화된 12개의 Skills(57개 마크다운 파일)를 구축했습니다. 이 글에서는 전환을 결정하게 된 배경과 Skills 시스템 구축 과정을 공유합니다.

---

## 전환을 결심하게 된 계기

### 2일 만에 50만원이 사라졌습니다

Eco² 프로젝트의 Agentic Workflow를 Cursor로 개발하던 중이었습니다. LangGraph 파이프라인 설계, gRPC 통합, 이벤트 아키텍처 구축 등 복잡한 작업을 Agent 모드로 진행하고 있었는데, **단 2일 만에 약 50-60만원**이 소진되었습니다.

남은 예산은 80만원. 프로젝트 완료까지 이 속도라면 턱없이 부족했습니다. 장기적으로 지속 가능한 대안이 필요했습니다.

### 두 도구의 요금제를 비교해 보았습니다

**Cursor 요금제**

| 플랜 | 월 요금 | 주요 특징 |
|------|---------|----------|
| Hobby | 무료 | 제한된 Agent 요청 |
| Pro | $20 | Extended limits, Background Agents |
| Pro+ | $60 | 3x 사용량 (OpenAI, Claude, Gemini) |
| Ultra | $200 | 20x 사용량 |

**Claude 요금제**

| 플랜 | 월 요금 | 주요 특징 |
|------|---------|----------|
| Free | 무료 | 기본 채팅 |
| Pro | $20 | Claude Code 접근, Extended Thinking |
| Max 5x | $100 | 5x 사용량, 고급 기능 |
| Max 20x | $200 | 20x 사용량, Claude Code 최적화 |

동일한 $200 가격대에서 두 도구를 비교하면 흥미로운 차이가 있습니다:
- **Cursor Ultra**: 서드파티 도구로서 OpenAI, Anthropic, Google의 API를 중개합니다
- **Claude Max 20x**: 모델 제공자인 Anthropic이 직접 운영하며, Claude Code에 최적화되어 있습니다

### 세 가지 이유로 전환을 결정했습니다

**첫째, 퍼스트파티의 이점**

Cursor는 여러 AI 제공자의 API를 중개하는 서드파티 도구입니다. 반면 Claude Code는 Anthropic이 직접 개발하고 운영합니다.

> "모델 제공자가 지원하지 않는 서드파티 도구에는 '장기적 비용 이점'이 없습니다."

API 비용 구조가 변경되거나 새로운 기능이 출시될 때, 퍼스트파티 도구가 더 빠르게 대응할 수 있다고 판단했습니다.

**둘째, 크레덴셜 제한 정책**

Anthropic은 구독 크레덴셜 헤더를 Claude Code 전용으로 제한했습니다. oh-my-opencode 같은 대안 도구들이 차단되면서, 공식 도구를 사용하는 것이 가장 안정적인 선택이 되었습니다.

**셋째, 학습 투자 관점**

남은 예산 80만원은 약 4개월 분의 Claude Max 20x 구독료에 해당합니다. 이 기간 동안 Claude Code에 익숙해지면, 장기적으로 더 효율적인 워크플로우를 구축할 수 있을 것이라 기대했습니다.

### 워크플로우 관점에서도 장점이 있었습니다

Cursor IDE는 GUI 기반의 직관적인 코딩 경험을 제공합니다. 하지만 터미널 중심 워크플로우에서는 몇 가지 한계가 있었습니다.

**Cursor의 강점**
- 뛰어난 UI와 코드 컨텍스트 인덱싱
- 시맨틱 검색을 통한 코드베이스 탐색
- VSCode 기반의 익숙한 개발 환경

**Cursor의 한계**
- SSH 터널링, 포트 포워딩이 잦은 클러스터 디버깅 작업에서 IDE 전환 오버헤드가 발생합니다
- 여러 레포지토리(Backend, Frontend, Resume)를 동시에 다룰 때 창 관리가 복잡해집니다
- 프로젝트별 컨텍스트를 체계적으로 관리하기 어렵습니다

**Claude Code의 강점**
- CLI 네이티브로 tmux, ssh, kubectl과 자연스럽게 연동됩니다
- Skills 시스템으로 마크다운 기반의 프로젝트 컨텍스트를 구조화할 수 있습니다
- 멀티 워킹 디렉토리를 지원해 여러 레포를 하나의 세션에서 관리할 수 있습니다
- CLAUDE.md를 통해 세션 시작 시 프로젝트 컨텍스트가 자동으로 로드됩니다

---

## Cursor에서 가져올 수 있는 것들

마이그레이션을 시작하기 전에, Cursor의 데이터 저장 구조를 분석해 이전 가능한 자산을 파악했습니다.

### Cursor의 시맨틱 검색은 어떻게 동작할까요?

Cursor는 7단계 벡터화 프로세스로 코드베이스를 인덱싱합니다:

```
┌─────────────────────────────────────────────────────────────────┐
│                 Cursor Semantic Search Pipeline                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. File Sync        워크스페이스 파일을 Cursor 서버로 동기화      │
│         ↓                                                        │
│  2. Code Chunking    함수, 클래스, 논리적 블록 단위로 분할         │
│         ↓                                                        │
│  3. Vector Embedding AI 모델로 청크를 수학적 벡터로 변환           │
│         ↓                                                        │
│  4. Database Storage 벡터 DB에 임베딩 저장 (서버 사이드)          │
│         ↓                                                        │
│  5. Query Conversion 검색 쿼리를 동일 모델로 벡터화               │
│         ↓                                                        │
│  6. Similarity Match 쿼리 벡터와 저장된 임베딩 비교               │
│         ↓                                                        │
│  7. Result Ranking   시맨틱 유사도 기준 결과 정렬                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

여기서 중요한 점이 있습니다:
- 임베딩 데이터는 **Cursor 서버에만 저장**됩니다. 로컬에는 벡터 데이터가 없습니다
- 소스 코드는 인덱싱 중 메모리에만 존재하며, 이후에는 폐기됩니다
- 5분마다 자동 동기화가 이루어지고, 6주간 미사용 시 인덱스가 삭제됩니다

### Cursor 로컬 저장소 구조를 살펴보았습니다

```
~/Library/Application Support/Cursor/
├── User/
│   ├── globalStorage/
│   │   └── state.vscdb              # 전역 상태 DB (~10GB)
│   ├── workspaceStorage/
│   │   └── {workspace-hash}/
│   │       ├── anysphere.cursor-retrieval/
│   │       │   ├── embeddable_files.txt      # 인덱싱 대상 파일 목록
│   │       │   └── high_level_folder_description.txt  # 폴더 설명 JSON
│   │       ├── state.vscdb          # 워크스페이스 상태 DB
│   │       └── workspace.json       # 워크스페이스 경로 매핑
│   ├── History/                     # 에디터 히스토리
│   └── settings.json                # 사용자 설정
│
~/.cursor/
├── projects/
│   └── {project-path-hash}/
│       ├── agent-tools/             # AI 대화 로그 (UUID.txt)
│       ├── rules/                   # 프로젝트 규칙
│       └── terminals/               # 터미널 히스토리
├── extensions/                      # 설치된 확장
└── plans/                           # AI 플랜 히스토리

{project-root}/
├── .cursorrules                     # 프로젝트별 AI 규칙
└── .cursorignore                    # 인덱싱 제외 패턴
```

### 이전 가능 여부를 정리했습니다

| 자산 | 위치 | 이전 가능 | 활용 방법 |
|------|------|----------|----------|
| `.cursorrules` | 프로젝트 루트 | ✅ | CLAUDE.md로 변환 |
| `embeddable_files.txt` | workspaceStorage | ✅ | 중요 파일 목록 참조 |
| `high_level_folder_description.txt` | workspaceStorage | ✅ | 프로젝트 구조 요약 |
| `agent-tools/*.txt` | ~/.cursor/projects | △ | 대화 히스토리 참고용 |
| 벡터 임베딩 | Cursor 서버 | ❌ | 서버 사이드, 접근 불가 |
| 시맨틱 인덱스 | Cursor 서버 | ❌ | 서버 사이드, 접근 불가 |

### 시맨틱 검색의 대안을 찾았습니다

Cursor의 클라우드 기반 시맨틱 검색을 완전히 대체하기는 어렵습니다. 하지만 다음과 같은 방법으로 보완할 수 있습니다:

1. **Claude Code의 Grep/Glob**: 키워드 기반 검색으로 대부분의 케이스를 커버할 수 있습니다
2. **Skills 시스템**: 도메인 지식을 명시적인 문서로 구조화합니다
3. **로컬 RAG 구축** (필요 시): LlamaIndex + ChromaDB로 자체 임베딩 시스템을 구축할 수 있습니다

```python
# 로컬 RAG 구축 예시 (향후 옵션)
from llama_index import VectorStoreIndex, SimpleDirectoryReader

documents = SimpleDirectoryReader("./apps").load_data()
index = VectorStoreIndex.from_documents(documents)
query_engine = index.as_query_engine()
```

현재로서는 Skills 시스템만으로도 충분히 효과적이었습니다.

---

## Skills 시스템 이해하기

Claude Code의 Skills는 특정 도메인에 대한 지식을 마크다운 파일로 구조화한 것입니다. 키워드 트리거를 통해 관련 컨텍스트가 자동으로 로드됩니다.

### 기본 구조

```
{skill-name}/
├── SKILL.md                # 메인 가이드
│                           # - 트리거 키워드 정의
│                           # - Quick Reference
│                           # - Reference 파일 링크
└── references/
    ├── topic-1.md          # 세부 참조 문서
    ├── topic-2.md
    └── ...
```

### SKILL.md와 Reference 문서는 역할이 다릅니다

| 구분 | SKILL.md | Reference 문서 |
|------|----------|----------------|
| **역할** | 진입점, Quick Reference | 세부 가이드, 심화 내용 |
| **트리거** | 키워드로 자동 로드 | SKILL.md에서 링크로 참조 |
| **내용** | 개요, 핵심 명령어, 체크리스트 | 상세 설명, 코드 예시, 시나리오 |
| **분량** | 100-200줄 | 200-500줄 |

```
{skill-name}/
├── SKILL.md              ← 트리거 시 먼저 로드됩니다 (Quick Reference)
└── references/
    ├── topic-1.md        ← 필요할 때 추가로 참조합니다 (Deep Dive)
    └── topic-2.md
```

### 트리거는 이렇게 정의합니다

```markdown
---
name: clean-architecture
description: Clean Architecture 구현 가이드. "clean architecture",
             "port", "adapter", "hexagonal" 키워드로 트리거됩니다.
---
```

---

## 구축한 Skills 현황

### 12개의 Skills를 생성했습니다

| 출처 | Skill 이름 | Reference 수 | 설명 |
|------|------------|--------------|------|
| Anthropic | mcp-builder | 4 | MCP 서버 구축 |
| Anthropic | doc-coauthoring | 0 | 문서 공동 작성 |
| Anthropic | skill-creator | 2 | Skill 생성 도구 |
| Custom | clean-architecture | 5 | Clean Architecture 4-Layer |
| Custom | code-review | 4 | 체계적 코드 리뷰 |
| Custom | langgraph-pipeline | 4 | LangGraph 1.0+ 파이프라인 |
| Custom | event-driven | 4 | Redis Composite Event Bus |
| Custom | grpc-service | 4 | gRPC 서비스 통합 |
| Custom | rag-pipeline | 4 | RAG (Contextual Retrieval) |
| Custom | prompt-engineering | 3 | 프롬프트 설계/평가 |
| Custom | redis-patterns | 3 | Redis 패턴 가이드 |
| Custom | k8s-debugging | 8 | Kubernetes 운영/디버깅 |

### 파일 수 요약

| 카테고리 | SKILL.md | Reference | 합계 |
|----------|----------|-----------|------|
| Anthropic Skills | 3 | 6 | 9 |
| Custom Skills | 9 | 39 | 48 |
| **총계** | **12** | **45** | **57** |

---

## Skills 폴더 구조

```
.claude/skills/
├── mcp-builder/                    # [Anthropic] MCP 서버 구축
│   ├── SKILL.md
│   └── references/
│       ├── mcp-architecture.md
│       ├── mcp-tools.md
│       ├── mcp-resources.md
│       └── mcp-prompts.md
│
├── doc-coauthoring/                # [Anthropic] 문서 공동 작성
│   └── SKILL.md
│
├── skill-creator/                  # [Anthropic] Skill 생성 도구
│   ├── SKILL.md
│   └── references/
│       ├── skill-structure.md
│       └── skill-examples.md
│
├── clean-architecture/             # Clean Architecture 4-Layer
│   ├── SKILL.md
│   └── references/
│       ├── layer-structure.md
│       ├── port-adapter.md
│       ├── cqrs-pattern.md
│       ├── evaluation-checklist.md
│       └── anti-patterns.md
│
├── code-review/                    # 체계적 코드 리뷰
│   ├── SKILL.md
│   └── references/
│       ├── review-workflow.md
│       ├── severity-levels.md
│       ├── python-best-practices.md
│       └── security-checklist.md
│
├── langgraph-pipeline/             # LangGraph 1.0+ 파이프라인
│   ├── SKILL.md
│   └── references/
│       ├── state-management.md
│       ├── graph-patterns.md
│       ├── checkpointing.md
│       └── testing-patterns.md
│
├── event-driven/                   # Redis Composite Event Bus
│   ├── SKILL.md
│   └── references/
│       ├── event-router.md
│       ├── sse-gateway.md
│       ├── idempotency.md
│       └── failure-recovery.md
│
├── grpc-service/                   # gRPC 서비스 통합
│   ├── SKILL.md
│   └── references/
│       ├── port-adapter-grpc.md
│       ├── proto-guide.md
│       ├── error-handling.md
│       └── testing-grpc.md
│
├── rag-pipeline/                   # RAG (Contextual Retrieval)
│   ├── SKILL.md
│   └── references/
│       ├── retrieval-strategy.md
│       ├── tag-based-retriever.md
│       ├── evidence-tracking.md
│       └── evaluation-phases.md
│
├── prompt-engineering/             # 프롬프트 설계/평가
│   ├── SKILL.md
│   └── references/
│       ├── template-structure.md
│       ├── evaluation-methods.md
│       └── optimization-techniques.md
│
├── redis-patterns/                 # Redis 패턴 가이드
│   ├── SKILL.md
│   └── references/
│       ├── cache-aside.md
│       ├── rate-limiting.md
│       └── messaging-patterns.md
│
└── k8s-debugging/                  # Kubernetes 운영/디버깅
    ├── SKILL.md
    └── references/
        ├── pod-troubleshooting.md      # Pod 트러블슈팅
        ├── log-analysis.md             # 로그 분석
        ├── network-diagnosis.md        # 네트워크 진단
        ├── label-policies.md           # 라벨 정책
        ├── cluster-architecture.md     # 클러스터 구조
        ├── gitops-argocd.md            # GitOps/ArgoCD
        ├── operators-crd.md            # Operator/CRD/CR
        └── helm-deployment.md          # Helm 배포
```

---

## 각 Skill을 소개합니다

### 1. clean-architecture

> 트리거: `clean architecture`, `port`, `adapter`, `hexagonal`, `layer`

Eco² 프로젝트의 핵심 아키텍처 원칙을 담은 Clean Architecture 4-Layer 구현 가이드입니다.

**주요 내용**
- **Layer 구조**: Domain → Application → Infrastructure → Presentation
- **Port/Adapter 패턴**: 인터페이스를 통한 의존성 역전
- **CQRS**: Command/Query 분리 패턴
- **평가 체크리스트**: 아키텍처 준수 여부 점검
- **Anti-Patterns**: 피해야 할 패턴 목록

```python
# Port 정의 (Application Layer)
class LLMClient(Protocol):
    async def generate(self, prompt: str) -> str: ...

# Adapter 구현 (Infrastructure Layer)
class GeminiClient(LLMClient):
    async def generate(self, prompt: str) -> str:
        return await self._client.generate_content(prompt)
```

---

### 2. code-review

> 트리거: `review`, `code review`, `evaluate`, `check code`, `PR review`

일관된 기준으로 코드 품질을 평가하는 체계적인 코드 리뷰 도구입니다.

**주요 내용**
- **6단계 리뷰 워크플로우**: Context → Architecture → Logic → Style → Security → Summary
- **심각도 레벨**: Critical / Major / Minor / Suggestion
- **Python Best Practices**: Eco² 코딩 컨벤션
- **Security Checklist**: OWASP Top 10 기반

```markdown
## 심각도 레벨

| Level | 설명 | 예시 |
|-------|------|------|
| Critical | 즉시 수정 필요 | SQL Injection, 인증 우회 |
| Major | 머지 전 수정 | 에러 핸들링 누락, 레이스 컨디션 |
| Minor | 권장 수정 | 네이밍 개선, 중복 코드 |
| Suggestion | 선택적 | 성능 최적화 힌트 |
```

---

### 3. langgraph-pipeline

> 트리거: `langgraph`, `pipeline`, `graph`, `workflow`, `subagent`, `checkpointer`

Eco² 챗봇의 Intent-Routed Workflow를 다루는 LangGraph 1.0+ 기반 파이프라인 구축 가이드입니다.

**주요 내용**
- **Eco² Pipeline**: Intent Node → Branching → Subagent Fan-out → Answer Generation
- **StateGraph 패턴**: Sequential, Branching, Fan-out, Loop, Feedback
- **Cache-Aside Checkpointing**: Redis L1 + PostgreSQL L2
- **State 관리**: TypedDict, Annotated Reducer

```python
# Eco² Intent-Routed Workflow
graph = StateGraph(ChatState)
graph.add_node("intent", intent_node)
graph.add_node("rag", rag_node)
graph.add_node("character", character_node)
graph.add_node("answer", answer_node)

graph.add_conditional_edges(
    "intent",
    route_by_intent,
    {"rag": "rag", "character": "character", "direct": "answer"}
)
```

---

### 4. event-driven

> 트리거: `event`, `sse`, `stream`, `pubsub`, `broadcast`, `realtime`

실시간 이벤트 스트리밍 아키텍처를 다루는 Redis 기반 Composite Event Bus 패턴 가이드입니다.

**주요 내용**
- **Event Router**: Redis Streams Consumer Group (XREADGROUP)
- **SSE Gateway**: Pub/Sub 구독 + State 폴링
- **Idempotency**: E2E Exactly-Once 보장 패턴
- **Failure Recovery**: Consumer Crash, Network Partition 시나리오

```
┌─────────────────────────────────────────────────────────────┐
│                    Event Flow Architecture                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Chat Worker ──XADD──▶ Redis Streams ──XREADGROUP──▶ Event  │
│                         (chat:events)                Router  │
│                                                       │      │
│                                                       ▼      │
│  SSE Gateway ◀──SUBSCRIBE── Redis Pub/Sub ◀──PUBLISH──┘     │
│       │                     (user:{id}:events)               │
│       ▼                                                      │
│   Browser (EventSource)                                      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

### 5. grpc-service

> 트리거: `grpc`, `proto`, `subagent`, `character`, `location`, `rpc`

Character/Location Subagent 연동 패턴을 다루는 gRPC 서비스 통합 가이드입니다.

**주요 내용**
- **Port/Adapter 적용**: gRPC 클라이언트의 인터페이스 추상화
- **Lazy Connection**: 필요 시점에 연결 수립
- **Proto 가이드**: 메시지/서비스 정의
- **테스트 패턴**: Mock Stub 활용

```python
# Port (Application Layer)
class CharacterClient(Protocol):
    async def get_by_match(self, label: str) -> Character | None: ...

# Adapter (Infrastructure Layer)
class GrpcCharacterClient(CharacterClient):
    async def get_by_match(self, label: str) -> Character | None:
        response = await self._stub.GetCharacterByMatch(
            CharacterRequest(match_label=label)
        )
        return self._to_domain(response)
```

---

### 6. rag-pipeline

> 트리거: `rag`, `retrieval`, `retriever`, `evidence`, `citation`, `nugget`

Anthropic의 Contextual Retrieval 패턴을 적용한 RAG 파이프라인 가이드입니다.

**주요 내용**
- **검색 전략**: Classification → Contextual → Keyword (Fallback Chain)
- **TagBasedRetriever**: 의도 기반 태그 필터링 + 임베딩 검색
- **Evidence 추적**: 출처 링크 및 신뢰도 스코어
- **평가 체계**: Citation → Completeness → Groundedness → Next Steps

```python
# Contextual Retrieval Flow
async def retrieve(self, query: str, intent: Intent) -> list[Evidence]:
    # 1. Intent에서 검색 태그 추출
    tags = self._extract_tags(intent)

    # 2. Tag 기반 필터링 + 임베딩 유사도
    candidates = await self._vector_store.search(
        query=query,
        filter={"tags": {"$in": tags}},
        top_k=10
    )

    # 3. Reranking
    return self._rerank(query, candidates)[:5]
```

---

### 7. prompt-engineering

> 트리거: `prompt`, `template`, `system prompt`, `few-shot`, `chain-of-thought`

템플릿 설계부터 평가까지 전 과정을 다루는 프롬프트 엔지니어링 가이드입니다.

**주요 내용**
- **템플릿 구조**: Role → Context → Instruction → Constraints → Format → Examples
- **평가 방법**: 자동 메트릭 (ROUGE, BERTScore) + LLM 기반 평가
- **최적화 기법**: Compression, Few-Shot Selection, CoT, Self-Consistency

```
┌─────────────────────────────────────┐
│ Role: 역할 정의                      │
├─────────────────────────────────────┤
│ Context: 배경 정보, 도메인 지식        │
├─────────────────────────────────────┤
│ Instruction: 구체적인 작업 지시        │
├─────────────────────────────────────┤
│ Constraints: 제약 조건, 금지 사항      │
├─────────────────────────────────────┤
│ Format: 출력 형식 (JSON, Markdown 등) │
├─────────────────────────────────────┤
│ Examples: Few-shot 예시 (선택)        │
└─────────────────────────────────────┘
```

---

### 8. redis-patterns

> 트리거: `redis`, `cache`, `rate limit`, `pubsub`, `streams`

Eco² 프로젝트에서 사용하는 캐시, 레이트 리밋, 메시징 패턴을 다루는 Redis 활용 가이드입니다.

**주요 내용**
- **Cache-Aside**: Read-through/Write-through 패턴
- **Rate Limiting**: Sliding Window, Token Bucket
- **Pub/Sub & Streams**: 실시간 메시징 vs 영속 이벤트 스트림

```python
# Cache-Aside Pattern
async def get_character(self, id: str) -> Character | None:
    # 1. Cache Hit?
    cached = await self._redis.get(f"character:{id}")
    if cached:
        return Character.model_validate_json(cached)

    # 2. Cache Miss → DB 조회
    character = await self._repo.find_by_id(id)
    if character:
        await self._redis.setex(
            f"character:{id}",
            timedelta(hours=1),
            character.model_dump_json()
        )
    return character
```

---

### 9. k8s-debugging

> 트리거: `k8s`, `kubernetes`, `pod`, `debug`, `logs`, `kubectl`, `argocd`, `helm`, `operator`, `crd`

디버깅뿐만 아니라 클러스터 인프라 전반을 다루는 Kubernetes 운영/디버깅 가이드입니다.

**디버깅 영역**
- **라벨 정책**: tier, domain, version, environment
- **Pod 트러블슈팅**: CrashLoopBackOff, ImagePullBackOff, Pending
- **로그 분석**: stern, kubectl logs 활용
- **네트워크 진단**: DNS, Service Discovery, gRPC 연결

**인프라/배포 영역**
- **클러스터 구조**: EKS Node Pool, Namespace Tier 체계, Istio Service Mesh
- **GitOps/ArgoCD**: App-of-Apps, Sync Wave 전략, Kustomize 통합
- **Operator/CRD/CR**: External Secrets, Prometheus Operator, Cert Manager
- **Helm 배포**: Values 관리, ArgoCD+Helm 통합, Chart 버전 관리

```bash
# 라벨 기반 조회
kubectl get pods -l tier=business-logic -A    # API 서비스
kubectl get pods -l tier=worker -A            # 워커
kubectl get pods -l domain=chat -A            # Chat 도메인 전체

# ArgoCD 상태 확인
argocd app list
argocd app get chat-api-prod

# Helm Release 확인
helm list -A
helm get values prometheus -n prometheus

# CRD/CR 상태
kubectl get externalsecret -A
kubectl get servicemonitor -A
```

---

## 마이그레이션 과정

### 1단계: Cursor 자산 분석

`.cursorrules`에 정의된 프로젝트 컨텍스트를 Claude Code 형식으로 변환했습니다.

**기존 .cursorrules (일부)**
```markdown
## 프로젝트 구조
backend/
├── domains/              # 도메인별 API 소스코드
├── workloads/           # Kubernetes 매니페스트
├── clusters/            # ArgoCD Applications
└── scripts/             # 유틸리티 스크립트

## 자주 사용하는 명령어
### SSH 접속
./scripts/utilities/connect-ssh.sh master
```

**변환된 CLAUDE.md**
```markdown
# Eco² Backend

## 아키텍처
- Clean Architecture 4-Layer
- Event-Driven (Redis Streams + Pub/Sub)
- LangGraph 1.0+ 파이프라인

## 디렉토리 구조
- apps/: 마이크로서비스 (chat_worker, sse_gateway, event_router)
- workloads/: Kubernetes 매니페스트 (Kustomize)
```

### 2단계: 외부 컨텍스트 정리

프로젝트 히스토리와 의사결정 배경을 Tistory 블로그에 정리했습니다. Claude Code에서 필요할 때 참조할 수 있는 외부 지식 베이스 역할을 합니다.

```
https://rooftopsnow.tistory.com/category/이코에코(Eco²)
https://rooftopsnow.tistory.com/category/이코에코(Eco²) Knowledge Base
```

### 3단계: CLAUDE.md 생성

프로젝트 루트에 `CLAUDE.md` 파일을 생성했습니다. 프로젝트 개요, 아키텍처 요약, 최근 작업 상태 등 세션 시작 시 자동으로 로드되는 핵심 컨텍스트입니다.

### 4단계: Anthropic Skills 배포

[anthropics/skills](https://github.com/anthropics/skills) 레포에서 범용 skills를 선별해 배포했습니다.

| Skill | 배포 위치 | 용도 |
|-------|-----------|------|
| mcp-builder | Backend | MCP 서버 구축 |
| doc-coauthoring | Backend | 문서 공동 작성 |
| skill-creator | Backend | 커스텀 skill 생성 |
| webapp-testing | Frontend | 웹앱 테스트 |
| pdf | Resume | PDF 처리 |

### 5단계: 커스텀 Skills 작성

프로젝트 코드베이스를 분석해 9개의 커스텀 skills를 작성했습니다.

**분석 대상**
- `infrastructure/orchestration/langgraph/` - LangGraph 파이프라인 패턴
- `infrastructure/integrations/` - gRPC 클라이언트 구현
- `apps/event_router/`, `apps/sse_gateway/` - 이벤트 아키텍처
- `workloads/` - Kustomize 라벨 정책
- `docs/blogs/async/34-sse-HA-architecture.md` - 아키텍처 문서

### 6단계: gitignore 설정

Skills는 로컬 전용으로 관리합니다. 개인 워크플로우 최적화 도구이므로 팀 레포에는 포함하지 않습니다.

```gitignore
# AI Coding Assistants (local skills)
.cursor/
.claude/
```

---

## 마치며

Claude Code로의 전환은 단순한 도구 교체가 아니었습니다. Eco² 프로젝트에는 이미 51개 이상의 로컬 문서와 83개 이상의 블로그 포스트로 구성된 Knowledge Base가 있었습니다. Skills 작성은 이 기존 자산을 Claude Code의 트리거 기반 시스템에 맞게 재구성하는 과정이었습니다.

**이번 작업을 통해 얻은 것들**

1. **컨텍스트 품질 향상**: 트리거 기반으로 관련 지식이 자동 로드됩니다
2. **일관성 확보**: 코드 리뷰, 아키텍처 평가에 동일한 기준을 적용할 수 있습니다
3. **에이전트 온보딩 가속**: 새 세션에서도 프로젝트 컨텍스트를 즉시 활용할 수 있습니다
4. **지식 재구조화**: 기존 문서를 트리거 기반 시스템에 최적화된 형태로 변환했습니다

Skills는 프로젝트와 함께 진화합니다. 새로운 패턴이 도입되거나 아키텍처가 변경될 때마다 업데이트해서 코드베이스와의 동기화를 유지할 예정입니다.

---

## 참고 자료

- [Cursor vs Claude Code 선택 과정](https://rooftopsnow.tistory.com/191)
- [Cursor Pricing](https://cursor.com/pricing)
- [Claude Pricing](https://claude.com/pricing)
- [Anthropic Skills Repository](https://github.com/anthropics/skills)
