# Observability 트러블슈팅

> ECO2 로깅/모니터링 시스템 운영 중 발생한 이슈와 해결 방법

---

## 📋 목차

1. [Fluent Bit Retry 과다 발생](#1-fluent-bit-retry-과다-발생)
2. [Redis Idle Connection 끊김](#2-redis-idle-connection-끊김)

---

## 1. Fluent Bit Retry 과다 발생

### 증상

```log
[2025/12/17 12:43:58] [ info] [engine] flush chunk '1-1765972927.624820831.flb' succeeded at retry 9: task_id=365, input=tail.0 > output=es.0
[2025/12/17 12:44:43] [ info] [engine] flush chunk '1-1765971907.624937360.flb' succeeded at retry 12: task_id=100, input=tail.0 > output=es.0
[2025/12/17 12:45:24] [ info] [engine] flush chunk '1-1765971667.624929742.flb' succeeded at retry 10: task_id=40, input=tail.0 > output=es.0
```

- 정상: retry 0~1에서 즉시 성공
- 문제: retry 9~12 후에야 성공 → Elasticsearch 응답 지연

### 원인 분석

```
k8s-logging 노드 메모리: 84% (6498Mi / ~7.7GB)
└── ES JVM Heap: 4GB (-Xms4g -Xmx4g)
└── ES Pod Limit: 5Gi
└── 노드 타입: t3.large (8GB)  ← 부족!
```

**병목 발생 흐름:**

```
로그 생성 → Fluent Bit 수집 → ES 전송 요청
                                    ↓
                              ES 메모리 84%
                                    ↓
                              GC 빈번 발생
                                    ↓
                              인덱싱 지연
                                    ↓
                              Fluent Bit 타임아웃
                                    ↓
                              retry 9~12회
```

### 해결 방안

| 옵션 | 방법 | 효과 | 비용 |
|------|------|------|------|
| **1. 노드 스케일업** | t3.large → t3.xlarge (16GB) | 🟢 최선 | +$30/월 |
| **2. JVM 힙 축소** | 4GB → 2GB | 🟡 임시방편 | 무료 |
| **3. ILM 강화** | 보존기간 단축 (14→7일) | 🟡 장기 개선 | 무료 |
| **4. Fluent Bit 튜닝** | Retry_Limit, Buffer 조정 | 🟡 증상 완화 | 무료 |

### 현재 상태

- **ES Health**: yellow (단일 노드라 replica 불가 - 정상)
- **권장 조치**: 노드 스케일업 (t3.large → t3.xlarge)

---

## 2. Redis Idle Connection 끊김

### 증상

```log
redis.exceptions.ConnectionError: Connection closed by server
```

- Redis 연결이 일정 시간 후 끊어짐
- 특히 트래픽이 적은 시간대에 발생

### 원인

Redis 서버의 `timeout` 설정으로 idle connection이 끊김

### 해결

`health_check_interval` 추가:

```python
# domains/*/core/config.py
redis = aioredis.from_url(
    settings.redis_url,
    encoding="utf-8",
    decode_responses=True,
    health_check_interval=30,  # 30초마다 PING
)
```

**커밋**: `b6525543 fix(redis): health_check_interval 추가로 idle connection 끊김 방지`

---

## 📊 도메인별 로그 레벨 현황

### 배포 환경 (ConfigMap)

| 도메인 | LOG_LEVEL | 위치 |
|--------|-----------|------|
| auth | `INFO` | `workloads/domains/auth/base/configmap.yaml` |
| character | `INFO` | `workloads/domains/character/base/configmap.yaml` |
| chat | `INFO` | `workloads/domains/chat/base/configmap.yaml` |
| image | `INFO` | `workloads/domains/image/base/configmap.yaml` |
| location | `INFO` | `workloads/domains/location/base/configmap.yaml` |
| my | `INFO` | `workloads/domains/my/base/configmap.yaml` |
| scan | `INFO` | `workloads/domains/scan/base/configmap.yaml` |

### 코드 기본값 (Fallback)

```python
# domains/*/core/constants.py
DEFAULT_LOG_LEVEL = "DEBUG"
```

- 환경변수 `LOG_LEVEL`이 없으면 `DEBUG` 사용
- 로컬 개발 시 자동으로 DEBUG 레벨

### 로그 레벨 우선순위

```
1. 환경변수 LOG_LEVEL (ConfigMap에서 주입)
2. 코드 기본값 DEFAULT_LOG_LEVEL ("DEBUG")
```

### 로그 볼륨 예상

| 레벨 | 예상 볼륨 | 용도 |
|------|----------|------|
| `DEBUG` | 🔴 매우 높음 | 로컬 개발 |
| `INFO` | 🟡 중간 | 운영 환경 (현재) |
| `WARNING` | 🟢 낮음 | 프로덕션 권장 |

---

## 🔧 디버깅 명령어

### Fluent Bit 로그 확인

```bash
kubectl logs -n logging daemonset/fluent-bit --tail=100 | grep -E 'warn|error|retry'
```

### ES 클러스터 상태

```bash
kubectl get elasticsearch -n logging
kubectl describe elasticsearch eco2-logs -n logging | grep -A5 'Status:'
```

### 노드 리소스 확인

```bash
kubectl top node k8s-logging
```

### 도메인 로그 레벨 확인

```bash
kubectl get configmap -n auth auth-config -o yaml | grep LOG_LEVEL
```
