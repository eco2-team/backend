# Redis 3-Node Cluster 프로비저닝 가이드 (Dev)

## 개요
기존 단일 Redis 노드를 3개의 전용 노드로 분리:
- `k8s-redis-auth` (t3.medium) - Blacklist + OAuth State
- `k8s-redis-streams` (t3.small) - SSE Events
- `k8s-redis-cache` (t3.small) - Celery Result + Domain Cache

## 사전 조건
- AWS 자격증명 설정 완료
- `~/.ssh/sesacthon.pem` 키 존재
- Terraform 상태 최신화

---

## Phase 1: Terraform - 인프라 변경 확인

```bash
cd /Users/mango/workspace/SeSACTHON/backend/terraform

# 1. 상태 동기화
terraform init

# 2. 변경 사항 미리보기 (중요!)
terraform plan -out=redis-3node.plan

# 예상 결과:
# + module.redis_auth (새로 생성)
# + module.redis_streams (새로 생성)
# + module.redis_cache (새로 생성)
# - module.redis (제거)

# 3. 기존 노드에 영향 없는지 확인 후 적용
terraform apply redis-3node.plan
```

### Terraform 적용 후 확인
```bash
# 새 노드 IP 확인
terraform output redis_auth_public_ip
terraform output redis_streams_public_ip
terraform output redis_cache_public_ip

# Ansible inventory 생성
terraform output -raw ansible_inventory > ../ansible/inventory/hosts.ini
```

---

## Phase 2: Ansible - 노드 Join

### 2.1 SSH 연결 확인
```bash
cd /Users/mango/workspace/SeSACTHON/backend/ansible

# 새 노드 SSH 확인
ansible -i inventory/hosts.ini redis -m ping
```

### 2.2 Master에서 Join Token 생성
```bash
# Master 접속
ssh -i ~/.ssh/sesacthon.pem ubuntu@$(terraform -chdir=../terraform output -raw master_public_ip)

# Join 토큰 생성 (24h 유효)
kubeadm token create --print-join-command > /tmp/kubeadm_join_command.sh

# 로컬로 복사
exit
scp -i ~/.ssh/sesacthon.pem ubuntu@$(terraform -chdir=../terraform output -raw master_public_ip):/tmp/kubeadm_join_command.sh /tmp/
```

### 2.3 Redis 노드만 Join
```bash
cd /Users/mango/workspace/SeSACTHON/backend/ansible

# Redis 노드만 대상으로 Join 실행
ansible-playbook -i inventory/hosts.ini playbooks/03-worker-join.yml \
  -l redis \
  -e kubectl_user=ubuntu
```

### 2.4 노드 라벨 적용 (선택: Join 시 자동 적용됨)
```bash
# 라벨 적용 확인
kubectl get nodes -l redis-cluster --show-labels

# 수동 라벨 적용 필요시
ansible-playbook -i inventory/hosts.ini site.yml \
  -l redis \
  -e migrate_node_labels=true \
  -e kubectl_user=ubuntu \
  --tags node-labels
```

---

## Phase 3: 클러스터 상태 확인

```bash
# Master SSH 접속
./scripts/utilities/connect-ssh.sh master

# 노드 상태 확인
kubectl get nodes -l redis-cluster -o wide

# 예상 결과:
# NAME              STATUS   ROLES    AGE   VERSION   ...   LABELS
# k8s-redis-auth    Ready    <none>   1m    v1.28.4   ...   redis-cluster=auth
# k8s-redis-streams Ready    <none>   1m    v1.28.4   ...   redis-cluster=streams
# k8s-redis-cache   Ready    <none>   1m    v1.28.4   ...   redis-cluster=cache

# Taint 확인
kubectl describe node k8s-redis-auth | grep Taints
# 예상: domain=data:NoSchedule
```

---

## Phase 4: ArgoCD - Redis Operator + CR 배포

```bash
# 1. Redis Operator 배포 확인
kubectl get pods -n redis-system

# 2. RedisFailover CR 동기화
kubectl -n argocd get application dev-redis-cluster

# 3. 수동 Sync (필요시)
argocd app sync dev-redis-cluster --prune

# 또는 kubectl로
kubectl -n argocd annotate application dev-redis-cluster \
  argocd.argoproj.io/refresh=hard --overwrite
```

---

## Phase 5: Redis 서비스 검증

```bash
# 1. RedisFailover 상태 확인
kubectl get redisfailover -n redis

# 2. Pod 상태 확인
kubectl get pods -n redis -o wide

# 예상:
# rfr-auth-redis-0     (k8s-redis-auth 노드)
# rfr-streams-redis-0  (k8s-redis-streams 노드)
# rfr-cache-redis-0    (k8s-redis-cache 노드)

# 3. Service 엔드포인트 확인
kubectl get svc -n redis

# 4. Redis 연결 테스트
kubectl run redis-test --rm -it --image=redis:7-alpine -- \
  redis-cli -h rfr-auth-redis.redis.svc.cluster.local ping
# 예상: PONG
```

---

## Rollback 절차

### Terraform Rollback
```bash
# 변경 전 상태로 복구
terraform apply -target=module.redis -var="..."

# 또는 상태 파일에서 복구
terraform state rm module.redis_auth
terraform state rm module.redis_streams
terraform state rm module.redis_cache
```

### Kubernetes Rollback
```bash
# RedisFailover 삭제
kubectl delete redisfailover -n redis --all

# 기존 Redis Helm으로 복구 (만약 백업해뒀다면)
helm upgrade --install dev-redis bitnami/redis -n redis
```

---

## 주의사항

1. **기존 데이터 마이그레이션**: 기존 `k8s-redis` 노드의 데이터 백업 필요
2. **환경변수 전파**: Application 재시작 필요 (새 Redis 엔드포인트 적용)
3. **단계별 검증**: 각 Phase 완료 후 다음 단계 진행
4. **모니터링**: Grafana에서 Redis 메트릭 확인

## 관련 문서
- `workloads/redis/README.md` - Redis 인프라 상세
- `terraform/outputs.tf` - Terraform 출력 변수
- `ansible/playbooks/03-worker-join.yml` - 노드 조인 절차
