# DB 설계 사례 분석 및 Growbin 적용 방안

분석 일시: 2025-11-06
대상 시스템: Growbin (폐기물 분석 서비스)
참고 사례: Robin Storage, OStore

---

## 📊 1. Robin Storage & OStore DB 구조 분석

### Robin Storage 구조 요약

```
┌─────────────────────────────────────────────┐
│ Control Plane (전역)                        │
├─────────────────────────────────────────────┤
│ Storage Manager → PostgreSQL (robin_storage)│
│  - task, zone, node, dev                    │
│  - volume, slice, snapshot, backup          │
│  - 클러스터 전역 메타데이터                 │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ Data Plane (노드별)                         │
├─────────────────────────────────────────────┤
│ RDVM → SQLite (rdvm.cfg, WAL)               │
│  - 노드 설정, 로컬 초기화                   │
│                                             │
│ RIO → SQLite (rio.cfg, Read-only)           │
│  - 노드 설정 읽기 전용                      │
│                                             │
│ Agent → SQLite (taskmgr.cfg)                │
│  - Task Queue 영속화                        │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ Object Storage (버킷별)                     │
├─────────────────────────────────────────────┤
│ DStore → SQLite (meta.db per bucket, WAL)   │
│  - 버킷별 청크 인덱스                       │
│  - 로컬 빠른 조회                           │
└─────────────────────────────────────────────┘
```

**핵심 설계 원칙**:
- ✅ **전역 조율**: PostgreSQL (Storage Manager)
- ✅ **로컬 최적화**: SQLite (노드별, 버킷별)
- ✅ **장애 격리**: 로컬 DB 독립 운영

---

### OStore 구조 요약 (3-Tier)

```
┌─────────────────────────────────────────────┐
│ Tier 1: CM (Control Manager)                │
├─────────────────────────────────────────────┤
│ PostgreSQL: robin_storage                   │
│  - mstore_config (MStore 등록)              │
│  - dstore_config (DStore 등록)              │
│  - bucket (버킷 메타, id→db→table 매핑)    │
│  - users, auth, policy (IAM)                │
│  - diskset (스토리지 풀)                    │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ Tier 2: MStore (메타데이터 계층)            │
├─────────────────────────────────────────────┤
│ MStore 설정 DB: mstore_0, mstore_1          │
│  - mstore_config                            │
│  - db_info (버킷 DB 목록)                   │
│                                             │
│ 버킷별 DB: db_<epoch><random> ⭐⭐⭐        │
│  ┌─────────────────────────────────┐        │
│  │ 버킷 1 → db_xxx1                │        │
│  │  - bkt_1 (오브젝트 메타)        │        │
│  │  - bkt_1_uploads (멀티파트)     │        │
│  │  - bkt_1_upload_parts           │        │
│  │  - bkt_1_lifecycle_rules        │        │
│  └─────────────────────────────────┘        │
│  ┌─────────────────────────────────┐        │
│  │ 버킷 2 → db_xxx2                │        │
│  │  - bkt_2 (...)                  │        │
│  └─────────────────────────────────┘        │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ Tier 3: DStore (데이터 계층)                │
├─────────────────────────────────────────────┤
│ SQLite (노드·버킷별): meta.db               │
│  /mnt/dstores/buckets/1/meta/meta.db        │
│  /mnt/dstores/buckets/2/meta/meta.db        │
│  - object (청크 인덱스)                     │
│  - WAL 모드                                 │
└─────────────────────────────────────────────┘
```

**핵심 설계 원칙**:
- ✅ **버킷별 DB 물리 격리** (Tenant Isolation)
- ✅ **무한 스케일**: 버킷 증가 시 DB 동적 생성
- ✅ **Fault Isolation**: 버킷 DB 장애 → 다른 버킷 영향 없음
- ✅ **로컬 빠른 조회**: DStore SQLite

---

## 🎯 2. Growbin 시스템 현황 분석

### 2.1 현재 데이터 구조

```
┌─────────────────────────────────────────────┐
│ PostgreSQL (단일 DB: growbin)                │
├─────────────────────────────────────────────┤
│ - users (사용자 정보)                        │
│ - waste_analysis (분석 결과)                 │
│ - waste_images (이미지 메타)                 │
│ - recycling_rules (분리배출 규칙)            │
│ - chat_history (LLM 채팅 이력)               │
│ - location_data (위치 정보)                  │
│ - feedback (사용자 피드백)                   │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ RabbitMQ (메시지 큐)                         │
├─────────────────────────────────────────────┤
│ - user_input_queue                          │
│ - vision_analysis_queue                     │
│ - rule_retrieval_queue                      │
│ - response_generation_queue                 │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ Redis (캐싱)                                 │
├─────────────────────────────────────────────┤
│ - session cache                             │
│ - API rate limiting                         │
│ - recycling_rules cache                     │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ S3 (이미지 저장)                             │
├─────────────────────────────────────────────┤
│ - prod-growbin-images/                      │
│   ├─ uploads/{user_id}/{timestamp}.jpg      │
│   └─ thumbnails/...                         │
└─────────────────────────────────────────────┘
```

### 2.2 현재 설계의 문제점

#### ❌ 단일 PostgreSQL DB의 한계
1. **모든 테이블이 하나의 DB에 집중**
   - 사용자·분석·채팅·위치 등 모든 데이터 혼재
   - 테넌트 격리 불가
   
2. **스케일링 어려움**
   - Vertical Scaling만 가능 (단일 DB 인스턴스)
   - 특정 기능의 부하가 전체 DB에 영향
   
3. **장애 격리 불가**
   - DB 장애 시 전체 서비스 다운
   - 백업·복구 시 전체 서비스 중단

#### ❌ 글로벌 확장 어려움
- 현재: 단일 리전(ap-northeast-2)
- 문제: 글로벌 사용자 지연 증가

#### ❌ 멀티테넌시 부재
- 현재: B2C 서비스 (개인 사용자만)
- 향후: B2B (기업별 격리 필요)

---

## 💡 3. Robin/OStore 사례에서 배울 수 있는 점

### 교훈 1: 전역 vs 로컬 분리 (Robin)

| 데이터 유형 | 저장 위치 | Robin 사례 |
|-------------|-----------|------------|
| **전역 메타** | PostgreSQL | 클러스터 전역 조율 |
| **노드별 설정** | SQLite | 로컬 최적화·장애 격리 |
| **빠른 조회** | SQLite (WAL) | 네트워크 없이 즉시 조회 |

**Growbin 적용**:
```
전역 조율: PostgreSQL (사용자·정책·인증)
로컬 최적화: Worker별 Task Queue (SQLite)
빠른 조회: 이미지 메타 로컬 캐시 (SQLite)
```

### 교훈 2: 버킷별 DB 격리 (OStore)

**OStore의 혁신**:
- ❌ 단일 테이블에 모든 오브젝트 → 수억 행 → 느림
- ✅ 버킷마다 별도 DB → 물리적 격리 → 빠름

**OStore 장점**:
1. **Tenant Isolation**: 버킷 A 장애 → 버킷 B 영향 없음
2. **Scalability**: 버킷 증가 → DB 동적 생성 (무한 확장)
3. **Fast Delete**: 버킷 삭제 → DB DROP (빠르고 안전)

**Growbin 적용 가능성**:
```
현재: 단일 DB (growbin)
개선: 도메인별 DB 분리
  - growbin_auth (인증/인가)
  - growbin_waste (폐기물 분석)
  - growbin_chat (LLM 채팅)
  - growbin_location (위치 정보)
  
또는 테넌트별 DB 분리 (B2B 확장 시):
  - growbin_tenant_company_a
  - growbin_tenant_company_b
```

### 교훈 3: 3-Tier 계층 분리 (OStore)

```
CM (Control Manager)     → 전역 조율
MStore (Meta Store)      → 메타데이터 계층 (샤딩)
DStore (Data Store)      → 데이터 계층 (로컬 인덱스)
```

**Growbin 적용**:
```
Control Plane    → PostgreSQL (사용자·정책·도메인 등록)
API Layer        → 도메인별 서비스 (waste, auth, chat, location)
Worker Layer     → Celery Workers (비동기 처리)
Data Layer       → S3/CloudFront (이미지), PostgreSQL (메타)
```

---

## 🚀 4. Growbin 개선 방안 제안

### 방안 A: 도메인별 DB 분리 (단기) ⭐ 권장

**현재**:
```sql
growbin (단일 DB)
  ├─ users
  ├─ waste_analysis
  ├─ waste_images
  ├─ chat_history
  ├─ location_data
  └─ recycling_rules
```

**개선 후**:
```sql
┌─────────────────────────────────────┐
│ growbin_auth (인증/인가)            │
├─────────────────────────────────────┤
│ - users                             │
│ - sessions                          │
│ - access_tokens                     │
│ - oauth_providers                   │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ growbin_waste (폐기물 분석)         │
├─────────────────────────────────────┤
│ - waste_analysis                    │
│ - waste_images                      │
│ - recycling_rules                   │
│ - gpt_vision_results                │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ growbin_chat (LLM 채팅)             │
├─────────────────────────────────────┤
│ - chat_messages                     │
│ - llm_prompts                       │
│ - feedback                          │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ growbin_location (위치 정보)        │
├─────────────────────────────────────┤
│ - user_locations                    │
│ - recycling_centers                 │
│ - disposal_sites                    │
│ - region_policies                   │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ growbin_analytics (분석/통계)       │
├─────────────────────────────────────┤
│ - user_stats                        │
│ - waste_trends                      │
│ - service_metrics                   │
│ - audit_logs                        │
└─────────────────────────────────────┘
```

**장점**:
- ✅ **장애 격리**: waste DB 장애 → chat/location 정상 운영
- ✅ **스케일 독립**: 트래픽 많은 도메인만 인스턴스 증설
- ✅ **백업 독립**: 도메인별 백업 정책 (waste=7일, chat=30일)
- ✅ **개발 독립**: 팀별 DB 스키마 수정 독립

**단점**:
- ⚠️ Cross-DB JOIN 불가 (애플리케이션 레벨 조인 필요)
- ⚠️ 분산 트랜잭션 복잡도 증가

---

### 방안 B: Worker별 로컬 SQLite (Robin 방식)

**적용 대상**: Celery Workers

**현재**:
```
모든 Worker → RabbitMQ → PostgreSQL
- Task 상태를 PostgreSQL에 저장
- 네트워크 지연
```

**개선 후**:
```
각 Worker → 로컬 SQLite (task_queue.db)
  - Task 상태 로컬 저장 (WAL 모드)
  - 완료 후 PostgreSQL 동기화
  - 네트워크 독립 운영 가능
```

**예시 구조**:
```python
# worker-storage (image-uploader, rule-retriever)
/var/lib/growbin/worker-storage/task_queue.db
  - tasks (id, type, status, payload, created_at, completed_at)
  - task_logs (task_id, timestamp, message, level)

# worker-ai (gpt5-analyzer, response-generator)
/var/lib/growbin/worker-ai/task_queue.db
  - tasks (...)
  - gpt_cache (prompt_hash, response, model, timestamp)
```

**장점**:
- ✅ **빠른 조회**: 네트워크 없이 로컬 파일 조회
- ✅ **장애 격리**: PostgreSQL 장애 시에도 Worker 작업 계속
- ✅ **재시작 빠름**: SQLite 복구 → 중앙 DB 의존 없음

**Robin 코드 참고**:
```c
// rdvm/cfg.c
flags = SQLITE_OPEN_FULLMUTEX | SQLITE_OPEN_READWRITE;
rc = sqlite3_open_v2(cfg->cfgfname.buf, &cfg->db, flags, NULL);
rc = sql_exec(cfg->db, "PRAGMA journal_mode=WAL", NULL, NULL, NULL);
```

---

### 방안 C: 테넌트별 DB 분리 (장기, B2B 확장 시)

**시나리오**: 기업 고객(B2B) 추가

**OStore 방식 적용**:
```
CM (Control Manager)
  ├─ tenant_registry (테넌트 등록)
  ├─ tenant_quota (할당량 관리)
  └─ tenant_db_mapping (tenant_id → db_name)

Tenant DB (테넌트별 물리 격리)
  ├─ growbin_tenant_company_a
  │   ├─ users
  │   ├─ waste_analysis
  │   └─ ...
  ├─ growbin_tenant_company_b
  └─ ...
```

**템플릿 DB 방식** (OStore 참고):
```sql
-- 1. 템플릿 DB 생성
CREATE DATABASE growbin_tenant_template;
ALTER DATABASE growbin_tenant_template SET datistemplate = TRUE;

-- 2. 새 테넌트 생성 시
CREATE DATABASE growbin_tenant_{company_id} 
  WITH TEMPLATE growbin_tenant_template;
```

**장점**:
- ✅ **완전한 Tenant Isolation**
- ✅ **무한 확장 가능** (테넌트 증가 시 DB 동적 생성)
- ✅ **빠른 삭제**: 테넌트 해지 → DROP DATABASE

**OStore 코드 참고**:
```python
# create_db_schema.py
template = "mstore_base_db"
cursor.execute(f"CREATE DATABASE {template} WITH OWNER robin TEMPLATE template1")
cursor.execute(f"UPDATE pg_database SET datistemplate = TRUE WHERE datname = '{template}'")

# 새 버킷 DB 생성
db_name = f"db_{nano_epoch}{random_suffix}"
cursor.execute(f"CREATE DATABASE {db_name} WITH TEMPLATE {template}")
```

---

### 방안 D: 이미지 메타 로컬 인덱스 (OStore DStore 방식)

**현재**:
```
S3 (images)
  └─ PostgreSQL (waste_images 테이블)
      - image_id, user_id, s3_path, upload_time, size, ...
```

**개선 후** (DStore 방식):
```
각 API 노드 → 로컬 SQLite (image_index.db)
  - 최근 업로드 이미지 메타 캐싱
  - S3 청크 인덱스 (빠른 조회)
  - WAL 모드
  
백그라운드 동기화:
  - 주기적으로 PostgreSQL과 동기화
  - S3 이벤트 → SQLite 업데이트
```

**예시 구조**:
```sql
-- /var/lib/growbin/api-waste/image_index.db
CREATE TABLE image_cache (
    image_id TEXT PRIMARY KEY,
    user_id TEXT,
    s3_path TEXT,
    s3_bucket TEXT,
    upload_time INTEGER,
    size INTEGER,
    analysis_status TEXT,
    last_synced INTEGER,
    UNIQUE (s3_path)
);
```

**장점**:
- ✅ **빠른 조회**: 로컬 파일 → 네트워크 지연 없음
- ✅ **PostgreSQL 부하 감소**: 이미지 메타 조회는 로컬에서
- ✅ **장애 복원력**: PostgreSQL 장애 시에도 최근 이미지 조회 가능

---

## 📊 5. 최종 권장 아키텍처 (단계별)

### Phase 1: 도메인별 DB 분리 (즉시 적용 가능) ⭐

```
┌─────────────────────────────────────────────┐
│ PostgreSQL Cluster (StatefulSet)            │
├─────────────────────────────────────────────┤
│ growbin_auth       (2GB, HA)                │
│ growbin_waste      (5GB, HA)                │
│ growbin_chat       (3GB, HA)                │
│ growbin_location   (1GB, HA)                │
│ growbin_analytics  (10GB, Read Replica)     │
└─────────────────────────────────────────────┘
```

**Terraform 코드**:
```hcl
# terraform/postgresql-dbs.tf
resource "kubernetes_config_map" "postgresql_init" {
  metadata {
    name = "postgresql-init-scripts"
    namespace = "data"
  }
  
  data = {
    "01-create-databases.sql" = <<-EOF
      -- 도메인별 DB 생성
      CREATE DATABASE growbin_auth;
      CREATE DATABASE growbin_waste;
      CREATE DATABASE growbin_chat;
      CREATE DATABASE growbin_location;
      CREATE DATABASE growbin_analytics;
      
      -- 도메인별 사용자 생성 (최소 권한)
      CREATE USER auth_user WITH PASSWORD 'xxx';
      GRANT ALL ON DATABASE growbin_auth TO auth_user;
      
      CREATE USER waste_user WITH PASSWORD 'xxx';
      GRANT ALL ON DATABASE growbin_waste TO waste_user;
      -- ...
    EOF
  }
}
```

### Phase 2: Worker 로컬 SQLite (3개월 후)

```
Worker-Storage Pod
  ├─ Celery Worker (image-uploader, rule-retriever)
  └─ /var/lib/growbin/task_queue.db (SQLite, WAL)

Worker-AI Pod
  ├─ Celery Worker (gpt5-analyzer, response-generator)
  └─ /var/lib/growbin/task_queue.db (SQLite, WAL)
```

### Phase 3: 테넌트별 DB 분리 (B2B 확장 시)

```
growbin_control (CM)
  └─ tenant_registry

growbin_tenant_{company_id} (동적 생성)
  ├─ users
  ├─ waste_analysis
  └─ ...
```

---

## 💻 6. 구현 예시

### 6.1 도메인별 DB 연결 (Python/FastAPI)

```python
# app/db/connections.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 도메인별 DB 엔진
auth_engine = create_engine(
    "postgresql://auth_user:xxx@postgresql:5432/growbin_auth",
    pool_size=10,
    max_overflow=20
)

waste_engine = create_engine(
    "postgresql://waste_user:xxx@postgresql:5432/growbin_waste",
    pool_size=20,  # 트래픽 많음
    max_overflow=40
)

chat_engine = create_engine(
    "postgresql://chat_user:xxx@postgresql:5432/growbin_chat",
    pool_size=15,
    max_overflow=30
)

# 세션 팩토리
AuthSession = sessionmaker(bind=auth_engine)
WasteSession = sessionmaker(bind=waste_engine)
ChatSession = sessionmaker(bind=chat_engine)
```

```python
# services/waste/api.py
from app.db.connections import WasteSession

@router.post("/analyze")
async def analyze_waste(image: UploadFile):
    with WasteSession() as db:
        # growbin_waste DB만 사용
        analysis = WasteAnalysis(
            user_id=current_user.id,
            image_path=s3_path,
            status="pending"
        )
        db.add(analysis)
        db.commit()
    
    # Celery Task 전송
    analyze_task.delay(analysis.id)
    return {"analysis_id": analysis.id}
```

### 6.2 Worker 로컬 SQLite (Robin 방식)

```python
# workers/storage/task_manager.py
import sqlite3
from contextlib import contextmanager

class LocalTaskQueue:
    def __init__(self, db_path="/var/lib/growbin/task_queue.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        with self._get_conn() as conn:
            # WAL 모드 활성화 (Robin 방식)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload JSON,
                    created_at INTEGER,
                    completed_at INTEGER
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_status 
                ON tasks(status, created_at)
            """)
    
    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(
            self.db_path,
            isolation_level=None,  # Autocommit
            check_same_thread=False
        )
        try:
            yield conn
        finally:
            conn.close()
    
    def save_task(self, task_id, task_type, payload):
        """로컬에 Task 저장"""
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO tasks (id, type, status, payload, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (task_id, task_type, "pending", json.dumps(payload), time.time()))
    
    def update_status(self, task_id, status):
        """Task 상태 업데이트"""
        with self._get_conn() as conn:
            completed_at = time.time() if status == "completed" else None
            conn.execute("""
                UPDATE tasks 
                SET status = ?, completed_at = ?
                WHERE id = ?
            """, (status, completed_at, task_id))
    
    def sync_to_postgres(self):
        """주기적으로 PostgreSQL과 동기화"""
        with self._get_conn() as conn:
            completed = conn.execute("""
                SELECT * FROM tasks 
                WHERE status = 'completed' AND completed_at > ?
            """, (time.time() - 3600,)).fetchall()  # 최근 1시간
            
            # PostgreSQL에 동기화
            for task in completed:
                # ... PostgreSQL INSERT
                pass

# Celery Worker에서 사용
task_queue = LocalTaskQueue()

@app.task
def image_upload_task(image_path):
    task_id = image_upload_task.request.id
    
    # 로컬 SQLite에 저장
    task_queue.save_task(task_id, "image_upload", {"path": image_path})
    
    try:
        # S3 업로드
        s3_path = upload_to_s3(image_path)
        
        # 상태 업데이트
        task_queue.update_status(task_id, "completed")
        
        return {"s3_path": s3_path}
    except Exception as e:
        task_queue.update_status(task_id, "failed")
        raise
```

---

## 📋 7. 마이그레이션 계획

### Step 1: 도메인별 DB 생성 (1주)
```bash
# PostgreSQL에서 실행
CREATE DATABASE growbin_auth;
CREATE DATABASE growbin_waste;
CREATE DATABASE growbin_chat;
CREATE DATABASE growbin_location;
CREATE DATABASE growbin_analytics;
```

### Step 2: 데이터 마이그레이션 (2주)
```bash
# 각 도메인별로 테이블 복사
pg_dump growbin -t users -t sessions | psql growbin_auth
pg_dump growbin -t waste_analysis -t waste_images | psql growbin_waste
pg_dump growbin -t chat_history -t chat_messages | psql growbin_chat
# ...
```

### Step 3: 애플리케이션 코드 수정 (2주)
- DB 연결 문자열 변경
- Cross-DB JOIN 제거 (애플리케이션 레벨로 이동)
- 분산 트랜잭션 처리

### Step 4: Worker 로컬 SQLite 도입 (1주)
- Celery Worker에 SQLite 추가
- Task Queue 로컬 저장
- 동기화 로직 구현

### Step 5: 테스트 및 롤백 계획 (1주)
- 부하 테스트
- 장애 시나리오 테스트
- 롤백 스크립트 준비

---

## 🎯 8. 결론 및 권장사항

### 즉시 적용 가능 (Phase 1)

**도메인별 DB 분리** ⭐⭐⭐
- Robin/OStore 교훈: 전역 vs 로컬 분리
- Growbin 적용: auth, waste, chat, location 도메인별 DB
- 장점: 장애 격리, 스케일 독립, 개발 독립
- 비용: 코드 수정 2주, 마이그레이션 2주

### 중기 적용 (Phase 2)

**Worker 로컬 SQLite** ⭐⭐
- Robin 교훈: 노드별 로컬 최적화
- Growbin 적용: Celery Worker Task Queue
- 장점: 빠른 조회, 장애 격리
- 비용: 코드 수정 1주

### 장기 준비 (Phase 3)

**테넌트별 DB 분리** ⭐
- OStore 교훈: 버킷별 물리 격리
- Growbin 적용: B2B 확장 시 기업별 DB
- 장점: 완전한 Tenant Isolation
- 비용: B2B 전략 확정 후 검토

---

## 📊 비교표

| 항목 | 현재 (단일 DB) | Phase 1 (도메인별) | Phase 2 (+ Worker SQLite) | Phase 3 (+ 테넌트별) |
|------|----------------|--------------------|-----------------------------|----------------------|
| **장애 격리** | ❌ 없음 | ✅ 도메인별 | ✅ 도메인+Worker | ✅ 완전 격리 |
| **스케일 독립** | ❌ 불가 | ✅ 도메인별 | ✅ 도메인+Worker | ✅ 테넌트별 |
| **로컬 최적화** | ❌ 없음 | ❌ 없음 | ✅ Worker 로컬 | ✅ Worker 로컬 |
| **멀티테넌시** | ❌ 없음 | ❌ 논리적만 | ❌ 논리적만 | ✅ 물리적 격리 |
| **복잡도** | 낮음 | 중간 | 중간 | 높음 |
| **개발 기간** | - | 4주 | +1주 | +4주 |

---

**최종 권장**: Phase 1 (도메인별 DB 분리)를 즉시 적용하고, Phase 2 (Worker SQLite)는 트래픽 증가 시 검토, Phase 3 (테넌트별)는 B2B 전략 확정 후 진행 🎯

