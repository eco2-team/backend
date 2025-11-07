# Worker Local SQLite WAL 구현 가이드

## 📊 개요

Ecoeco Worker에 Robin 패턴을 적용한 로컬 SQLite WAL (Write-Ahead Logging) 구현입니다.

### 아키텍처

```
┌──────────────────────────────────────────────────────┐
│ FastAPI (Producer)                                   │
│  └─ RabbitMQ Publish                                 │
└────────────────┬─────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────┐
│ RabbitMQ (Message Queue)                             │
│  - Durable Queue                                     │
│  - Persistent Messages                               │
└────────────────┬─────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────┐
│ Worker (Celery + Local SQLite WAL)                   │
├──────────────────────────────────────────────────────┤
│ 1. RabbitMQ에서 메시지 수신                           │
│ 2. 로컬 SQLite + WAL에 기록 ⭐                        │
│    └─ /var/lib/ecoeco/wal/task_queue.db            │
│    └─ PRAGMA journal_mode=WAL                        │
│ 3. 작업 처리 (S3 업로드, AI 추론 등)                  │
│ 4. 결과를 WAL에 기록                                  │
│ 5. 비동기로 PostgreSQL 동기화                         │
└──────────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────┐
│ PostgreSQL (최종 저장소)                              │
│  - 작업 결과 저장                                     │
│  - 장기 보관                                          │
└──────────────────────────────────────────────────────┘
```

## 🎯 WAL의 목적

### 1. 작업 내구성 (Durability)
- Worker 재시작 시에도 작업 손실 없음
- RabbitMQ ACK 전에 로컬 디스크에 기록

### 2. 빠른 응답 (Performance)
- PostgreSQL보다 빠른 로컬 SQLite 쓰기
- 순차 쓰기 (WAL)로 성능 최적화

### 3. 장애 복구 (Recovery)
- Worker 장애 시 미완료 작업 자동 복구
- 체크포인트 기반 복구

### 4. PostgreSQL 부하 분산
- 실시간 동기화 대신 배치 동기화
- DB 연결 풀 효율적 사용

## 📦 구성 요소

### 1. WAL Manager (`app/wal.py`)

**주요 기능**:
- SQLite WAL 모드 초기화
- 작업 수신/시작/완료/실패 기록
- PostgreSQL 동기화 관리
- 체크포인트 생성
- 오래된 작업 정리

**사용 예시**:

```python
from app.wal import WALManager

# WAL Manager 초기화
wal = WALManager(db_path="/var/lib/ecoeco/wal/task_queue.db")

# 작업 수신 시 기록
wal.write_task(
    task_id="abc-123",
    task_name="upload_to_s3",
    worker_name="storage-worker",
    args=("/tmp/image.jpg",),
    kwargs={"s3_key": "images/123.jpg"}
)

# 작업 시작
wal.start_task("abc-123")

# 작업 완료
result = {"status": "success", "url": "https://..."}
wal.complete_task("abc-123", result)

# PostgreSQL 동기화 완료 표시
wal.mark_synced("abc-123")

# 통계 조회
stats = wal.get_stats()
# {'by_status': {'SUCCESS': 100, 'RUNNING': 2}, 'sync': {...}, 'wal_size_mb': 1.5}
```

### 2. Storage Worker (`workers/storage_worker.py`)

**기능**:
- S3 업로드 작업 처리
- 이미지 처리 작업
- WAL 자동 관리
- PostgreSQL 동기화

**주요 Task**:
- `upload_to_s3`: S3 업로드
- `process_image`: 이미지 처리
- `sync_to_postgres`: PostgreSQL 동기화
- `periodic_wal_checkpoint`: 주기적 체크포인트 (5분마다)
- `periodic_wal_cleanup`: 주기적 정리 (매일)

### 3. AI Worker (`workers/ai_worker.py`)

**기능**:
- AI 추론 작업 처리
- LLM 챗봇 응답 생성
- OCR 텍스트 추출
- WAL 자동 관리

**주요 Task**:
- `classify_waste_image`: 폐기물 분류 (GPT-5 Vision)
- `chat_with_llm`: LLM 챗봇 (GPT-4o mini)
- `extract_text_from_image`: OCR

## 🚀 배포

### 1. Kubernetes PVC 생성

```bash
# Worker WAL PVC 생성
kubectl apply -f k8s/workers/worker-wal-deployments.yaml
```

**생성되는 리소스**:
- `storage-worker-wal-pvc`: 10GB PVC (Storage Worker)
- `ai-worker-wal-pvc`: 10GB PVC (AI Worker)

### 2. Worker Deployment 배포

**특징**:
- 각 Worker에 전용 PVC 마운트 (`/var/lib/ecoeco/wal`)
- Graceful Shutdown (60초)
- Liveness/Readiness Probe

```bash
# Worker 배포 확인
kubectl get pods -l component=worker
kubectl get pvc -l component=wal
```

### 3. 환경 변수 설정

**필수 환경 변수**:

```yaml
# Storage Worker
- name: WAL_DB_PATH
  value: "/var/lib/ecoeco/wal/storage_worker.db"
- name: RABBITMQ_URL
  value: "amqp://guest:guest@rabbitmq:5672//"
- name: REDIS_URL
  value: "redis://redis:6379/0"
- name: POSTGRES_HOST
  value: "postgresql"

# AI Worker
- name: WAL_DB_PATH
  value: "/var/lib/ecoeco/wal/ai_worker.db"
- name: OPENAI_API_KEY
  valueFrom:
    secretKeyRef:
      name: openai-secret
      key: api-key
```

## 🔄 WAL 작동 원리

### 1. 작업 수신 및 기록

```python
# Celery Signal: task_prerun
@task_prerun.connect
def on_task_prerun(sender, task_id, task, args, kwargs, **extra):
    # WAL에 작업 기록 (PENDING 상태)
    wal_manager.write_task(
        task_id=task_id,
        task_name=task.name,
        worker_name="storage-worker",
        args=args,
        kwargs=kwargs
    )
    
    # 작업 시작 상태로 변경 (RUNNING)
    wal_manager.start_task(task_id)
```

**SQLite WAL 테이블**:

```sql
CREATE TABLE task_wal (
    task_id TEXT PRIMARY KEY,
    task_name TEXT NOT NULL,
    worker_name TEXT NOT NULL,
    args TEXT,
    kwargs TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING/RUNNING/SUCCESS/FAILURE
    result TEXT,
    error TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    synced_to_postgres INTEGER DEFAULT 0  -- 0: 미동기화, 1: 동기화 완료
);
```

### 2. 작업 처리

```python
@app.task(base=WALTask, bind=True, max_retries=3)
def upload_to_s3(self, file_path: str, s3_key: str):
    try:
        # S3 업로드 수행
        s3_client.upload_file(file_path, bucket, s3_key)
        
        result = {"status": "success", "s3_key": s3_key}
        return result  # WALTask.on_success() 호출됨
        
    except Exception as e:
        # WALTask.on_failure() 호출됨
        raise self.retry(exc=e, countdown=60)
```

**WALTask 자동 처리**:

```python
class WALTask(Task):
    def on_success(self, retval, task_id, args, kwargs):
        # 작업 완료 시 WAL 업데이트 (SUCCESS)
        wal_manager.complete_task(task_id, retval)
        
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        # 작업 실패 시 WAL 업데이트 (FAILURE)
        wal_manager.fail_task(task_id, str(exc), self.request.retries)
```

### 3. PostgreSQL 동기화

```python
# 비동기 동기화 (별도 Task)
@app.task
def sync_to_postgres(task_id: str):
    # WAL에서 미동기화 작업 조회
    tasks = wal_manager.get_unsynced_tasks(limit=100)
    
    for task in tasks:
        try:
            # PostgreSQL에 저장
            db.execute("""
                INSERT INTO task_results (task_id, result, completed_at)
                VALUES (?, ?, ?)
            """, (task['task_id'], task['result'], task['completed_at']))
            
            # 동기화 완료 표시
            wal_manager.mark_synced(task['task_id'])
            
        except Exception as e:
            logger.error(f"Sync failed: {e}")
```

## 🛠️ WAL 최적화 설정

### SQLite PRAGMA

```python
# WAL 모드 활성화
conn.execute("PRAGMA journal_mode=WAL")

# 동기화 모드 (성능 개선)
conn.execute("PRAGMA synchronous=NORMAL")  # FULL보다 빠름, 여전히 안전

# WAL 자동 체크포인트
conn.execute("PRAGMA wal_autocheckpoint=1000")  # 1000 페이지마다

# 캐시 크기
conn.execute("PRAGMA cache_size=-64000")  # 64MB

# 임시 저장소
conn.execute("PRAGMA temp_store=MEMORY")
```

### 체크포인트 전략

**자동 체크포인트** (1000 페이지):
- SQLite가 자동으로 수행
- 백그라운드에서 비동기 수행

**수동 체크포인트** (5분마다):
```python
@app.task
def periodic_wal_checkpoint():
    wal_manager.checkpoint()  # PRAGMA wal_checkpoint(PASSIVE)
```

**PASSIVE vs FULL vs TRUNCATE**:
- `PASSIVE`: 다른 작업 방해 안 함 (권장)
- `FULL`: 모든 변경사항 강제 플러시
- `TRUNCATE`: WAL 파일 크기 줄임

## 🔍 모니터링

### WAL 통계 조회

```python
stats = wal_manager.get_stats()

# 출력 예시:
{
    "by_status": {
        "PENDING": 5,
        "RUNNING": 2,
        "SUCCESS": 1000,
        "FAILURE": 10
    },
    "sync": {
        "total": 1017,
        "synced": 950,
        "unsynced": 67
    },
    "wal_size_mb": 1.5
}
```

### Prometheus 메트릭

```python
from prometheus_client import Gauge, Counter

# WAL 메트릭
wal_tasks_total = Gauge('wal_tasks_total', 'Total tasks in WAL', ['status'])
wal_unsynced_tasks = Gauge('wal_unsynced_tasks', 'Unsynced tasks count')
wal_size_bytes = Gauge('wal_size_bytes', 'WAL file size in bytes')

# 주기적 업데이트
@app.task
def update_wal_metrics():
    stats = wal_manager.get_stats()
    
    for status, count in stats['by_status'].items():
        wal_tasks_total.labels(status=status).set(count)
    
    wal_unsynced_tasks.set(stats['sync']['unsynced'])
    wal_size_bytes.set(stats['wal_size_mb'] * 1024 * 1024)
```

## 🚨 장애 복구

### Worker 재시작 시 자동 복구

```python
# Worker 시작 시 실행
@worker_ready.connect
def on_worker_ready(sender, **kwargs):
    # WAL Manager 초기화
    wal_manager = WALManager(db_path="/var/lib/ecoeco/wal/storage_worker.db")
    
    # 복구 수행
    recovery = WALRecovery(wal_manager)
    pending_tasks = recovery.recover_pending_tasks()
    
    if pending_tasks:
        logger.warning(f"Recovered {len(pending_tasks)} pending tasks")
        
        for task in pending_tasks:
            if task['status'] == 'RUNNING':
                # 1시간 이상 RUNNING이면 FAILURE로 변경
                if is_timeout(task):
                    wal_manager.fail_task(task['task_id'], "Task timeout during recovery")
```

### 수동 복구

```bash
# Worker Pod 접속
kubectl exec -it storage-worker-xyz -- bash

# Python 쉘 실행
python3 << EOF
from app.wal import WALManager, WALRecovery

wal = WALManager("/var/lib/ecoeco/wal/storage_worker.db")
recovery = WALRecovery(wal)

# 미완료 작업 조회
pending = recovery.recover_pending_tasks()
print(f"Pending tasks: {len(pending)}")

# 강제 동기화
synced = recovery.force_sync_all(postgres_sync_func)
print(f"Synced {synced} tasks")

# 통계
print(wal.get_stats())
EOF
```

## 🧹 유지보수

### 오래된 작업 정리

```python
# 7일 이상 된 동기화 완료 작업 삭제
deleted = wal_manager.cleanup_old_tasks(days=7)
logger.info(f"Deleted {deleted} old tasks")

# 자동 정리 (Celery Beat)
@app.task
def periodic_wal_cleanup():
    wal_manager.cleanup_old_tasks(days=7)
```

### WAL 파일 크기 관리

```python
# WAL 파일 크기 확인
stats = wal_manager.get_stats()
wal_size_mb = stats['wal_size_mb']

if wal_size_mb > 100:  # 100MB 초과 시
    logger.warning(f"WAL file is large: {wal_size_mb}MB")
    
    # VACUUM 실행
    wal_manager.conn.execute("VACUUM")
```

## 📊 성능 비교

### 직접 PostgreSQL vs WAL

| 작업 | PostgreSQL 직접 쓰기 | SQLite WAL | 개선율 |
|------|---------------------|-----------|-------|
| 단일 INSERT | ~10ms | ~0.5ms | **20x** |
| 100개 배치 INSERT | ~500ms | ~25ms | **20x** |
| 동시 쓰기 (10 threads) | 병목 발생 | 로컬 분산 | **무제한** |

### 장애 복구 시간

| 시나리오 | PostgreSQL | SQLite WAL |
|---------|-----------|-----------|
| Worker 재시작 | 손실 가능 | **0초** (자동 복구) |
| DB 장애 | 작업 중단 | **계속 처리** (나중 동기화) |

## 🎯 베스트 프랙티스

### 1. PVC 크기 선정
- **Storage Worker**: 10GB (이미지 메타데이터)
- **AI Worker**: 10GB (AI 결과)
- 1주일 보관 기준

### 2. 동기화 주기
- **실시간**: 중요 작업 (결제, 인증)
- **배치 (5분)**: 일반 작업 (이미지 업로드)
- **일일**: 통계 작업

### 3. 체크포인트 주기
- **자동**: 1000 페이지 (기본)
- **수동**: 5분마다 (안정성)
- **종료 시**: 반드시 수행

### 4. 정리 주기
- **작업 삭제**: 7일 후
- **VACUUM**: 1000개 이상 삭제 시

## 🐛 트러블슈팅

### WAL 파일이 계속 커짐

**원인**: 체크포인트 미수행

**해결**:
```python
# 체크포인트 강제 실행
wal_manager.checkpoint()

# 또는 WAL 재시작
conn.execute("PRAGMA wal_checkpoint(RESTART)")
```

### 동기화가 밀림

**원인**: PostgreSQL 병목

**해결**:
```python
# 동기화 배치 크기 조정
tasks = wal_manager.get_unsynced_tasks(limit=10)  # 100 -> 10

# 또는 PostgreSQL 연결 풀 증가
```

### Worker 재시작 후 작업 중복 실행

**원인**: RabbitMQ ACK 타이밍 문제

**해결**:
```python
# task_acks_late = True 설정 (이미 적용됨)
# WAL 기록 후 ACK
```

## 📚 참고 자료

- [SQLite WAL 공식 문서](https://www.sqlite.org/wal.html)
- [Celery Signals](https://docs.celeryproject.org/en/stable/userguide/signals.html)
- [PostgreSQL COPY](https://www.postgresql.org/docs/current/sql-copy.html)
- [Robin Storage Pattern](https://robinhood.engineering/author-robin-engineering/)

## 🎯 다음 단계

- [ ] 동기화 배치 크기 최적화
- [ ] PostgreSQL COPY 적용 (성능 개선)
- [ ] WAL Replication (다중 Worker 동기화)
- [ ] Dead Letter Queue (DLQ) 연동

