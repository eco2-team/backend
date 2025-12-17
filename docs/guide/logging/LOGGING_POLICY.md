# ECO2 Backend Logging Policy

> **Version**: 1.1.0  
> **Last Updated**: 2025-12-17  
> **Status**: Active

## 목차

1. [개요](#개요)
2. [로깅 원칙](#로깅-원칙)
3. [로그 포맷 표준](#로그-포맷-표준)
4. [로그 레벨 가이드라인](#로그-레벨-가이드라인)
5. [도메인별 로깅 스코프](#도메인별-로깅-스코프)
6. [트레이싱 연동](#트레이싱-연동)
7. [민감 정보 처리](#민감-정보-처리)
8. [성능 고려사항](#성능-고려사항)
9. [구현 가이드](#구현-가이드)
10. [구현 현황](#구현-현황)

---

## 개요

### 목적

이 문서는 ECO2 Backend 마이크로서비스의 로깅 표준과 정책을 정의합니다.

### 적용 범위

| 서비스 | 언어 | 정책 적용 | ECS 로깅 구현 |
|--------|------|----------|--------------|
| auth-api | Python/FastAPI | ✅ | ✅ 완료 |
| character-api | Python/FastAPI | ✅ | ⏳ 예정 |
| chat-api | Python/FastAPI | ✅ | ⏳ 예정 |
| scan-api | Python/FastAPI | ✅ | ⏳ 예정 |
| location-api | Python/FastAPI | ✅ | ⏳ 예정 |
| my-api | Python/FastAPI | ✅ | ⏳ 예정 |
| image-api | Python/FastAPI | ✅ | ⏳ 예정 |
| ext-authz | Go/gRPC | ✅ | ⏳ 예정 |

### 로깅 스택

```
┌─────────────────────────────────────────────────────────────┐
│                        Kibana                                │
│                    (시각화/분석)                              │
├─────────────────────────────────────────────────────────────┤
│                     Elasticsearch                            │
│                    (저장/인덱싱)                              │
├─────────────────────────────────────────────────────────────┤
│                      Fluent Bit                              │
│                    (수집/전송)                                │
├─────────────────────────────────────────────────────────────┤
│  auth-api │ character-api │ chat-api │ ... │ ext-authz      │
│                    (로그 생성)                                │
└─────────────────────────────────────────────────────────────┘
```

---

## 로깅 원칙

### 1. 구조화된 로깅 (Structured Logging)

- **JSON 포맷** 사용 필수
- 텍스트 로그 대신 키-값 쌍으로 구성
- 파싱/검색/필터링 용이성 확보

### 2. 컨텍스트 풍부화 (Context Enrichment)

- 모든 로그에 **trace_id**, **span_id** 포함
- 요청별 **request_id** 추적
- 사용자/세션 정보 포함 (가능한 경우)

### 3. 일관성 (Consistency)

- 전체 서비스에서 동일한 로그 포맷 사용
- 표준화된 필드명 사용
- 동일한 로그 레벨 기준 적용

### 4. 적정성 (Appropriateness)

- 과도한 로깅 지양 (성능 영향)
- 불필요한 DEBUG 로그 프로덕션 비활성화
- 의미 있는 정보만 로깅

---

## 로그 포맷 표준

### 필수 필드

```json
{
  "timestamp": "2025-12-17T09:15:30.123456Z",
  "level": "INFO",
  "service": "auth-api",
  "version": "0.7.3",
  "environment": "dev",
  "message": "User login successful",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "request_id": "req-abc123-def456"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `timestamp` | string (ISO 8601) | ✅ | 로그 발생 시간 (UTC) |
| `level` | string | ✅ | 로그 레벨 |
| `service` | string | ✅ | 서비스명 |
| `version` | string | ✅ | 서비스 버전 |
| `environment` | string | ✅ | 환경 (dev/staging/prod) |
| `message` | string | ✅ | 로그 메시지 |
| `trace_id` | string | ✅ | OpenTelemetry Trace ID |
| `span_id` | string | ✅ | OpenTelemetry Span ID |
| `request_id` | string | ✅ | 요청 고유 ID |

### 선택 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `user_id` | string | 인증된 사용자 ID |
| `session_id` | string | 세션 ID |
| `method` | string | HTTP 메서드 |
| `path` | string | 요청 경로 |
| `status_code` | integer | HTTP 응답 코드 |
| `duration_ms` | float | 처리 시간 (밀리초) |
| `error` | object | 에러 정보 |
| `extra` | object | 추가 컨텍스트 |

### 에러 로그 포맷

```json
{
  "timestamp": "2025-12-17T09:15:30.123456Z",
  "level": "ERROR",
  "service": "auth-api",
  "message": "Database connection failed",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "request_id": "req-abc123-def456",
  "error": {
    "type": "ConnectionError",
    "message": "Connection refused",
    "stack_trace": "Traceback (most recent call last):\n  File...",
    "code": "DB_CONNECTION_ERROR"
  }
}
```

---

## 로그 레벨 가이드라인

### 레벨 정의

| Level | 값 | 설명 | 프로덕션 활성화 |
|-------|---|------|----------------|
| **DEBUG** | 10 | 상세 디버깅 정보 | ❌ |
| **INFO** | 20 | 정상 운영 정보 | ✅ |
| **WARNING** | 30 | 잠재적 문제 | ✅ |
| **ERROR** | 40 | 오류 발생 | ✅ |
| **CRITICAL** | 50 | 심각한 오류 | ✅ |

### 레벨별 사용 가이드

#### DEBUG
```python
# ✅ 적절한 사용
logger.debug("Processing request", extra={"payload_size": len(data)})
logger.debug("Cache lookup", extra={"key": cache_key, "hit": cache_hit})

# ❌ 피해야 할 사용
logger.debug(f"Full payload: {payload}")  # 민감 정보 노출 가능
```

#### INFO
```python
# ✅ 적절한 사용
logger.info("User login successful", extra={"user_id": user.id, "provider": "kakao"})
logger.info("Character created", extra={"character_id": char.id, "user_id": user.id})
logger.info("Request completed", extra={"path": path, "status": 200, "duration_ms": 45.2})

# ❌ 피해야 할 사용
logger.info("Entering function foo")  # DEBUG 레벨 사용
```

#### WARNING
```python
# ✅ 적절한 사용
logger.warning("Rate limit approaching", extra={"current": 95, "limit": 100})
logger.warning("Retry attempt", extra={"attempt": 2, "max_retries": 3})
logger.warning("Deprecated API used", extra={"endpoint": "/v1/old", "suggested": "/v2/new"})
```

#### ERROR
```python
# ✅ 적절한 사용
logger.error("Database query failed", extra={
    "error_type": type(e).__name__,
    "error_message": str(e),
    "query": "SELECT * FROM users WHERE id = ?"
}, exc_info=True)

logger.error("External API call failed", extra={
    "service": "kakao-oauth",
    "status_code": 500,
    "response_time_ms": 3000
})
```

#### CRITICAL
```python
# ✅ 적절한 사용
logger.critical("Database connection pool exhausted", extra={
    "pool_size": 10,
    "active_connections": 10,
    "waiting_requests": 50
})

logger.critical("Service startup failed", extra={
    "reason": "Missing required configuration",
    "missing_vars": ["DATABASE_URL", "REDIS_URL"]
})
```

---

## 도메인별 로깅 스코프

### auth-api

| 이벤트 | 레벨 | 필수 필드 |
|--------|------|----------|
| OAuth 로그인 시작 | INFO | `provider`, `state` |
| OAuth 콜백 성공 | INFO | `provider`, `user_id` |
| OAuth 콜백 실패 | ERROR | `provider`, `error_type`, `error_message` |
| 토큰 발급 | INFO | `user_id`, `token_type` |
| 토큰 갱신 | INFO | `user_id` |
| 토큰 검증 실패 | WARNING | `reason`, `token_prefix` |
| 로그아웃 | INFO | `user_id` |

```python
# 예시
logger.info("OAuth login initiated", extra={
    "provider": "kakao",
    "state": state[:8] + "...",
    "redirect_uri": redirect_uri
})

logger.info("Token issued", extra={
    "user_id": user.id,
    "token_type": "access",
    "expires_in": 3600
})
```

### character-api

| 이벤트 | 레벨 | 필수 필드 |
|--------|------|----------|
| 캐릭터 생성 | INFO | `character_id`, `user_id`, `type` |
| 캐릭터 업데이트 | INFO | `character_id`, `updated_fields` |
| 경험치 획득 | INFO | `character_id`, `exp_gained`, `new_level` |
| 레벨업 | INFO | `character_id`, `old_level`, `new_level` |

### chat-api

| 이벤트 | 레벨 | 필수 필드 |
|--------|------|----------|
| 채팅 세션 시작 | INFO | `session_id`, `user_id` |
| 메시지 전송 | INFO | `session_id`, `message_length` |
| AI 응답 생성 | INFO | `session_id`, `response_time_ms`, `token_count` |
| AI 응답 실패 | ERROR | `session_id`, `error_type` |

### scan-api

| 이벤트 | 레벨 | 필수 필드 |
|--------|------|----------|
| 이미지 업로드 | INFO | `image_size`, `content_type` |
| 분석 시작 | INFO | `scan_id`, `scan_type` |
| 분석 완료 | INFO | `scan_id`, `result_category`, `confidence` |
| 분석 실패 | ERROR | `scan_id`, `error_type` |

### ext-authz (Go)

| 이벤트 | 레벨 | 필수 필드 |
|--------|------|----------|
| 인증 요청 | DEBUG | `path`, `method` |
| 인증 성공 | INFO | `user_id`, `path` |
| 인증 실패 | WARNING | `path`, `reason` |
| JWT 검증 실패 | WARNING | `reason`, `token_prefix` |

---

## 트레이싱 연동

### OpenTelemetry 통합

Istio 서비스 메시에서 전파되는 트레이스 컨텍스트를 로그에 포함:

```python
from opentelemetry import trace

def get_trace_context():
    """현재 트레이스 컨텍스트 추출"""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    
    return {
        "trace_id": format(ctx.trace_id, '032x') if ctx.trace_id else None,
        "span_id": format(ctx.span_id, '016x') if ctx.span_id else None,
    }
```

### 헤더 전파

Istio/Envoy가 전파하는 헤더:

| 헤더 | 설명 |
|------|------|
| `x-request-id` | Envoy 생성 요청 ID |
| `x-b3-traceid` | Zipkin B3 Trace ID |
| `x-b3-spanid` | Zipkin B3 Span ID |
| `traceparent` | W3C Trace Context |
| `tracestate` | W3C Trace State |

### Jaeger 연동

로그의 `trace_id`로 Jaeger UI에서 해당 트레이스 조회 가능:

```
https://jaeger.dev.growbin.app/trace/{trace_id}
```

---

## 민감 정보 처리

### 자동 마스킹 대상 (OWASP 기준)

로그 출력 시 다음 필드명을 포함하는 키는 **자동 마스킹**됩니다:

| 패턴 | 매칭 예시 | 설명 |
|------|----------|------|
| `password` | `password`, `user_password` | 비밀번호 |
| `secret` | `jwt_secret_key`, `client_secret` | 비밀 키 |
| `token` | `token`, `access_token`, `refresh_token` | 인증 토큰 |
| `api_key` | `api_key`, `OPENAI_API_KEY` | 외부 API 키 |
| `authorization` | `Authorization` 헤더 | HTTP 인증 헤더 |

> **참고**: OWASP Logging Cheat Sheet 기반, 실제 코드베이스에서 사용되는 패턴만 포함

### 마스킹 규칙

```python
# domains/*/core/constants.py
SENSITIVE_FIELD_PATTERNS = frozenset({
    "password", "secret", "token", "api_key", "authorization"
})

# 마스킹 설정
MASK_PLACEHOLDER = "***REDACTED***"
MASK_PRESERVE_PREFIX = 4  # 앞 4자 유지
MASK_PRESERVE_SUFFIX = 4  # 뒤 4자 유지
MASK_MIN_LENGTH = 10      # 최소 길이 (이하면 전체 마스킹)
```

### 마스킹 예시

```json
{
  "message": "OAuth callback received",
  "labels": {
    "access_token": "eyJh...abc1",
    "refresh_token": "eyJh...xyz9",
    "user_id": "usr-123"
  }
}
```

| 원본 값 | 마스킹 결과 | 규칙 |
|---------|------------|------|
| `eyJhbGciOiJIUzI1NiJ9.abc123` | `eyJh...c123` | 부분 마스킹 (길이 > 10) |
| `short123` | `***REDACTED***` | 전체 마스킹 (길이 <= 10) |
| `null` | `***REDACTED***` | null 값 |

### 구현 (ECSJsonFormatter 내장)

```python
# domains/*/core/logging.py
def mask_sensitive_data(data: dict[str, Any]) -> dict[str, Any]:
    """재귀적으로 민감 필드 마스킹"""
    if not isinstance(data, dict):
        return data
    result = {}
    for key, value in data.items():
        if _is_sensitive_key(key):
            result[key] = _mask_value(value)
        elif isinstance(value, dict):
            result[key] = mask_sensitive_data(value)
        elif isinstance(value, list):
            result[key] = [
                mask_sensitive_data(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result
```

### 절대 로깅 금지 항목

자동 마스킹과 별개로, 아래 항목은 **로그에 포함하지 않도록** 코드 레벨에서 주의:

| 항목 | 예시 |
|------|------|
| 개인정보 (PII) | 주민번호, 전화번호, 실명 |
| 금융정보 | 신용카드, 계좌번호 |
| 건강정보 | 의료 기록 |

---

## 성능 고려사항

### 로깅 오버헤드 최소화

1. **비동기 로깅**
   - 로그 I/O를 별도 스레드에서 처리
   - 메인 요청 처리 차단 방지

2. **로그 레벨 게이팅**
   ```python
   # ✅ 좋은 예: 레벨 체크 후 로깅
   if logger.isEnabledFor(logging.DEBUG):
       logger.debug("Expensive computation", extra={"result": expensive_fn()})
   
   # ❌ 나쁜 예: 항상 연산 수행
   logger.debug("Expensive computation", extra={"result": expensive_fn()})
   ```

3. **샘플링**
   - 고빈도 이벤트는 샘플링 적용
   - 예: Health check 로그 10%만 기록

### 버퍼링

```yaml
# Fluent Bit 버퍼 설정
[INPUT]
    Name              tail
    Mem_Buf_Limit     50MB  # 메모리 버퍼 제한
    
[OUTPUT]
    Name            es
    Buffer_Size     5MB   # 출력 버퍼
```

### 로그 볼륨 관리

| 환경 | 기본 레벨 | 예상 볼륨 |
|------|----------|----------|
| Development | DEBUG | ~100 MB/day |
| Staging | INFO | ~50 MB/day |
| Production | INFO | ~200 MB/day |

---

## 구현 가이드

### Python (FastAPI) 구현

#### 1. 의존성 설치

```bash
pip install structlog python-json-logger opentelemetry-api
```

#### 2. 로거 설정

```python
# domains/_shared/logging/config.py
import structlog
import logging
from pythonjsonlogger import jsonlogger

def configure_logging(service_name: str, version: str, environment: str):
    """구조화된 로깅 설정"""
    
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # 기본 컨텍스트 바인딩
    structlog.contextvars.bind_contextvars(
        service=service_name,
        version=version,
        environment=environment,
    )
```

#### 3. 미들웨어

```python
# domains/_shared/logging/middleware.py
from starlette.middleware.base import BaseHTTPMiddleware
from opentelemetry import trace
import structlog
import uuid
import time

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # 트레이스 컨텍스트 추출
        span = trace.get_current_span()
        ctx = span.get_span_context()
        
        # 요청 ID (Istio에서 전달되거나 새로 생성)
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        
        # 로깅 컨텍스트 바인딩
        structlog.contextvars.bind_contextvars(
            trace_id=format(ctx.trace_id, '032x') if ctx.trace_id else None,
            span_id=format(ctx.span_id, '016x') if ctx.span_id else None,
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        
        start_time = time.perf_counter()
        
        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            logger = structlog.get_logger()
            logger.info(
                "Request completed",
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2)
            )
            
            return response
        finally:
            structlog.contextvars.unbind_contextvars(
                "trace_id", "span_id", "request_id", "method", "path"
            )
```

#### 4. 사용 예시

```python
# domains/auth/services/auth.py
import structlog

logger = structlog.get_logger()

async def login_with_oauth(provider: str, code: str):
    logger.info("OAuth login started", provider=provider)
    
    try:
        user = await oauth_service.authenticate(provider, code)
        logger.info("OAuth login successful", 
                   user_id=user.id, 
                   provider=provider)
        return user
    except OAuthError as e:
        logger.error("OAuth login failed",
                    provider=provider,
                    error_type=type(e).__name__,
                    error_message=str(e))
        raise
```

### Go (ext-authz) 구현

```go
// pkg/logging/logger.go
package logging

import (
    "go.uber.org/zap"
    "go.uber.org/zap/zapcore"
)

func NewLogger(service, version, environment string) *zap.Logger {
    config := zap.NewProductionConfig()
    config.EncoderConfig.TimeKey = "timestamp"
    config.EncoderConfig.EncodeTime = zapcore.ISO8601TimeEncoder
    
    logger, _ := config.Build(
        zap.Fields(
            zap.String("service", service),
            zap.String("version", version),
            zap.String("environment", environment),
        ),
    )
    
    return logger
}
```

---

## 구현 현황

### 구현 방식

각 도메인에서 **독립적으로** 로깅 모듈을 구현합니다 (공통 모듈 미사용).

```
domains/
├── auth/
│   └── core/logging.py      ✅ 구현 완료
├── character/
│   └── core/logging.py      ⏳ 예정
├── chat/
│   └── core/logging.py      ⏳ 예정
└── ...
```

### 구현 파일 구조

```python
# domains/{service}/core/logging.py
- ECSJsonFormatter: ECS 기반 JSON 포매터
- configure_logging(): 로깅 설정 함수

# domains/{service}/main.py
from domains.{service}.core.logging import configure_logging
configure_logging(service_name="{service}-api", service_version="x.x.x")
```

### auth-api 구현 예시

```python
# domains/auth/core/logging.py
class ECSJsonFormatter(logging.Formatter):
    """Elastic Common Schema 기반 JSON 포매터"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "@timestamp": datetime.now(timezone.utc).isoformat(),
            "message": record.getMessage(),
            "log.level": record.levelname.lower(),
            "log.logger": record.name,
            "service.name": self.service_name,
            "service.version": self.service_version,
            "service.environment": self.environment,
        }
        
        # OpenTelemetry trace context
        if HAS_OPENTELEMETRY:
            span = trace.get_current_span()
            ctx = span.get_span_context()
            if ctx.is_valid:
                log_obj["trace.id"] = format(ctx.trace_id, "032x")
                log_obj["span.id"] = format(ctx.span_id, "016x")
        
        return json.dumps(log_obj)
```

### 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `LOG_LEVEL` | `INFO` | 로그 레벨 (DEBUG, INFO, WARNING, ERROR) |
| `LOG_FORMAT` | `json` | 로그 포맷 (json, text) |
| `ENVIRONMENT` | `dev` | 환경 (dev, staging, prod) |

---

## 참고 자료

- [OpenTelemetry Python Documentation](https://opentelemetry.io/docs/languages/python/)
- [Elastic Common Schema Reference](https://www.elastic.co/guide/en/ecs/current/ecs-reference.html)
- [Kubernetes Logging Best Practices](https://kubernetes.io/docs/concepts/cluster-administration/logging/)
- [Istio Distributed Tracing](https://istio.io/latest/docs/tasks/observability/distributed-tracing/)
- [LOGGING_BEST_PRACTICES.md](./LOGGING_BEST_PRACTICES.md) - 빅테크/CNCF 벤더 사례

---

## 변경 이력

| 버전 | 날짜 | 변경 내용 | 작성자 |
|------|------|----------|--------|
| 1.0.0 | 2025-12-17 | 초기 문서 작성 | - |
| 1.1.0 | 2025-12-17 | 구현 현황 추가, auth-api ECS 로깅 적용 | - |
