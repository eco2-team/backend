# 🔍 Ansible 사전 점검 체크리스트

## 1️⃣ Security Group 포트 검증

### Master SG (필수 포트)

```
Inbound:
✅ 22 (SSH) - 백업 접속
✅ 6443 (K8s API) - 0.0.0.0/0 + Worker SG
✅ 80 (HTTP) - Ingress
✅ 443 (HTTPS) - Ingress
✅ 2379-2380 (etcd) - Self
✅ 10250-10252 (Kubelet, Scheduler, Controller) - Worker SG

Outbound:
✅ All traffic (0.0.0.0/0)

⚠️ 누락 확인:
- [ ] Worker SG → Master 6443 (방금 추가했는지 확인 필요)
```

### Worker SG (필수 포트)

```
Inbound:
✅ 22 (SSH)
✅ 10250 (Kubelet) - Master SG
✅ 30000-32767 (NodePort) - Master SG
✅ All from Master SG
✅ Self (Worker 간 통신)

Outbound:
✅ All traffic

⚠️ 중요:
- [ ] Master 6443 포트 접근 가능한지 (terraform apply 필요)
```

---

## 2️⃣ Containerd 설정 검증

### 현재 설정 확인

```yaml
# ansible/roles/docker/tasks/main.yml

필수 항목:
✅ SystemdCgroup = true
✅ disabled_plugins에 "cri" 없음
✅ sandbox_image = "registry.k8s.io/pause:3.9"
✅ /etc/crictl.yaml 생성
✅ containerd 소켓 확인

추가 확인:
- [ ] containerd.service 활성화
- [ ] daemon_reload
```

---

## 3️⃣ Ansible Playbook 순서 검증

### site.yml 실행 순서

```
1. Prerequisites (OS 설정)
   ├─ 스왑 비활성화 ✅
   ├─ 커널 모듈 ✅
   └─ sysctl 설정 ✅

2. Docker 설치
   ├─ containerd 설치 ✅
   ├─ containerd 설정 ✅
   └─ crictl 설정 ✅

3. Kubernetes 설치
   ├─ kubeadm, kubelet, kubectl ✅
   └─ hold (자동 업그레이드 방지) ✅

4. Master 초기화
   ├─ kubeadm init ✅
   ├─ kubeconfig 설정 ✅
   ├─ API 서버 대기 ✅ (새로 추가)
   └─ join 명령어 생성 ✅

5. CNI 설치
   └─ Flannel ✅

6. Worker 조인
   ├─ join 스크립트 복사 ✅
   ├─ shebang 추가 ✅ (새로 추가)
   └─ bash 실행 ✅

7. Add-ons
   ├─ Nginx Ingress ✅
   ├─ Cert-manager ✅
   └─ Metrics Server ✅

8. ArgoCD ✅
9. RabbitMQ ✅
10. Monitoring ✅
```

---

## 4️⃣ 네트워크 연결성 체크

### 필수 연결

```
Master ↔ Worker:
✅ Master 10.0.1.218:6443 ← Worker (K8s API)
✅ Worker 10250 ← Master (Kubelet)
✅ Worker 30000-32767 ← Master (NodePort)

Master 자체:
✅ 127.0.0.1:6443 (API Server)
✅ 127.0.0.1:2379-2380 (etcd)
✅ 127.0.0.1:10250 (Kubelet)

Worker 간:
✅ All traffic (Pod network)
```

---

## 5️⃣ 이전 설치 흔적 제거

### kubeadm reset 필요 여부

```bash
# Master 노드에서 확인
ls -la /etc/kubernetes/

# 있으면 이전 설치 흔적
# kubeadm reset 필요

sudo kubeadm reset -f
sudo rm -rf /etc/kubernetes/
sudo rm -rf /var/lib/etcd/
sudo rm -rf /var/lib/kubelet/
sudo rm -rf /etc/cni/net.d/

# Worker 노드도 동일하게
```

---

## 6️⃣ Terraform 재적용 필수 사항

### Security Group 업데이트

```bash
cd terraform

# ⚠️ 중요: 새로 추가한 규칙 적용
terraform plan

# 확인할 것:
# + aws_security_group_rule.worker_to_master_api (6443)

terraform apply

# 반드시 apply 해야 Worker join 성공!
```

---

## 7️⃣ 점검 체크리스트

### Terraform 단계

```
- [ ] terraform destroy 완료
- [ ] terraform apply 완료
- [ ] Security Group 규칙 확인 (worker_to_master_api 생성됨)
- [ ] Master IP 확인
- [ ] Ansible inventory 재생성 (terraform output)
```

### Ansible 전 단계

```
- [ ] 모든 노드 kubeadm reset (이전 설치 제거)
- [ ] /etc/kubernetes/ 디렉토리 삭제
- [ ] containerd 재시작
- [ ] crictl 설정 확인 (/etc/crictl.yaml)
```

### Ansible 실행 전 테스트

```bash
# SSH 연결 테스트
ansible all -i inventory/hosts.ini -m ping
# ✅ 모두 SUCCESS

# containerd 상태 확인
ansible all -i inventory/hosts.ini -m shell -a "sudo systemctl status containerd" | grep Active
# ✅ active (running)
```

---

## ⚠️ 주요 체크 포인트

### 1. Security Group (가장 중요!)

```bash
# terraform apply 후 확인
aws ec2 describe-security-groups \
  --group-ids <MASTER_SG_ID> \
  --query 'SecurityGroups[].IpPermissions[?FromPort==`6443`]'

# Worker SG에서 6443 포트 접근 가능한지 확인
```

### 2. containerd 설정

```bash
# 모든 노드에서
sudo crictl info | grep -i runtimeType
# 출력: "runtimeType": "containerd"

sudo crictl images | head -5
# pause 이미지 보여야 함
```

### 3. 깨끗한 상태

```bash
# kubeadm reset 확인
ls /etc/kubernetes/
# No such file or directory ← 깨끗함
```

---

## 🚀 권장 실행 순서

```
1. Terraform destroy + apply (Security Group 포함)
   └─ 약 10분

2. 모든 노드 정리 (선택, 안전)
   └─ sudo kubeadm reset -f
   └─ sudo rm -rf /etc/kubernetes/

3. Ansible 재실행
   └─ ansible-playbook site.yml
   └─ 약 35분

총: 45분
```

---

## 📋 필수 확인 사항

```
⚠️ Terraform apply 후:
aws ec2 describe-security-groups --group-ids sg-xxx \
  --query 'SecurityGroups[].IpPermissions[*].[FromPort,ToPort,IpProtocol,UserIdGroupPairs]'

6443 포트 규칙 있는지 확인!

없으면 Worker join 실패!
```

**terraform apply → Security Group 확인 → ansible 실행** 순서 지키세요! ✅
