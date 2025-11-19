# 2025-11-19 RabbitMQ / Redis 운영 이슈 정리

## 개요
- **대상 환경**: `dev` Argo CD Application (`dev-rabbitmq-operator`, `dev-data-crs`, `dev-rbac-storage`)
- **문제 요약**
  1. ✅ RabbitMQ Cluster Operator: `kustomize v5.3.0` 제거로 해결
  2. ✅ Redis Cluster: EBS CSI Driver 설치 및 StorageClass 수정으로 PVC 생성 성공
  3. 🔄 Redis Cluster: Permission denied on `/data/appendonlydir` - fsGroup 설정 필요
  4. ✅ CRD 이중 적용 우려: 운영자 질문 대응 (CRD 분리 전략 문서화)

---

## 1. RabbitMQ Cluster Operator Sync Error

### 증상
- Argo CD `dev-rabbitmq-operator` 앱에서 `ComparisonError: kustomize version v5.3.0 is not registered`

### 원인
- 공식 리포(`rabbitmq/cluster-operator` v1.11.0)의 `config/installation`은 **Kustomize v5** 스키마를 사용
- ArgoCD에 v5.3.0이 등록되지 않아 빌드 실패

### 조치
1. `clusters/{dev,prod}/apps/32-rabbitmq-operator.yaml`에서 `kustomize.version: v5.3.0` 제거
   - ArgoCD 기본 kustomize 버전 사용
2. 기존 패치 유지:
   ```yaml
   - op: remove
     path: /
   ```
   → upstream `crd` 리소스를 제거하여 `platform/crds/*`에서만 CRD를 관리

### 결과
- ✅ Argo CD가 기본 Kustomize로 빌드하면서 오류 제거
- ✅ CRD는 여전히 `dev-crds` 애플리케이션을 통해 단일 경로로 관리

---

## 2. Redis PVC External Provisioning Pending

### 증상
- `redis-cluster-redis-cluster-0` PVC 이벤트:
  ```
  Waiting for a volume to be created either by the external provisioner 'ebs.csi.aws.com'...
  ```
- StatefulSet `redis-cluster` 파드가 PVC 바인딩 실패로 Pending
- **근본 원인**: EBS CSI Driver가 설치되지 않음

### 원인
1. **StorageClass provisioner 불일치**:
   - 기존: `kubernetes.io/aws-ebs` (legacy in-tree provisioner)
   - 필요: `ebs.csi.aws.com` (CSI driver)
2. **EBS CSI Driver 미설치**:
   - Ansible playbook에 정의되어 있으나 실제 설치되지 않음
   - `kubectl get csidriver` 결과 empty

### 조치
1. **EBS CSI Driver 수동 설치**:
   ```bash
   kubectl apply -k "github.com/kubernetes-sigs/aws-ebs-csi-driver/deploy/kubernetes/overlays/stable/?ref=release-1.24"
   ```

2. **StorageClass 수정** (`workloads/rbac-storage/base/storage-class.yaml`):
   ```yaml
   provisioner: ebs.csi.aws.com
   parameters:
     type: gp3
     iops: "3000"
     throughput: "125"
     encrypted: "true"
     csi.storage.k8s.io/fstype: ext4
   ```

3. **Redis Cluster 설정 수정** (`platform/cr/base/redis-cluster.yaml`):
   - nodeSelector: `kubernetes.io/hostname: k8s-redis` → `infra-type: redis`
   - 이미지: `quay.io/opstree/redis:7.2.4` (not found) → `v7.0.15`
   - storageClassName: 명시적으로 `gp3` 추가
   - volumeClaimTemplate.metadata.name 제거 (Redis Operator가 지원하지 않음)

4. **RabbitMQ Cluster 설정 수정** (`platform/cr/base/rabbitmq-cluster.yaml`):
   - nodeSelector: `kubernetes.io/hostname: k8s-rabbitmq` → `infra-type: rabbitmq`
   - secretBackend 제거 (ExternalSecret이 없어 diff 발생)

### 결과
- ✅ EBS CSI Driver 설치 완료 (controller 2 pods, node daemonset 14 pods)
- ✅ PVC 2개 Bound 성공 (redis 10Gi, postgres 20Gi)
- ✅ Postgres: Running 상태
- 🔄 Redis: Permission denied 문제로 CrashLoopBackOff

---

## 3. Redis Permission Denied 문제

### 증상
```
Redis is running without password which is not recommended
Can't open or create append-only dir appendonlydir: Permission denied
```

### 원인
- Redis Operator가 생성하는 StatefulSet에 `securityContext`가 없음
- PVC 볼륨의 기본 소유권이 root이며, Redis 프로세스가 쓰기 권한 없음
- AOF(Append-Only File) 디렉토리 생성 시 Permission denied 발생

### 조치
Redis CR에 `redisConfig` 추가하여 AOF 비활성화 및 RDB snapshot 사용:

```yaml
spec:
  redisConfig:
    additionalRedisConfig: |
      appendonly no
      save 900 1      # 15분마다 1개 이상 key 변경시 저장
      save 300 10     # 5분마다 10개 이상 key 변경시 저장
      save 60 10000   # 1분마다 10000개 이상 key 변경시 저장
```

**설명**:
- `appendonly no`: AOF persistence 비활성화 (디렉토리 생성 불필요)
- `save` 옵션: RDB snapshot 기반 persistence 사용
- 개발 환경에서 충분한 데이터 내구성 제공

### 결과
- ✅ Redis Pod 정상 시작
- ✅ RDB snapshot으로 데이터 persistence 유지

---

## 3. CRD 분리 전략 FAQ

| 항목 | Postgres Operator | Redis Operator | RabbitMQ Operator |
| --- | --- | --- | --- |
| 배포 방식 | Helm (`skipCrds: true`) | Kustomize (`config/default`) | Kustomize (`config/installation`) |
| CRD 관리 | `platform/crds/*` App | 동일 | 동일 |
| 중복 방지 방법 | Helm values (`skipCrds`) | (필요 시) Kustomize patch로 CRD 제거 | 이미 patch 적용 |

- RabbitMQ는 Helm Chart를 제공하지 않아 `helm.skipCrds` 옵션을 쓸 수 없음 → 패치로 CRD 제거.
- Redis도 같은 패턴을 적용할 수 있으며, 버전 업 시 patch 유지 필요.
- 모든 데이터 계층 Operator는 “Operator와 CRD를 분리 관리”한다는 전략을 공유.

---

## 4. RabbitMQ & Postgres: nodeAffinity vs nodeSelector 전환

### 배경
- **기존 방식**: RabbitMQ는 `nodeSelector: kubernetes.io/hostname: k8s-rabbitmq` 사용 (단일 노드 고정)
- **변경 방식**: Postgres와 동일하게 **nodeAffinity + infra-type 라벨** 기반 스케줄링으로 통일
- **목표**: 확장성 및 표준화 (Infrastructure 워크로드는 infra-type 라벨로 배치)

### 문제점: nodeSelector의 한계
```yaml
# 기존 RabbitMQ 설정 (문제점)
nodeSelector:
  kubernetes.io/hostname: k8s-rabbitmq  # ❌ 단일 호스트 고정, 확장 불가
```

**이슈**:
1. 호스트명은 클러스터 재배포/노드 교체 시 변경될 수 있음
2. 여러 RabbitMQ 노드로 확장하려면 매번 수동 수정 필요
3. Postgres와 표준이 달라 운영 복잡도 증가

### nodeAffinity + infra-type 라벨 사용

#### RabbitMQ Cluster 설정
#### ✅ Postgres Cluster 설정 (참고)
```yaml
# platform/cr/base/postgres-cluster.yaml
spec:
  # ✅ nodeAffinity 사용
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
        - matchExpressions:
            - key: infra-type
              operator: In
              values:
                - postgresql
  
  # ✅ tolerations (domain=data)
  tolerations:
    - key: domain
      operator: Equal
      value: data
      effect: NoSchedule
```

### Node 라벨 구성 (Terraform)

#### RabbitMQ Node
```hcl
# terraform/main.tf
"k8s-rabbitmq" = "--node-labels=role=infrastructure,domain=integration,infra-type=rabbitmq,workload=message-queue,tier=platform,phase=4 --register-with-taints=domain=integration:NoSchedule"
```

**핵심 라벨**:
- `infra-type=rabbitmq`: nodeAffinity 매칭에 사용
- `domain=integration`: toleration 매칭에 사용
- `role=infrastructure`: 인프라 워크로드 식별

#### Postgres Node
```hcl
"k8s-postgresql" = "--node-labels=role=infrastructure,domain=data,infra-type=postgresql,workload=database,tier=data,phase=1 --register-with-taints=domain=data:NoSchedule"
```

**핵심 라벨**:
- `infra-type=postgresql`: nodeAffinity 매칭에 사용
- `domain=data`: toleration 매칭에 사용

### 트러블슈팅 시나리오

#### 시나리오 1: Pod가 Pending 상태 (노드 라벨 불일치)
```bash
# 증상
$ kubectl get pods -n rabbitmq
NAME                       READY   STATUS    RESTARTS   AGE
rabbitmq-cluster-server-0  0/1     Pending   0          5m

# 원인 확인
$ kubectl describe pod rabbitmq-cluster-server-0 -n rabbitmq | grep -A 5 "Events:"
Events:
  Type     Reason            Age   From               Message
  ----     ------            ----  ----               -------
  Warning  FailedScheduling  3m    default-scheduler  0/14 nodes are available: 1 node had untolerated taint {domain: integration}...
```

**원인**: Node에 `infra-type=rabbitmq` 라벨이 없거나 taint를 tolerate하지 못함

**해결**:
```bash
# 1. 노드 라벨 확인
kubectl get nodes -l infra-type=rabbitmq --show-labels

# 2. 라벨이 없다면 추가
kubectl label node k8s-rabbitmq infra-type=rabbitmq

# 3. taint 확인
kubectl describe node k8s-rabbitmq | grep Taints
# 예상: Taints: domain=integration:NoSchedule

# 4. Pod의 tolerations 확인
kubectl get rabbitmqcluster rabbitmq-cluster -n rabbitmq -o yaml | grep -A 5 tolerations
```

#### 시나리오 2: podAntiAffinity로 인한 스케줄링 실패
```bash
# 증상
$ kubectl get pods -n rabbitmq
NAME                        READY   STATUS    RESTARTS   AGE
rabbitmq-cluster-server-0   1/1     Running   0          10m
rabbitmq-cluster-server-1   0/1     Pending   0          5m
```

**원인**: 
- podAntiAffinity가 `topologyKey: kubernetes.io/hostname` 기준으로 동일 호스트 회피 설정
- RabbitMQ 노드가 1개만 존재해 두 번째 Pod 배치 불가

**해결**:
1. **단일 노드 환경**: podAntiAffinity를 `preferredDuringScheduling`으로 변경 (이미 적용됨)
2. **다중 노드 환경**: infra-type=rabbitmq 라벨을 가진 노드 추가
   ```bash
   # 두 번째 RabbitMQ 노드 추가
   kubectl label node k8s-rabbitmq-2 infra-type=rabbitmq domain=integration
   kubectl taint node k8s-rabbitmq-2 domain=integration:NoSchedule
   ```

#### 시나리오 3: Postgres Pod가 잘못된 노드에 배치
```bash
# 증상
$ kubectl get pods -n postgres -o wide
NAME                   READY   STATUS    NODE
postgres-cluster-0     1/1     Running   k8s-api-auth  # ❌ 잘못된 노드
```

**원인**: 
- `nodeAffinity`가 없거나 API 노드가 infra-type=postgresql 라벨을 가지고 있음
- tolerations가 없어 taint가 없는 노드에 배치됨

**해결**:
```bash
# 1. 잘못된 노드에서 라벨 제거
kubectl label node k8s-api-auth infra-type-

# 2. Postgres 전용 노드 라벨 확인
kubectl get nodes -l infra-type=postgresql

# 3. Postgres CR에 nodeAffinity 및 tolerations 확인
kubectl get postgresql postgres-cluster -n postgres -o yaml

# 4. Pod 재생성 (필요 시)
kubectl delete pod postgres-cluster-0 -n postgres
```

#### 시나리오 4: Node Taint 변경 후 기존 Pod 미적용
```bash
# 증상: 노드에 taint를 추가했지만 기존 Pod는 계속 Running
$ kubectl taint node k8s-rabbitmq domain=integration:NoSchedule
node/k8s-rabbitmq tainted

$ kubectl get pods -n rabbitmq -o wide
NAME                        NODE          STATUS
rabbitmq-cluster-server-0   k8s-rabbitmq  Running  # 여전히 Running
```

**원인**: 
- 기존에 실행 중인 Pod는 taint 변경의 영향을 받지 않음 (toleration이 없어도 계속 실행)

**해결**:
```bash
# 1. RabbitmqCluster CR에 tolerations 추가/확인
kubectl edit rabbitmqcluster rabbitmq-cluster -n rabbitmq

# 2. StatefulSet Pod 재생성 (Rolling Restart)
kubectl rollout restart statefulset rabbitmq-cluster-server -n rabbitmq

# 또는 CR 업데이트로 자동 Rolling Update 트리거
kubectl patch rabbitmqcluster rabbitmq-cluster -n rabbitmq --type=merge -p '{"spec":{"rabbitmq":{"additionalConfig":"# force update"}}}'
```

### 체크리스트: Affinity/Toleration 설정 검증

#### RabbitMQ
```bash
# 1. Node 라벨 확인
kubectl get nodes -l infra-type=rabbitmq --show-labels

# 2. Node taint 확인
kubectl describe node k8s-rabbitmq | grep Taints
# 예상: domain=integration:NoSchedule

# 3. RabbitmqCluster CR 설정 확인
kubectl get rabbitmqcluster rabbitmq-cluster -n rabbitmq -o yaml | grep -A 20 affinity
kubectl get rabbitmqcluster rabbitmq-cluster -n rabbitmq -o yaml | grep -A 5 tolerations

# 4. 실제 Pod 스펙 확인 (StatefulSet)
kubectl get statefulset -n rabbitmq rabbitmq-cluster-server -o yaml | grep -A 20 affinity
kubectl get statefulset -n rabbitmq rabbitmq-cluster-server -o yaml | grep -A 5 tolerations

# 5. Pod 배치 확인
kubectl get pods -n rabbitmq -o wide
```

#### Postgres
```bash
# 1. Node 라벨 확인
kubectl get nodes -l infra-type=postgresql --show-labels

# 2. Node taint 확인
kubectl describe node k8s-postgresql | grep Taints
# 예상: domain=data:NoSchedule

# 3. Postgresql CR 설정 확인
kubectl get postgresql postgres-cluster -n postgres -o yaml | grep -A 20 nodeAffinity
kubectl get postgresql postgres-cluster -n postgres -o yaml | grep -A 5 tolerations

# 4. 실제 Pod 스펙 확인 (StatefulSet)
kubectl get statefulset -n postgres -o yaml | grep -A 20 affinity
kubectl get statefulset -n postgres -o yaml | grep -A 5 tolerations

# 5. Pod 배치 확인
kubectl get pods -n postgres -o wide
```

### 표준 패턴 요약

| 항목 | RabbitMQ | Postgres | 공통 원칙 |
|------|----------|----------|-----------|
| **nodeAffinity** | `infra-type: rabbitmq` | `infra-type: postgresql` | infra-type 라벨 기반 매칭 |
| **tolerations** | `domain: integration` | `domain: data` | 각 인프라의 domain taint 허용 |
| **podAntiAffinity** | ✅ (preferred, hostname) | ❌ (Operator 자체 관리) | 고가용성 필요 시 적용 |
| **nodeSelector** | ❌ (deprecated) | ❌ (deprecated) | nodeAffinity로 대체 |

### 참고 문서
- [k8s-label-annotation-system.md](../infrastructure/k8s-label-annotation-system.md): 전체 라벨 체계
- [CLUSTER_METADATA_REFERENCE.md](../architecture/CLUSTER_METADATA_REFERENCE.md): Node 라벨 및 Taint 레퍼런스
- [NODE_TAINT_MANAGEMENT.md](../architecture/NODE_TAINT_MANAGEMENT.md): Taint 관리 전략

---

## 후속 체크리스트
- [ ] `dev-rbac-storage` Sync 후 Redis PVC 상태 확인
- [ ] `dev-rabbitmq-operator`/`prod-rabbitmq-operator` Sync 결과 확인
- [ ] CRD 업데이트 필요 시 `platform/crds/base` 버전 업과 패치 목록 동기화
- [ ] RabbitMQ nodeSelector → nodeAffinity 전환 후 Pod 재배치 확인
- [ ] Postgres nodeAffinity 및 tolerations 적용 상태 검증


