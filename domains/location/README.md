# Location API

서울시 제로웨이스트 지도/수거함 데이터를 제공하는 FastAPI 서비스입니다. `domains/location/jobs`의 CSV 파이프라인으로 데이터셋을 정규화한 뒤 `/api/v1/location` 계층에서 검색 API를 노출합니다.

## Remote ArgoCD Sync

Location 서버 코드가 업데이트되면 **모든 노드(master, worker-1, worker-2, storage)**에서 `sync-argocd-all.sh`를 실행해 전체 Wave를 강제로 동기화해야 합니다. 한 노드에서만 sync하면 나머지 노드의 로그/상태를 확인하기 어려워지므로, 아래처럼 순차 실행하는 것을 표준으로 합니다.

```bash
for node in master worker-1 worker-2 storage; do
  SSH_NODE="$node" ./scripts/sync-argocd-all.sh dev
done
```

`scripts/sync-argocd-all.sh`는 로컬에서 AWS CLI로 `k8s-$SSH_NODE` 인스턴스의 Public IP를 조회한 뒤 해당 노드로 SSH 접속해 `kubectl` 동기화 명령을 실행합니다. 따라서 실행 환경에는 해당 노드에 접근 가능한 SSH 키와 AWS 자격 증명이 준비되어 있어야 합니다.

## Observability

- Prometheus 스크레이프 엔드포인트: `/metrics/status` (HTTP 상태/지연 지표)
- Grafana 패널: *Domain API Error Overview* (4xx/5xx 오류율)
