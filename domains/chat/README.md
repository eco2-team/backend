# Chat API

이 파일은 Chat 도메인 서비스를 설명하는 임시 문서입니다.

최근 `_shared` 모듈 변경 사항 반영 및 이미지 재패키징을 위해 Chat 서비스 CI를 다시 실행해야 하므로,
CI 트리거용으로 본 문서를 재차 업데이트했습니다.

## CI 트리거 메모
- 2025-12-01: 네 번째 트리거 - Vision 이미지 패키징
- 2025-12-02: waste_pipeline 업데이트 복구 사항 반영으로 Chat 도커 이미지를 재빌드했습니다.
- 2025-12-02: waste_pipeline text/vision 재정비 이후 Chat 이미지 재패키징

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

- CI repackaging trigger: 2025-12-09
