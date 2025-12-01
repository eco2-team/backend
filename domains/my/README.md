# My API

유저 프로필 및 리워드 정보를 제공하는 FastAPI 마이크로서비스입니다. Auth 서비스의 **canonical user id**(`auth.users.id`)를 기준으로 사용자 기본 프로필을 관리하며, `auth.user_social_accounts`와 조인해 각 소셜(provider) 별 이메일/닉네임 정보를 읽고 업데이트합니다.

## 주요 기능

- `/health`, `/ready` 헬스 체크
- `/api/v1/user/{user_id}` 프로필 조회/수정/삭제
- `/api/v1/metrics` 서비스 메트릭 반환
- (내부) `UserRepository`/`MyService` 레이어를 통한 Postgres 접근

## 기술 스택

- Python 3.11, FastAPI, Pydantic v2
- SQLAlchemy 2.x + asyncpg
- ExternalSecret 기반 환경 변수 주입

## 환경 변수

| 이름 | 설명 |
| --- | --- |
| `MY_DATABASE_URL` | `postgresql+asyncpg://` 형식의 접속 URL |
| `MY_JWT_SECRET_KEY` | JWT 서명 키 (다른 서비스 검증용) |
| `MY_METRICS_CACHE_TTL_SECONDS` | 메트릭 캐시 TTL (초) |
| `MY_ACCESS_COOKIE_NAME` | 액세스 토큰 쿠키 이름 (기본값 `s_access`) |

> Dev/Prod 클러스터에서는 ExternalSecret(`my-secret`)이 위 변수들을 생성합니다.

캐릭터 도메인과의 연동 기능을 쓰려면 `CHARACTER_DATABASE_URL` 환경 변수도 필요합니다. 이 값은
동일한 Postgres 클러스터(예: `postgresql+asyncpg://.../ecoeco`)를 바라보도록 설정하면 됩니다.

## 로컬 실행 방법

```bash
cd domains/my
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
UVICORN_CMD="uvicorn domains.my.main:app --reload --port 8000"
MY_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/my" \
MY_JWT_SECRET_KEY="local-secret" \
$UVICORN_CMD
```

## Docker Compose 로컬 실행

`docker compose`를 통해 Postgres, 캐릭터 카탈로그 부트스트랩 잡, My API를 한 번에 올릴 수 있습니다.

```bash
cd domains/my
docker compose -f docker-compose.my-local.yml up --build
```

`character-bootstrap` 서비스가 `domains.character.jobs.import_character_catalog` 잡을 실행해
샘플 캐릭터 데이터를 주입하며, `api` 컨테이너는 `CHARACTER_DATABASE_URL`과 `MY_DATABASE_URL`을
동일한 Postgres 인스턴스로 설정합니다.

## API 문서

- Swagger UI: `http://localhost:8000/api/v1/user/docs`
- ReDoc: `http://localhost:8000/api/v1/user/redoc`
- OpenAPI JSON: `http://localhost:8000/api/v1/user/openapi.json`

## 테스트

```bash
cd domains/my
pytest
```

CI(GitHub Actions `ci-services.yml`)에서 `black`, `ruff`, `pytest`, Docker 이미지 빌드가 자동으로 실행됩니다. 수동 실행 시:

```bash
gh workflow run ci-services.yml -f target_services=my
```

## Remote ArgoCD Sync

My 서버 변경 사항이 머지되면 master, worker-1, worker-2, storage 노드에서 모두 `sync-argocd-all.sh`를 실행해 전체 Wave를 순차 동기화해야 합니다.

```bash
for node in master worker-1 worker-2 storage; do
  SSH_NODE="$node" ./scripts/sync-argocd-all.sh dev
done
```

`scripts/sync-argocd-all.sh`는 로컬에서 AWS CLI로 `k8s-$SSH_NODE` 인스턴스를 조회한 뒤 SSH로 접속해 `kubectl` 동기화 명령을 실행합니다. 따라서 실행 환경에는 해당 노드로 접속 가능한 SSH 키와 AWS 자격 증명이 필요합니다.

## Observability

- Prometheus 스크레이프 엔드포인트: `/metrics/status` (HTTP 상태/지연 지표)
- Grafana 패널: *Domain API Error Overview* (4xx/5xx 오류율)
