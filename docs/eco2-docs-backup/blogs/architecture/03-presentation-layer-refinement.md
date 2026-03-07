# Clean Architecture #9: Presentation Layer 정제

> Presentation Layer의 gRPC 구조를 정제하고, 횡단 관심사를 인터셉터로 분리한 과정을 기록합니다.

---

## 1. 판단 기준

Presentation Layer 내부 폴더 구조를 결정할 때 적용한 판단 기준:

### 1.1 폴더 분리 기준

| 기준 | 질문 | 분리 조건 |
|------|------|----------|
| **역할 분리** | 이 파일의 책임은 무엇인가? | 서로 다른 책임 → 다른 폴더 |
| **변경 주기** | 언제 이 파일이 수정되는가? | 다른 시점에 변경 → 다른 폴더 |
| **생성 방식** | 수동 작성인가, 자동 생성인가? | 자동 생성 파일 → 별도 폴더 |
| **재사용성** | 여러 서비스에서 공유되는가? | 공유 가능 → 별도 폴더 |

### 1.2 gRPC 폴더 구조 결정

| 파일 종류 | 역할 | 변경 주기 | 생성 방식 | 재사용 | 결론 |
|-----------|------|----------|----------|--------|------|
| `*_pb2.py` | 메시지 정의 | proto 변경 시 | 자동 생성 | X | `protos/` |
| `*_pb2_grpc.py` | 서비스 스텁 | proto 변경 시 | 자동 생성 | X | `protos/` |
| `*_servicer.py` | 요청 처리 | 비즈니스 변경 시 | 수동 작성 | X | `servicers/` |
| `error_handler.py` | 예외 변환 | 정책 변경 시 | 수동 작성 | O | `interceptors/` |
| `logging.py` | 요청 로깅 | 정책 변경 시 | 수동 작성 | O | `interceptors/` |
| `server.py` | 서버 부트스트랩 | 설정 변경 시 | 수동 작성 | X | 루트 |

### 1.3 네이밍 결정: schemas vs protos

| 옵션 | 장점 | 단점 |
|------|------|------|
| `schemas/` | HTTP Pydantic과 일관성 | Protobuf와 Pydantic 혼동 |
| `protos/` | Protocol Buffers 명시적 | HTTP와 네이밍 불일치 |

**결론:** `protos/` 채택

- pb2 파일은 Pydantic이 아닌 **Protobuf 컴파일러 생성물**
- "자동 생성 파일"이라는 특성을 폴더명으로 표현
- HTTP의 `schemas/`는 Pydantic, gRPC의 `protos/`는 Protobuf로 명확히 구분

### 1.4 인터셉터 도입 기준

| 기준 | 질문 | 예시 |
|------|------|------|
| **중복** | 여러 메서드에 동일 패턴이 반복되는가? | try/except 에러 핸들링 |
| **횡단 관심사** | 비즈니스 로직과 분리 가능한가? | 로깅, 인증, 메트릭 |
| **재사용성** | 다른 서비스에서도 사용 가능한가? | 에러→status 변환 |
| **SRP** | Servicer가 여러 책임을 갖고 있는가? | 요청 처리 + 에러 변환 + 로깅 |

---

## 2. AS-IS 구조

```
presentation/grpc/
├── server.py
├── servicers/
│   └── users_servicer.py    ← try/except 중복, 에러 변환 책임 혼재
├── users_pb2.py             ← 자동 생성 파일이 루트에 혼재
└── users_pb2_grpc.py        ← 자동 생성 파일이 루트에 혼재
```

### 문제점

| 문제 | 설명 |
|------|------|
| **자동 생성 파일 혼재** | pb2 파일이 수동 작성 파일과 같은 레벨에 위치 |
| **try/except 중복** | 모든 메서드에 동일한 에러 핸들링 패턴 반복 |
| **책임 혼재** | Servicer가 요청 처리 + 에러 변환 + 로깅 모두 담당 |

**중복 패턴 예시:**

```python
async def GetOrCreateFromOAuth(self, request, context):
    try:
        # 비즈니스 로직
        ...
    except ValueError as e:
        logger.error("Invalid argument", extra={"error": str(e)})
        await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
    except Exception:
        logger.exception("Internal error")
        await context.abort(grpc.StatusCode.INTERNAL, "Internal server error")

async def GetUser(self, request, context):
    try:
        # 비즈니스 로직 (동일한 패턴 반복)
        ...
    except ValueError as e:
        # 중복...
```

---

## 3. TO-BE 구조

```
presentation/grpc/
├── server.py                ← 서버 부트스트랩 + 인터셉터 등록
├── protos/                  ← 자동 생성 파일 분리
│   ├── __init__.py
│   ├── users_pb2.py
│   └── users_pb2_grpc.py
├── servicers/               ← Thin Adapter (요청 처리만)
│   └── users_servicer.py
└── interceptors/            ← 횡단 관심사 분리
    ├── __init__.py
    ├── error_handler.py     ← 예외 → gRPC status 변환
    └── logging.py           ← 요청/응답 로깅
```

---

## 4. 인터셉터 구현

### 4.1 ErrorHandlerInterceptor

예외를 gRPC status code로 변환:

```python
class ErrorHandlerInterceptor(grpc.aio.ServerInterceptor):
    """예외를 gRPC status로 변환하는 인터셉터."""

    async def intercept_service(self, continuation, handler_call_details):
        handler = await continuation(handler_call_details)
        if handler.unary_unary:
            return grpc.unary_unary_rpc_method_handler(
                self._wrap_unary_unary(handler.unary_unary),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )
        return handler

    def _wrap_unary_unary(self, behavior):
        async def wrapper(request, context):
            try:
                return await behavior(request, context)
            except ValueError as e:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
            except KeyError as e:
                await context.abort(grpc.StatusCode.NOT_FOUND, str(e))
            except PermissionError as e:
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, str(e))
            except Exception:
                await context.abort(grpc.StatusCode.INTERNAL, "Internal server error")
        return wrapper
```

### 4.2 LoggingInterceptor

요청/응답 로깅:

```python
class LoggingInterceptor(grpc.aio.ServerInterceptor):
    """요청/응답 로깅 인터셉터."""

    def _wrap_unary_unary(self, behavior, method):
        async def wrapper(request, context):
            start_time = time.perf_counter()

            logger.debug("gRPC request started", extra={"method": method})

            try:
                response = await behavior(request, context)
                elapsed_ms = (time.perf_counter() - start_time) * 1000

                logger.info(
                    "gRPC request completed",
                    extra={"method": method, "elapsed_ms": round(elapsed_ms, 2)},
                )
                return response

            except Exception as e:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.warning(
                    "gRPC request failed",
                    extra={"method": method, "elapsed_ms": round(elapsed_ms, 2)},
                )
                raise
        return wrapper
```

### 4.3 예외 → gRPC Status 매핑

| Python 예외 | gRPC Status Code | 의미 |
|-------------|------------------|------|
| `ValueError` | `INVALID_ARGUMENT` | 잘못된 요청 파라미터 |
| `KeyError` | `NOT_FOUND` | 리소스 없음 |
| `PermissionError` | `PERMISSION_DENIED` | 권한 부족 |
| `NotImplementedError` | `UNIMPLEMENTED` | 미구현 기능 |
| `Exception` | `INTERNAL` | 서버 내부 오류 |

---

## 5. 인터셉터 등록

```python
# server.py
interceptors = [
    LoggingInterceptor(),      # 1. 요청/응답 로깅 (먼저 실행)
    ErrorHandlerInterceptor(), # 2. 예외 → gRPC status 변환
]

server = grpc.aio.server(
    futures.ThreadPoolExecutor(max_workers=settings.grpc_max_workers),
    interceptors=interceptors,
)
```

**실행 순서:**

```
Request → LoggingInterceptor → ErrorHandlerInterceptor → Servicer
                ↓                        ↓                    ↓
              로깅                   예외 캐치           비즈니스 로직
```

---

## 6. Servicer 간소화

**AS-IS:**

```python
async def GetOrCreateFromOAuth(self, request, context):
    try:
        dto = OAuthUserRequest(...)
        async with self._session_factory() as session:
            command = self._use_case_factory.create_get_or_create_from_oauth_command(session)
            result = await command.execute(dto)
            await session.commit()
        return GetOrCreateFromOAuthResponse(...)
    except ValueError as e:
        logger.error("Invalid argument", extra={"error": str(e)})
        await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
    except Exception:
        logger.exception("Internal error")
        await context.abort(grpc.StatusCode.INTERNAL, "Internal server error")
```

**TO-BE:**

```python
async def GetOrCreateFromOAuth(self, request, context):
    # try/except 없이 비즈니스 로직만
    dto = OAuthUserRequest(...)
    async with self._session_factory() as session:
        command = self._use_case_factory.create_get_or_create_from_oauth_command(session)
        result = await command.execute(dto)
        await session.commit()
    return GetOrCreateFromOAuthResponse(...)
```

**변화:**

| 항목 | AS-IS | TO-BE |
|------|-------|-------|
| 코드 라인 | ~15줄 | ~8줄 |
| 책임 | 요청 처리 + 에러 변환 + 로깅 | 요청 처리만 |
| 테스트 | 에러 케이스도 테스트 필요 | 비즈니스 로직만 테스트 |

---

## 7. 요약

| 원칙 | 적용 |
|------|------|
| 자동 생성 파일은 별도 폴더 | `protos/` |
| 횡단 관심사는 인터셉터로 | `interceptors/` |
| Servicer는 비즈니스 로직만 | try/except 제거 |
| Protobuf는 `protos/` 네이밍 | Pydantic `schemas/`와 구분 |
| 에러 변환은 매핑 테이블로 | Python 예외 → gRPC Status |

