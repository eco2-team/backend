## Image API

CI 재트리거를 위해 2025-11-27 기준 업데이트.

## Remote ArgoCD Sync

Image 서버도 다른 도메인과 동일하게 master, worker-1, worker-2, storage 노드 전부에서 `sync-argocd-all.sh`를 실행해 전체 Wave를 재동기화해야 합니다.

```bash
for node in master worker-1 worker-2 storage; do
  SSH_NODE="$node" ./scripts/sync-argocd-all.sh dev
done
```

`scripts/sync-argocd-all.sh`는 로컬에서 AWS CLI로 대상 노드(`k8s-$SSH_NODE`) Public IP를 찾고, SSH로 접속해 `kubectl` 동기화를 실행합니다. 따라서 실행 환경에 AWS 자격 증명과 SSH 키가 준비되어 있어야 합니다.

## Observability

- Prometheus 스크레이프 엔드포인트: `/metrics/status` (HTTP 상태/지연 지표)
- Grafana 패널: *Domain API Error Overview* (4xx/5xx 오류율)

- CI repackaging trigger: 2025-12-09

<!-- Trigger CI: 2025-12-11T11:39:17.975707 -->
