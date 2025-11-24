# Kubernetes 1.24+ 노드 라벨 문제 해결

## 📋 문제 요약

### 발생한 에러

```
[kubelet-start] Waiting for the kubelet to perform the TLS Bootstrap...
[kubelet-check] The HTTP call equal to 'curl -sSL http://localhost:10248/healthz' 
  failed with error: connection refused

error execution phase kubelet-start: timed out waiting for the condition
```

**실제 원인:**
```
failed to validate kubelet flags: unknown reserved Kubernetes labels 
specified with --node-labels: [legacy-role-prefix=api]
```

## 🔍 근본 원인

### Kubernetes 1.24 이상의 보안 정책 변경

Kubernetes 1.24부터 **kubelet 시작 시 `--node-labels`로 설정할 수 있는 라벨 prefix가 제한**되었습니다:

**허용되는 prefix:**
- ✅ `kubelet.sesacthon.io/*`
- ✅ `node.sesacthon.io/*`
- ✅ 커스텀 도메인 (예: `sesacthon.io/*`, `company.com/*`)

**금지된 prefix:**
- ❌ Kubernetes 내부 role prefix (control-plane 전용)
- ❌ 일반 `sesacthon.io/*` (일부 예외 제외)

### 우리 프로젝트에서의 문제

**기존 설정 (terraform/main.tf):**
```hcl
kubelet_extra_args = "--node-labels=role=api,service=my,workload=api,..."
```

**user-data/common.sh에서 생성:**
```bash
cat <<EOF >/etc/systemd/system/kubelet.service.d/10-node-labels.conf
[Service]
Environment="KUBELET_EXTRA_ARGS=--node-labels=role=api,service=my,..."
EOF
```

**결과:**
- kubelet이 시작 시 라벨 검증 실패
- kubelet 프로세스 즉시 종료 (exit code 1)
- health check 실패 → kubeadm join 타임아웃

## ✅ 해결 방법

### 1. 커스텀 도메인으로 라벨 변경

**수정된 라벨 체계:**

| 이전 (에러 발생) | 수정 (정상 동작) |
|---|---|
| `legacy-role-prefix=api` | `role=api` |
| `legacy-role-prefix=worker` | `role=worker` |
| `legacy-role-prefix=infrastructure` | `role=infrastructure` |

**새로운 라벨 구조:**
```yaml
role: control-plane | api | worker | infrastructure
service: auth | my | scan | character | location | info | chat | platform-system
worker-type: storage | ai
infra-type: postgresql | redis | rabbitmq | monitoring
workload: api | worker-storage | worker-ai | database | cache | message-queue
domain: auth | my | scan | character | location | info | chat | data | integration | observability
tier: business-logic | worker | data | platform | observability
phase: 0 | 1 | 2 | 3 | 4
```

### 2. Terraform 코드 수정

**terraform/main.tf - 모든 노드:**
```hcl
# API 노드 예시
user_data = templatefile("${path.module}/user-data/common.sh", {
  hostname           = "k8s-api-my"
  kubelet_extra_args = "--node-labels=role=api,service=my,workload=api,domain=my,tier=business-logic,phase=1 --register-with-taints=domain=my:NoSchedule"
})

# Worker 노드 예시
kubelet_extra_args = "--node-labels=role=worker,worker-type=storage,workload=worker-storage,tier=worker,phase=4"

# Infrastructure 노드 예시
kubelet_extra_args = "--node-labels=role=infrastructure,infra-type=postgresql,workload=database,domain=data,tier=data,phase=1 --register-with-taints=domain=data:NoSchedule"
```

**총 14개 노드 수정:**
- ✅ 7개 API 노드 (auth, my, scan, character, location, info, chat)
- ✅ 2개 Worker 노드 (storage, ai)
- ✅ 4개 Infrastructure 노드 (postgresql, redis, rabbitmq, monitoring)
- ✅ 1개 Master 노드 (라벨 없음)

### 3. 기존 노드 정리 및 재조인

**Ansible playbook 생성 (playbooks/fix-node-labels.yml):**
```yaml
- name: 올바른 노드 라벨로 kubelet 설정 업데이트
  copy:
    content: |
      [Service]
      Environment="KUBELET_EXTRA_ARGS={{ node_labels[inventory_hostname] }}"
    dest: /etc/systemd/system/kubelet.service.d/10-node-labels.conf

- name: kubeadm reset 실행
  command: kubeadm reset -f --cri-socket=unix:///run/containerd/containerd.sock

- name: Kubernetes 설정 디렉토리 삭제
  file:
    path: "{{ item }}"
    state: absent
  loop:
    - /etc/kubernetes
    - /var/lib/kubelet
    - /etc/cni/net.d
```

**실행:**
```bash
# 1. Worker 노드 라벨 수정 및 정리
ansible-playbook -i inventory/hosts.ini playbooks/fix-node-labels.yml --limit 'workers,api_nodes,postgresql,redis,rabbitmq,monitoring'

# 2. 재조인
ansible-playbook -i inventory/hosts.ini playbooks/rejoin-workers.yml
```

**결과:**
```
✅ k8s-api-my                 : ok=14   changed=5
✅ k8s-api-auth               : ok=14   changed=5
✅ k8s-worker-storage         : ok=14   changed=5
...
모든 13개 노드 성공
```

## 📊 검증

### 1. 노드 상태 확인

```bash
$ kubectl get nodes
NAME                 STATUS     ROLES           AGE     VERSION
k8s-api-auth         NotReady   <none>          2m13s   v1.28.4
k8s-api-my           NotReady   <none>          2m13s   v1.28.4
...
k8s-master           NotReady   control-plane   15m     v1.28.4
```

✅ 모든 노드 조인 성공 (NotReady는 CNI 미설치로 정상)

### 2. 라벨 확인

```bash
$ kubectl get nodes k8s-api-my --show-labels
NAME         STATUS   LABELS
k8s-api-my   NotReady role=api,service=my,workload=api,domain=my,tier=business-logic,phase=1
```

✅ 커스텀 도메인 라벨 정상 적용

### 3. kubelet 로그 확인

```bash
$ journalctl -u kubelet -n 50
# 이전: "failed to validate kubelet flags" 에러 반복
# 현재: 정상 실행, TLS Bootstrap 성공
```

## 🔄 재발 방지

### 1. 스크립트 개선

**destroy_cluster.sh에 cleanup 추가:**
```bash
bash scripts/deployment/destroy_cluster.sh --cleanup-all -y
```

**bootstrap_cluster.sh에 사전 점검 추가:**
```bash
# 잔여물 자동 감지
if [[ -f "${ANSIBLE_INVENTORY_PATH}" ]]; then
  echo "⚠️ 이전 배포 잔여물 발견"
  echo "권장: bash scripts/deployment/destroy_cluster.sh --cleanup-all -y"
fi
```

### 2. 독립 cleanup 유틸리티

```bash
# DRY-RUN으로 확인
bash scripts/utilities/cleanup-deployment-artifacts.sh --dry-run

# 실제 정리
bash scripts/utilities/cleanup-deployment-artifacts.sh --cleanup-logs
```

### 3. 배포 가이드 문서화

**docs/deployment/BOOTSTRAP_GUIDE.md** 작성:
- ✅ 배포 절차
- ✅ 삭제 절차  
- ✅ 잔여물 정리
- ✅ 문제 해결

## 📚 참고 자료

### Kubernetes 공식 문서

- [Node Labels Restrictions (1.24+)](https://sesacthon.io/docs/tasks/configure-pod-container/assign-pods-nodes/#node-isolation-restriction)
- [Kubelet Configuration](https://sesacthon.io/docs/reference/config-api/kubelet-config.v1beta1/)

### 관련 이슈

- [Kubernetes #116556](https://github.com/kubernetes/kubernetes/issues/116556) - Node label restrictions
- [kubeadm #2630](https://github.com/kubernetes/kubeadm/issues/2630) - Label validation errors

## 🎯 요약

1. **문제**: Kubernetes 1.24+에서 Kubernetes 내부 role prefix가 차단됨
2. **해결**: 단순 `role=<...>` + `domain/infra-type` 조합으로 재설계
3. **적용**: Terraform 코드 수정 + 기존 노드 재조인
4. **예방**: 스크립트 개선 + 문서화

**핵심 교훈:**
- Kubernetes 버전 업그레이드 시 breaking changes 확인 필수
- 라벨/어노테이션은 커스텀 도메인 사용 권장
- 배포 스크립트에 사전 점검 및 정리 기능 필수

---

**작성일**: 2025-11-17  
**해결자**: Backend Team  
**소요시간**: 약 2시간 (진단 30분 + 수정 1시간 + 검증 30분)


