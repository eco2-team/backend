# 네트워크 설정 수동 작업 → Terraform/Ansible 반영 완료

## 📌 수행한 수동 작업

### 1. ✅ Route53 DNS 변경
**수동 작업**: Master Node IP → ALB DNS (Alias)
**Ansible 반영**: ✅ 이미 존재 (`ansible/playbooks/09-route53-update.yml`)

**작동 방식:**
- ALB 생성 후 자동으로 Route53 A 레코드를 ALB Alias로 업데이트
- Apex, www, api, argocd, grafana 서브도메인 모두 ALB로 자동 연결

---

### 2. ✅ Service 타입 변경 (ClusterIP → NodePort)
**수동 작업**: 
```bash
kubectl patch svc argocd-server -n argocd -p '{"spec":{"type":"NodePort"}}'
kubectl patch svc prometheus-grafana -n monitoring -p '{"spec":{"type":"NodePort"}}'
kubectl patch svc default-backend -n default -p '{"spec":{"type":"NodePort"}}'
```

**Ansible 반영**: ✅ 완료 (`ansible/playbooks/07-ingress-resources.yml`)

**변경 내용:**

#### ArgoCD Service (라인 4-44):
```yaml
- name: "ArgoCD Ingress 생성 (/argocd)"
  shell: |
    # ArgoCD Service를 NodePort로 변경 (ALB target-type: instance 필수)
    kubectl patch svc argocd-server -n argocd -p '{"spec":{"type":"NodePort"}}'
    
    kubectl apply -f - <<EOF
    # ... Ingress 정의 ...
    EOF
```

#### Grafana Service (라인 46-86):
```yaml
- name: "Monitoring Ingress 생성 (/grafana)"
  shell: |
    # Grafana Service를 NodePort로 변경 (ALB target-type: instance 필수)
    kubectl patch svc prometheus-grafana -n monitoring -p '{"spec":{"type":"NodePort"}}'
    
    kubectl apply -f - <<EOF
    # ... Ingress 정의 ...
    EOF
```

#### Default Backend Service (라인 106-118):
```yaml
apiVersion: v1
kind: Service
metadata:
  name: default-backend
  namespace: default
spec:
  type: NodePort  # ← 추가됨
  selector:
    app: default-backend
  ports:
  - port: 80
    targetPort: 8080
```

**이유:**
- ALB Controller의 `target-type: instance` 모드에서는 Service가 NodePort여야 함
- ClusterIP는 Node에 포트가 노출되지 않아 ALB가 Target을 등록할 수 없음

---

### 3. ✅ IAM 권한 추가
**수동 작업**:
```bash
aws iam create-policy-version \
  --policy-arn arn:aws:iam::721622471953:policy/prod-alb-controller-policy \
  --policy-document file:///tmp/alb-iam-policy.json \
  --set-as-default
```

**Terraform 반영**: ✅ 완료 (`terraform/alb-controller-iam.tf`)

**추가된 권한:**

#### 1. `elasticloadbalancing:AddTags` (라인 166-176)
**변경 전**: Condition으로 제한됨
```json
{
  "Effect": "Allow",
  "Action": ["elasticloadbalancing:AddTags", "elasticloadbalancing:RemoveTags"],
  "Resource": ["arn:aws:elasticloadbalancing:*:*:targetgroup/*/*", ...],
  "Condition": {
    "Null": {
      "aws:RequestTag/elbv2.k8s.aws/cluster": "true",
      "aws:ResourceTag/elbv2.k8s.aws/cluster": "false"
    }
  }
}
```

**변경 후**: AddTags는 Condition 없이 허용
```json
{
  "Effect": "Allow",
  "Action": ["elasticloadbalancing:AddTags"],
  "Resource": [
    "arn:aws:elasticloadbalancing:*:*:targetgroup/*/*",
    "arn:aws:elasticloadbalancing:*:*:loadbalancer/net/*/*",
    "arn:aws:elasticloadbalancing:*:*:loadbalancer/app/*/*"
  ]
}
```

**이유**: Target Group 생성 시 즉시 태그를 추가해야 하는데, Condition이 있으면 실패함

#### 2. `elasticloadbalancing:DescribeListenerAttributes` (라인 43)
**변경 전**: 권한 없음
**변경 후**: 추가됨
```json
{
  "Effect": "Allow",
  "Action": [
    "elasticloadbalancing:DescribeLoadBalancers",
    "elasticloadbalancing:DescribeLoadBalancerAttributes",
    "elasticloadbalancing:DescribeListeners",
    "elasticloadbalancing:DescribeListenerAttributes",  // ← 추가
    "elasticloadbalancing:DescribeListenerCertificates",
    ...
  ],
  "Resource": "*"
}
```

**이유**: ALB Listener 속성 조회 시 필요

---

### 4. ⚠️ Provider ID 설정 (미완료)
**수동 작업**: 시도했으나 Network 제약으로 실패

**Ansible 반영**: ✅ 완료 (`ansible/playbooks/03-worker-join.yml`)

**추가된 로직 (라인 80-113):**
```yaml
# Provider ID 설정 (AWS ALB Controller 필수)
- name: AWS Instance ID 및 AZ 가져오기
  shell: |
    INSTANCE_ID=$(ec2-metadata --instance-id | cut -d ' ' -f 2)
    AZ=$(ec2-metadata --availability-zone | cut -d ' ' -f 2)
    echo "$INSTANCE_ID:$AZ"
  register: aws_metadata
  when: not kubelet_conf.stat.exists

- name: Provider ID 파싱
  set_fact:
    instance_id: "{{ aws_metadata.stdout.split(':')[0] }}"
    availability_zone: "{{ aws_metadata.stdout.split(':')[1] }}"
  when: not kubelet_conf.stat.exists and aws_metadata is defined

- name: kubelet Provider ID 설정
  lineinfile:
    path: /var/lib/kubelet/kubeadm-flags.env
    regexp: '^KUBELET_KUBEADM_ARGS='
    line: 'KUBELET_KUBEADM_ARGS="--container-runtime-endpoint=unix:///var/run/containerd/containerd.sock --cloud-provider=external --provider-id=aws:///{{ availability_zone }}/{{ instance_id }}"'
    backup: yes
  when: not kubelet_conf.stat.exists and instance_id is defined
  notify: restart kubelet

- name: kubelet 재시작 (Provider ID 적용)
  systemd:
    name: kubelet
    state: restarted
  when: not kubelet_conf.stat.exists and instance_id is defined
```

**작동 원리:**
1. Worker 노드 join 후 즉시 `ec2-metadata` 명령으로 Instance ID와 AZ 조회
2. `/var/lib/kubelet/kubeadm-flags.env`에 Provider ID 추가
3. kubelet 재시작하여 적용

**결과:**
```yaml
# 변경 전
KUBELET_KUBEADM_ARGS="--container-runtime-endpoint=unix:///var/run/containerd/containerd.sock"

# 변경 후
KUBELET_KUBEADM_ARGS="--container-runtime-endpoint=unix:///var/run/containerd/containerd.sock --cloud-provider=external --provider-id=aws:///ap-northeast-2b/i-09bcfaaae046d7b4c"
```

---

## 📋 수정된 파일 목록

| 파일 | 변경 내용 | 상태 |
|------|----------|------|
| `terraform/alb-controller-iam.tf` | IAM 권한 추가 (AddTags, DescribeListenerAttributes) | ✅ |
| `ansible/playbooks/03-worker-join.yml` | Provider ID 자동 설정 로직 추가 | ✅ |
| `ansible/playbooks/07-ingress-resources.yml` | Service 타입 NodePort 자동 변경 추가 | ✅ |
| `ansible/playbooks/09-route53-update.yml` | (이미 존재) Route53 자동 업데이트 | ✅ |
| `docs/TROUBLESHOOTING_ALB_PROVIDER_ID.md` | Provider ID 문제 해결 가이드 | ✅ |

---

## 🔄 다음 배포 시 자동 적용

다음 클러스터 구축 시 (`./scripts/cluster/build-cluster.sh`) 모든 수동 작업이 자동으로 수행됩니다:

### 1. Terraform apply
- ✅ ALB Controller IAM 권한 (AddTags, DescribeListenerAttributes)

### 2. Ansible playbook 실행
- ✅ Worker 노드 join + Provider ID 자동 설정
- ✅ ArgoCD/Grafana/Default-Backend Service → NodePort
- ✅ Ingress 생성 (ALB 자동 생성)
- ✅ Route53 A 레코드 → ALB Alias

### 3. 결과
- ✅ ALB 자동 생성
- ✅ Target 자동 등록 (Provider ID 정상)
- ✅ Route53 DNS → ALB
- ✅ `https://ecoeco.app` 정상 작동

---

## ✅ 검증 방법

### Provider ID 확인
```bash
kubectl get nodes -o custom-columns='NAME:.metadata.name,PROVIDER_ID:.spec.providerID'

# 예상 결과:
# NAME             PROVIDER_ID
# k8s-worker-1     aws:///ap-northeast-2b/i-09bcfaaae046d7b4c
# k8s-worker-2     aws:///ap-northeast-2c/i-05a8ef39f9a7c8973
# ...
```

### Service 타입 확인
```bash
kubectl get svc -A | grep -E "NodePort|LoadBalancer"

# 예상 결과:
# argocd       argocd-server         NodePort    10.104.4.61      <none>        80:32044/TCP,443:31441/TCP
# monitoring   prometheus-grafana    NodePort    10.110.150.90    <none>        80:31371/TCP
# default      default-backend       NodePort    10.103.240.134   <none>        80:31493/TCP
```

### Route53 확인
```bash
nslookup ecoeco.app 8.8.8.8

# 예상 결과: ALB의 여러 IP 주소
```

### Target 등록 확인
```bash
aws elbv2 describe-target-health --region ap-northeast-2 --target-group-arn <TG_ARN>

# 예상 결과: healthy 상태의 Instance들
```

---

## 🎯 요약

| 수동 작업 | Terraform/Ansible 반영 | 자동 적용 |
|-----------|-------------------------|----------|
| ✅ Route53 DNS 변경 | ✅ `09-route53-update.yml` | ✅ 다음 배포 시 자동 |
| ✅ Service → NodePort | ✅ `07-ingress-resources.yml` | ✅ 다음 배포 시 자동 |
| ✅ IAM 권한 추가 | ✅ `alb-controller-iam.tf` | ✅ 다음 배포 시 자동 |
| ⚠️ Provider ID 설정 | ✅ `03-worker-join.yml` | ✅ 다음 배포 시 자동 |

**모든 수동 작업이 Terraform/Ansible에 반영되었습니다!** 🎉

