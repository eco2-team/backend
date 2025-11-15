# Node Taint 자동화 가이드

**문서 버전**: v0.8.1  
**최종 업데이트**: 2025-11-12  
**참고**: Kubernetes Best Practices - Infrastructure as Code

---

## 🎯 Node Taint 관리 전략

### 계층 분리 원칙

| Layer | 관리 대상 | 도구 | 책임 |
|-------|----------|------|------|
| **Infrastructure** | Node Taint | Terraform/Ansible/kubectl | Cluster Admin |
| **Application** | Pod Toleration | Kustomize/Helm/ArgoCD | Developer |

**중요**: Node Taint는 **인프라 속성**이므로 Application manifest 도구(Kustomize/Helm)로 관리하지 않음.

---

## 🔧 현재 설정 (Manual)

### 설정된 Taint

```bash
# API 전용 노드 (2025-11-12 설정)
kubectl taint nodes k8s-api-auth domain=auth:NoSchedule
kubectl taint nodes k8s-api-my domain=my:NoSchedule
kubectl taint nodes k8s-api-scan domain=scan:NoSchedule
kubectl taint nodes k8s-api-character domain=character:NoSchedule
kubectl taint nodes k8s-api-location domain=location:NoSchedule
kubectl taint nodes k8s-api-chat domain=chat:NoSchedule

# info 노드는 NotReady 상태로 제외
```

### 설정 확인

```bash
# 모든 API 노드의 Taint 확인
kubectl get nodes -l workload=api -o custom-columns=\
NAME:.metadata.name,\
TAINTS:.spec.taints[*].key

# 특정 노드 상세 확인
kubectl describe node k8s-api-auth | grep Taints
```

---

## 🤖 Ansible 자동화 (권장)

### 1. Ansible Role 구조

```
ansible/roles/k8s-taints/
├── tasks/
│   └── main.yml
├── defaults/
│   └── main.yml
└── README.md
```

### 2. Ansible Playbook

```yaml
# ansible/roles/k8s-taints/tasks/main.yml
---
- name: Apply taints to API nodes
  kubernetes.core.k8s:
    api_version: v1
    kind: Node
    name: "{{ item.node_name }}"
    resource_definition:
      spec:
        taints:
          - key: domain
            value: "{{ item.domain }}"
            effect: NoSchedule
  loop:
    - { node_name: 'k8s-api-auth', domain: 'auth' }
    - { node_name: 'k8s-api-my', domain: 'my' }
    - { node_name: 'k8s-api-scan', domain: 'scan' }
    - { node_name: 'k8s-api-character', domain: 'character' }
    - { node_name: 'k8s-api-location', domain: 'location' }
    - { node_name: 'k8s-api-info', domain: 'info' }
    - { node_name: 'k8s-api-chat', domain: 'chat' }
  when: item.node_name in ansible_play_hosts
```

### 3. 실행 방법

```bash
# Ansible로 Taint 적용
cd ansible
ansible-playbook -i inventory/hosts.ini playbooks/apply-node-taints.yml

# Dry-run (테스트)
ansible-playbook -i inventory/hosts.ini playbooks/apply-node-taints.yml --check
```

---

## 🏗️ Terraform 통합 (선택사항)

### AWS Node Label → Kubernetes Taint

```hcl
# terraform/modules/eks-nodes/main.tf
resource "aws_instance" "api_node" {
  for_each = var.api_domains

  tags = {
    "kubernetes.io/taint/domain" = "${each.key}:NoSchedule"
    "kubernetes.io/label/domain" = each.key
  }
}
```

**장점**: EC2 생성 시 자동으로 Taint 설정  
**단점**: Terraform으로 K8s API 직접 제어 필요 (복잡도 증가)

---

## ✅ Application Layer: Pod Toleration (Kustomize)

### 각 API Overlay에 Toleration 설정

```yaml
# k8s/overlays/auth/deployment-patch.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  template:
    spec:
      nodeSelector:
        domain: auth
      tolerations:
      - key: domain
        operator: Equal
        value: auth
        effect: NoSchedule
```

**패턴**:
- `nodeSelector`: 특정 노드 **선택**
- `tolerations`: 해당 노드의 Taint **허용**

---

## 🔄 Workflow

### 신규 API 추가 시

```
1. [Infrastructure] Ansible로 Node Taint 설정
   $ ansible-playbook apply-node-taints.yml

2. [Application] Kustomize Overlay 생성
   $ mkdir k8s/overlays/new-api/
   $ cat > k8s/overlays/new-api/deployment-patch.yaml << EOF
   tolerations:
   - key: domain
     value: new-api
     effect: NoSchedule
   EOF

3. [GitOps] ArgoCD ApplicationSet에 추가
   $ vim argocd/applications/ecoeco-appset-kustomize.yaml
```

### 노드 교체 시

```
1. 새 노드 생성 (Terraform/Ansible)
2. Ansible로 Taint 자동 적용
3. 기존 노드 drain & delete
4. Application은 자동으로 새 노드로 이동 (Toleration 덕분)
```

---

## 🎓 베스트 프랙티스 체크리스트

### Infrastructure Layer
- [x] Node Taint를 kubectl/Ansible/Terraform로 관리
- [x] Taint 설정을 문서화
- [ ] Ansible Playbook으로 자동화 (권장)
- [ ] 노드 프로비저닝 시 자동 적용 (선택)

### Application Layer
- [x] Kustomize Overlay에 Toleration 설정
- [x] nodeSelector와 Toleration 조합 사용
- [x] 각 API가 독립적인 Overlay 보유
- [ ] 나머지 6개 API Overlay 생성 (진행 예정)

---

## 📚 참고 문서

### Kubernetes 공식 문서
- [Taints and Tolerations](https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/)
- [Assigning Pods to Nodes](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/)

### Ansible Kubernetes Module
- [kubernetes.core.k8s](https://docs.ansible.com/ansible/latest/collections/kubernetes/core/k8s_module.html)

### Kustomize Best Practices
- [Strategic Merge Patch](https://kubectl.docs.kubernetes.io/references/kustomize/patches/)

---

## 📝 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|-----------|
| 2025-11-12 | v0.8.1 | Node Taint 관리 전략 및 자동화 가이드 작성 |

---

**작성자**: Claude Sonnet 4.5 Thinking, mango  
**최종 업데이트**: 2025-11-12

