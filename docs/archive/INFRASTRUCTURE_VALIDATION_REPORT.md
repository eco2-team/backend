# 🔍 인프라 구성 검증 보고서

**작성일**: 2025-11-06  
**대상 브랜치**: develop  
**아키텍처**: 13 Node Microservices (1 Master + 6 API + 2 Worker + 4 Infra)

---

## 📋 Executive Summary

13노드 마이크로서비스 아키텍처의 Terraform, Ansible, Helm Charts, ArgoCD, ALB Ingress 구성을 평가했습니다.

### ✅ 전체 평가 결과

| 구성 요소 | 상태 | 적합성 | 주요 이슈 |
|-----------|------|--------|-----------|
| Terraform | ✅ 양호 | 적합 | 노드 태그 개선 필요 |
| Ansible | ⚠️ 주의 | 부분 적합 | 인벤토리 구조 불일치 |
| Helm Charts | ✅ 양호 | 적합 | Service 리소스 누락 |
| ArgoCD | ⚠️ 주의 | 부분 적합 | repoURL 업데이트 필요 |
| ALB Ingress | ⚠️ 주의 | 부분 적합 | ACM 인증서 미설정 |
| Ingress Rules | ✅ 양호 | 적합 | 6개 API 라우팅 완비 |

---

## 1️⃣ Terraform 13노드 구성 평가

### ✅ 강점

**1. 올바른 노드 분리**
```terraform
# 6개 API 노드 (각 도메인 독립)
- k8s-api-waste (t3.small, 2GB)      # 폐기물 분석 (High Traffic)
- k8s-api-auth (t3.micro, 1GB)       # 인증 (High Traffic)
- k8s-api-userinfo (t3.micro, 1GB)   # 사용자 정보 (Medium)
- k8s-api-location (t3.micro, 1GB)   # 지도/위치 (Medium)
- k8s-api-recycle-info (t3.micro, 1GB) # 재활용 정보 (Low)
- k8s-api-chat-llm (t3.small, 2GB)   # LLM 채팅 (High Traffic)

# 2개 Worker 노드
- k8s-worker-storage (t3.medium, 4GB)  # I/O 집약 (image-uploader, rule-retriever, beat)
- k8s-worker-ai (t3.medium, 4GB)       # Network 집약 (gpt5-analyzer, response-generator)

# 4개 Infrastructure 노드
- k8s-rabbitmq (t3.small, 2GB)
- k8s-postgresql (t3.small, 2GB)
- k8s-redis (t3.small, 2GB)
- k8s-monitoring (t3.large, 8GB)
```

**2. 리소스 최적화**
- 트래픽 패턴에 따른 인스턴스 타입 차등 배치
- Waste/Chat-LLM은 t3.small (2GB), 나머지 API는 t3.micro (1GB)
- 총 비용: ~$180/월 (이전 대비 최적화)

**3. 명확한 노드 네이밍**
- 용도 기반 이름 (descriptive naming)
- 서비스 도메인 명시

### ⚠️ 개선 필요 사항

**1. 노드 태그 불일치**

현재 Terraform 태그:
```terraform
tags = {
  Role     = "worker"
  Workload = "api"
  Service  = "waste"
  Traffic  = "high"
}
```

하지만 Ansible/Helm은 다른 라벨을 기대:
- Ansible: `service=waste`, `workload=api`
- Helm: `service: waste` (nodeSelector)

**해결책**: Terraform과 Ansible/Helm 라벨 통일

**2. IAM Instance Profile 미정의**
```terraform
iam_instance_profile  = aws_iam_instance_profile.k8s.name
```
- `aws_iam_instance_profile.k8s` 리소스가 정의되지 않음
- ECR/S3 접근, ALB 통합 등을 위한 IAM 역할 필요

**3. ALB 리소스 없음**
- Terraform에 ALB, Target Group, Listener 정의 없음
- 현재 Ingress Controller가 ALB를 자동 생성하도록 의존

---

## 2️⃣ Ansible 플레이북 검증

### ✅ 강점

**1. 노드 라벨링 플레이북 존재**
- `ansible/playbooks/label-nodes.yml`
- API 노드에 `service` 라벨 자동 할당
- Worker 노드에 `workload`, `type` 라벨 할당

**2. Modular 구조**
- 역할별 플레이북 분리
- 확장 가능한 구조

### ⚠️ 개선 필요 사항

**1. 인벤토리 그룹 불일치**

`ansible/playbooks/label-nodes.yml`:
```yaml
when: "'api_nodes' in group_names"
```

하지만 `terraform/templates/hosts.tpl`에서:
```jinja
[api_nodes]
k8s-api-waste ...
k8s-api-auth ...
```

**확인 필요**: 
- 실제 생성된 `ansible/inventory.ini` 파일의 그룹 이름
- Terraform outputs에서 생성하는 인벤토리 파일 확인

**2. 라벨링 조건문 복잡성**
```yaml
when: "workload is defined and 'api_nodes' not in group_names and 'workers' not in group_names"
```
- 조건이 복잡하고 오류 가능성
- 명시적 그룹 기반 라벨링 권장

**3. ALB Ingress Controller 설치 없음**
- Ansible 플레이북에 ALB Ingress Controller 설치 단계 없음
- Helm을 통한 수동 설치 필요

---

## 3️⃣ Helm Charts 마이크로서비스 적합성

### ✅ 강점

**1. 완벽한 6개 API 서비스 정의**
```yaml
api:
  waste:      /api/v1/waste      (3 replicas, t3.small node)
  auth:       /api/v1/auth       (2 replicas, t3.micro node)
  userinfo:   /api/v1/users      (2 replicas, t3.micro node)
  location:   /api/v1/locations  (2 replicas, t3.micro node)
  recycleInfo: /api/v1/recycle   (1 replica,  t3.micro node)
  chatLlm:    /api/v1/chat       (2 replicas, t3.small node)
```

**2. NodeSelector 정확히 설정**
```yaml
nodeSelector:
  service: waste  # k8s-api-waste 노드 타겟팅
```

**3. 5개 Worker Deployment 완비**
- image-uploader (Storage Worker)
- gpt5-analyzer (AI Worker)
- rule-retriever (Storage Worker)
- response-generator (AI Worker)
- task-scheduler (Celery Beat)

**4. 리소스 요청/제한 명확**
```yaml
resources:
  requests:
    cpu: 300m
    memory: 512Mi
  limits:
    cpu: 800m
    memory: 1024Mi
```

### ⚠️ 개선 필요 사항

**1. Service 리소스 누락**

각 API Deployment 파일:
```yaml
# charts/ecoeco-backend/templates/api/waste-deployment.yaml
apiVersion: apps/v1
kind: Deployment
# ... (Deployment만 정의됨)
```

**문제**: Service 리소스가 없음!

**해결책**: 각 Deployment 파일에 Service 정의 추가 필요
```yaml
---
apiVersion: v1
kind: Service
metadata:
  name: waste-api
  namespace: {{ .Values.namespaces.api }}
spec:
  type: ClusterIP
  selector:
    app: waste-api
  ports:
    - port: {{ .Values.api.waste.port }}
      targetPort: {{ .Values.api.waste.port }}
      protocol: TCP
```

**2. Health Check 엔드포인트 누락**
```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
```
- Deployment 템플릿에 liveness/readiness probe 없음
- ALB Health Check가 실패할 수 있음

**3. 환경 변수 관리**
```yaml
env:
  - name: SERVICE_NAME
    value: "waste-api"
```
- PostgreSQL, Redis, RabbitMQ 연결 정보가 하드코딩
- ConfigMap/Secret 참조 필요

**4. Namespace 생성 누락**
- `api`, `workers`, `data`, `messaging` 네임스페이스 사전 생성 필요
- Helm Chart에 Namespace 리소스 정의 없음

---

## 4️⃣ ArgoCD Application 설정

### ✅ 강점

**1. GitOps 자동 배포 설정**
```yaml
syncPolicy:
  automated:
    prune: true
    selfHeal: true
```

**2. Sync Wave 정의**
```yaml
syncWave:
  - wave: 0  # Namespaces & ConfigMaps
  - wave: 1  # Secrets
  - wave: 2  # Infrastructure
  - wave: 3  # Workers
  - wave: 4  # APIs
  - wave: 5  # Ingress
```

**3. Health Check Lua 스크립트**
- Deployment 상태 검증 로직 포함

### ⚠️ 개선 필요 사항

**1. Repository URL 미설정**
```yaml
repoURL: https://github.com/your-org/SeSACTHON  # ❌ 플레이스홀더
```

**해결책**:
```yaml
repoURL: https://github.com/SeSACTHON/backend
```

**2. Target Revision**
```yaml
targetRevision: main
```
- develop에서 테스트 시에는 `develop` 브랜치 지정 필요

**3. Namespace 범위**
```yaml
destination:
  namespace: api
```
- 단일 네임스페이스만 지정
- `workers`, `data`, `messaging` 네임스페이스는 어떻게 배포?

**해결책**: Multi-namespace 배포 설정 필요
- 옵션 1: 각 네임스페이스별 별도 Application
- 옵션 2: Helm Chart가 알아서 네임스페이스 생성하도록 수정

**4. Image Tag 관리**
```yaml
parameters:
  - name: global.image.tag
    value: "latest"
```
- `latest` 태그는 프로덕션에서 권장되지 않음
- CI/CD에서 SHA 기반 태그로 업데이트 필요

---

## 5️⃣ ALB Ingress Controller 설정

### ✅ 강점

**1. ALB Annotation 완비**
```yaml
annotations:
  alb.ingress.kubernetes.io/scheme: internet-facing
  alb.ingress.kubernetes.io/target-type: instance
  alb.ingress.kubernetes.io/healthcheck-path: /health
  alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}, {"HTTPS": 443}]'
  alb.ingress.kubernetes.io/ssl-redirect: '443'
```

**2. IngressClass 지정**
```yaml
ingressClassName: alb
```

### ⚠️ 개선 필요 사항

**1. ACM 인증서 미설정**
```yaml
# 필요한 annotation 누락:
alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:...
```

**문제**: HTTPS 리스닝은 설정되어 있지만, SSL 인증서가 없음

**해결책**:
```yaml
alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:ap-northeast-2:ACCOUNT_ID:certificate/CERT_ID
```

**2. ALB 이름 지정 없음**
```yaml
# 권장:
alb.ingress.kubernetes.io/load-balancer-name: ecoeco-api-alb
```

**3. 보안 그룹 미지정**
```yaml
# 권장:
alb.ingress.kubernetes.io/security-groups: sg-xxxxxxxx
```
- Terraform에서 생성한 보안 그룹 지정 필요

**4. Subnet 지정 없음**
```yaml
# 권장:
alb.ingress.kubernetes.io/subnets: subnet-xxx,subnet-yyy,subnet-zzz
```
- Public Subnet 3개 명시 권장

**5. ALB Ingress Controller 설치 가이드 없음**
- Ansible이나 Helm Chart에 설치 절차 없음
- 수동 설치 필요:
```bash
helm repo add eks https://aws.github.io/eks-charts
helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=k8s-cluster \
  --set serviceAccount.create=false \
  --set serviceAccount.name=aws-load-balancer-controller
```

---

## 6️⃣ Ingress 라우팅 규칙 검증

### ✅ 강점

**1. 6개 API 모두 라우팅 정의됨**
```yaml
paths:
  - /api/v1/waste      → waste-api:8000
  - /api/v1/auth       → auth-api:8000
  - /api/v1/users      → userinfo-api:8000
  - /api/v1/locations  → location-api:8000
  - /api/v1/recycle    → recycle-info-api:8000
  - /api/v1/chat       → chat-llm-api:8000
```

**2. Prefix 기반 라우팅**
```yaml
pathType: Prefix
```
- `/api/v1/waste/*` 형태의 하위 경로 자동 매칭

**3. Conditional 활성화**
```yaml
{{- if .Values.api.waste.enabled }}
```
- 서비스별 활성화/비활성화 가능

### ⚠️ 개선 필요 사항

**1. Path 중복 가능성**
- `/api/v1/users` (userinfo)
- `/api/v1/userinfo`도 고려?

**결정 필요**: 
- 현재: `/api/v1/users` (REST 스타일)
- 대안: `/api/v1/userinfo` (서비스명 기반)

**2. CORS 설정 없음**
```yaml
# 권장:
alb.ingress.kubernetes.io/actions.response-headers: |
  {"Type":"fixed-response","FixedResponseConfig":{"StatusCode":"200","ContentType":"text/plain"}}
```

**3. Rate Limiting 없음**
```yaml
# 권장:
alb.ingress.kubernetes.io/wafv2-acl-arn: arn:aws:wafv2:...
```

**4. Health Check 타겟 불명확**
```yaml
alb.ingress.kubernetes.io/healthcheck-path: /health
```
- 모든 서비스가 `/health` 엔드포인트를 가지고 있는가?
- 현재 스켈레톤 코드에는 있음 ✅

---

## 🔧 즉시 수정 필요 사항 (Critical)

### 1. Service 리소스 추가
각 API Deployment 템플릿에 Service 리소스 추가:
```yaml
# charts/ecoeco-backend/templates/api/waste-deployment.yaml
---
apiVersion: v1
kind: Service
metadata:
  name: waste-api
  namespace: {{ .Values.namespaces.api }}
spec:
  type: ClusterIP
  selector:
    app: waste-api
  ports:
    - port: 8000
      targetPort: 8000
      protocol: TCP
```

### 2. Namespace 리소스 생성
```yaml
# charts/ecoeco-backend/templates/namespaces.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: api
---
apiVersion: v1
kind: Namespace
metadata:
  name: workers
---
apiVersion: v1
kind: Namespace
metadata:
  name: data
---
apiVersion: v1
kind: Namespace
metadata:
  name: messaging
```

### 3. ArgoCD repoURL 수정
```yaml
# argocd/application-13nodes.yaml
repoURL: https://github.com/SeSACTHON/backend
```

### 4. Health Probes 추가
각 Deployment에:
```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10
readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
```

### 5. IAM Role 정의
```terraform
# terraform/iam.tf
resource "aws_iam_role" "k8s_node" {
  name = "k8s-node-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_instance_profile" "k8s" {
  name = "k8s-instance-profile"
  role = aws_iam_role.k8s_node.name
}
```

---

## ⚡ 배포 전 체크리스트

### Terraform
- [ ] `terraform/iam.tf` 생성 (IAM Role & Instance Profile)
- [ ] 노드 태그를 Ansible/Helm 라벨과 일치시키기
- [ ] `terraform init && terraform validate`
- [ ] `terraform plan` 검토

### Ansible
- [ ] 생성된 inventory.ini 파일 확인
- [ ] `api_nodes` 그룹이 올바르게 생성되었는지 확인
- [ ] ALB Ingress Controller 설치 플레이북 추가
- [ ] `ansible-playbook --syntax-check site.yml`

### Helm Charts
- [ ] 각 API Deployment에 Service 리소스 추가
- [ ] Health Probes 추가
- [ ] Namespace 리소스 추가
- [ ] ConfigMap으로 환경 변수 관리
- [ ] Secret으로 민감 정보 관리
- [ ] `helm lint charts/ecoeco-backend`
- [ ] `helm template charts/ecoeco-backend --values charts/ecoeco-backend/values-13nodes.yaml`

### ArgoCD
- [ ] repoURL을 실제 GitHub repository로 변경
- [ ] `kubectl apply -f argocd/application-13nodes.yaml`
- [ ] ArgoCD UI에서 Sync 상태 확인

### ALB Ingress
- [ ] ACM에서 SSL 인증서 생성 (*.ecoeco.app)
- [ ] ALB Ingress Controller 설치
- [ ] Ingress에 certificate-arn 추가
- [ ] security-groups, subnets annotation 추가

### Services
- [ ] 모든 서비스에 `/health`, `/ready` 엔드포인트 구현 확인
- [ ] Docker 이미지 GHCR에 푸시 완료 확인
- [ ] Image Pull Secret 설정 (필요 시)

---

## 📊 전체 평가 점수

| 항목 | 점수 | 설명 |
|------|------|------|
| 아키텍처 설계 | 9/10 | 13노드 마이크로서비스 분리 우수 |
| Terraform 구성 | 7/10 | IAM 누락, ALB 미정의 |
| Ansible 자동화 | 7/10 | 인벤토리 불일치, ALB Controller 없음 |
| Helm Charts | 7/10 | Service 누락, Health Probe 없음 |
| ArgoCD | 6/10 | repoURL 미설정, Namespace 이슈 |
| Ingress/ALB | 6/10 | ACM 미설정, Security 설정 부족 |
| **전체 평균** | **7.0/10** | **양호 (재구축 가능, 수정 필요)** |

---

## 🎯 권장 사항

### 단기 (배포 전 필수)
1. **Service 리소스 추가** - Ingress가 작동하지 않음
2. **Namespace 생성** - Pod 배포 실패
3. **ArgoCD repoURL 수정** - GitOps 작동 안 함
4. **IAM Role 생성** - 노드가 AWS API 호출 불가
5. **Health Probes 추가** - ALB Health Check 실패

### 중기 (배포 후 개선)
1. **ACM 인증서 설정** - HTTPS 활성화
2. **ALB Security Groups** - 보안 강화
3. **ConfigMap/Secret 분리** - 환경 변수 관리
4. **Resource Quota** - 네임스페이스별 리소스 제한
5. **Network Policy** - Pod 간 통신 제한

### 장기 (운영 최적화)
1. **HPA 추가** - 자동 스케일링
2. **PDB 설정** - 고가용성 보장
3. **Monitoring** - Prometheus/Grafana 메트릭
4. **Logging** - ELK/Loki 로그 수집
5. **Backup** - etcd, PostgreSQL 백업 자동화

---

## ✅ 결론

**재구축 가능 여부**: ✅ **가능** (단, 즉시 수정 필요 사항 해결 후)

**주요 강점**:
- 13노드 마이크로서비스 아키텍처가 잘 설계됨
- Helm Charts가 모든 서비스를 정확히 정의
- Ingress 라우팅 규칙이 완벽

**주요 약점**:
- Service 리소스 누락 (치명적)
- IAM Role 미정의
- ACM 인증서 미설정
- ArgoCD 설정 불완전

**재구축 순서**:
1. 즉시 수정 필요 사항 5개 해결
2. Terraform Apply
3. Ansible Playbook 실행
4. ALB Ingress Controller 수동 설치
5. ArgoCD Application 배포
6. 서비스별 Health Check 확인

**예상 소요 시간**: 4-6시간 (수정 + 배포 + 검증)

---

**다음 단계**: 즉시 수정 필요 사항을 코드로 반영하고 PR 생성

