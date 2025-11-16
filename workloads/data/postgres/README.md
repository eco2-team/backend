# PostgreSQL Cluster (Zalando Postgres Operator)

이 디렉터리는 Zalando Postgres Operator가 관리하는 `postgresql` Custom Resource를 정의한다.

## 구조

- `base/postgres-cluster.yaml`: 공통 템플릿 (teamId, version, users, databases)
- `overlays/dev/`: Dev 환경 패치 (replicas: 1, volume: 20Gi, backup 비활성)
- `overlays/prod/`: Prod 환경 패치 (replicas: 1, volume: 100Gi, logical backup 활성)

## 선행 조건

- **Wave 25**: `platform/helm/postgres-operator` (Operator 먼저 설치)
- **Wave 35**: 이 CR 배포
- **Secret**: `postgresql-secret` (ExternalSecret으로 생성, `/sesacthon/{env}/data/postgres-password`)

## 배포 후 확인

```bash
kubectl get postgresql -n postgres
kubectl get pods -n postgres -l application=spilo
kubectl logs -n postgres postgres-main-0
```

## 참고
- Operator 스펙: `docs/architecture/operator/OPERATOR_SOURCE_SPEC.md`
- CRD 문서: https://github.com/zalando/postgres-operator/blob/master/docs/reference/cluster_manifest.md

