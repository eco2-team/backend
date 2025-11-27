# Character API

Character 도메인은 수집형 캐릭터 카탈로그와 보상 로직을 제공하는 FastAPI 서비스입니다. Scan 서비스 등에서 내부 API(`/api/v1/internal/characters/rewards`)로 호출해 사용자에게 캐릭터를 부여할 수 있습니다.

## 주요 기능
- `POST /api/v1/internal/characters/rewards` : 분리배출 분류 결과 기반 보상 평가
- `POST /api/v1/characters/acquire` : 특정 캐릭터 수동 지급
- `POST /api/v1/characters/default` : 기본 캐릭터 지급
- `GET /api/v1/characters/catalog` : 공개 카탈로그

## 데이터 시드
- `domains/character/data/character_catalog.csv` 를 `domains/character/jobs/import_character_catalog.py` 가 PostSync Job으로 읽어 DB에 적재합니다.
- CSV의 `match` 컬럼은 `characters.match_label` 컬럼과 `metadata.match` 필드에 기록되어 Scan 보상 매칭에 활용됩니다.

## 로컬 실행
```bash
poetry install
poetry run uvicorn domains.character.main:app --reload --port 8001
```

필수 환경 변수:
- `CHARACTER_DATABASE_URL`

## CI 메모
2025-11-28: 캐릭터 도메인 README를 추가해 CI를 트리거했습니다.
