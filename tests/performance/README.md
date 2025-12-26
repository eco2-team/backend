# Performance Tests

## SSE 스트리밍 성능 테스트

### 테스트 대상

| 구성요소 | 설명 |
|---------|------|
| **Endpoint** | `POST /api/v1/scan/classify/completion` |
| **Pipeline** | vision → rule → answer → reward (4단계 Celery Chain) |
| **Worker** | scan-worker, character-match-worker, character-worker, my-worker |

### 실행 방법

```bash
# Web UI 모드
ACCESS_COOKIE="your-cookie" locust -f tests/performance/locustfile_sse.py \
    --host=https://api.dev.growbin.app

# Headless 모드 (동시 10명, 초당 2명, 60초)
ACCESS_COOKIE="your-cookie" locust -f tests/performance/locustfile_sse.py \
    --host=https://api.dev.growbin.app \
    --headless -u 10 -r 2 -t 60s

# 결과 저장
ACCESS_COOKIE="your-cookie" locust -f tests/performance/locustfile_sse.py \
    --host=https://api.dev.growbin.app \
    --headless -u 10 -r 2 -t 60s \
    --csv=sse-results --html=sse-report.html
```

### 측정 항목

| 지표 | 설명 | 목표 |
|-----|------|-----|
| **Total Time** | 전체 파이프라인 완료 시간 | < 30초 |
| **TTFB** | 첫 이벤트 수신까지 시간 | < 3초 |
| **Stage Completion** | 4단계 모두 완료 | 100% |
| **Failure %** | 실패율 | < 5% |

### 주의사항

- SSE는 오래 걸리므로 동시 사용자 수를 적게 설정 (10-20명 권장)
- OpenAI API 비용이 발생하므로 테스트 시간 제한 권장
- `ACCESS_COOKIE` 환경변수 필수

---

## ext-authz 부하 테스트

### 테스트 대상

| 구성요소 | 설명 |
|---------|------|
| **Endpoint** | `GET /api/v1/auth/ping` |
| **ext-authz (Go)** | Envoy sidecar에서 gRPC로 JWT 검증 수행 |
| **auth API (FastAPI)** | 검증 통과 후 간단한 JSON 응답 |

### 측정 항목

- ext-authz gRPC 서버 동시 처리 성능
- JWT 서명 검증 + Redis 블랙리스트 조회 지연
- Istio service mesh 인증 오버헤드

---

## 설치

```bash
pip install locust
```

## 토큰 획득

브라우저 로그인 후 개발자 도구에서 `access_token` 쿠키 복사:

```bash
export ACCESS_TOKEN="eyJhbGciOiJIUzI1NiIs..."
```

---

## 실행 방법

### 1. Web UI 모드

```bash
ACCESS_TOKEN="your-token" locust -f tests/performance/test_ext_authz.py \
    --host=https://api.dev.growbin.app
```

http://localhost:8089 접속

### 2. Headless 모드

```bash
# 기본 테스트: 100명, 초당 10명, 60초
ACCESS_TOKEN="your-token" locust -f tests/performance/test_ext_authz.py \
    --host=https://api.dev.growbin.app \
    --headless -u 100 -r 10 -t 60s

# 스트레스 테스트: 500명, 초당 50명, 2분
ACCESS_TOKEN="your-token" locust -f tests/performance/test_ext_authz.py \
    --host=https://api.dev.growbin.app \
    --headless -u 500 -r 50 -t 120s
```

### 3. 결과 저장

```bash
ACCESS_TOKEN="your-token" locust -f tests/performance/test_ext_authz.py \
    --host=https://api.dev.growbin.app \
    --headless -u 100 -r 10 -t 60s \
    --csv=ext-authz-results --html=ext-authz-report.html
```

---

## 결과 해석

| 지표 | 설명 | 목표 |
|-----|------|-----|
| **RPS** | 초당 요청 처리량 | > 500 |
| **p50** | 중간값 응답 시간 | < 50ms |
| **p95** | 95% 응답 시간 | < 200ms |
| **p99** | 99% 응답 시간 | < 500ms |
| **Failure %** | 실패율 | 0% |

---

## User Class

| Class | 대기 시간 | 용도 |
|-------|----------|------|
| `ExtAuthzPingUser` | 1~3초 | 일반 부하 테스트 |
| `ExtAuthzStressUser` | 0.1~0.3초 | 극한 스트레스 테스트 |

특정 클래스만 사용:

```bash
ACCESS_TOKEN="your-token" locust -f tests/performance/test_ext_authz.py \
    --host=https://api.dev.growbin.app \
    ExtAuthzStressUser
```
