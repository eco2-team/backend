# Scan API

Scan 도메인은 폐기물 이미지 분류 파이프라인을 제공하는 FastAPI 애플리케이션입니다.
Swagger는 `https://api.dev.growbin.app/api/v1/scan/docs`, OpenAPI JSON은 `https://api.dev.growbin.app/api/v1/scan/openapi.json` 에서 확인할 수 있습니다.

## 주요 엔드포인트
- `GET /api/v1/scan/health`, `GET /api/v1/scan/ready`
- `GET /api/v1/scan/metrics`
- `POST /api/v1/scan/classify`
- `GET /api/v1/scan/task/{task_id}`
- `GET /api/v1/scan/categories`

세부 명세와 테스트 절차는 `docs/development/SCAN_API_SPEC.md`, `docs/development/SCAN_TEST_GUIDE.md` 를 참고하세요.

## 로컬 실행
```bash
poetry install
poetry run uvicorn domains.scan.main:app --reload --port 8000
```

필수 환경 변수:
- `OPENAI_API_KEY` : ExternalSecret `scan-secret`이 주입하며, Chat 서비스와 동일한 SSM 값을 사용합니다.

## CI 트리거 메모
2025-11-28 CI 재실행을 위해 문서를 한 차례 더 갱신했습니다.
