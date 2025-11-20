# Character Service

FastAPI 기반 캐릭터 API. JWT 인증 기반으로 사용자 캐릭터 보상, 소유 현황, 애정도 증가를 제공합니다.

## 주요 기능
- `/api/v1/character/ownerships` : 분류 결과에 따라 캐릭터 지급
- `/api/v1/character/me` : 현재 사용자가 보유한 캐릭터 목록 조회
- `/health`, `/ready`, `/metrics` : 헬스/레디/메트릭 엔드포인트

## 실행 방법
```bash
cd services/character
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## 테스트
```bash
cd services/character
python3 -m pytest
```

## Docker
- Dockerfile: 멀티 스테이지, `python:3.11-slim`
- 비루트 사용자 `appuser`
- 헬스체크: `http://127.0.0.1:8000/health`

## 환경 변수
- `CHARACTER_DATABASE_URL`: PostgreSQL 접속 문자열 (ConfigMap 참고)
- JWT 검증은 `services/_shared/security` 의존성 사용

## 데이터 계층
- `app/database/` : SQLAlchemy Base, Session, Models
- `app/repositories/` : 캐릭터/사용자 캐릭터 저장소
- `tests/test_user_character_repository.py` : 레포지토리 단위 테스트

## GitOps 경로
- `workloads/apis/character/` : ConfigMap / Deployment 정의
