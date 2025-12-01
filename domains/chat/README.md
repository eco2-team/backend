# Chat API

이 파일은 Chat 도메인 서비스를 설명하는 임시 문서입니다.

최근 `_shared` 모듈 변경 사항 반영 및 재패키징을 위해 Chat 서비스 CI를 재실행해야 하므로,
CI 트리거용으로 본 문서를 다시 업데이트했습니다. (2025-12-01 세 번째 트리거)

## Remote ArgoCD Sync

Chat 서버 업데이트 후에는 master, worker-1, worker-2, storage 노드에서 모두 `sync-argocd-all.sh`를 실행해 전체 Wave를 강제로 다시 맞춰야 합니다.

```bash
for node in master worker-1 worker-2 storage; do
  SSH_NODE="$node" ./scripts/sync-argocd-all.sh dev
done
```

해당 스크립트는 AWS CLI로 `k8s-$SSH_NODE` 인스턴스의 Public IP를 조회하고, SSH 접속해 `kubectl` 동기화를 수행합니다. 실행 PC에는 적절한 AWS 자격 증명과 SSH 키가 준비되어 있어야 합니다.

## Observability

- Prometheus 스크레이프 엔드포인트: `/metrics/status` (HTTP 상태/지연 지표)
- Grafana 패널: *Domain API Error Overview* (4xx/5xx 오류율)
