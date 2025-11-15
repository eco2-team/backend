# FastAPI Endpoint 스타일 가이드

- **작성일**: 2025-11-15  
- **목적**: `services/*/app/api/v1/endpoints/` 디렉터리에 작성되는 FastAPI 라우터 코드의 일관된 구조와 스타일을 정의  
- **참고 서적/자료**
  - Sebastián Ramírez, *FastAPI User Guide* (공식 문서)
  - Tiago Silva, *Building APIs with FastAPI*
  - Rick van Hattem, *Mastering Python – 3rd Edition* (Python 코드 스타일 챕터)
  - Luciano Ramalho, *Fluent Python – 2nd Edition* (타이핑, 모듈 구조 관례)

---

## 1. 디렉터리 구조와 책임

```
services/<domain>/app/
└── api/
    └── v1/
        └── endpoints/
            ├── __init__.py
            ├── health.py           # 서비스 공통 health/router (선택)
            ├── users.py            # 리소스 단위 엔드포인트
            └── metrics.py          # 별도 라우터
```

| 파일 | 역할 |
|------|------|
| `endpoints/__init__.py` | `APIRouter` 객체를 모아 `router` 로 export |
| `endpoints/*.py` | 리소스 단위로 라우팅/스키마/비즈니스 호출 정의 |
| `app/main.py` | `endpoints`에서 export한 `router` 를 include 하고, CORS/미들웨어/공통 의존성 구성 |

> **원칙**: `main.py`는 애플리케이션 wiring과 health check만 담당하고, 실제 엔드포인트 함수는 모두 `endpoints/*.py` 로 분리한다. (FastAPI User Guide “Bigger Applications” 섹션 참조)

---

## 2. 코드 스타일

### 2.1 모듈 템플릿

```python
# services/<domain>/app/api/v1/endpoints/users.py
from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.users import UserCreate, UserResponse
from app.services.users import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, service: UserService = Depends()):
    user = await service.create(payload)
    if not user:
        raise HTTPException(status_code=400, detail="User not created")
    return user
```

**규칙**
1. `APIRouter` 수준에서 `prefix`, `tags` 를 명시 (책 *Building APIs with FastAPI* 권장).
2. 타입 힌트와 `pydantic` 모델을 모든 인자/반환 값에 적용 (`Fluent Python` 타입 챕터).
3. 예외는 `HTTPException` 을 사용하고 상태 코드를 명시한다.
4. 비즈니스 로직은 `services/<domain>/app/services/*.py` 의 클래스/함수로 위임한다.
5. 공통 의존성(`db session`, `UserService`)은 `Depends()` 로 주입하고, side-effect가 있는 코드는 라우터 함수 내부가 아니라 서비스 레이어에서 처리한다.

### 2.2 파일당 책임
- 한 파일은 하나의 리소스/도메인만 다룬다. 예: `users.py`, `auth.py`, `orders.py`.
- 파일 상단에는 표준 라이브러리 → 외부 라이브러리 → 내부 모듈 순으로 import 정렬 (`Mastering Python` 권장).
- docstring은 Google Style 또는 FastAPI 예제를 따른다. (간결하게 설명/파라미터/응답 기술)

### 2.3 Health / Meta 라우터
`endpoints/health.py` 를 만들어 `/health`, `/ready` 를 `APIRouter` 로 작성하면, 서비스별 main이 간결해진다.

```python
# app/api/v1/endpoints/health.py
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "healthy"}
```

메인에서 `include_router(health.router, prefix="")` 형태로 붙인다.

---

## 3. 문서화 & 예외 처리 베스트 프랙티스

1. **Response Model**: 반환 dict 대신 `schemas` 모듈의 Pydantic 모델을 사용.
2. **에러 모델**: 공통 오류 응답은 `schemas/errors.py`에 정의하고 `responses` 매개변수로 연결.
3. **상태 코드**: `status.HTTP_200_OK` 와 같은 enum 상수를 사용해 가독성을 높인다.
4. **비동기/동기 혼용 금지**: DB I/O가 async라면 라우터도 async/await 패턴을 유지.
5. **테스트**: 각 엔드포인트 파일마다 `tests/test_<resource>.py` 에 `TestClient` 기반 테스트 추가. (FastAPI 공식문서 Testing 섹션)

---

## 4. `endpoints/__init__.py` 예시

```python
from fastapi import APIRouter

from . import health, users, metrics

router = APIRouter()
router.include_router(health.router)
router.include_router(users.router, prefix="/users")
router.include_router(metrics.router, prefix="/metrics")
```

`main.py` 에서는 다음과 같이 사용:

```python
from app.api.v1.endpoints import router as v1_router

app.include_router(v1_router, prefix="/api/v1")
```

---

## 5. 추가 참고

- **Dependency Injection**: `Depends` 로 서비스/DB 세션을 주입하고, `background_tasks` / `events` 는 `endpoints` 레이어에서만 선언한다.
- **OpenAPI 문서화**: `responses`, `summary`, `description` 을 적극적으로 활용하면 Swagger UI가 명확해진다.
- **코드 생성**: 템플릿화된 모듈 구조를 지키기 위해 Cookiecutter 또는 사내 스캐폴딩 스크립트를 사용한다.

이 가이드를 기반으로 `services/*/app/api/v1/endpoints/` 내부에 작성되는 모든 라우터가 동일한 구조와 스타일을 유지하도록 한다.

