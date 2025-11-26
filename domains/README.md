# Domain API Services

`domain/` 디렉터리는 FastAPI 기반 마이크로서비스 7개(auth, my, scan, character, location, image, chat)를 담고 있습니다. 모든 서비스는 동일한 프로젝트 스캐폴딩과 테스트 규칙을 공유하며, 세부 코딩 스타일은 `docs/development/FASTAPI_ENDPOINT_STYLE.md` 를 따른다.

## 1. 디렉터리 개요

```
domain/
├── _shared/     # 공통 보안 모듈 (JWT, dependencies)
├── auth/        # 인증/인가
├── my/          # 사용자 프로필·포인트
├── scan/        # 폐기물 이미지 분류
├── character/   # 성향/캐릭터 분석
├── location/    # 위치/지도 서비스
├── image/       # 이미지 업로드 & Presigned URL 교환
└── chat/        # GPT-4o-mini 챗봇
```

각 서비스는 아래와 같은 공통 레이아웃을 유지한다.

```
<service>/
├── Dockerfile
├── requirements.txt
├── app/
│   ├── main.py
│   ├── api/v1/endpoints/   # health / metrics / domain router
│   ├── schemas/
│   └── services/
└── tests/
    └── test_health.py
```

## 2. 서비스 요약

| Service | Namespace | 주요 역할 | Docker Hub 이미지 |
|---------|-----------|-----------|-------------------|
| `auth` | `auth` | JWT 발급, 토큰 리프레시, 블랙리스트 | `docker.io/mng990/eco2:auth-{env}-latest` |
| `my` | `my` | 프로필/포인트/활동 관리 | `docker.io/mng990/eco2:my-{env}-latest` |
| `scan` | `scan` | 이미지 분류 작업(비동기 파이프라인 연동 예정) | `docker.io/mng990/eco2:scan-{env}-latest` |
| `character` | `character` | 사용자 캐릭터 분석·히스토리 | `docker.io/mng990/eco2:character-{env}-latest` |
| `location` | `location` | 근처 수거함·센터 탐색, 좌표 변환 | `docker.io/mng990/eco2:location-{env}-latest` |
| `image` | `image` | 이미지 업로드·Presigned URL 발급 | `docker.io/mng990/eco2:image-{env}-latest` |
| `chat` | `chat` | GPT-4o-mini 챗봇, 피드백 수집 | `docker.io/mng990/eco2:chat-{env}-latest` |

모든 서비스는 `/api/v1/health` 와 `/api/v1/metrics` 를 노출하여 Prometheus(ServiceMonitor)에서 namespace 단위로 상태를 수집할 수 있도록 구성했다.

## 3. 개발 규칙

- **라우터 구성**: `api/v1/endpoints/__init__.py` 에서 `health_router`, `metrics_router`, `<domain>_router` 를 통합하고 `app/main.py` 에서 `/api/v1` prefix 로 포함시킨다.
- **비즈니스 로직**: FastAPI 라우터에서는 DTO ↔ 서비스 호출만 담당하고, 실제 로직은 `app/services/*.py` 에 분리한다.
- **스키마/서비스 명명**: `app/schemas/<domain>.py`, `app/services/<domain>.py` naming 을 지키고, `pydantic` 모델은 `PascalCase`, 환경 변수는 `pydantic-settings` 로 관리한다.
- **테스트**: 각 서비스는 `tests/test_health.py` 기본 케이스를 포함하며, 도메인별 기능이 추가될 때 pytest 모듈을 확장한다. CI는 `black`, `ruff`, `pytest` 를 서비스 단위 matrix 로 실행한다.
- **requirements.txt**: 공통 베이스( FastAPI, uvicorn, pydantic, httpx 등 )는 모든 서비스가 동일 버전을 사용한다. 추가 의존성은 해당 서비스의 `requirements.txt` 에만 추가한다.

## 4. 로컬 실행 & 컨테이너 빌드

```bash
# 예: auth 서비스
cd domain/auth
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn domains.auth.main:app --reload --port 8000
```

GitHub Actions는 변경된 서비스만 빌드/푸시 한다. 수동으로 검사하고 싶다면 다음과 같이 실행한다.

```bash
# 빌드 컨텍스트는 domain/의 상위 디렉토리
cd /path/to/backend/worktrees/feature-auth
docker build -f domain/auth/Dockerfile -t docker.io/mng990/eco2-auth:dev-latest .
docker run --rm -p 8080:8000 docker.io/mng990/eco2-auth:dev-latest
```

## 5. 다음 작업

- metrics/health 테스트 확대 (`services/**/tests/test_metrics.py`)
- 공통 인증/로깅 모듈을 `_shared/` 패키지로 분리 검토
- External Secrets / ConfigMap 연동 시 `app/core/config.py` 에 설정 추가
