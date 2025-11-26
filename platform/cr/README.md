## Data Layer Custom Resources

Wave 35에서 운영되는 Postgres·Redis 인스턴스를 정의합니다. 공통 스펙은 `platform/cr/base`에, 환경별 리소스 증감은 `platform/cr/{dev,prod}` 패치에 정리했습니다. RabbitMQ는 2025-11-19 장애 분석(`docs/troubleshooting/2025-11-19-rabbitmq-redis.md`) 이후 재도입 예정으로 현재 CR/CRD가 비활성화된 상태입니다.

### 디렉터리 구조
- `base/postgres-cluster.yaml` : Zalando Postgres Operator CR (`acid.zalan.do/v1`)
- `base/redis-cluster.yaml` / `base/redis-sentinel.yaml` : OT-Container-Kit Redis Operator CR (`redis.redis.opstreelabs.in/v1beta2`)
- `dev/` : base를 참조하고 `postgres-patch.yaml`, `redis-patch.yaml`로 리소스·스토리지 조정
- `prod/` : 고가용성 용량/백업 옵션을 패치 (`enableLogicalBackup`, Sentinel 리소스 증설 등)

### 배포 순서
1. **Wave 00** – `platform/crds/{env}`: AWS LB / External Secrets / Redis / Postgres / Prometheus CRD를 선적용
2. **Wave 24** – Postgres Operator(`clusters/{env}/apps/24-postgres-operator.yaml`) Helm sync
3. **Wave 28** – Redis Operator(`clusters/{env}/apps/28-redis-operator.yaml`) Helm sync
4. **Wave 35** – `platform/cr/{env}` Kustomize sync → StatefulSet/PVC/Service 생성

### 환경별 주요 스펙
| 리소스 | dev | prod | 비고 |
|--------|-----|------|------|
| Postgres volume | 20Gi | 100Gi (`enableLogicalBackup=true`) | `gp3`, taint `domain=data` toleration |
| Postgres 리소스 | 0.5 vCPU / 1Gi → 1 vCPU / 2Gi | 1 vCPU / 4Gi → 2 vCPU / 8Gi | `platform` 팀 권한 (`teamId`) |
| Redis volume | 10Gi | 50Gi | `RedisReplication` + `RedisSentinel` |
| Redis 리소스 | 0.2 vCPU / 512Mi | 0.5 vCPU / 2Gi | Sentinel 리소스 별도 패치 |

### 운영 메모
- **Secret 경로**: `workloads/secrets/external-secrets/{env}/data-secrets.yaml` 이 `postgresql-secret`, `redis-secret`을 생성하면 Operator가 자동으로 참조합니다.
- **노드 스케줄링**: Redis는 `infra-type=redis` nodeSelector + `domain=data` taint toleration을 사용하며, Postgres는 taint 기반으로 격리합니다. 인프라 노드 라벨/taint는 `docs/architecture/NODE_TAINT_MANAGEMENT.md` 참고.
- **RabbitMQ**: Operator/CR은 현재 repository(worktrees 제외)에서 제외되어 있으며, 재도입 시 `platform/cr/base/rabbitmq-cluster.yaml` 과 kustomization patch를 복구해야 합니다.

### 적용 예시

```bash
# dev 데이터 스택
kustomize build platform/cr/dev | kubectl apply -f -

# prod 데이터 스택
kustomize build platform/cr/prod | kubectl apply -f -
```
