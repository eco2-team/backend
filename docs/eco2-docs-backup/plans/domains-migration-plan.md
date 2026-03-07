# domains 의존성 제거 마이그레이션 계획

> 목표: `apps/` 서비스들이 `domains/_shared`에 의존하지 않고 완전히 독립적으로 동작

---

## 1. 현재 domains 의존성 현황

### 1.1 서비스별 의존성

| 서비스 | 상태 | 의존 모듈 | 용도 |
|--------|------|----------|------|
| **scan_worker** | ✅ 완료 | 없음 | 완전 독립 |
| **scan** | ⚠️ 필요 | `domains._shared.events` | Redis Streams 이벤트 발행 |
| | | `domains._shared.waste_pipeline.rag` | 배출 규정 검색 |
| **character** | ⚠️ 필요 | `domains._shared.database.base` | SQLAlchemy Base |
| | | `domains._shared.observability.tracing` | OpenTelemetry |
| **character_worker** | ⚠️ 필요 | `domains._shared.observability.tracing` | OpenTelemetry |
| **location** | ⚠️ 필요 | `domains._shared.observability.tracing` | OpenTelemetry |
| **auth** | ✅ 완료 | 없음 | 완전 독립 |
| **auth_worker** | ✅ 완료 | 없음 | 완전 독립 |
| **users** | ✅ 완료 | 없음 | 완전 독립 |

### 1.2 domains/_shared 모듈 분석

```
domains/_shared/
├── cache/           # 캐릭터 캐시 (character만 사용)
├── celery/          # Celery 설정 (더 이상 사용 안 함)
├── database/        # SQLAlchemy Base (character만 사용)
├── events/          # Redis Streams 클라이언트 (scan만 사용)
├── observability/   # OpenTelemetry 설정 (여러 서비스 사용)
├── schemas/         # Waste 스키마 (scan만 사용)
└── waste_pipeline/  # RAG + 프롬프트 (scan만 사용)
```

---

## 2. 마이그레이션 전략

### 원칙
1. **코드 중복 허용**: API와 Worker 간 도메인 모델 공유 ❌
2. **완전 독립**: 각 서비스는 자체 코드만 사용
3. **점진적 이행**: 기존 기능 유지하면서 단계별 이행

---

## 3. 서비스별 마이그레이션 계획

### 3.1 scan_worker (✅ 완료)

```dockerfile
# 변경 전
COPY domains/_shared /app/domains/_shared
COPY apps/scan/domain /app/apps/scan/domain
COPY apps/scan_worker /app/apps/scan_worker
CMD ["celery", "-A", "apps.scan_worker.setup.celery:celery_app", ...]

# 변경 후
COPY apps/scan_worker /app/scan_worker
CMD ["celery", "-A", "scan_worker.setup.celery:celery_app", ...]
```

- **상태**: 완료
- **변경사항**: Dockerfile에서 불필요한 복사 제거, import 경로 변경

---

### 3.2 scan (예정)

**현재 의존성**:
```python
# event_publisher_redis.py
from domains._shared.events import publish_stage_event, get_sync_redis_client

# yaml_rule_repository.py
from domains._shared.waste_pipeline.rag import get_disposal_rules
```

**마이그레이션 계획**:

#### A. Redis 이벤트 발행 (내부화)
```
apps/scan/infrastructure/messaging/
├── redis_client.py          # 복제: domains._shared/events/redis_client.py
└── redis_streams.py         # 복제: domains._shared/events/redis_streams.py
```

#### B. 배출 규정 검색 (내부화)
```
apps/scan/infrastructure/data/
├── source/                   # 복제: domains/_shared/waste_pipeline/data/source/
│   ├── 재활용폐기물_*.json
│   └── ...
└── rag_service.py           # 복제: domains/_shared/waste_pipeline/rag.py
```

**예상 변경**:
```python
# event_publisher_redis.py (변경 후)
from scan.infrastructure.messaging.redis_streams import publish_stage_event

# yaml_rule_repository.py (변경 후)
from scan.infrastructure.data.rag_service import get_disposal_rules
```

---

### 3.3 character + character_worker (예정)

**현재 의존성**:
```python
# SQLAlchemy Base
from domains._shared.database.base import Base

# OpenTelemetry
from domains._shared.observability.tracing import setup_tracing
```

**마이그레이션 계획**:

#### A. SQLAlchemy Base (내부화)
```python
# apps/character/infrastructure/persistence_postgres/base.py
from sqlalchemy.orm import declarative_base
Base = declarative_base()
```

#### B. OpenTelemetry (공통 패키지화 또는 내부화)
```
apps/character/infrastructure/observability/
└── tracing.py   # setup_tracing() 복제
```

---

### 3.4 location (예정)

**현재 의존성**:
```python
from domains._shared.observability.tracing import setup_tracing
```

**마이그레이션 계획**:
```
apps/location/infrastructure/observability/
└── tracing.py   # setup_tracing() 복제
```

---

## 4. 공통 모듈 처리 방안

### 4.1 OpenTelemetry (setup_tracing)

**선택지**:
1. ❌ 공용 라이브러리로 분리 → 복잡성 증가
2. ✅ **각 서비스에 복제** → 독립성 보장 (선택)

**이유**: 
- 코드량 적음 (~50줄)
- 서비스별 리소스 이름/속성 다름
- 독립 배포 원칙 준수

### 4.2 waste_pipeline 데이터 (JSON, 프롬프트)

**위치 이동**:
```
domains/_shared/waste_pipeline/data/
    ↓ 복사
apps/scan/infrastructure/data/
apps/scan_worker/infrastructure/asset_loader/data/  # ← 이미 복사됨
```

---

## 5. 마이그레이션 순서

| 순서 | 서비스 | 작업 내용 | 예상 시간 |
|------|--------|----------|----------|
| 1 | ✅ scan_worker | Dockerfile + import 경로 정리 | 완료 |
| 2 | scan | Redis 이벤트 + RAG 내부화 | 2시간 |
| 3 | character | SQLAlchemy Base + Tracing 내부화 | 1시간 |
| 4 | character_worker | Tracing 내부화 | 30분 |
| 5 | location | Tracing 내부화 | 30분 |
| 6 | 정리 | domains/_shared 삭제 | 10분 |

---

## 6. 검증 체크리스트

### 각 서비스 마이그레이션 후:
- [ ] `grep "domains\._shared" apps/{service}` → 0건
- [ ] `docker build -f apps/{service}/Dockerfile .` 성공
- [ ] 로컬 테스트 통과
- [ ] K8s 배포 후 기능 테스트

### 전체 완료 후:
- [ ] `domains/_shared/` 디렉토리 삭제
- [ ] CI에서 domains 의존성 검사 추가

---

## 7. 롤백 전략

- Git 브랜치 전략 사용
- 서비스별 순차 배포
- 문제 발생 시 이전 이미지로 롤백 (ArgoCD)

---

**작성일**: 2026-01-07
**상태**: scan_worker 완료, 나머지 예정




