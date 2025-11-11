# ALB Controller Provider ID 문제 해결

## 📌 문제 요약

**증상**:
- ALB가 생성되었지만 Target Group에 Instance가 등록되지 않음
- `https://growbin.app` 접속 시 `503 Service Unavailable` 발생
- Ingress의 `ADDRESS` 필드가 비어있음

**원인**:
- Worker 노드의 `spec.providerID`가 불완전하게 설정됨
- 현재 값: `aws:///ap-northeast-2a/` (Instance ID 누락)
- 필요한 값: `aws:///ap-northeast-2b/i-09bcfaaae046d7b4c`

---

## 🔍 문제 발견 과정

### 1. ALB는 생성되었지만 503 에러 발생

```bash
$ curl -I https://growbin.app
HTTP/2 503
server: awselb/2.0
```

### 2. Target Group에 Instance가 없음

```bash
$ aws elbv2 describe-target-health --target-group-arn <TG_ARN>
{
    "TargetHealthDescriptions": []
}
```

### 3. ALB Controller 로그에서 에러 발견

```bash
$ kubectl logs -n kube-system deployment/aws-load-balancer-controller --tail=50 | grep error

{"level":"error","msg":"Reconciler error","error":"providerID is not specified for node: k8s-worker-1"}
{"level":"error","msg":"Reconciler error","error":"providerID is not specified for node: k8s-worker-2"}
{"level":"error","msg":"Reconciler error","error":"providerID is not specified for node: k8s-monitoring"}
```

### 4. 노드의 Provider ID 확인

```bash
$ kubectl get nodes -o custom-columns='NAME:.metadata.name,PROVIDER_ID:.spec.providerID'

NAME             PROVIDER_ID
k8s-master       <none>
k8s-monitoring   aws:///ap-northeast-2a/
k8s-postgresql   aws:///ap-northeast-2a/
k8s-rabbitmq     aws:///ap-northeast-2a/
k8s-redis        aws:///ap-northeast-2a/
k8s-worker-1     aws:///ap-northeast-2a/
k8s-worker-2     aws:///ap-northeast-2a/
```

**문제**: Instance ID가 누락됨!

---

## ⚠️ 왜 이 문제가 발생했는가?

### 근본 원인

**Ansible Worker Join Playbook에서 Provider ID 자동 설정이 누락됨**

`ansible/playbooks/03-worker-join.yml`에서 Worker 노드가 클러스터에 join한 후, kubelet의 Provider ID를 설정하는 로직이 없었습니다.

### Provider ID가 중요한 이유

AWS Load Balancer Controller는 다음과 같은 과정으로 작동합니다:

1. Ingress 리소스를 감지
2. Service의 NodePort 확인
3. **각 노드의 `spec.providerID`에서 AWS Instance ID 추출**
4. ALB Target Group에 Instance 등록

**Provider ID가 불완전하면 3번 단계에서 Instance ID를 찾지 못하고, Target 등록이 실패합니다.**

---

## ✅ 해결 방법

### Option 1: 수동 수정 (현재 클러스터)

#### 각 Worker 노드에서 직접 수정:

```bash
# Worker 노드 SSH 접속
ssh ubuntu@<WORKER_NODE_IP>

# 1. kubelet 중지
sudo systemctl stop kubelet

# 2. kubeadm-flags.env 백업
sudo cp /var/lib/kubelet/kubeadm-flags.env /var/lib/kubelet/kubeadm-flags.env.bak

# 3. Provider ID 추가
# Instance ID와 AZ를 실제 값으로 변경
sudo sed -i 's/"$/ --cloud-provider=external --provider-id=aws:\/\/\/ap-northeast-2b\/i-09bcfaaae046d7b4c"/' /var/lib/kubelet/kubeadm-flags.env

# 4. 수정된 내용 확인
cat /var/lib/kubelet/kubeadm-flags.env

# 5. kubelet 재시작
sudo systemctl start kubelet
sudo systemctl status kubelet
```

#### 모든 Worker 노드 정보:

| Node Name       | Instance ID         | Availability Zone | Private IP  |
|-----------------|---------------------|-------------------|-------------|
| k8s-worker-1    | i-09bcfaaae046d7b4c | ap-northeast-2b   | 10.0.2.57   |
| k8s-worker-2    | i-05a8ef39f9a7c8973 | ap-northeast-2c   | 10.0.3.125  |
| k8s-rabbitmq    | i-039672e9dbef43093 | ap-northeast-2a   | 10.0.1.146  |
| k8s-postgresql  | i-08f64b8d6e8ca0a22 | ap-northeast-2b   | 10.0.2.134  |
| k8s-redis       | i-049ff392632813341 | ap-northeast-2c   | 10.0.3.175  |
| k8s-monitoring  | i-0956fd40bdaaaaf80 | ap-northeast-2b   | 10.0.2.243  |

### Option 2: Ansible Playbook 수정 (근본 해결)

**`ansible/playbooks/03-worker-join.yml` 수정 완료!**

Worker join 후 자동으로 Provider ID를 설정하도록 다음 로직이 추가되었습니다:

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

---

## 🔄 다음 배포 시 자동 적용

다음 클러스터 재구축 시 Provider ID가 자동으로 올바르게 설정됩니다:

```bash
./scripts/cluster/build-cluster.sh
```

**확인 방법**:

```bash
# Master 노드 접속
ssh ubuntu@<MASTER_IP>

# Provider ID 확인
kubectl get nodes -o custom-columns='NAME:.metadata.name,PROVIDER_ID:.spec.providerID'

# 예상 결과:
# NAME             PROVIDER_ID
# k8s-worker-1     aws:///ap-northeast-2b/i-09bcfaaae046d7b4c
# k8s-worker-2     aws:///ap-northeast-2c/i-05a8ef39f9a7c8973
# ...
```

---

## 📊 Target 등록 확인

Provider ID 수정 후 약 30초 이내에 ALB Controller가 자동으로 Target을 등록합니다.

```bash
# TargetGroupBinding 상태 확인
kubectl get targetgroupbinding -A

# Target Health 확인
aws elbv2 describe-target-health \
  --region ap-northeast-2 \
  --target-group-arn <TG_ARN>

# 예상 결과:
# {
#     "TargetHealthDescriptions": [
#         {
#             "Target": {
#                 "Id": "i-09bcfaaae046d7b4c",
#                 "Port": 31493
#             },
#             "HealthCheckPort": "31493",
#             "TargetHealth": {
#                 "State": "healthy"
#             }
#         }
#     ]
# }
```

---

## 🚨 추가로 확인해야 할 사항

### 1. IAM 권한

ALB Controller가 작동하려면 다음 IAM 권한이 필요합니다:

```json
{
  "Effect": "Allow",
  "Action": [
    "elasticloadbalancing:AddTags",
    "elasticloadbalancing:DescribeListenerAttributes",
    "elasticloadbalancing:CreateTargetGroup",
    "elasticloadbalancing:RegisterTargets",
    "elasticloadbalancing:DeregisterTargets"
  ],
  "Resource": "*"
}
```

**이미 수정 완료**: `terraform/alb-controller-iam.tf`

### 2. Service 타입

Ingress의 backend Service는 반드시 `NodePort` 또는 `LoadBalancer` 타입이어야 합니다.

```bash
# Service 타입 확인
kubectl get svc -A | grep -E "NodePort|LoadBalancer"

# Service 타입 변경 (필요시)
kubectl patch svc <SERVICE_NAME> -n <NAMESPACE> -p '{"spec":{"type":"NodePort"}}'
```

**이미 수정 완료**:
- `argocd-server`: NodePort (31441)
- `prometheus-grafana`: NodePort (31371)
- `default-backend`: NodePort (31493)

### 3. Security Group

Worker 노드의 Security Group에서 ALB로부터의 Ingress를 허용해야 합니다.

```bash
# ALB Security Group ID 확인
aws elbv2 describe-load-balancers \
  --region ap-northeast-2 \
  --query 'LoadBalancers[0].SecurityGroups[]' \
  --output text

# Worker Security Group에 Ingress 규칙 추가 (Terraform으로 관리됨)
```

**이미 설정 완료**: Terraform에서 자동으로 ALB SG → Worker SG Ingress 규칙 생성

---

## 📝 관련 파일

- **Ansible Playbook**: `ansible/playbooks/03-worker-join.yml`
- **IAM Policy**: `terraform/alb-controller-iam.tf`
- **Ingress 설정**: `ansible/playbooks/07-ingress-resources.yml`
- **Build Script**: `scripts/cluster/build-cluster.sh`

---

## 🎯 요약

| 항목 | 문제 | 해결 |
|------|------|------|
| **Provider ID** | Instance ID 누락 | Ansible playbook 수정 완료 |
| **IAM 권한** | AddTags, DescribeListenerAttributes 누락 | IAM policy 업데이트 완료 |
| **Service 타입** | ClusterIP로 설정됨 | NodePort로 수동 변경 완료 |
| **Route53 DNS** | Master Node IP를 가리킴 | ALB DNS로 업데이트 완료 |

**다음 배포부터는 모든 설정이 자동으로 올바르게 적용됩니다.** ✅

---

## 📚 참고 자료

- [AWS Load Balancer Controller 공식 문서](https://kubernetes-sigs.github.io/aws-load-balancer-controller/)
- [Kubernetes Provider ID 문서](https://kubernetes.io/docs/concepts/architecture/nodes/#provider-id)
- [kubeadm 외부 Cloud Provider 설정](https://kubernetes.io/docs/tasks/administer-cluster/running-cloud-controller/)

