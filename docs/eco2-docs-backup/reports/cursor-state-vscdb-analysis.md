# Cursor state.vscdb 16GB 분석 리포트

> 2025.01.15
> AI Coding Agent의 상태 관리 및 컨텍스트 영속화에 대한 기술 분석

## 1. 문제 현황

### 측정 결과

```
/Users/mango/Library/Application Support/Cursor/User/globalStorage/
├── state.vscdb         → 9.2GB
├── state.vscdb.backup  → 7.1GB
├── state.vscdb-wal     → 11MB
└── state.vscdb-shm     → 32KB
                        ─────────
                        Total: ~16.3GB
```

### 전체 디스크 사용량

| 위치 | 용량 | 비고 |
|------|------|------|
| Cursor (state.vscdb) | 16.3GB | **🔥 주범** |
| Notion | 10GB | |
| Library/Caches | 9.6GB | 정리 가능 |
| Google (Chrome) | 5.5GB | |

---

## 2. Cursor 전체 데이터 분포 분석 (~35GB)

### 2.0 전체 데이터 분포

macOS 저장 공간 관리에서 35.10GB로 표시되는 Cursor 데이터의 실제 구성:

| 위치 | 크기 | 설명 |
|------|------|------|
| **Application Support/Cursor** | **17GB** | 핵심 사용자 데이터 |
| **Caches/com.todesktop** | **2.6GB** | Cursor 업데이터 (이전 버전 보관) |
| **~/.cursor** | **1.2GB** | 확장 프로그램, AI 트래킹 |
| **/Applications/Cursor.app** | **892MB** | Cursor 앱 번들 |
| **Caches/Cursor** | **739MB** | 런타임 캐시 |
| **기타 시스템 메타데이터** | ~12GB | Spotlight 인덱스, 임시 파일 등 |
| **총합** | **~35GB** | macOS 저장공간 관리 기준 |

### 2.1 Application Support/Cursor 상세 (17GB)

```
/Users/mango/Library/Application Support/Cursor/
├── User/
│   ├── globalStorage/          → 16GB (state.vscdb 9.2G + backup 7.1G)
│   ├── History/                → 273MB (파일 편집 히스토리)
│   └── workspaceStorage/       → 130MB (프로젝트별 상태)
├── CachedData/                 → 323MB (V8 코드 캐시)
├── logs/                       → 255MB (애플리케이션 로그)
├── Partitions/                 → 88MB
├── WebStorage/                 → 59MB
└── Cache/                      → 50MB
```

### 2.2 ~/.cursor 상세 (1.2GB)

```
~/.cursor/
├── extensions/     → 1.1GB  # 설치된 확장 프로그램 (VS Code 확장)
├── ai-tracking/    → 42MB   # AI 사용량 추적 데이터
├── projects/       → 11MB   # 프로젝트 메타데이터 (터미널 상태 등)
├── browser-logs/   → 9.4MB  # 브라우저 DevTools 로그
└── plans/          → 360KB  # AI Task 계획 (Cursor의 Agent 기능)
```

### 2.3 Cursor 업데이터 캐시 (2.6GB)

```
~/Library/Caches/com.todesktop.230313mzl4w4u92.ShipIt/
└── 이전 버전 설치 파일 보관 (롤백용)
```

**문제점:** 자동 정리 없이 버전 업데이트마다 누적

### 2.4 데이터 유형별 용량 분석

| 데이터 유형 | 예상 용량 | 설명 |
|------------|----------|------|
| **AI Chat History** | ~8GB | 모든 대화 + 코드 블록 (state.vscdb 내) |
| **Composer Sessions** | ~3GB | 멀티파일 편집 세션 컨텍스트 |
| **Codebase Indexing** | ~2GB | 임베딩 벡터, RAG 인덱스 |
| **확장 프로그램** | ~1.1GB | VS Code 호환 확장 |
| **백업/로그** | ~8GB | .backup, -wal, logs |
| **업데이터 캐시** | ~2.6GB | 이전 버전 설치 파일 |
| **기타** | ~10GB | 시스템 메타데이터, 임시 파일 |

---

## 3. Cursor state.vscdb 구조 분석

### 3.1 저장되는 데이터 유형

`state.vscdb`는 **SQLite 데이터베이스**로, 다음 데이터를 저장:

| 데이터 유형 | 설명 | 용량 영향 |
|------------|------|----------|
| **AI Chat History** | 모든 대화 기록 (코드 블록 포함) | 🔥🔥🔥 **매우 큼** |
| **Composer Sessions** | 멀티파일 편집 세션 전체 컨텍스트 | 🔥🔥🔥 |
| **Codebase Indexing** | 임베딩 벡터, RAG 인덱스 | 🔥🔥 |
| **Autocomplete Cache** | AI 코드 완성 히스토리 | 🔥 |
| **Extension globalState** | 확장 프로그램 전역 상태 | 🔥 |
| **Workspace State** | 열린 파일, 커서 위치, 에디터 상태 | 작음 |
| **Error Logs** | 오류 및 디버그 로그 | 중간 |

### 3.2 왜 이렇게 커졌나?

#### 사용 패턴 분석

```
• 83+ 블로그 포스트 작성 (AI 대화로)
• 51+ Knowledge Base 문서 작성
• 긴 Agent 대화 세션 (이 대화만 해도 수만 토큰)
• 멀티파일 Composer 세션 다수
• 대규모 코드베이스 인덱싱 (24-node K8s 인프라 코드)
```

#### 핵심 원인: **컨텍스트 영속화 (Context Persistence)**

Cursor는 **모든 AI 대화를 전체 컨텍스트와 함께 저장**합니다:

```
대화 1개 = 시스템 프롬프트 + 사용자 메시지 + AI 응답 + 코드 블록 + 파일 참조
       ≈ 10,000 ~ 100,000 tokens per session
       ≈ 50KB ~ 500KB per session (압축 전)
```

**100개 세션 × 평균 100KB = 10GB** (실제로는 압축 없이 저장)

---

## 4. AI Coding Agent 아키텍처 인사이트

### 4.1 Cursor의 컨텍스트 관리 전략

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Cursor Context Architecture                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   ┌──────────────────┐                                              │
│   │   User Input     │                                              │
│   │   (Query/Code)   │                                              │
│   └────────┬─────────┘                                              │
│            │                                                         │
│            ▼                                                         │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │              Context Assembly Layer                          │  │
│   │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐│  │
│   │  │ Chat History│ │ Codebase    │ │ File Context            ││  │
│   │  │ (state.vscdb)│ │ Index (RAG) │ │ (Open Files, Cursor)    ││  │
│   │  └─────────────┘ └─────────────┘ └─────────────────────────┘│  │
│   └────────────────────────┬─────────────────────────────────────┘  │
│                            │                                         │
│                            ▼                                         │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │                    LLM API Call                              │  │
│   │           (Claude / GPT-4 / Custom Models)                   │  │
│   └──────────────────────────────────────────────────────────────┘  │
│                            │                                         │
│                            ▼                                         │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │              Response + State Update                         │  │
│   │         (저장: state.vscdb, -wal, -journal)                  │  │
│   └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 SQLite WAL Mode의 영향

Cursor는 **WAL (Write-Ahead Logging) 모드**를 사용:

```sql
-- Cursor가 사용하는 SQLite 설정 (추정)
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
```

**WAL 모드 특성:**
- 읽기/쓰기 동시성 향상
- `-wal` 파일에 변경사항 먼저 기록
- 주기적으로 main DB에 checkpoint
- **문제: checkpoint가 제대로 안 되면 -wal 파일 비대화**

### 4.3 지속적 쓰기 문제 (Constant Writes)

사용자 포럼 보고에 따르면:
- `state.vscdb-journal`에 **몇 초마다** 쓰기 발생
- **HDD 사용률 100%** 유발 가능
- 시스템 전체 프리징 발생 사례

**원인:** 
- AI 대화 중 실시간 상태 저장
- 자동 완성 캐시 업데이트
- Extension 상태 동기화

### 4.4 실제 사용자 사례 분석

#### Case 1: Notepad 데이터 손실 ([Forum #101145](https://forum.cursor.com/t/today-i-deleted-the-chat-records-and-the-data-in-notepad-myself/101145))

> "채팅 중 창이 갑자기 응답하지 않았습니다. 재시작 후에도 창이 응답하지 않고, 채팅 영역이 로딩 상태로 유지되었습니다."

**상황:**
- 특정 프로젝트에서만 Cursor 창 응답 없음
- 다른 프로젝트는 정상 작동
- 데이터 오류로 인한 문제로 추정

**해결 방법:**
```
C:\Users\xxx\AppData\Roaming\Cursor\User\workspaceStorage\{project md5}
```
해당 폴더 삭제 → **채팅 기록 + Notepad 데이터 손실**

**교훈:**
- `state.vscdb`에 저장된 Notepad 데이터는 백업/복구가 번거로움
- IDE 레벨의 Recycle 시스템 필요 (삭제 대신 .history로 이동)
- [SpecStory](https://github.com/specstory/specstory) 확장 프로그램으로 대화 기록 백업 권장

#### Case 2: Multi-Agent Workflow 메모리 누수 ([Forum #142762](https://forum.cursor.com/t/slowness-since-2-0/142762))

> "Cursor 2.0 이후 점점 느려지고 있습니다. IDE를 닫을 때마다 대기 다이얼로그가 나타납니다."

**분석 결과:**
```
globalStorage/state.vscdb: 13.71GB (정상: <10MB)
cursorDiskKV 테이블: 354,893 엔트리 (정상: ~300개)
ItemTable: 303 엔트리
```

**핵심 발견:**
1. `cursorDiskKV` 테이블에 **cleanup 버그** 존재
2. Multi-agent workflow 데이터가 계속 누적
3. 삭제 후 노트북 온도 즉시 하강
4. **하루 만에 다시 1GB로 증가** → 근본적 버그

**Cursor 공식 권장 복구:**
```bash
# 1. Cursor 완전 종료
# 2. 파일 삭제 또는 이름 변경
~/Library/Application Support/Cursor/User/globalStorage/state.vscdb
~/Library/Application Support/Cursor/User/globalStorage/state.vscdb.backup

# 3. Cursor 재시작
```

**손실되는 데이터:** 전역 UI 상태, 일부 확장 프로그램 UI 상태, 창 위치
**유지되는 데이터:** 설정, 확장 프로그램, 워크스페이스 데이터

#### Case 3: 100GB 극단적 사례 ([Forum #147615](https://forum.cursor.com/t/surely-its-a-bug-that-it-49-8gb-for-state-vscdb-backup-and-50-54gb-for-state-vscdb/147615))

```
state.vscdb:        50.54GB
state.vscdb.backup: 49.8GB
────────────────────────────
Total:              ~100GB (!!)
```

**Cursor 공식 답변 요약:**

> "VS Code의 알려진 시스템 레벨 이슈입니다. Cursor는 VS Code fork이므로 동일한 문제가 발생할 수 있습니다."

**원인 3가지:**
1. **다중 workspace 캐시** - 새 창마다 `workspaceStorage/`에 새 폴더 생성
2. **확장 프로그램** - 대용량 인덱스 DB 생성 (예: 코드 분석 도구)
3. **전역 설정 정크** - 오래된 데이터 누적

**중요 사실: 채팅 기록은 손실되지 않음**
```
globalStorage/state.vscdb     → 전역 UI 설정 (삭제 가능)
workspaceStorage/<id>/state.vscdb → 프로젝트별 채팅 기록 (보존됨)
```

**권장 복구 절차:**
```bash
# 1. 프로필 내보내기 (Settings → Profiles → Export)
# 2. 삭제
rm ~/Library/Application\ Support/Cursor/User/globalStorage/state.vscdb*
# 3. 재시작 → 새로운 clean DB 생성
```

**Cursor 팀 계획:**
- 오래된 데이터 **자동 정리** 기능 추가 예정
- **디스크 사용량 경고** 기능 추가 예정

---

## 5. Agent 개발을 위한 설계 인사이트

### 5.1 컨텍스트 영속화 전략

| 전략 | 장점 | 단점 | Cursor 적용 |
|------|------|------|------------|
| **전체 저장** | 완전한 복구 가능 | 용량 폭증 | ✅ 현재 방식 |
| **요약 저장** | 용량 절약 | 디테일 손실 | ❌ |
| **TTL 기반 삭제** | 자동 정리 | 중요 데이터 유실 | ❌ |
| **계층적 저장** | 균형 | 구현 복잡도 | ❌ |

#### 권장: 계층적 컨텍스트 저장

```python
class HierarchicalContextStore:
    """계층적 컨텍스트 저장소"""
    
    def __init__(self):
        self.hot_cache = LRUCache(maxsize=10)      # 최근 10개 세션 (메모리)
        self.warm_storage = SQLite("state.vscdb")  # 30일 이내 (로컬)
        self.cold_archive = S3("context-archive")  # 30일+ (클라우드)
    
    def save_session(self, session: ChatSession):
        # 1. Hot cache에 즉시 저장
        self.hot_cache[session.id] = session
        
        # 2. 요약본만 warm storage에 저장
        summary = self._summarize(session)
        self.warm_storage.insert(summary)
        
        # 3. 전체 데이터는 비동기로 cold archive에
        asyncio.create_task(
            self.cold_archive.upload(session.to_json())
        )
    
    def _summarize(self, session: ChatSession) -> dict:
        """세션 요약 (용량 90% 감소)"""
        return {
            "id": session.id,
            "timestamp": session.timestamp,
            "topic": self._extract_topic(session),
            "key_decisions": self._extract_decisions(session),
            "files_modified": session.files_modified,
            # 전체 대화는 저장하지 않음
        }
```

### 5.2 Anthropic의 Agent 설계 원칙

Anthropic "Building Effective Agents" 블로그에서 제시하는 패턴:

#### Workflow vs Agent

```
┌─────────────────────────────────────────────────────────────────────┐
│  Workflow (Predefined)           │  Agent (Dynamic)                 │
├──────────────────────────────────┼──────────────────────────────────┤
│  Chain: A → B → C → D            │  Loop:                           │
│  • 고정된 실행 순서              │    while not done:               │
│  • 예측 가능한 결과              │      action = llm.decide()       │
│  • 디버깅 용이                   │      result = tool.execute()     │
│                                  │      context.update(result)      │
│  Routing: if x → A else B        │  • 동적 의사결정                 │
│  • 조건부 분기                   │  • 예측 불가능한 경로            │
│  • 제한된 유연성                 │  • 복잡한 디버깅                 │
└──────────────────────────────────┴──────────────────────────────────┘
```

#### 상태 관리 패턴

```python
# Bad: 모든 상태를 하나의 DB에 저장
class MonolithicState:
    db: SQLite  # state.vscdb가 이 방식
    
# Good: 책임 분리된 상태 관리
class SeparatedState:
    chat_history: ChatHistoryStore      # 대화 기록 (요약 + 참조)
    codebase_index: VectorStore         # 임베딩 (별도 파일)
    user_preferences: ConfigStore       # 설정 (작은 파일)
    session_state: InMemoryCache        # 현재 세션 (휘발성)
```

### 5.3 컨텍스트 윈도우 최적화

Claude API의 **Prompt Caching** 활용:

```python
# Anthropic Prompt Caching 예시
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    system=[
        {
            "type": "text",
            "text": "You are a helpful coding assistant...",
            "cache_control": {"type": "ephemeral"}  # 캐시 활성화
        }
    ],
    messages=[...]
)

# 캐시 히트 시 비용 90% 절감, 지연 75% 감소
```

**Cursor에서의 적용:**
- 시스템 프롬프트 캐싱
- 코드베이스 컨텍스트 캐싱
- 반복 패턴 캐싱

### 5.4 자동 정리 메커니즘

```python
class AutoCleanupManager:
    """자동 정리 관리자"""
    
    POLICIES = {
        "chat_history": {
            "max_age_days": 30,
            "max_size_mb": 500,
            "keep_starred": True,
        },
        "codebase_index": {
            "rebuild_on_change": True,
            "max_staleness_hours": 24,
        },
        "cache": {
            "max_size_mb": 100,
            "eviction": "LRU",
        },
    }
    
    async def cleanup(self):
        for store_name, policy in self.POLICIES.items():
            store = getattr(self, store_name)
            
            # 오래된 데이터 삭제
            if "max_age_days" in policy:
                cutoff = datetime.now() - timedelta(days=policy["max_age_days"])
                await store.delete_older_than(cutoff)
            
            # 크기 제한 적용
            if "max_size_mb" in policy:
                while store.size_mb > policy["max_size_mb"]:
                    await store.evict_oldest()
            
            # VACUUM 실행 (SQLite)
            await store.vacuum()
```

---

## 6. 즉시 적용 가능한 해결책

### 6.1 Cursor 정리 스크립트

```bash
#!/bin/bash
# cursor-cleanup.sh

CURSOR_DATA="$HOME/Library/Application Support/Cursor"

# 1. Cursor 종료 확인
if pgrep -x "Cursor" > /dev/null; then
    echo "⚠️  Cursor를 먼저 종료해주세요"
    exit 1
fi

# 2. 백업 파일 삭제 (안전)
rm -f "$CURSOR_DATA/User/globalStorage/state.vscdb.backup"
rm -f "$CURSOR_DATA/User/globalStorage/state.vscdb-wal"

# 3. 캐시 정리
rm -rf "$CURSOR_DATA/Cache"
rm -rf "$CURSOR_DATA/CachedData"
rm -rf "$CURSOR_DATA/logs"

# 4. SQLite VACUUM (선택)
# sqlite3 "$CURSOR_DATA/User/globalStorage/state.vscdb" "VACUUM;"

echo "✅ 정리 완료"
du -sh "$CURSOR_DATA"
```

### 6.2 시스템 캐시 정리

```bash
# macOS 캐시 전체 정리
rm -rf ~/Library/Caches/*

# Docker 정리 (사용 시)
docker system prune -a --volumes

# Homebrew 캐시
brew cleanup --prune=all
```

---

## 7. Chat Worker Agent 설계에 적용

### 현재 chat_worker 아키텍처

```
chat_worker/
├── application/
│   ├── intent/          # 의도 분류
│   ├── feedback/        # 품질 평가 ← NEW
│   └── commands/        # CQRS Command
├── infrastructure/
│   ├── orchestration/
│   │   └── langgraph/   # 상태 기계
│   └── feedback/
│       └── llm_feedback_evaluator.py
└── domain/
    └── enums/
        └── fallback_reason.py  # Fallback 사유
```

### 상태 관리 개선 제안

```python
# chat_worker의 세션 상태 관리 개선
class ChatSessionState:
    """Redis 기반 세션 상태 (휘발성)"""
    
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.ttl = 3600  # 1시간 후 자동 삭제
    
    async def save(self, session_id: str, state: dict):
        # 전체 대화 대신 요약만 저장
        summary = {
            "intent": state.get("classified_intent"),
            "stage": state.get("current_stage"),
            "fallback_count": state.get("fallback_count", 0),
            "last_message_preview": state.get("user_message", "")[:100],
        }
        await self.redis.setex(
            f"chat:session:{session_id}",
            self.ttl,
            json.dumps(summary)
        )
    
    # 전체 대화 기록은 별도 영속 스토어에
    async def archive_full_conversation(self, session_id: str, messages: list):
        # PostgreSQL 또는 S3에 비동기 저장
        pass
```

---

## 8. 핵심 인사이트 정리

### 8.1 AI Coding Agent의 상태 관리 트레이드오프

| 관점 | Cursor 선택 | 대안 | 트레이드오프 |
|------|------------|------|-------------|
| **완전성** | 모든 대화 저장 | 요약만 저장 | 복구 가능성 vs 용량 |
| **응답성** | 로컬 SQLite | 클라우드 동기화 | 오프라인 지원 vs 동기화 |
| **영속성** | 무기한 보관 | TTL 기반 삭제 | 히스토리 vs 정리 |
| **일관성** | WAL 모드 | 주기적 커밋 | 동시성 vs I/O 부하 |

### 8.2 데이터 유형별 최적 저장 전략

```
┌─────────────────────────────────────────────────────────────────────┐
│              AI Agent 데이터 저장 전략 매트릭스                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐         │
│  │   Hot Data     │  │   Warm Data    │  │   Cold Data    │         │
│  │   (메모리)      │  │   (로컬 DB)    │  │   (클라우드)   │         │
│  ├────────────────┤  ├────────────────┤  ├────────────────┤         │
│  │ • 현재 세션    │  │ • 최근 30일    │  │ • 30일+ 아카이브│         │
│  │ • 활성 컨텍스트│  │ • 자주 참조    │  │ • 드문 참조    │         │
│  │ • 자동완성 캐시│  │ • 프로젝트 설정│  │ • 전체 대화 로그│         │
│  ├────────────────┤  ├────────────────┤  ├────────────────┤         │
│  │ TTL: 세션 종료 │  │ TTL: 30일      │  │ TTL: 1년+      │         │
│  │ Size: ~100MB  │  │ Size: ~500MB   │  │ Size: 무제한   │         │
│  └────────────────┘  └────────────────┘  └────────────────┘         │
│                                                                      │
│  ───────────────────────────────────────────────────────────────────│
│  Key Insight: Cursor는 모든 데이터를 Warm Storage(SQLite)에          │
│  집중시켜 용량 폭증. 계층 분리가 필요.                                │
└─────────────────────────────────────────────────────────────────────┘
```

### 8.3 I/O 패턴 최적화

| 문제 | 원인 | 해결책 |
|------|------|--------|
| 지속적 디스크 쓰기 | WAL 모드 + 실시간 저장 | 배치 쓰기 (debounce) |
| 백업 파일 비대화 | 자동 정리 없음 | 롤링 백업 (최근 N개만) |
| 인덱스 재구축 | 변경 시 전체 재인덱싱 | 증분 인덱싱 (delta) |
| 캐시 누적 | LRU 없음 | 용량 기반 eviction |

### 8.4 Agent 아키텍처 설계 권장사항

```python
# ❌ Anti-pattern: Cursor의 현재 방식
class MonolithicAgentState:
    db: SQLite("state.vscdb")  # 모든 것을 하나의 DB에
    
    def save_everything(self):
        # 전체 컨텍스트를 매번 저장
        self.db.insert(self.full_context)

# ✅ Recommended: 책임 분리
class LayeredAgentState:
    """계층화된 상태 관리"""
    
    # Layer 1: Hot (In-Memory)
    session_cache: LRUCache[SessionID, SessionContext]
    
    # Layer 2: Warm (Local SQLite with TTL)
    recent_history: SQLiteStore(max_age_days=30, max_size_mb=500)
    
    # Layer 3: Cold (Cloud Storage)
    archive: S3Store(compression="zstd")
    
    # Layer 4: Indexes (Separate, Rebuildable)
    codebase_index: VectorStore(path="embeddings.lance")
    
    def save_session(self, session: Session):
        # 1. Hot cache 즉시 업데이트
        self.session_cache[session.id] = session
        
        # 2. Warm storage에 요약만 (debounced)
        self._debounce_save(session.summarize())
        
        # 3. Cold archive에 전체 (비동기, 배치)
        self._queue_archive(session)
```

### 8.5 Cursor/Claude Code 비교 인사이트

| 기능 | Cursor | Claude Code (MCP) |
|------|--------|-------------------|
| **상태 저장** | 로컬 SQLite (무제한) | 세션 기반 (휘발성) |
| **컨텍스트** | 전체 히스토리 참조 | Prompt Caching |
| **인덱싱** | 임베딩 벡터 로컬 저장 | MCP 서버로 분리 |
| **확장성** | 확장 프로그램 (~1GB) | MCP 도구 (경량) |
| **업데이터** | todesktop (버전 보관) | CLI 업데이트 |

**핵심 차이:**
- Cursor: **UX 우선** (오프라인 지원, 완전한 히스토리)
- Claude Code: **경량화 우선** (MCP로 기능 분리, 세션 기반)

### 8.6 실사용자 사례에서 얻은 교훈

| 사례 | 문제 | 원인 | Agent 설계 시사점 |
|------|------|------|------------------|
| **Notepad 손실** | 프로젝트 응답 없음 | 손상된 상태 데이터 | 데이터 무결성 검증 + 자동 복구 |
| **13GB 누적** | IDE 점점 느려짐 | cursorDiskKV cleanup 미동작 | 테이블별 정리 스케줄러 필수 |
| **100GB 극단** | 디스크 풀 | 다중 workspace + 확장 인덱스 | **용량 제한 + 경고 시스템** |
| **하루 1GB 증가** | 재발 | Multi-agent 세션 누적 | 세션 종료 시 명시적 정리 |
| **UI 저장 hang** | 종료 지연 | 대용량 DB 쓰기 | 비동기 저장 + 청크 분할 |

#### 핵심 Anti-Pattern: cursorDiskKV 테이블

```sql
-- Cursor의 실제 테이블 구조 (추정)
CREATE TABLE cursorDiskKV (
    key TEXT PRIMARY KEY,
    value BLOB
);

-- 문제: 354,893개 엔트리 누적 (정상 ~300개)
-- 원인: Multi-agent workflow 데이터 cleanup 누락

-- 권장 해결책
CREATE TABLE cursorDiskKV (
    key TEXT PRIMARY KEY,
    value BLOB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP  -- TTL 추가
);

-- 주기적 정리
DELETE FROM cursorDiskKV WHERE expires_at < datetime('now');
```

#### Agent 세션 정리 패턴

```python
class AgentSessionManager:
    """Multi-agent 세션 관리자"""
    
    def __init__(self, db: SQLite):
        self.db = db
        self._register_cleanup_hook()
    
    def _register_cleanup_hook(self):
        """종료 시 정리 훅 등록"""
        import atexit
        atexit.register(self._cleanup_all_sessions)
    
    async def create_session(self, session_id: str) -> AgentSession:
        session = AgentSession(session_id)
        # 세션 생성 시 expires_at 설정
        await self.db.execute(
            "INSERT INTO sessions (id, expires_at) VALUES (?, ?)",
            (session_id, datetime.now() + timedelta(hours=24))
        )
        return session
    
    async def close_session(self, session_id: str):
        """세션 종료 시 관련 데이터 즉시 정리"""
        # 1. Hot cache에서 제거
        self.cache.pop(session_id, None)
        
        # 2. DB에서 세션 관련 KV 삭제
        await self.db.execute(
            "DELETE FROM agentDiskKV WHERE key LIKE ?",
            (f"session:{session_id}:%",)
        )
        
        # 3. 필요 시 요약만 아카이브
        await self._archive_summary(session_id)
    
    async def _cleanup_all_sessions(self):
        """앱 종료 시 전체 정리"""
        # 만료된 세션 일괄 삭제
        await self.db.execute(
            "DELETE FROM sessions WHERE expires_at < datetime('now')"
        )
        # VACUUM으로 공간 회수
        await self.db.execute("VACUUM")
```

### 8.7 데이터 정리 정책 설계

```yaml
# agent-cleanup-policy.yaml
policies:
  chat_history:
    retention_days: 30
    max_size_mb: 500
    summarize_after_days: 7
    archive_to: s3://agent-archive
    
  codebase_index:
    rebuild_trigger: "file_change > 100"
    max_staleness_hours: 24
    incremental: true
    
  session_cache:
    max_entries: 50
    eviction: "LRU"
    persist_on_close: true
    
  backups:
    max_count: 3
    rotation: "daily"
    compression: "zstd"
    
  logs:
    retention_days: 7
    max_size_mb: 100
    level: "INFO"
```

---

## 9. 결론 및 권장사항

### 즉시 조치

1. **state.vscdb.backup 삭제** → 7.1GB 즉시 회수
2. **Library/Caches 정리** → 9.6GB 회수
3. **Cursor 로그/캐시 정리** → 500MB+ 회수

### 장기 개선 (Agent 개발 시)

| 항목 | 현재 (Cursor) | 권장 방식 |
|------|--------------|----------|
| 대화 저장 | 전체 저장 (SQLite) | 요약 + Cold Archive |
| 인덱스 | 단일 DB | 별도 Vector Store |
| 캐시 | 무제한 | LRU + TTL |
| 정리 | 수동 | 자동 (Policy 기반) |

### 참고 자료

**Cursor Forum 사례:**
- [Notepad 데이터 손실 사례](https://forum.cursor.com/t/today-i-deleted-the-chat-records-and-the-data-in-notepad-myself/101145) - workspaceStorage 손상으로 인한 데이터 손실
- [Cursor 2.0 이후 느려짐](https://forum.cursor.com/t/slowness-since-2-0/142762) - cursorDiskKV 354,893 엔트리 누적, 13.71GB 문제
- [100GB 극단적 사례](https://forum.cursor.com/t/surely-its-a-bug-that-it-49-8gb-for-state-vscdb-backup-and-50-54gb-for-state-vscdb/147615) - VS Code 상속 이슈, 자동 정리 필요성
- [state.vscdb 응답 없음](https://forum.cursor.com/t/window-unresponsive-when-generating-reply/86346)
- [state.vscdb-journal 지속적 쓰기](https://forum.cursor.com/t/i-see-constant-writes-to-state-vscdb-journal/86078)

**기술 문서:**
- [Anthropic: Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- [Anthropic: Prompt Caching](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
- [SQLite WAL Mode](https://www.sqlite.org/wal.html)

**관련 도구:**
- [SpecStory](https://github.com/specstory/specstory) - Cursor 대화 기록 백업 확장

---

## 변경 이력

| 날짜 | 변경 내용 |
|------|----------|
| 2025-01-15 | 초안 작성 |
| 2025-01-15 | 전체 데이터 분포 분석 추가 (~35GB 상세 내역) |
| 2025-01-15 | 핵심 인사이트 섹션 추가 (8.1~8.7) |
| 2025-01-15 | Cursor Forum 실사용자 사례 분석 추가 (4.4, 8.6) |
| 2025-01-15 | cursorDiskKV 테이블 누적 버그 및 Multi-agent cleanup 패턴 추가 |
| 2025-01-15 | 100GB 극단적 사례 추가 (VS Code 상속 이슈, 자동 정리 계획) |

