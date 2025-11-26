# Namespaces Kustomize

전체 네임스페이스 정의 및 Tier 레이블 관리.

## 구조

- `base/namespaces.yaml`: 15개 네임스페이스 정의
  - Business Logic (7): auth, my, scan, character, location, image, chat
  - Data (2): postgres, redis
  - Integration (1): rabbitmq
  - Observability (2): prometheus, grafana
  - Infrastructure (3): platform-system, data-system, messaging-system

- `overlays/dev/`: environment=dev 레이블 추가
- `overlays/prod/`: environment=prod 레이블 추가

## Tier 분류

| Tier | Namespaces | 용도 |
|------|-----------|------|
| business-logic | auth, my, scan, ... | API 서비스 |
| data | postgres, redis | 데이터 저장소 |
| integration | rabbitmq | RabbitMQ |
| observability | prometheus, grafana | Prometheus / Grafana |
| infrastructure | *-system | Operators |

## 배포

Wave 0에서 가장 먼저 적용됨 (`clusters/dev/apps/05-namespaces.yaml`).

```bash
kubectl apply -k workloads/namespaces/overlays/dev
kubectl get ns -l app.kubernetes.io/part-of=ecoeco-backend
```
