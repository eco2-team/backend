# SSE 파이프라인 병목 분석 (2025-12-26 18:03:43 ~ 18:05:46)

## 개요

Redis Streams 기반 SSE 마이그레이션 후 첫 부하 테스트에서 발견된 병목 지점 분석.

**테스트 환경:**
- 시간: 2025-12-26 18:03:43 ~ 18:05:46 (약 2분)
- k6 VU: 50
- 엔드포인트: `/api/v1/classify/completion` (SSE)

---

## 1. SSE 핵심 지표

| 메트릭 | 값 | 평가 |
|--------|-----|------|
| Active Connections (max) | 9 | |
| Success | 251 | |
| Failed | 174 | 🔴 **실패율 41%** |

### Chain Duration (전체 파이프라인 소요)

| Percentile | 값 | 평가 |
|------------|-----|------|
| p50 | 8s | 🟡 |
| p95 | 35s | 🔴 |
| p99 | **51s** | 🔴 매우 높음 |

### TTFB (Time To First Byte)

| Percentile | 값 | 평가 |
|------------|-----|------|
| p50 | 5ms | ✅ |
| p95 | 10ms | ✅ |
| p99 | 19ms | ✅ |

**분석:** TTFB는 매우 양호 → Redis Streams 기반 이벤트 발행이 빠르게 동작함. 문제는 Chain Duration (OpenAI API 지연).

---

## 2. Redis 분석

### 연결 수 (Connected Clients)

| Redis 인스턴스 | Clients | Commands/sec | 용도 |
|----------------|---------|--------------|------|
| **cache-redis** | **890** | 446 | Celery 결과 백엔드 |
| streams-redis | 61 | 194 | SSE 이벤트 |
| auth-redis | 9 | 7 | JWT 블랙리스트 |

**🔴 병목 1: cache-redis 연결 폭발 (925 clients)**

**근본 원인: 유휴 연결 미정리 (Connection Pool Leak)**

```
CLIENT LIST 분석:
- 127.0.0.6 (Istio Proxy): 1,156 연결
- 대부분 cmd=unsubscribe, idle=2000초 이상
```

**발생 메커니즘:**
1. Celery `AsyncResult.get()` → Redis SUBSCRIBE로 결과 대기
2. 결과 수신 후 UNSUBSCRIBE 호출
3. **문제**: 연결이 풀에 반환되지 않고 idle 상태로 유지
4. Gevent greenlet 재사용 시 새 연결 생성 (기존 연결 미반환)

**Worker별 연결 가능 수:**
| Worker | Pods | Concurrency | 최대 연결 |
|--------|------|-------------|-----------|
| scan-worker | 3 | 100 | 300 |
| character-match-worker | 2 | 16 | 32 |
| character-worker | 1 | 20 | 20 |
| my-worker | 1 | ? | ~20 |
| **합계** | | | **~372** |

실제 925 연결 = 연결 풀 누수로 인한 누적

**해결 방안:**
1. Redis `timeout` 설정 (idle 연결 자동 정리)
2. Celery `result_backend_transport_options` 튜닝
3. `redis_socket_timeout`, `redis_socket_connect_timeout` 설정

### Redis Streams 상태

| 메트릭 | 값 |
|--------|-----|
| Stream Length (max) | 6,581 |
| Memory | 7MB |

**분석:** Streams 메모리 사용량은 적정. 이벤트가 빠르게 소비됨.

---

## 3. RabbitMQ 분석

### 메시지 처리율

| 메트릭 | 값 | 평가 |
|--------|-----|------|
| Publish Rate | **95.5 msg/sec** | 입력 |
| Deliver Rate | 21.4 msg/sec | 🔴 출력 (22%) |
| Ack Rate | 32.4 msg/sec | 처리 완료 |

**🔴 병목 2: Publish >> Deliver (4.5배 불균형)**

```
Publish: 95.5 msg/sec  ────┐
                           │ 차이 = 74 msg/sec (큐에 적체)
Deliver: 21.4 msg/sec  ────┘
```

- 메시지 발행 속도가 소비 속도보다 **4.5배** 빠름
- 2분간 약 8,880개 메시지 적체 발생
- 원인: OpenAI API 호출 지연으로 Worker 처리량 제한

### 큐별 메시지 상태 (max)

| Queue | Ready | Unacked | 합계 | 분석 |
|-------|-------|---------|------|------|
| scan.vision | 16 | **65** | 81 | 🔴 병목 (OpenAI Vision) |
| scan.rule | 0 | 2 | 2 | ✅ 빠름 (로컬 처리) |
| scan.answer | 18 | **31** | 49 | 🔴 병목 (OpenAI Answer) |
| scan.reward | 0 | 9 | 9 | ✅ 정상 |
| character.match | 0 | 1 | 1 | ✅ 정상 |
| character.reward | 0 | 7 | 7 | ✅ 정상 |

**분석:**
- **Unacked 높음** = Worker가 메시지를 가져갔지만 처리 중 (ACK 대기)
- vision (65) + answer (31) = 96개 메시지가 OpenAI API 응답 대기 중
- **병목 = OpenAI API 지연**, Worker 수 부족 아님

### Consumer 수 분석

| Queue | Consumers | Worker Pods | 분석 |
|-------|-----------|-------------|------|
| scan.vision | **1** | 3 | 🔴 불일치 |
| scan.answer | **1** | 3 | 🔴 불일치 |
| character.match | 3 | 2 | ✅ 정상 |

**🔴 병목 3: Consumer 수 불일치**

Worker Pod 3개인데 Consumer 1개인 이유:
1. **Gevent Pool 특성**: 100 greenlets가 1개 AMQP 연결 공유
2. **Celery prefetch**: 연결당 prefetch_count만큼만 가져옴
3. **결과**: 실제 동시 처리는 greenlet 수 (100)로 제한

```
Worker Pod 1 ──┬── 100 greenlets ──> 1 Consumer (prefetch=100)
Worker Pod 2 ──┼── 100 greenlets ──> 1 Consumer (prefetch=100)  
Worker Pod 3 ──┴── 100 greenlets ──> 1 Consumer (prefetch=100)
                                     ↓
                    총 3 Consumers, 300 동시 처리 가능
```

**실제 Consumer 1개인 이유**: 테스트 시점에 1개 Pod만 활성 상태였거나, 메트릭 수집 시점 차이

### RabbitMQ 리소스

| 메트릭 | 값 | 평가 |
|--------|-----|------|
| Connections | 61 | ✅ 정상 |
| Channels | 67 | ✅ 정상 |
| Memory | 189MB | ✅ 여유 |
| File Descriptors | 98 | ✅ 여유 |

---

## 4. Worker 리소스

| Pod | CPU (max) | Memory (max) |
|-----|-----------|--------------|
| scan-worker | **79%** | 213MB |
| scan-api | 9% | 104MB |

**분석:** Worker CPU 79%는 높아 보이지만, 대부분 I/O 대기 (OpenAI API). 실제 CPU 작업은 적음.

---

## 5. 노드 메모리

| 노드 | 메모리 | 추정 역할 |
|------|--------|-----------|
| 10.0.3.59 | **80%** | k8s-worker-ai |
| 10.0.3.246 | 71% | k8s-worker-storage |

---

## 6. 발견된 병목 지점 요약

### 🔴 Critical

1. **cache-redis 연결 누수** (925 clients, idle 2000s+)
   - **근본 원인**: Celery Redis 결과 백엔드 연결 미반환
   - **메커니즘**: UNSUBSCRIBE 후 연결이 풀에 반환되지 않음
   - **영향**: 메모리 증가, 연결 한도 도달 시 장애
   - **해결**: Redis timeout 설정, Celery 연결 풀 튜닝

2. **Chain Duration 지연** (p99: 51s)
   - **근본 원인**: OpenAI API 호출 지연 (Vision 15s + Answer 15s)
   - **영향**: SSE 타임아웃, 실패율 41%
   - **해결**: SSE timeout 60s → 120s, Streaming API 검토

3. **RabbitMQ Publish >> Deliver** (4.5배 불균형)
   - **근본 원인**: OpenAI API 지연으로 Worker 블로킹
   - **증거**: Unacked 96개 = API 응답 대기 중
   - **해결**: Worker 수 증가는 효과 제한적, API 최적화 필요

### 🟡 Warning

4. **노드 메모리 압박** (k8s-worker-ai: 80%)
   - 원인: scan-worker 3 pods + 시스템 pods
   - 해결: 노드 리소스 모니터링, 필요시 스케일아웃

---

## 7. 조치 사항

### 완료

| 조치 | 커밋 |
|------|------|
| KEDA cooldownPeriod 30s → 120s | `eefea2ee` |
| stabilizationWindowSeconds 120s → 300s | `eefea2ee` |
| Grafana 대시보드 라벨 수정 (job=rfr-*) | `eefea2ee` |
| ext-authz ServiceMonitor 추가 | `e922749c` |

### 예정

| 우선순위 | 조치 | 예상 효과 |
|----------|------|-----------|
| 🔴 높음 | cache-redis `timeout` 설정 (300s) | idle 연결 자동 정리 |
| 🔴 높음 | SSE timeout 60s → 120s | 실패율 감소 |
| 🟡 중간 | Celery `result_backend_transport_options` 튜닝 | 연결 풀 최적화 |
| 🟡 중간 | OpenAI Streaming API 검토 | Chain Duration 단축 |
| 🟢 낮음 | scan-worker min replica 1 → 2 | 초기 응답 속도 |

---

## 8. KEDA 스케일링 문제 해결

### 8.1 문제 1: 메트릭 수집 실패 (AMQP → HTTP)

**증상**: KEDA ScaledObject가 `ScalerNotActive` 상태, 메트릭이 항상 0

**원인**: 
- AMQP 프로토콜은 `messages_ready`만 측정
- Worker가 모든 메시지를 prefetch하여 ready=0

```yaml
# 변경 전 (AMQP)
triggers:
- type: rabbitmq
  metadata:
    protocol: amqp
    queueName: scan.vision

# 변경 후 (HTTP - ready + unacked 측정)
triggers:
- type: rabbitmq
  metadata:
    protocol: http
    host: http://admin:***@rabbitmq:15672
    queueName: scan.vision
    vhostName: eco2
```

### 8.2 문제 2: KEDA 내부 gRPC 통신 차단

**증상**: `timeout while waiting to establish gRPC connection to KEDA Metrics Service server`

**원인**: NetworkPolicy가 KEDA namespace 내부 통신(port 9666) 차단

**해결**:
```yaml
# allow-keda-egress.yaml
egress:
- to:
  - namespaceSelector:
      matchLabels:
        kubernetes.io/metadata.name: keda
  ports:
  - protocol: TCP
    port: 9666  # gRPC metrics service
```

### 8.3 문제 3: ArgoCD selfHeal과 KEDA 충돌

**증상**: 스케일업 직후 즉시 스케일다운 (1초 이내)

**원인**: ArgoCD `selfHeal: true`가 Git의 `replicas: 1`로 강제 동기화

**해결**:
```yaml
# 41-workers-appset.yaml
spec:
  template:
    spec:
      ignoreDifferences:
      - group: apps
        kind: Deployment
        jsonPointers:
        - /spec/replicas
```

### 8.4 최종 결과

| 지표 | 수정 전 | 수정 후 |
|------|---------|---------|
| Worker replicas | 1 (고정) | 1-5 (동적) |
| Consumer per queue | 1 | 3+ |
| 메트릭 수집 | 실패 (0) | 정상 (실시간) |
| 스케일업 유지 | ❌ (즉시 다운) | ✅ (5분 안정화) |

## 9. 관련 커밋

- `eefea2ee`: fix(monitoring): update Redis dashboard labels and KEDA tuning
- `e922749c`: feat(monitoring): add ext-authz ServiceMonitor for Prometheus metrics

---

## 9. OpenAI API 병목 최적화 방안

**현재 제약**: Structured JSON 응답 사용 → Streaming API 불가

### 현재 구현 분석

```python
# vision.py - 현재 구현
content_items.append({"type": "input_image", "image_url": image_url})
# ❌ detail 파라미터 미사용 (auto 기본값)
# ❌ 이미지 리사이즈 없이 원본 URL 전송
```

**프롬프트 토큰 분석:**
| 파일 | 크기 | 용도 |
|------|------|------|
| vision_classification_prompt.txt | 2,632 chars | 시스템 프롬프트 |
| item_class_list.yaml | 3,891 chars | 분류 체계 (전체 삽입) |
| situation_tags.yaml | 2,143 chars | 상황 태그 (전체 삽입) |
| **합계** | **~8,666 chars** | Vision 입력 |

### 🔴 즉시 적용 가능 (OpenAI 공식 문서 기반)

#### 1. Vision API `detail` 파라미터 활용

```python
# 현재 (auto)
{"type": "input_image", "image_url": image_url}

# 최적화 (low)
{
    "type": "input_image",
    "image_url": image_url,
    "detail": "low"  # 85 토큰 고정, 512x512 저해상도
}
```

**토큰 비용 비교 (gpt-4o 기준):**
| 이미지 크기 | detail: auto/high | detail: low | 절감 |
|-------------|-------------------|-------------|------|
| 1024x1024 | 765 tokens | **85 tokens** | 89% |
| 2048x2048 | 1,105 tokens | **85 tokens** | 92% |
| 4096x8192 | 2,380 tokens | **85 tokens** | 96% |

**적용 기준:**
- 대분류/중분류 판단: `low` 충분 (전체 형태 인식)
- 소분류/텍스트 인식: `high` 필요 (세부 식별)
- **권장**: 2단계 분류 (low로 대분류 → high로 소분류 필요시만)

#### 2. 이미지 전처리 (서버 사이드 리사이즈)

```python
# 최대 512x512로 리사이즈 (detail: low 최적화)
from PIL import Image
import io

def preprocess_image(image_bytes, max_size=512):
    img = Image.open(io.BytesIO(image_bytes))
    img.thumbnail((max_size, max_size), Image.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=85)
    return buffer.getvalue()
```

**예상 효과:**
- 네트워크 전송 시간 감소
- OpenAI 서버 처리 시간 감소
- 이미지 토큰 수 감소

#### 3. 프롬프트 토큰 최적화

| 최적화 | 현재 | 개선 | 절감 |
|--------|------|------|------|
| YAML 압축 | 6KB 전체 | 필수 필드만 | ~50% |
| 예시 제거 | 포함 | 제거 | ~20% |
| 중복 지시문 | 있음 | 통합 | ~10% |

```yaml
# 현재: 전체 분류 체계 삽입
item_class_list:
  재활용폐기물:
    플라스틱:
      - PET병
      - PE용기
      ...

# 최적화: 대분류 목록만 제공
major_categories: [재활용폐기물, 일반종량제폐기물, 음식물류폐기물, ...]
```

### 🟡 단기 적용 (1-2주)

| 방안 | 설명 | 예상 효과 |
|------|------|-----------|
| **max_tokens 제한** | 응답 길이 제한 | 생성 시간 단축 |
| **temperature 0 고정** | 결정적 출력 | 재시도 감소 |
| **응답 캐싱** | 이미지 해시 기반 | 중복 요청 제거 |

**응답 캐싱 구현:**
```python
import hashlib
from redis import Redis

def get_cached_or_analyze(image_url: str, redis: Redis):
    # 이미지 해시 계산
    image_hash = hashlib.sha256(image_url.encode()).hexdigest()[:16]
    cache_key = f"vision:{image_hash}"
    
    # 캐시 조회
    cached = redis.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # API 호출
    result = analyze_images(user_input, image_url)
    
    # 캐시 저장 (24시간)
    redis.setex(cache_key, 86400, json.dumps(result))
    return result
```

### 🟢 중기 검토 (1-2개월)

| 방안 | 설명 | 고려사항 |
|------|------|----------|
| **gpt-4o-mini 검토** | 경량 모델 | 정확도 테스트 필요 |
| **배치 API** | 비실시간 분석 | 비용 50% 절감, 24시간 내 결과 |
| **2단계 분류** | low → high 순차 | 복잡도 증가 |

### 아키텍처 수준

| 방안 | 설명 | 복잡도 |
|------|------|--------|
| **Vision + Answer 병렬화** | 독립 실행 후 병합 | 높음 (파이프라인 재설계) |
| **Predicted Output** | 예측 가능한 부분 사전 생성 | 중간 |

### 권장 우선순위 (수정)

1. **즉시 (오늘)**: 
   - `detail: "low"` 적용 (토큰 89% 절감)
   - max_tokens 설정
2. **단기 (이번 주)**: 
   - 이미지 전처리 (리사이즈)
   - 프롬프트 YAML 압축
3. **중기 (다음 주)**: 
   - 응답 캐싱 도입
   - temperature 0 고정
4. **장기 (검토)**: 
   - gpt-4o-mini 정확도 테스트
   - 배치 API 도입

---

## 10. 결론

**핵심 병목: OpenAI API 지연**

모든 문제의 근본 원인은 OpenAI API 호출 지연 (Vision + Answer = 30-50초):
1. Worker가 API 응답 대기 → RabbitMQ Unacked 증가
2. 응답 대기 중 Redis 연결 유지 → cache-redis 연결 누수
3. Chain Duration 증가 → SSE 타임아웃 → 실패율 41%

**이번 적용한 조치**:
| 조치 | 내용 | 예상 효과 |
|------|------|-----------|
| cache-redis timeout | 0 → 300초 | idle 연결 자동 정리 |
| Celery result_backend_transport_options | socket_timeout, health_check | 연결 풀 안정화 |
| Vision API `detail: "low"` | 토큰 89% 절감 | API 응답 시간 단축 |

**단기 해결책**: timeout 조정, 연결 풀 정리, Vision detail 최적화
**장기 해결책**: 이미지 전처리, 응답 캐싱, 프롬프트 압축

---

## 11. 커밋 히스토리

| 커밋 | 내용 |
|------|------|
| `eefea2ee` | fix(monitoring): update Redis dashboard labels and KEDA tuning |
| `e922749c` | feat(monitoring): add ext-authz ServiceMonitor |
| (예정) | perf(openai): add detail:low to Vision API for 89% token reduction |

