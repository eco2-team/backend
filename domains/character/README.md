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

## Remote ArgoCD Sync

Character 서버를 배포할 때는 master, worker-1, worker-2, storage 노드 각각에서 `sync-argocd-all.sh`를 실행해 전체 Wave를 순차 동기화해야 합니다.

```bash
for node in master worker-1 worker-2 storage; do
  SSH_NODE="$node" ./scripts/sync-argocd-all.sh dev
done
```

`sync-argocd-all.sh`는 로컬에서 AWS CLI로 대상 노드(`k8s-$SSH_NODE`)의 Public IP를 조회한 뒤 SSH 접속해 `kubectl` 동기화를 수행합니다. 실행 환경에는 해당 노드에 접근 가능한 SSH 키와 AWS 자격 증명이 필요합니다.

## Observability

- Prometheus 스크레이프 엔드포인트: `/metrics/status` (HTTP 상태/지연 지표)
- Grafana 패널: *Domain API Error Overview* (4xx/5xx 오류율)

- CI repackaging trigger: 2025-12-09
