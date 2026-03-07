# Celery Redis ReadOnlyError 트러블슈팅

**Date:** 2025-12-24  
**Tags:** `celery`, `redis`, `sentinel`, `replica`, `troubleshooting`

---

## 📌 증상

### 사용자 요청 결과
```json
{
    "step": "reward",
    "status": "completed",
    "progress": 100,
    "result": {
        "task_id": "cae074a8-2e31-4ca3-9f03-3522c7d592a3",
        "status": "completed",
        "message": "classification completed",
        "pipeline_result": {
            "classification_result": null,
            "disposal_rules": null,
            "final_answer": null
        },
        "reward": null,
        "error": null
    }
}
```

모든 `pipeline_result` 필드가 `null`로 반환됨.

---

## 🔍 원인 분석

### Worker 로그 확인
```
redis.exceptions.ReadOnlyError: Command # 1 (SETEX celery-task-meta-xxx ...)
You can't write against a read only replica.
```

### 근본 원인

```
┌─────────────────────────────────────────────────────────────┐
│                    Redis Sentinel 구조                        │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│   dev-redis-node-0 (Master)   ←─┐                            │
│   ├── 읽기 ✓                      │ Replication               │
│   └── 쓰기 ✓                      │                            │
│                                    │                            │
│   dev-redis-node-1 (Replica)  ───┘                            │
│   ├── 읽기 ✓                                                   │
│   └── 쓰기 ✗ (ReadOnlyError!)                                  │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

| 서비스 | 대상 | 문제 |
|--------|------|------|
| `dev-redis` (ClusterIP) | 모든 노드 | 랜덤 라우팅 → Replica 연결 시 쓰기 실패 |
| `dev-redis-headless` | 개별 Pod | 직접 지정 가능 |

### 기존 설정 (잘못된 구성)
```yaml
- name: CELERY_RESULT_BACKEND
  value: redis://dev-redis.redis.svc.cluster.local:6379/0
```

→ ClusterIP가 Replica로 라우팅되면 **ReadOnlyError** 발생!

---

## ✅ 해결책

### Master 노드 직접 연결
```yaml
- name: CELERY_RESULT_BACKEND
  value: redis://dev-redis-node-0.dev-redis-headless.redis.svc.cluster.local:6379/0
```

### 수정된 서비스
| 서비스 | 변경 전 | 변경 후 |
|--------|---------|---------|
| scan-worker | `dev-redis` | `dev-redis-node-0.dev-redis-headless` |
| scan-api | `dev-redis` | `dev-redis-node-0.dev-redis-headless` |
| character-match-worker | `dev-redis` | `dev-redis-node-0.dev-redis-headless` |
| character-worker | `dev-redis` | `dev-redis-node-0.dev-redis-headless` |
| my-worker | `dev-redis` | `dev-redis-node-0.dev-redis-headless` |
| celery-beat | `dev-redis` | `dev-redis-node-0.dev-redis-headless` |

---

## 🧪 Master 확인 방법

```bash
# node-0이 Master인지 확인
kubectl exec -n redis dev-redis-node-0 -c redis -- redis-cli INFO replication | head -5

# 결과:
# role:master
# connected_slaves:1
# slave0:ip=dev-redis-node-1...

# node-1이 Replica인지 확인
kubectl exec -n redis dev-redis-node-1 -c redis -- redis-cli INFO replication | head -5

# 결과:
# role:slave
# master_host:dev-redis-node-0...
```

---

## 📚 장기적 개선 방안

### Option 1: Redis Sentinel 연결 사용
Celery는 `redis+sentinel://` 스키마를 지원하지만 추가 구성 필요:

```python
CELERY_RESULT_BACKEND = "sentinel://dev-redis:26379/0"
CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS = {
    "master_name": "mymaster",
    "sentinel_kwargs": {"password": "xxx"},
}
```

### Option 2: Master-only Service 생성
```yaml
apiVersion: v1
kind: Service
metadata:
  name: dev-redis-master
  namespace: redis
spec:
  selector:
    app.kubernetes.io/name: redis
    role: master  # Master Pod만 선택
  ports:
  - port: 6379
```

### Option 3: 현재 방식 유지 (권장)
- Headless Service로 Master 직접 연결
- Failover 시 수동 업데이트 필요
- 개발/스테이징 환경에 적합

---

## 📊 영향 분석

### 증상 발생 경로
```
1. scan.vision → 성공 (결과 Redis 저장 시도)
2. scan.rule   → 성공 (결과 Redis 저장 시도)
3. scan.answer → 성공 (결과 Redis 저장 시도)
   ↓
   ReadOnlyError! → 결과 저장 실패
   ↓
4. scan.reward → prev_result에서 null 수신
   ↓
5. character.match 호출 → Timeout (10s)
   ↓
6. API 응답: 모든 필드 null
```

### 실제 처리 상태
- **LLM 분석**: ✓ 성공 (종이가방 → 기타 종이류)
- **규칙 조회**: ✓ 성공 (배출 방법 확인)
- **결과 저장**: ✗ 실패 (ReadOnlyError)
- **클라이언트 응답**: ✗ null 반환

---

## 🎯 핵심 교훈

1. **Redis Sentinel/Replica 구조에서는 Master만 쓰기 가능**
2. **ClusterIP 서비스는 랜덤 라우팅 → Replica로 갈 수 있음**
3. **Celery Result Backend는 반드시 쓰기 가능한 노드에 연결**
4. **다른 서비스 설정 참고** (auth, image는 이미 Master 직접 연결 사용)

---

## 📎 관련 커밋

- `ca40e662` - fix(redis): Master 노드 직접 연결로 ReadOnlyError 해결












