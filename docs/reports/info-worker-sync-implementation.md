# Info Worker 구현 리포트

> **작성일**: 2026-01-17
> **브랜치**: `feat/info-worker-topology` (PR #386), `fix/info-worker-beat` (PR #391-#394)
> **상태**: Production Ready ✅

---

## 요약

| 항목 | 내용 |
|------|------|
| **목적** | 환경/에너지 뉴스 자동 수집 및 캐시 기반 API 제공 |
| **아키텍처** | CQRS (info_worker: Write, info API: Read) + Cache Aside |
| **핵심 패턴** | Beat Sidecar, Topology CR, Postgres Fallback |
| **Pod 구성** | 3 컨테이너 (worker + beat + istio-proxy) |
| **현재 상태** | 129건 캐시, 5분 주기 수집 정상 동작 |

---

## 1. 구현 목표

뉴스 수집 워커를 Clean Architecture 기반으로 구현하고, Celery Beat를 통한 주기적 데이터 파이프라인 구축.

### 핵심 요구사항

- 환경/에너지 뉴스 자동 수집 (Naver API + NewsData.io)
- Read/Write 분리 (CQRS): info API(Read), info_worker(Write)
- Redis 캐시 워밍으로 API 응답 최적화
- RabbitMQ Topology CR 패턴 적용
- **Cache Aside 패턴으로 가용성 확보** (Postgres Fallback)

---

## 2. 기술 선택

### 2.1 동기 드라이버 선택 (info_worker)

| 컴포넌트 | 선택 | 근거 |
|----------|------|------|
| **PostgreSQL** | psycopg2 + ThreadedConnectionPool | gevent 몽키패칭 환경에서 안정적 동작 |
| **Redis** | redis-py (sync) | 단순한 캐시 연산에 async 불필요 |
| **HTTP Client** | httpx.Client | OG 이미지 추출 시 connection pooling |

**설계 결정**: Celery + gevent pool 환경에서 모든 I/O를 sync로 통일하여 greenlet 전환이 자연스럽게 처리되도록 함.

### 2.2 비동기 드라이버 선택 (info API)

| 컴포넌트 | 선택 | 근거 |
|----------|------|------|
| **PostgreSQL** | asyncpg | FastAPI async 환경과 일치 |
| **Redis** | redis.asyncio | 비동기 캐시 조회 |

### 2.3 RabbitMQ Topology CR 패턴

```yaml
# Kubernetes CR로 큐 생성 (워커는 consume만)
apiVersion: rabbitmq.com/v1beta1
kind: Queue
metadata:
  name: info-collect-news-queue
spec:
  name: info.collect_news
  type: classic
  durable: true
  arguments:
    x-dead-letter-exchange: dlx
    x-dead-letter-routing-key: dlq.info.collect_news
    x-message-ttl: 600000  # 10분
```

**Python 코드**:
```python
INFO_TASK_QUEUES = [
    Queue("info.collect_news", exchange="", routing_key="info.collect_news", no_declare=True),
]

celery_app.conf.update(
    task_create_missing_queues=False,  # Topology CR에 위임
)
```

**결정 근거**: 큐 설정(TTL, DLX)을 코드에서 분리하여 인프라 레벨에서 관리. 워커 재배포 없이 큐 정책 변경 가능.

---

## 3. 아키텍처

### 3.1 데이터 플로우 (CQRS + Cache Aside)

```
┌─────────────────────────────────────────────────────────────────┐
│                     WRITE PATH (info_worker Pod)                 │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐                                            │
│  │ Beat Sidecar    │──► RabbitMQ ───► Worker Container          │
│  │ (5분/30분 주기) │    (info.collect_news)    │                │
│  └─────────────────┘                           │                │
│                                                ▼                │
│                               ┌──────────────────────┐          │
│                               │ CollectNewsCommand   │          │
│                               │ 1. Naver API 호출    │          │
│                               │ 2. NewsData.io 호출  │          │
│                               │ 3. OG 이미지 추출    │          │
│                               │ 4. PostgreSQL UPSERT │          │
│                               │ 5. Redis 캐시 워밍   │          │
│                               └──────────────────────┘          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                READ PATH (info API - Cache Aside)                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Client ──► info-api ──► Redis Cache                            │
│                              │                                   │
│                   ┌──────────┴──────────┐                       │
│                   │                     │                       │
│                   ▼                     ▼                       │
│               HIT ───► 응답         MISS ───► PostgreSQL        │
│           (source: redis)                        │              │
│                                                  ▼              │
│                                          응답 반환              │
│                                     (source: postgres)          │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Cache Aside 패턴 (Fallback 구현)

**문제 상황**:
- Worker의 캐시 워밍이 실패하거나 지연될 경우 API가 빈 응답 반환
- Redis 장애 시 서비스 전체 불가용
- 캐시 TTL 만료 시점에 일시적 서비스 품질 저하

**해결책**: PostgreSQL을 Fallback으로 추가하여 가용성 확보

```python
# fetch_news_command.py
async def execute(self, request: NewsListRequest) -> NewsListResponse:
    # 1. Redis 캐시 조회 (Primary) - 빠른 응답
    articles, next_cursor, has_more = await self._news_cache.get_articles(...)

    # 2. 캐시 미스 → Postgres Fallback - 데이터 보장
    if not articles and self._news_repository:
        logger.info("Cache miss, falling back to Postgres")
        result = await self._news_repository.get_articles(...)
        articles = result.articles
        # 응답에 source 표시로 모니터링 가능
        source = "postgres"

    return NewsListResponse(articles=articles, meta={"source": source}, ...)
```

**Fallback 도입 효과**:

| 시나리오 | Before | After |
|----------|--------|-------|
| 캐시 미스 | 빈 배열 `[]` | DB 조회 후 데이터 반환 |
| Redis 장애 | 500 에러 | DB Fallback으로 정상 응답 |
| Worker 지연 | 빈 응답 | 기존 DB 데이터 활용 |
| 캐시 TTL 만료 | 일시적 빈 응답 | 무중단 서비스 |

**ExternalSecret 설정**:
```yaml
# info-api-secrets.yaml (dev/prod 공통)
- secretKey: dbPassword
  remoteRef:
    key: /sesacthon/dev/data/postgres-password
# Template에서 DATABASE_URL 구성
INFO_DATABASE_URL: postgresql+asyncpg://sesacthon:{{ .dbPassword | urlquery }}@dev-postgresql.postgres.svc.cluster.local:5432/ecoeco
```

**모니터링**: API 응답의 `meta.source` 필드로 캐시 히트율 추적 가능

### 3.3 레이어 구조

```
apps/info_worker/                    apps/info/
├── domain/                          ├── domain/
│   └── entities/                    │   └── entities/
├── application/                     ├── application/
│   ├── commands/                    │   ├── commands/
│   │   └── CollectNewsCommand       │   │   └── FetchNewsCommand (Cache Aside)
│   └── ports/                       │   └── ports/
├── infrastructure/                  ├── infrastructure/
│   ├── integrations/                │   ├── cache/
│   ├── persistence/ (psycopg2)      │   └── persistence/ (asyncpg)
│   └── cache/ (sync)                │
├── presentation/                    ├── presentation/
│   └── tasks/                       │   └── http/
└── setup/                           └── setup/
```

---

## 4. 운영 데이터

### 4.1 Celery Worker 상태

```
celery@info-worker-6f4f786c7b-vrs4m v5.6.2 (recovery)

[config]
  .> app:         info_worker:0x78b87ee64b60
  .> transport:   amqp://admin:**@eco2-rabbitmq.rabbitmq.svc.cluster.local:5672/eco2
  .> results:     disabled://
  .> concurrency: 100 (gevent)
  .> task events: ON

[queues]
  .> info.collect_news exchange=(direct) key=info.collect_news

[tasks]
  . info.collect_news
  . info.collect_news_newsdata
```

### 4.2 Task 실행 로그 (2026-01-16 22:31)

**타이밍 분석**:

| 단계 | 시작 | 종료 | 소요 |
|------|------|------|------|
| Task 수신 | 22:31:00.617 | - | - |
| 리소스 초기화 | 22:31:01.113 | 22:31:01.205 | 0.09s |
| Naver API (3회) | 22:31:01.399 | 22:31:02.502 | 1.10s |
| NewsData API (3회) | 22:31:02.103 | 22:31:02.797 | 0.69s |
| OG 이미지 추출 (95건) | 22:31:02.801 | 22:31:17.333 | 14.53s |
| PostgreSQL UPSERT | 22:31:17.333 | 22:31:17.530 | 0.20s |
| Redis 캐시 워밍 | 22:31:17.530 | 22:31:17.570 | 0.04s |
| **총 소요** | - | - | **16.95s** |

**결과 메트릭**:
```json
{
  "status": "success",
  "fetched": 110,
  "unique": 110,
  "saved": 110,
  "cached": 110,
  "with_images": 95,
  "category": "all"
}
```

### 4.3 OG 이미지 추출 (Naver API 한계 극복)

**문제**: Naver News API는 검색 결과에 썸네일 이미지를 제공하지 않음. 뉴스 목록 UI에서 이미지 없이 텍스트만 노출되면 사용자 경험이 크게 저하됨.

**해결책**: 각 기사의 원문 페이지에서 Open Graph `og:image` 메타 태그를 추출

```
┌────────────────────────────────────────────────────────────────┐
│  Naver API 응답 (이미지 없음)                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ { "title": "...", "link": "https://news.com/123", ... }  │  │
│  │   (thumbnail 필드 없음)                                   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ OG Image Enrichment (gevent 병렬 처리)                    │  │
│  │ 1. 원문 페이지 HTTP GET                                   │  │
│  │ 2. HTML 파싱 → <meta property="og:image"> 추출           │  │
│  │ 3. 이미지 URL 검증 및 저장                                │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 최종 결과: 86.4% 이미지 보강 성공 (95/110건)              │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

**구현 특징**:
- **병렬 처리**: gevent Pool (concurrency: 100)으로 동시 요청
- **Connection Pooling**: httpx.Client로 TCP 연결 재사용
- **Graceful Degradation**: OG 추출 실패 시 이미지 없이 저장 (서비스 중단 없음)

**성능 측정**:

| 지표 | 값 |
|------|-----|
| 총 기사 | 110건 |
| 이미지 추출 성공 | 95건 (86.4%) |
| 평균 추출 시간 | ~153ms/건 |
| 총 소요 시간 | 14.53초 |

**주요 소스별 응답 시간**:
```
news1.kr       : 97-106ms   (국내, 빠름)
koreaherald    : 100-200ms  (국내 영문)
nytimes.com    : 200-500ms  (해외, 지연)
breaknews.com  : 300-600ms  (변동 큼)
```

**실패 케이스 (13.6%)**:
- OG 메타 태그 미설정 페이지
- 로그인/구독 필요 페이지
- 타임아웃 (3초 초과)

### 4.4 데이터 소스 현황

| 소스 | 이미지 제공 | 카테고리 | 주기 | 건수/회 |
|------|------------|----------|------|---------|
| Naver News API | ❌ (OG 추출로 보완) | environment, energy, ai | 5분 | 30건/카테고리 |
| NewsData.io | ✅ (API 제공) | environment, energy, ai | 30분 | 10건/카테고리 |

**Rate Limit 대응**: NewsData.io는 무료 플랜 제약(200건/일)으로 30분 주기 설정.

---

## 5. 캐시 전략

### 5.1 Write Path: 캐시 워밍 (Write-through)

수집 완료 시 즉시 Redis에 캐시 워밍:

```python
# 카테고리별 캐시 키
news:list:all         # 전체 기사
news:list:environment # 환경 카테고리
news:list:energy      # 에너지 카테고리
news:list:ai          # AI 카테고리
```

**TTL 설정**:
- 목록 캐시: 3600초 (1시간)
- 개별 기사: 86400초 (24시간)

### 5.2 Read Path: Cache Aside

| 시나리오 | 동작 | 응답 source |
|----------|------|-------------|
| 캐시 히트 | Redis에서 반환 | `redis` |
| 캐시 미스 + DB 있음 | Postgres 조회 후 반환 | `postgres` |
| 캐시 미스 + DB 없음 | 빈 배열 반환 | - |

**응답 예시**:
```json
{
  "articles": [...],
  "meta": {
    "total_cached": 110,
    "cache_expires_in": 2889,
    "source": "redis"  // or "postgres"
  }
}
```

---

## 6. 배포 구성

### 6.1 Kubernetes Deployment (Beat Sidecar 패턴)

gevent pool 환경에서는 `-B` 플래그 사용 불가. 별도 Beat 사이드카 컨테이너로 구성.

```yaml
containers:
  # Worker 컨테이너 (gevent pool)
  - name: worker
    image: docker.io/mng990/eco2:info-worker-dev-latest
    args:
    - |
      celery -A info_worker.setup.celery:celery_app worker \
        --loglevel=info \
        -E \
        -P gevent \
        -Q info.collect_news \
        -c 100 \
        --prefetch-multiplier=1
    resources:
      requests: { cpu: 100m, memory: 256Mi }
      limits: { cpu: 500m, memory: 512Mi }

  # Beat 스케줄러 사이드카 (standalone)
  - name: beat
    image: docker.io/mng990/eco2:info-worker-dev-latest
    command: [celery, -A, info_worker.setup.celery:celery_app, beat, --loglevel=info, -s, /tmp/celerybeat-schedule]
    resources:
      requests: { cpu: 50m, memory: 64Mi }
      limits: { cpu: 100m, memory: 128Mi }
    volumeMounts:
    - name: beat-schedule
      mountPath: /tmp
    livenessProbe:
      exec:
        command: [/bin/sh, -c, "cat /proc/1/cmdline 2>/dev/null | tr '\\0' ' ' | grep -q celery"]
      initialDelaySeconds: 10
      periodSeconds: 30

volumes:
- name: beat-schedule
  emptyDir: {}
```

**설계 결정**:
- `-B` 플래그는 `eventlet/gevent pool과 호환 불가` (Celery 제약)
- Beat를 사이드카로 분리하여 독립적 스케줄링
- `emptyDir` 볼륨으로 schedule 파일 쓰기 권한 확보
- `/proc/1/cmdline` 기반 liveness probe (Python slim 이미지 호환)

### 6.2 Celery Beat Schedule

```python
beat_schedule = {
    "collect-news-naver": {
        "task": "info.collect_news",
        "schedule": 300.0,  # 5분
        "kwargs": {"category": "all", "source": "naver"},
    },
    "collect-news-newsdata": {
        "task": "info.collect_news_newsdata",
        "schedule": 1800.0,  # 30분
        "kwargs": {"category": "all"},
    },
}
```

### 6.3 RabbitMQ Queue 상태

```
Queue: info.collect_news
  - Messages: 0
  - Consumers: 1
  - TTL: 10분
  - DLX: dlx → dlq.info.collect_news
```

---

## 7. API 엔드포인트

### 7.1 External (Istio Gateway)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `api.dev.growbin.app/api/v1/info/news` | 뉴스 목록 |
| GET | `api.dev.growbin.app/api/v1/info/news?category=energy` | 카테고리 필터 |
| GET | `api.dev.growbin.app/api/v1/info/news/categories` | 카테고리 목록 |
| GET | `api.dev.growbin.app/api/v1/info/health` | 헬스체크 |

### 7.2 응답 예시

```json
// GET /api/v1/info/news?limit=3 (캐시 히트)
{
  "articles": [...],
  "next_cursor": "1737072000000_abc123",
  "has_more": true,
  "meta": {
    "total_cached": 110,
    "cache_expires_in": 2889,
    "source": "redis"
  }
}

// GET /api/v1/info/news?category=energy (캐시 미스 → Fallback)
{
  "articles": [...],
  "next_cursor": "1737072000000_def456",
  "has_more": true,
  "meta": {
    "total_cached": 29,
    "cache_expires_in": 0,
    "source": "postgres"
  }
}
```

---

## 8. 설정 레퍼런스

### 8.1 info_worker 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `INFO_WORKER_NAVER_CLIENT_ID` | - | 네이버 API ID |
| `INFO_WORKER_NAVER_CLIENT_SECRET` | - | 네이버 API Secret |
| `INFO_WORKER_NEWSDATA_API_KEY` | - | NewsData.io API Key |
| `INFO_WORKER_DATABASE_URL` | - | PostgreSQL (psycopg2) |
| `INFO_WORKER_REDIS_URL` | - | Redis 캐시 |
| `INFO_WORKER_CELERY_BROKER_URL` | - | RabbitMQ |
| `INFO_WORKER_COLLECT_INTERVAL_NAVER` | 300 | Naver 수집 주기 (초) |
| `INFO_WORKER_COLLECT_INTERVAL_NEWSDATA` | 1800 | NewsData 수집 주기 (초) |
| `INFO_WORKER_NEWS_CACHE_TTL` | 3600 | 목록 캐시 TTL (초) |

### 8.2 info API 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `INFO_REDIS_URL` | - | Redis 캐시 (Primary) |
| `INFO_DATABASE_URL` | - | PostgreSQL (Cache Aside Fallback) |
| `INFO_NEWS_CACHE_TTL` | 3600 | 캐시 TTL (초) |

---

## 9. 트러블슈팅 기록

### 9.1 Beat + gevent 호환성 문제 (PR #391)

**에러**:
```
celery.exceptions.ImproperlyConfigured: -B option doesn't work with eventlet/gevent pools: use standalone beat instead.
```

**원인**: Celery의 `-B` (embedded beat) 플래그는 eventlet/gevent pool과 호환 불가

**해결**: Beat를 별도 사이드카 컨테이너로 분리

### 9.2 pgrep 미설치 (PR #392)

**에러**:
```
exec: "pgrep": executable file not found in $PATH
```

**원인**: Python slim 이미지에 `procps` 패키지 미포함

**해결**: `pgrep -f` → `ps aux | grep` 로 변경

### 9.3 ps 명령어 미설치 (PR #394)

**에러**:
```
/bin/sh: 1: ps: not found
```

**원인**: Python slim 이미지에 `ps` 명령어도 없음

**해결**: `/proc/1/cmdline` 파일시스템 직접 조회
```bash
cat /proc/1/cmdline 2>/dev/null | tr '\0' ' ' | grep -q celery
```

### 9.4 Schedule 파일 쓰기 권한 (PR #393)

**에러**:
```
[Errno 13] Permission denied: 'celerybeat-schedule'
```

**원인**: 컨테이너 기본 작업 디렉토리에 쓰기 권한 없음

**해결**:
- `emptyDir` 볼륨을 `/tmp`에 마운트
- Beat 실행 시 `-s /tmp/celerybeat-schedule` 옵션 추가

---

## 변경 이력

| 날짜 | PR | 내용 |
|------|-----|------|
| 2026-01-17 | #386 | 최초 구현 - sync 드라이버 + Topology CR |
| 2026-01-17 | #386 | 운영 데이터 추가 (Task 16.95s, 110건, 이미지 86.4%) |
| 2026-01-17 | #390 | Cache Aside 패턴 추가 (info-api에 DATABASE_URL 설정) |
| 2026-01-17 | #391 | Beat 사이드카 분리 (gevent 호환성) |
| 2026-01-17 | #392 | Liveness probe: pgrep → ps+grep |
| 2026-01-17 | #393 | emptyDir 볼륨으로 schedule 파일 쓰기 권한 확보 |
| 2026-01-17 | #394 | Liveness probe: /proc/1/cmdline 기반으로 변경 |
