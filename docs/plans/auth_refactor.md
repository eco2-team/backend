# Auth Service Clean Architecture Refactoring Plan

## 목표

`fastapi-clean-example` 패턴을 참고하여 Auth 서비스를 Clean Architecture로 리팩토링한다.

- 참고: https://github.com/ivan-borovets/fastapi-clean-example

## 목표 구조

```
domains/auth/
├── domain/                              # 도메인 레이어
│   ├── entities/                        # 엔티티 (ID 있음)
│   │   ├── user.py
│   │   ├── user_social_account.py
│   │   └── login_audit.py
│   ├── value_objects/                   # 값 객체 (ID 없음, 선택적)
│   │   └── token_payload.py             # 현재 core/jwt.py의 TokenPayload
│   ├── services/                        # 도메인 서비스 (선택적)
│   └── exceptions.py                    # 도메인 예외
│
├── application/                         # 애플리케이션 레이어
│   ├── commands/                        # Write 연산 (CQRS)
│   │   ├── login.py                     # OAuth 로그인
│   │   ├── logout.py                    # 로그아웃
│   │   └── refresh_token.py             # 토큰 갱신
│   ├── queries/                         # Read 연산 (CQRS)
│   │   ├── get_user.py
│   │   └── get_metrics.py
│   ├── common/
│   │   ├── ports/                       # 인터페이스
│   │   │   ├── outbox.py
│   │   │   └── user_repository.py       # Repository 인터페이스
│   │   └── services/                    # 공통 서비스
│   │       └── authorization.py
│   └── dto/                             # 현재 schemas/
│       ├── auth.py
│       └── oauth.py
│
├── infrastructure/                      # 인프라 레이어
│   ├── persistence/                     # DB 관련
│   │   ├── database.py                  # 현재 database/
│   │   └── repositories/                # Repository 구현체
│   │       ├── user_repository.py
│   │       └── login_audit_repository.py
│   ├── adapters/                        # Port 구현체
│   │   ├── redis_outbox.py              # 현재 messaging/
│   │   └── rabbitmq_publisher.py
│   ├── auth/                            # 인증 인프라
│   │   ├── jwt.py                       # 현재 core/jwt.py
│   │   └── security.py                  # 현재 core/security.py
│   └── redis/                           # Redis 클라이언트
│       └── client.py
│
├── presentation/                        # 프레젠테이션 레이어
│   └── http/
│       ├── controllers/                 # 현재 api/v1/endpoints/
│       │   ├── auth.py
│       │   ├── health.py
│       │   └── metrics.py
│       ├── middleware/
│       └── errors/                      # HTTP 에러 핸들링
│           └── handlers.py
│
├── setup/                               # 설정 및 부트스트랩
│   ├── config/
│   │   └── settings.py                  # 현재 core/config.py
│   ├── ioc/                             # DI 설정 (선택적)
│   ├── logging.py
│   └── tracing.py
│
├── workers/                             # 백그라운드 작업
│   ├── blacklist_relay.py
│   └── init_db.py
│
├── tests/
└── main.py                              # 엔트리포인트
```

## 현재 구조와의 매핑

| 현재 위치 | 목표 위치 | 비고 |
|-----------|-----------|------|
| `domain/models/` | `domain/entities/` | 이름 변경 |
| `core/jwt.py (TokenPayload)` | `domain/value_objects/token_payload.py` | 값 객체 분리 |
| `core/exceptions.py` | `domain/exceptions.py` + `presentation/http/errors/` | 분리 |
| `application/services/auth.py` | `application/commands/` + `application/queries/` | CQRS 분리 |
| `application/ports/` | `application/common/ports/` | 경로 변경 |
| `application/schemas/` | `application/dto/` | 이름 변경 |
| `infrastructure/database/` | `infrastructure/persistence/` | 이름 변경 |
| `infrastructure/messaging/` | `infrastructure/adapters/` | 이름 변경 |
| `infrastructure/repositories/` | `infrastructure/persistence/repositories/` | 하위로 이동 |
| `core/jwt.py, security.py` | `infrastructure/auth/` | 인프라로 이동 |
| `api/v1/endpoints/` | `presentation/http/controllers/` | 경로 변경 |
| `core/config.py` | `setup/config/settings.py` | 경로 변경 |
| `core/logging.py, tracing.py` | `setup/` | 경로 변경 |

## 리팩토링 우선순위

| 순서 | 작업 | 영향도 | 복잡도 | 상태 |
|------|------|--------|--------|------|
| 1 | `core/` → `setup/` + `infrastructure/auth/` 분리 | 높음 | 중간 | ⬜ |
| 2 | `api/` → `presentation/http/controllers/` | 낮음 | 낮음 | ⬜ |
| 3 | `application/ports/` → `application/common/ports/` | 낮음 | 낮음 | ⬜ |
| 4 | `domain/models/` → `domain/entities/` | 낮음 | 낮음 | ⬜ |
| 5 | `infrastructure/` 재구성 | 중간 | 중간 | ⬜ |
| 6 | CQRS 도입 (services → commands/queries) | 높음 | 높음 | ⬜ |
| 7 | Repository 인터페이스 추가 | 중간 | 중간 | ⬜ |

## 의존성 흐름

```
┌─────────────────────────────────────────────────────────────────┐
│                      Presentation Layer                          │
│  (HTTP Controllers, Middleware, Error Handlers)                  │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Application Layer                           │
│  (Commands, Queries, DTOs, Ports)                                │
└─────────────────────────────┬───────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────────────┐
│      Domain Layer       │     │     Infrastructure Layer         │
│  (Entities, Value       │◄────│  (Adapters, Persistence,         │
│   Objects, Services)    │     │   Auth, Redis)                   │
└─────────────────────────┘     └─────────────────────────────────┘
```

---

## Python/FastAPI Clean Architecture 지원 도구

### 1. Dependency Injection 라이브러리

#### Dishka (권장)
- **GitHub**: https://github.com/reagento/dishka
- **특징**:
  - 현대적인 async-first DI 컨테이너
  - FastAPI 통합 지원
  - Scope 관리 (App, Request, Action)
  - `fastapi-clean-example`에서 사용
- **장점**: 타입 힌트 기반, 간결한 API, 비동기 지원
- **단점**: 상대적으로 신규 (커뮤니티 작음)

```python
from dishka import Provider, Scope, provide
from dishka.integrations.fastapi import setup_dishka

class AppProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_user_repository(self, session: AsyncSession) -> UserRepository:
        return UserRepositoryImpl(session)
```

#### dependency-injector
- **GitHub**: https://github.com/ets-labs/python-dependency-injector
- **특징**:
  - 가장 오래되고 안정적인 Python DI 라이브러리
  - 다양한 프레임워크 통합
  - 풍부한 문서와 예제
- **장점**: 안정성, 큰 커뮤니티, 풍부한 기능
- **단점**: 설정이 verbose함

```python
from dependency_injector import containers, providers

class Container(containers.DeclarativeContainer):
    user_repository = providers.Factory(
        UserRepositoryImpl,
        session=providers.Dependency(),
    )
```

#### Lagom
- **GitHub**: https://github.com/meadsteve/lagom
- **특징**: 경량, 타입 기반 자동 해결
- **장점**: 간단함, 자동 의존성 해결
- **단점**: 기능이 제한적

#### punq
- **GitHub**: https://github.com/bobthemighty/punq
- **특징**: 매우 경량, 심플한 API
- **장점**: 학습 곡선 낮음
- **단점**: 고급 기능 부족

### 2. 비교표

| 라이브러리 | Stars | Async | FastAPI | 복잡도 | 추천 |
|-----------|-------|-------|---------|--------|------|
| dishka | ~400 | ✅ Native | ✅ | 낮음 | ⭐⭐⭐ |
| dependency-injector | 3.5k+ | ✅ | ✅ | 높음 | ⭐⭐ |
| lagom | ~300 | ✅ | ⬜ | 낮음 | ⭐ |
| punq | ~200 | ⬜ | ⬜ | 매우 낮음 | - |

### 3. FastAPI 내장 DI vs 외부 라이브러리

**FastAPI 내장 Depends()의 한계:**
- 글로벌 상태 관리 어려움 (싱글톤)
- 복잡한 의존성 그래프 관리 어려움
- Request scope 외의 scope 지원 부족

**외부 라이브러리가 필요한 경우:**
- 복잡한 DI 그래프
- 테스트에서 의존성 교체 필요
- Request scope 외의 라이프사이클 관리
- Clean Architecture에서 레이어 간 의존성 역전

### 4. 현재 프로젝트에 대한 권장사항

**현재 상태**: FastAPI `Depends()` 사용 중

**권장**: 
- **단기**: FastAPI `Depends()` 유지 + Protocol 인터페이스로 DIP 적용 (현재 방식)
- **중장기**: Dishka 도입 검토 (복잡도 증가 시)

**이유**:
1. 현재 규모에서는 FastAPI 내장 DI로 충분
2. Protocol + TYPE_CHECKING으로 이미 DIP 적용 중
3. 라이브러리 추가 시 학습 곡선 발생

---

## 참고 자료

- [fastapi-clean-example](https://github.com/ivan-borovets/fastapi-clean-example)
- [Dishka Documentation](https://dishka.readthedocs.io/)
- [dependency-injector Documentation](https://python-dependency-injector.ets-labs.org/)
- [Clean Architecture by Robert C. Martin](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)

---

## 변경 이력

| 날짜 | 변경 내용 |
|------|-----------|
| 2025-12-30 | 초안 작성 |

