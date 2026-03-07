# 이코에코(Eco2) Message Queue #13: Worker Pool 통합 및 DB Connection Pool 최적화

> **작성일**: 2025-12-24  
> **GitHub**: [eco2-team/backend](https://github.com/eco2-team/backend)  
> **브랜치**: `feat/high-throughput-workers`  
> **관련 문서**: [#12: Celery Gevent Pool 전환](./16-celery-gevent-pool-migration.md)

## 1. 개요

본 문서는 모든 Worker를 역할에 맞는 Pool 타입으로 통합하고, PostgreSQL Connection Pool을 환경변수로 중앙 관리하여 Worker의 Concurrency와 DB Pool을 정합시킨 과정을 기록합니다.

### 1.1 변경 목표

1. **Worker Pool 통합**: 역할별 최적 Pool 타입 선정
2. **DB Pool 중앙 관리**: 환경변수 기반 설정으로 유연성 확보
3. **Concurrency ↔ Pool 정합**: Worker 동시성과 DB 커넥션 제한 일치
4. **DLQ 라우팅 수정**: Dead Letter Queue가 올바른 Worker로 전달되도록 수정

---

## 2. 아키텍처: Worker 중심 DB 접근

### 2.1 미래 방향성

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Worker 중심 DB 접근 아키텍처                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [Client] ──→ [API Services] ──→ [RabbitMQ] ──→ [Workers] ──→ [PostgreSQL] │
│                    │                                ↑                       │
│                    └── DB 직접 접근 최소화 ──────────┘                      │
│                        (읽기/캐시 위주)      (쓰기 집중)                     │
│                                                                             │
│  장기 목표:                                                                  │
│  - API → 캐시/읽기 위주 (pool_size=5)                                       │
│  - Worker → 쓰기 집중 (pool_size=15, max_overflow=20)                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Worker 역할 분류

| Worker | 역할 | I/O 특성 | DB 접근 |
|--------|------|----------|---------|
| **scan-worker** | OpenAI API 호출 | 외부 API (10~40초) | ❌ |
| **character-match-worker** | 캐시 기반 캐릭터 매칭 | 메모리 (<1ms) | ❌ |
| **character-worker** | character DB 저장 | DB I/O | ✅ Bulk INSERT |
| **my-worker** | my DB 저장 | DB I/O | ✅ Bulk INSERT |

---

## 3. Worker Pool 통합 스펙

### 3.1 최종 Worker 설정

| Worker | Pool | Concurrency | 선정 이유 |
|--------|------|-------------|-----------|
| **scan-worker** (×3) | `gevent` | 100 | 외부 API I/O 대기 시간 긴 작업 |
| **character-match-worker** (×2) | `threads` | 16 | 캐시 공유 필요 (MainProcess) |
| **character-worker** (×1) | `gevent` | 20 | DB I/O 바운드, 배치 처리 |
| **my-worker** (×1) | `gevent` | 20 | DB I/O 바운드, 배치 처리 |

### 3.2 Pool 타입별 특성

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Pool 타입 비교                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  prefork (멀티프로세스)                                                      │
│  ├── 장점: CPU-bound 작업에 적합, GIL 회피                                   │
│  ├── 단점: 메모리 많이 사용, 프로세스간 메모리 공유 불가                      │
│  └── 사용: (현재 사용 안함)                                                  │
│                                                                             │
│  threads (멀티스레드)                                                        │
│  ├── 장점: MainProcess 메모리 공유 (캐시)                                    │
│  ├── 단점: GIL로 인한 CPU 병목                                               │
│  └── 사용: character-match-worker (캐시 조회)                                │
│                                                                             │
│  gevent (Greenlet)                                                          │
│  ├── 장점: 높은 I/O 동시성, 메모리 효율적                                    │
│  ├── 단점: CPU-bound 작업 불가, monkey patching 필요                        │
│  └── 사용: scan-worker, character-worker, my-worker                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.3 Concurrency 결정 요인

| Worker | Concurrency | 결정 요인 |
|--------|-------------|-----------|
| scan-worker | 100 | OpenAI 500 RPM ÷ 2 calls/chain = 250 chains/min → 충분한 버퍼 |
| character-match-worker | 16 | 캐시 조회 <1ms, 과도한 스레드 불필요 |
| character-worker | 20 | DB pool(35) > concurrency(20) 보장 |
| my-worker | 20 | DB pool(35) > concurrency(20) 보장 |

---

## 4. DB Connection Pool 환경변수 통합

### 4.1 공통 설정 모듈

```python
# domains/_shared/database/config.py

class DatabasePoolSettings(BaseSettings):
    """Database connection pool settings."""
    
    pool_size: int = Field(default=5, ge=1, le=100)
    max_overflow: int = Field(default=10, ge=0, le=100)
    pool_timeout: int = Field(default=30, ge=1, le=300)
    pool_recycle: int = Field(default=1800)  # 30분
    pool_pre_ping: bool = Field(default=True)
    
    model_config = SettingsConfigDict(
        env_prefix="DB_",
        case_sensitive=False,
    )

# Worker 전용 프리셋
class WorkerDatabasePoolSettings(DatabasePoolSettings):
    """Worker 전용 DB 풀 설정 (높은 동시성)."""
    
    pool_size: int = Field(default=15)
    max_overflow: int = Field(default=20)
```

### 4.2 환경변수 매핑

| 환경변수 | 기본값 (API) | 기본값 (Worker) | 설명 |
|----------|--------------|-----------------|------|
| `DB_POOL_SIZE` | 5 | **15** | 상시 유지 커넥션 |
| `DB_MAX_OVERFLOW` | 10 | **20** | 초과 허용 커넥션 |
| `DB_POOL_TIMEOUT` | 30 | 30 | 커넥션 획득 대기 (초) |
| `DB_POOL_RECYCLE` | 1800 | 1800 | 커넥션 재생성 주기 (초) |
| `DB_POOL_PRE_PING` | true | true | 커넥션 유효성 사전 검사 |

### 4.3 Deployment 적용

```yaml
# workloads/domains/character-worker/base/deployment.yaml
env:
  # Database Pool (Worker 전용 - concurrency에 맞춤)
  - name: DB_POOL_SIZE
    value: '15'   # 상시 유지 커넥션
  - name: DB_MAX_OVERFLOW
    value: '20'   # 초과 허용 (합계 35 > concurrency 20)
  - name: DB_POOL_TIMEOUT
    value: '30'
  - name: DB_POOL_RECYCLE
    value: '1800'
```

---

## 5. Concurrency vs DB Pool 정합성

### 5.1 공식

```
DB 최대 커넥션 = pool_size + max_overflow
Concurrency ≤ DB 최대 커넥션  (필수 조건)
```

### 5.2 현재 설정 검증

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  character-worker / my-worker                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Pool: gevent                                                               │
│  Concurrency: 20 greenlets                                                  │
│  DB pool_size: 15                                                           │
│  DB max_overflow: 20                                                        │
│  ─────────────────────────                                                  │
│  DB 최대 커넥션: 15 + 20 = 35                                               │
│  35 > 20 ✅ (concurrency 충족)                                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.3 PostgreSQL 전체 커넥션 검증

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  PostgreSQL max_connections: 200 (dev) / 300 (prod)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  API 서비스 (7개 × 15 = 105)                                                │
│  ├── auth-api:       15                                                     │
│  ├── character-api:  15                                                     │
│  ├── chat-api:       15                                                     │
│  ├── image-api:      15                                                     │
│  ├── location-api:   15                                                     │
│  ├── my-api:         15                                                     │
│  └── scan-api:       15                                                     │
│                                                                             │
│  Worker 서비스 (2개 × 35 = 70)                                              │
│  ├── character-worker: 35                                                   │
│  └── my-worker:        35                                                   │
│                                                                             │
│  기타 (PostgreSQL 내부, 백업 등): 20                                         │
│  ─────────────────────────                                                  │
│  총계: 105 + 70 + 20 = 195 / 200 ✅                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. DLQ 라우팅 수정

### 6.1 문제

```python
# 기존 (문제)
"task_routes": {
    "dlq.*": {"queue": "celery"},  # celery 큐 consumer 없음 → 메시지 적체
}
```

### 6.2 해결

```python
# 변경 (해결)
"task_routes": {
    # DLQ 재처리 → 각 도메인 worker가 처리
    "dlq.reprocess_scan_vision": {"queue": "scan.vision"},
    "dlq.reprocess_scan_rule": {"queue": "scan.rule"},
    "dlq.reprocess_scan_answer": {"queue": "scan.answer"},
    "dlq.reprocess_scan_reward": {"queue": "scan.reward"},
    "dlq.reprocess_character_reward": {"queue": "character.reward"},
    "dlq.reprocess_my_reward": {"queue": "my.reward"},
}
```

### 6.3 흐름도

```
┌───────────────────────────────────────────────────────────────────────────┐
│                          Celery Beat (스케줄러)                            │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  매 5분마다 DLQ 재처리 task 발행:                                          │
│                                                                           │
│    dlq.reprocess_scan_vision ──────→ scan.vision ──→ scan-worker ✅       │
│    dlq.reprocess_scan_rule ────────→ scan.rule ───→ scan-worker ✅        │
│    dlq.reprocess_scan_answer ──────→ scan.answer ─→ scan-worker ✅        │
│    dlq.reprocess_scan_reward ──────→ scan.reward ─→ scan-worker ✅        │
│    dlq.reprocess_character_reward ─→ character.reward → character-worker ✅│
│    dlq.reprocess_my_reward ────────→ my.reward ───→ my-worker ✅          │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 7. 리소스 최적화

### 7.1 메모리 절감

| Worker | 이전 | 변경 후 | 절감 |
|--------|------|---------|------|
| character-worker | 2Gi limit | 512Mi limit | **75%** |
| my-worker | 1Gi limit | 512Mi limit | **50%** |

### 7.2 동시성 향상

| Worker | 이전 | 변경 후 | 향상 |
|--------|------|---------|------|
| character-worker | prefork ×2 | gevent ×20 | **10×** |
| my-worker | prefork ×2 | gevent ×20 | **10×** |

---

## 8. 변경 파일 목록

### 8.1 신규 생성

| 파일 | 설명 |
|------|------|
| `domains/_shared/database/__init__.py` | 모듈 초기화 |
| `domains/_shared/database/config.py` | DB 풀 환경변수 설정 |

### 8.2 수정

| 파일 | 변경 내용 |
|------|-----------|
| `domains/_shared/celery/config.py` | DLQ 라우팅 수정 |
| `domains/character/tasks/reward.py` | Worker DB 풀 설정 적용 |
| `domains/my/tasks/sync_character.py` | Worker DB 풀 설정 적용 |
| `workloads/domains/character-worker/base/deployment.yaml` | gevent pool, 환경변수 |
| `workloads/domains/my-worker/base/deployment.yaml` | gevent pool, 환경변수 |

---

## 9. 전체 Worker 현황 요약

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ECO2 Worker 스펙 현황 (2025-12-24)                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Worker                    Pool     Concurrency   DB Pool   Memory          │
│  ─────────────────────────────────────────────────────────────────────      │
│  scan-worker (×3)          gevent   100           N/A       512Mi           │
│  character-match-worker (×2) threads  16          N/A       512Mi           │
│  character-worker (×1)     gevent   20            35        512Mi           │
│  my-worker (×1)            gevent   20            35        512Mi           │
│                                                                             │
│  총 Pods: 7                                                                 │
│  총 동시 처리 용량:                                                          │
│  - OpenAI 파이프라인: 300 동시 (scan-worker)                                │
│  - 캐릭터 매칭: 32 동시 (character-match-worker)                            │
│  - DB 배치 저장: 40 동시 (character + my worker)                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. 다음 단계

1. **클러스터 배포 및 검증** - ArgoCD sync 후 Worker 상태 확인
2. **Locust 성능 테스트** - RPS 측정 및 병목 분석
3. **OpenAI Rate Limit 최적화** - 토큰 버킷 레이트 리밋 도입 검토
4. **API DB 접근 최소화** - Worker 중심 아키텍처로 점진적 전환

---

## 참고 자료

- [이전 블로그: Celery Gevent Pool 전환](./16-celery-gevent-pool-migration.md)
- [SQLAlchemy Connection Pool](https://docs.sqlalchemy.org/en/20/core/pooling.html)
- [PostgreSQL max_connections](https://www.postgresql.org/docs/current/runtime-config-connection.html)
- [Celery Concurrency](https://docs.celeryq.dev/en/stable/userguide/workers.html#concurrency)

---

## 변경 이력

| 날짜 | 내용 |
|------|------|
| 2025-12-24 | 최초 작성 - Worker Pool 통합 및 DB Pool 최적화 |












