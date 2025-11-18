## Data Layer Custom Resources

Wave 35에서 운영되는 Postgres·Redis·RabbitMQ 데이터 인스턴스를 정의한다. `platform/cr/base`에 공통 스펙을 두고 `platform/cr/{dev,prod}`에서 환경별 패치를 적용한다.

### 디렉터리 구조
- `base/postgres-cluster.yaml`: Zalando Postgres Operator CR (`acid.zalan.do/v1`)
- `base/redis-{replication,sentinel}.yaml`: OT-Container-Kit Redis Operator CR (`redis.redis.opstreelabs.in/v1beta2`)
- `base/rabbitmq-cluster.yaml`: RabbitMQ Cluster Operator CR (`rabbitmq.com/v1beta1`)
- `dev/`: Base 참조 + dev 패치
- `prod/`: Base 참조 + prod 패치

### 배포 순서
1. **Wave 25**: 각 Operator 설치 (`platform/helm/postgres-operator`, `redis-operator`, `rabbitmq-operator`)
2. **Wave 35**: `platform/cr/{dev,prod}` Kustomize 적용
3. Operator가 CR을 Reconcile하여 StatefulSet/PVC/Service를 생성

### 환경별 개요
| 항목 | dev | prod |
|------|-----|------|
| Postgres volume | 20Gi | 100Gi + 백업 |
| Redis volume | 10Gi | 50Gi |
| RabbitMQ volume | 20Gi | 50Gi |
| RabbitMQ replicas | 1 | 3 |

### 참고 자료
- Operator 스펙: `docs/operator/OPERATOR-DESIGN-SPEC.md`
- Secret 주입: `docs/deployment/gitops/TERRAFORM_SECRET_INJECTION.md`


