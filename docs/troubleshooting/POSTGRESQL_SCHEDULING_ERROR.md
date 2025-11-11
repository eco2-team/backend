# PostgreSQL Pod FailedScheduling 오류 분석

> 날짜: 2025-11-04  
> 증상: PostgreSQL Pod가 Pending 상태로 스케줄링되지 않음  

---

## 📋 PostgreSQL 배치 설계

### 1. 의도된 배치 전략

**파일**: `ansible/roles/postgresql/tasks/main.yml`

```yaml
spec:
  nodeSelector:
    workload: storage  # Storage 노드에 배포
  containers:
  - name: postgres
    image: postgres:16-alpine
    resources:
      requests:
        memory: "1Gi"
        cpu: "500m"
      limits:
        memory: "2Gi"
        cpu: "1000m"
```

**배치 의도**:
- **Target Node**: `k8s-storage` (Storage 전용 노드)
- **NodeSelector**: `workload=storage`
- **이유**: 
  - Stateful 워크로드
  - 대용량 스토리지 (100GB EBS)
  - 데이터베이스 전용 노드 분리
  - 리소스 격리 (다른 워크로드 영향 최소화)

---

### 2. 노드 레이블링 계획

**파일**: `ansible/site.yml` (Line 52-86)

```yaml
- name: 노드 레이블 지정
  hosts: masters
  tasks:
    - name: Label worker-1 (Application)
      command: kubectl label nodes k8s-worker-1 workload=application --overwrite
    
    - name: Label worker-2 (Async Workers)
      command: kubectl label nodes k8s-worker-2 workload=async-workers --overwrite
    
    - name: Label storage (Stateful Services)
      command: kubectl label nodes k8s-storage workload=storage --overwrite
```

**레이블링 타이밍**: PostgreSQL 설치 **전**에 실행됨 (플레이북 순서상 보장)

---

## 🚨 현재 오류 분석

### 오류 메시지 해석

```
Events:
  Warning  FailedScheduling  3m13s (x6 over 28m)  default-scheduler  
  0/4 nodes are available: 
    1 Insufficient cpu, 
    1 node(s) had untolerated taint {node-role.kubernetes.io/control-plane: }, 
    2 node(s) didn't match Pod's node affinity/selector.
```

### 상세 분석

#### 1️⃣ **0/4 nodes are available**
**의미**: 클러스터에 4개 노드가 있지만, 모두 스케줄링 불가

**4개 노드 구성**:
- `k8s-master` (Master)
- `k8s-worker-1` (Application)
- `k8s-worker-2` (Async Workers)
- `k8s-storage` (Storage) ← **배치 의도 노드**

---

#### 2️⃣ **1 Insufficient cpu**
**의미**: 1개 노드에서 CPU 리소스 부족

**PostgreSQL 요구사항**:
- Requests: `500m` (0.5 CPU)
- Limits: `1000m` (1 CPU)

**가능한 원인**:
- 해당 노드에 이미 많은 Pod가 실행 중
- 가용 CPU가 500m 미만

**확인 필요**:
```bash
kubectl top nodes
kubectl describe node <NODE_NAME> | grep -A 10 "Allocated resources"
```

---

#### 3️⃣ **1 node(s) had untolerated taint {node-role.kubernetes.io/control-plane: }**
**의미**: Master 노드는 Taint 때문에 스케줄링 불가

**Master 노드 Taint**:
```yaml
Taints:
  node-role.kubernetes.io/control-plane:NoSchedule
```

**PostgreSQL에는 Toleration이 없음** (의도적):
```yaml
# PostgreSQL StatefulSet에는 tolerations 설정 없음
spec:
  nodeSelector:
    workload: storage
  # tolerations: (없음)
```

**결과**: Master 노드는 배제됨 (정상)

---

#### 4️⃣ **2 node(s) didn't match Pod's node affinity/selector** ⚠️
**의미**: 2개 노드가 `workload=storage` 레이블을 가지고 있지 않음

**이것이 핵심 문제입니다!**

**예상 시나리오**:
- `k8s-worker-1`: `workload=application` (불일치)
- `k8s-worker-2`: `workload=async-workers` (불일치)
- `k8s-storage`: 레이블 없음 또는 잘못된 레이블 ⚠️

**총 스케줄링 불가 노드**:
- Master: 1 (Taint)
- CPU 부족: 1 (아마도 k8s-storage)
- NodeSelector 불일치: 2 (worker-1, worker-2)
- **결과**: 4/4 노드 모두 불가능

---

## 🔍 근본 원인 분석

### 가능한 원인 3가지

#### 원인 1: Storage 노드 레이블 누락
**증상**: `k8s-storage` 노드에 `workload=storage` 레이블이 적용되지 않음

**발생 가능 상황**:
1. Ansible 플레이북 실행 중 레이블 단계가 실패했으나 무시됨
2. 노드 이름 불일치 (`k8s-storage` vs 실제 노드 이름)
3. 네트워크 일시 장애로 `kubectl label` 명령 실패

**확인**:
```bash
kubectl get nodes -L workload
```

**예상 출력 (정상)**:
```
NAME            STATUS   WORKLOAD
k8s-master      Ready    <none>
k8s-worker-1    Ready    application
k8s-worker-2    Ready    async-workers
k8s-storage     Ready    storage       ← 이 레이블이 있어야 함
```

**예상 출력 (문제)**:
```
NAME            STATUS   WORKLOAD
k8s-storage     Ready    <none>        ← 레이블 누락!
```

---

#### 원인 2: 노드 이름 불일치
**증상**: Ansible이 `k8s-storage` 노드를 찾지 못함

**가능한 시나리오**:
```bash
# Ansible이 시도하는 노드 이름
kubectl label nodes k8s-storage workload=storage --overwrite

# 실제 노드 이름이 다를 수 있음
ip-10-0-1-234.ap-northeast-2.compute.internal
```

**확인**:
```bash
kubectl get nodes
```

---

#### 원인 3: Storage 노드 CPU 부족
**증상**: `k8s-storage` 노드에 레이블은 있지만 CPU 리소스 부족

**t3.large 스펙**:
- vCPU: 2
- Memory: 8GB

**이미 실행 중인 Pod**:
- RabbitMQ (Storage 노드 배치)
- 시스템 Pod (kube-proxy, calico-node 등)

**PostgreSQL 요구**:
- Requests: 500m CPU

**확인**:
```bash
kubectl describe node k8s-storage | grep -A 10 "Allocated resources"
```

---

## 🔧 해결 방법

### 1단계: 노드 레이블 확인

```bash
# Master 노드 접속
ssh ubuntu@<MASTER_IP>

# 모든 노드의 레이블 확인
kubectl get nodes -L workload,instance-type,role

# 예상 출력:
# NAME            WORKLOAD        INSTANCE-TYPE   ROLE
# k8s-master      <none>          <none>          <none>
# k8s-worker-1    application     t3.medium       application
# k8s-worker-2    async-workers   t3.medium       workers
# k8s-storage     storage         t3.large        storage
```

---

### 2단계: Storage 노드 레이블 수정 (누락 시)

#### 방법 A: 자동 스크립트 (권장)

```bash
# 로컬에서 실행
bash scripts/fix-node-labels.sh <MASTER_IP> ubuntu
```

이 스크립트는 자동으로:
1. 모든 노드에 올바른 레이블 적용
2. Storage 노드 레이블 검증
3. PostgreSQL Pod 재시작 (자동 재스케줄링)

---

#### 방법 B: 수동 수정

```bash
# Master 노드에서 실행
kubectl label nodes k8s-storage workload=storage instance-type=t3.large role=storage --overwrite

# 레이블 적용 확인
kubectl get nodes k8s-storage -L workload

# 출력:
# NAME          STATUS   WORKLOAD
# k8s-storage   Ready    storage   ← 확인!
```

---

### 3단계: 노드 이름 불일치 해결 (필요 시)

**실제 노드 이름 확인**:
```bash
kubectl get nodes
```

**실제 이름이 다른 경우** (예: `ip-10-0-1-234.ap-northeast-2.compute.internal`):
```bash
# 실제 노드 이름으로 레이블 적용
kubectl label nodes ip-10-0-1-234.ap-northeast-2.compute.internal \
  workload=storage instance-type=t3.large role=storage --overwrite
```

---

### 4단계: PostgreSQL Pod 재시작

```bash
# 기존 PostgreSQL Pod 삭제 (StatefulSet이 자동 재생성)
kubectl delete pod -l app=postgres -n default --force --grace-period=0

# 또는 StatefulSet 재시작
kubectl rollout restart statefulset/postgres -n default

# 30초 대기
sleep 30

# Pod 상태 확인
kubectl get pods -n default -o wide | grep postgres
```

**예상 출력 (정상)**:
```
NAME         READY   STATUS    NODE
postgres-0   1/1     Running   k8s-storage   ← Storage 노드에 배치됨!
```

---

### 5단계: CPU 리소스 부족 해결 (필요 시)

**CPU 사용량 확인**:
```bash
kubectl top nodes
kubectl describe node k8s-storage | grep -A 10 "Allocated resources"
```

**해결책 A: 리소스 요청량 조정**

`ansible/roles/postgresql/tasks/main.yml` 수정:
```yaml
resources:
  requests:
    memory: "1Gi"
    cpu: "250m"      # 500m → 250m으로 감소
  limits:
    memory: "2Gi"
    cpu: "1000m"
```

**해결책 B: 다른 Pod 이동**

RabbitMQ가 Storage 노드에 있다면:
```bash
# RabbitMQ를 Worker-2로 이동
kubectl patch rabbitmqcluster rabbitmq -n messaging --type merge -p '
spec:
  override:
    statefulSet:
      spec:
        template:
          spec:
            nodeSelector:
              workload: async-workers
'
```

---

## 🎯 Ansible 플레이북 재실행 (전체 해결)

노드 레이블이 완전히 누락된 경우, 레이블 단계만 재실행:

```bash
cd ansible

# 노드 레이블 단계부터 재실행
ansible-playbook -i inventory/hosts.ini site.yml \
  --start-at-task='노드 레이블 지정'
```

또는 PostgreSQL 설치만 재실행:
```bash
ansible-playbook -i inventory/hosts.ini site.yml \
  --tags postgresql
```

---

## 📊 검증

### 최종 확인 체크리스트

```bash
# 1. 노드 레이블 확인
kubectl get nodes -L workload
# ✅ k8s-storage에 workload=storage 있어야 함

# 2. PostgreSQL Pod 상태
kubectl get pods -n default -o wide | grep postgres
# ✅ STATUS: Running
# ✅ NODE: k8s-storage

# 3. Pod Events 확인
kubectl describe pod -l app=postgres -n default | grep Events -A 20
# ✅ FailedScheduling 이벤트 없어야 함

# 4. 연결 테스트
kubectl exec -it statefulset/postgres -n default -- psql -U admin -d sesacthon -c "SELECT 1;"
# ✅ 결과: 1 (연결 성공)

# 5. Storage 노드 리소스 확인
kubectl top node k8s-storage
# ✅ CPU/Memory 사용량 확인
```

---

## 📝 요약

### 오류 원인
1. **Primary**: `k8s-storage` 노드에 `workload=storage` 레이블 누락
2. **Secondary**: CPU 리소스 부족 가능성
3. **Tertiary**: 노드 이름 불일치 가능성

### 해결 순서
1. 노드 레이블 확인 (`kubectl get nodes -L workload`)
2. Storage 노드 레이블 적용 (`kubectl label nodes k8s-storage workload=storage --overwrite`)
3. PostgreSQL Pod 재시작 (`kubectl delete pod -l app=postgres -n default`)
4. 상태 확인 (`kubectl get pods -o wide`)

### 예방 조치
- Ansible 플레이북에 레이블 검증 단계 추가됨 (`site.yml`)
- `fix-node-labels.sh` 스크립트로 레이블 복구 자동화
- 노드 레이블 적용 실패 시 플레이북 즉시 중단 (`failed_when`)

---

**작성일**: 2025-11-04  
**관련 파일**:
- `ansible/roles/postgresql/tasks/main.yml`
- `ansible/site.yml`
- `scripts/fix-node-labels.sh`

