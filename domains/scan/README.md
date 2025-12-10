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
- 2025-11-28: CI 재실행을 위해 문서를 한 차례 더 갱신했습니다.
- 2025-12-01: Scan 패키징 재배포를 위해 README를 추가 갱신했습니다.
- 2025-12-01: Vision 이미지 패키징 재구성을 위해 한 번 더 업데이트했습니다.
- 2025-12-02: waste_pipeline 업데이트 복구본을 반영하기 위해 Scan 도커 이미지를 재빌드합니다.
- 2025-12-02: waste_pipeline text/vision 조정분 반영을 위해 Scan 도커 이미지를 다시 패키징합니다.

## Remote ArgoCD Sync

Scan 서버 변경 후에는 master, worker-1, worker-2, storage 노드에서 모두 `sync-argocd-all.sh`를 실행해 전체 Wave를 강제로 재동기화하세요.

```bash
for node in master worker-1 worker-2 storage; do
  SSH_NODE="$node" ./scripts/sync-argocd-all.sh dev
done
```

해당 스크립트는 로컬에서 AWS CLI로 `k8s-$SSH_NODE` Public IP를 찾고, SSH로 접속해 `kubectl` 동기화를 수행합니다. 실행 PC에 적절한 AWS 자격 증명과 SSH 키가 준비되어 있어야 합니다.

## Observability

- Prometheus 스크레이프 엔드포인트: `/metrics/status` (HTTP 상태/지연 지표)
- Grafana 패널: *Domain API Error Overview* (4xx/5xx 오류율)

- CI repackaging trigger: 2025-12-09
