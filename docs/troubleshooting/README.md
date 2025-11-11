# Troubleshooting 가이드

클러스터 구축 및 운영 중 발생하는 문제들의 해결 방법을 정리한 문서입니다.

---

## 📋 목차

- [인프라 관련](#인프라-관련)
- [네트워크 관련](#네트워크-관련)
- [스케줄링 관련](#스케줄링-관련)
- [애플리케이션 관련](#애플리케이션-관련)
- [로컬 환경 관련](#로컬-환경-관련)

---

## 인프라 관련

### 🗑️ VPC 삭제 지연 및 Security Group 삭제 실패
**파일**: [VPC_DELETION_DELAY.md](./VPC_DELETION_DELAY.md)

**문제 요약**:
- `destroy-with-cleanup.sh` 실행 시 VPC 삭제가 5분 이상 지연
- Kubernetes ALB Controller가 생성한 Security Groups가 남아있음
- Security Groups 간 순환 참조로 인한 삭제 실패

**주요 원인**:
- ALB가 Security Group을 사용 중인 상태에서 삭제 시도
- ALB 삭제가 비동기로 처리되어 완전 삭제 전에 다음 단계 진행
- ENI가 detaching 상태에서 삭제 시도

**해결 방법**:
- 개선된 `destroy-with-cleanup.sh` 사용 (자동)
- 또는 수동으로 ALB → Security Group 순서로 삭제

**영향**:
- 전체 삭제 시간 50% 단축 (7-10분 → 3-5분)
- VPC 삭제 지연 완전 해결

---

### 🔌 ALB Provider ID 누락으로 인한 Target 등록 실패
**파일**: [ALB_PROVIDER_ID.md](./ALB_PROVIDER_ID.md)

**문제 요약**:
- ALB Controller가 Worker 노드를 Target Group에 등록하지 못함
- `growbin.app` 접속 시 503 Service Unavailable 발생
- ALB Controller 로그에 `providerID is not specified` 에러

**주요 원인**:
```bash
# 잘못된 providerID
spec.providerID: "k8s-worker-1"  # ❌ Instance ID 누락

# 올바른 providerID
spec.providerID: "aws:///ap-northeast-2a/i-0123456789abcdef0"  # ✅
```

**해결 방법**:
- Ansible playbook에 자동 설정 로직 추가 (Worker join 시)
- 또는 Master 노드에서 수동으로 설정

**영향**:
- ALB Target 자동 등록 가능
- 외부 트래픽이 정상적으로 Pod에 도달

---

## 네트워크 관련

### 🌐 Route53 및 ALB 라우팅 문제
**파일**: [ROUTE53_ALB_ROUTING_FIX.md](./ROUTE53_ALB_ROUTING_FIX.md)

**문제 요약**:
- `growbin.app`가 Master Node IP로 라우팅됨 (ALB 대신)
- Service가 ClusterIP 타입이어서 ALB가 생성되지 않음
- IAM 권한 부족으로 ALB Controller 동작 실패

**주요 원인**:
1. Route53 A 레코드가 Master Node의 Public IP를 직접 가리킴
2. ArgoCD, Grafana, Default Backend Service가 `ClusterIP` 타입
3. ALB Controller IAM Policy에 필요한 권한 누락

**해결 방법**:
1. Service 타입을 `NodePort`로 변경
2. Route53 A 레코드를 ALB Alias 레코드로 변경
3. IAM Policy에 `AddTags`, `DescribeListenerAttributes` 권한 추가

**영향**:
- 외부 트래픽이 ALB를 통해 정상 라우팅
- HTTPS 인증서 자동 적용
- 경로 기반 라우팅 정상 작동 (`/argocd`, `/grafana`, `/api`)

---

## 스케줄링 관련

### 📦 PostgreSQL Pod 스케줄링 실패
**파일**: [POSTGRESQL_SCHEDULING_ERROR.md](./POSTGRESQL_SCHEDULING_ERROR.md)

**문제 요약**:
- PostgreSQL Pod이 `FailedScheduling` 상태로 Pending
- `nodeSelector: workload=database`를 만족하는 노드가 없음

**주요 원인**:
```bash
# Ansible playbook에 nodeSelector 설정 누락
# 또는 node label 누락

# 필요한 설정
kubectl label nodes k8s-postgresql workload=database --overwrite
```

**해결 방법**:
1. 노드에 적절한 label 추가
2. Ansible playbook에 node labeling 로직 추가
3. Pod 재시작 (자동 스케줄링)

**영향**:
- PostgreSQL이 전용 Storage 노드에 배치
- 리소스 격리 및 성능 최적화

---

## 애플리케이션 관련

### 🚫 ArgoCD 502 Bad Gateway 문제
**파일**: [ARGOCD_502_BAD_GATEWAY.md](./ARGOCD_502_BAD_GATEWAY.md)

**문제 요약**:
- `https://growbin.app/argocd` 접속 시 502 Bad Gateway 발생
- ALB Target Health가 모두 Unhealthy 상태
- ALB Controller 로그에 Health Check 실패

**주요 원인**:
```yaml
# Ingress 설정
alb.ingress.kubernetes.io/backend-protocol: HTTPS  # ❌
service.port.number: 443

# 하지만 ArgoCD는
server.insecure: "true"  # HTTP만 지원
실제 포트: 8080 (HTTP)

→ 프로토콜 불일치!
```

**해결 방법**:
1. Ingress annotation을 `backend-protocol: HTTP`로 변경
2. Service Port를 `443` → `80`으로 변경
3. Ansible playbook 업데이트

**영향**:
- ArgoCD 정상 접속 가능
- Target Health가 healthy 상태로 전환
- 서브 경로 (`/argocd`) 라우팅 정상 작동

---

### 📊 Prometheus Pod Pending 문제
**파일**: [PROMETHEUS_PENDING.md](./PROMETHEUS_PENDING.md)

**문제 요약**:
- Prometheus Pod이 `Pending` 상태에서 스케줄링되지 않음
- `FailedScheduling: 0/7 nodes available: 1 Insufficient cpu`
- k8s-monitoring 노드 (t3.large, 2 vCPU)의 CPU 부족

**주요 원인**:
```
k8s-monitoring 노드 (2000m CPU):
  현재 사용:
    - Calico: 250m
    - EBS CSI: 30m
    - Metrics Server: 100m
    - Alertmanager: 250m
    - Grafana: 500m
    합계: 1130m (56%)

  Prometheus 요청: 1000m

  필요 총량: 2130m > 2000m ❌
```

**해결 방법**:

**Option 1**: Prometheus CPU 요청 낮추기 (채택)
```bash
# 1000m → 500m 변경
kubectl patch prometheus prometheus-kube-prometheus-prometheus -n monitoring --type merge -p '{
  "spec": {
    "resources": {
      "requests": {
        "cpu": "500m",
        "memory": "2Gi"
      }
    }
  }
}'
```

**Option 2**: 노드 업그레이드 (t3.large → t3.xlarge)

**영향**:
- Prometheus Pod 정상 스케줄링
- 500m CPU도 충분 (CPU 버스트 가능)
- 여유 CPU: 370m (18%)

---

## 로컬 환경 관련

### 🔐 macOS TLS Certificate 오류
**파일**: [MACOS_TLS_CERTIFICATE_ERROR.md](./MACOS_TLS_CERTIFICATE_ERROR.md)

**문제 요약**:
- macOS에서 Terraform 실행 시 TLS certificate verification 실패
- `x509: certificate signed by unknown authority` 에러
- Go 기반 도구들 (Terraform, kubectl 등)에서 공통적으로 발생

**주요 원인**:
- macOS 시스템 인증서 저장소 문제
- Go가 macOS 시스템 인증서를 인식하지 못함

**해결 방법**:

**Option 1**: Docker 사용 (권장)
```bash
docker run --rm -v $(pwd):/workspace -w /workspace hashicorp/terraform:latest init
```

**Option 2**: TLS 검증 임시 비활성화 (개발 환경만)
```bash
export GODEBUG=x509ignoreCN=0
export SSL_CERT_FILE=/etc/ssl/cert.pem
```

**Option 3**: macOS 인증서 업데이트
```bash
# Keychain Access에서 인증서 갱신
```

**영향**:
- Terraform init/apply 정상 실행
- S3 Backend 연결 정상화

---

## 문제 해결 우선순위

| 우선순위 | 문제 | 영향도 | 긴급도 |
|---------|------|-------|--------|
| 🔴 High | ALB Provider ID | ⭐⭐⭐ | 즉시 |
| 🔴 High | Route53 ALB 라우팅 | ⭐⭐⭐ | 즉시 |
| 🔴 High | ArgoCD 502 Bad Gateway | ⭐⭐⭐ | 즉시 |
| 🟡 Medium | Prometheus Pending | ⭐⭐ | 1시간 이내 |
| 🟡 Medium | PostgreSQL 스케줄링 | ⭐⭐ | 1시간 이내 |
| 🟡 Medium | VPC 삭제 지연 | ⭐⭐ | 비긴급 |
| 🟢 Low | macOS TLS 오류 | ⭐ | 비긴급 |

---

## 일반적인 디버깅 절차

### 1. 문제 식별

```bash
# 클러스터 상태 확인
kubectl get nodes
kubectl get pods -A

# 특정 Pod 상세 확인
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace>

# Ingress 상태 확인
kubectl get ingress -A
kubectl describe ingress <ingress-name> -n <namespace>

# Service 상태 확인
kubectl get svc -A
```

### 2. AWS 리소스 확인

```bash
# VPC 리소스
aws ec2 describe-vpcs --region ap-northeast-2
aws ec2 describe-security-groups --filters "Name=group-name,Values=k8s-*" --region ap-northeast-2

# Load Balancer
aws elbv2 describe-load-balancers --region ap-northeast-2
aws elbv2 describe-target-groups --region ap-northeast-2

# ENI
aws ec2 describe-network-interfaces --filters "Name=vpc-id,Values=<vpc-id>" --region ap-northeast-2
```

### 3. 로그 확인

```bash
# ALB Controller 로그
kubectl logs -n kube-system deployment/aws-load-balancer-controller

# CoreDNS 로그
kubectl logs -n kube-system deployment/coredns

# Calico 로그
kubectl logs -n kube-system daemonset/calico-node
```

### 4. 네트워크 테스트

```bash
# Pod에서 외부 연결 테스트
kubectl run -it --rm debug --image=nicolaka/netshoot --restart=Never -- /bin/bash
> curl https://www.google.com
> nslookup growbin.app

# Service 연결 테스트
kubectl run -it --rm debug --image=nicolaka/netshoot --restart=Never -- /bin/bash
> curl http://<service-name>.<namespace>.svc.cluster.local
```

---

## 유용한 스크립트

### 클러스터 전체 상태 확인
```bash
./scripts/diagnostics/check-cluster-health.sh
```

### 특정 서비스 진단
```bash
./scripts/diagnostics/diagnose-postgresql.sh
./scripts/diagnostics/diagnose-redis.sh
```

### 원격 진단 (Master 노드에서)
```bash
./scripts/diagnostics/run-diagnosis-on-master.sh
```

---

## 추가 리소스

### 관련 문서
- [REBUILD_GUIDE.md](../REBUILD_GUIDE.md) - 클러스터 재구축 가이드
- [MANUAL_OPERATIONS_TO_IAC.md](../MANUAL_OPERATIONS_TO_IAC.md) - 수동 작업 자동화 문서
- [CODE_REVIEW_RESULT.md](../CODE_REVIEW_RESULT.md) - 인프라 코드 리뷰 결과

### AWS 문서
- [Amazon VPC 사용자 가이드](https://docs.aws.amazon.com/vpc/latest/userguide/)
- [Application Load Balancer](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/)
- [AWS Load Balancer Controller](https://kubernetes-sigs.github.io/aws-load-balancer-controller/)

### Kubernetes 문서
- [Troubleshooting Applications](https://kubernetes.io/docs/tasks/debug/)
- [Debug Pods](https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/)
- [Debug Services](https://kubernetes.io/docs/tasks/debug/debug-application/debug-service/)

---

## 문의 및 지원

문제가 해결되지 않거나 문서에 없는 새로운 이슈가 발생한 경우:

1. GitHub Issues에 문제 보고
2. 로그 및 상태 정보 첨부
3. 재현 가능한 단계 설명

**템플릿**:
```markdown
### 문제 요약
(간단한 설명)

### 재현 단계
1. ...
2. ...

### 예상 동작
(무엇을 기대했는지)

### 실제 동작
(실제로 무슨 일이 일어났는지)

### 환경 정보
- Kubernetes 버전: 
- AWS 리전: 
- 영향받는 서비스: 

### 로그
```
(로그 첨부)
```
```

---

**마지막 업데이트**: 2025-11-04  
**담당**: Infrastructure Team

