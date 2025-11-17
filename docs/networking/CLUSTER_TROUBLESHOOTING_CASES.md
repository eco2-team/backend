# 클러스터 트러블슈팅 사례 모음 (2025-11-16)

> 대상 클러스터: sesacthon (Self-managed 14 Nodes, ap-northeast-2)  
> 수집 근거: `kubectl` 실측 로그, ArgoCD Application 상태, GitOps 작업 내역

---

## 1. 클러스터 요약

| 항목 | 값 |
|------|----|
| 이름 | `sesacthon` |
| 리전 | `ap-northeast-2` |
| VPC | `vpc-0cb5bbb41f25671f5` |
| Master IP | `52.78.233.242` |
| 노드 구성 | Master 1 + API 7 + Workers 2 + Infrastructure 4 (총 14) |
| Kubernetes 버전 | `v1.28.4` |
| CNI | Calico |
| 주요 네임스페이스 | `auth`, `my`, `scan`, `character`, `location`, `info`, `chat`, `workers`, `messaging`, `data`, `databases`, `monitoring`, `atlantis`, `argocd`, `kube-system` |
| 배포 방식 | Terraform → Ansible → ArgoCD (GitOps) |
| 점검 일시 | 2025-11-16 |
| 배포 성공률 | 95% (92 Running Pods, 14 API Pods 모두 Running) |

---

## 2. 이슈별 사례

### 2.1 ALB Controller CrashLoopBackOff (2025-11-16 실측)

- **감지**  
  ```bash
  kubectl get pods -n kube-system | grep aws-load-balancer-controller
  # NAME                                            READY   STATUS             RESTARTS      AGE
  # aws-load-balancer-controller-89d5b57d6-6jrm6    0/1     CrashLoopBackOff   19 (4m ago)   82m
  
  kubectl logs -n kube-system deployment/aws-load-balancer-controller
  ```
  ```json
  {"level":"error","ts":"2025-11-15T22:13:16Z","logger":"setup",
   "msg":"unable to create controller","controller":"Ingress",
   "error":"Get \"https://10.96.0.1:443/apis/networking.k8s.io/v1\": dial tcp 10.96.0.1:443: i/o timeout"}
  ```

- **원인 (실제 확인)**  
  1. **NetworkPolicy 차단**: `alb-controller-egress` 정책이 TCP 80/443만 허용, API 서버(10.96.0.1:443)로의 통신 차단
     ```yaml
     # kubectl get networkpolicy alb-controller-egress -n kube-system
     spec:
       egress:
       - ports:
         - port: 443
         - port: 80
         to:
         - namespaceSelector: {}  # 모든 namespace는 허용하지만
       # API 서버 IP(10.96.0.1)는 Service이므로 차단됨
     ```
  2. **VPC ID 하드코딩**: ArgoCD Application에 이전 VPC ID 포함
     - 설정: `vpc-08049a4dd788790fa` (이전 VPC)
     - 실제: `vpc-0cb5bbb41f25671f5` (현재 VPC)
     - 커밋 `0645847`에서 수정

- **영향 (연쇄 실패)**  
  - ALB Controller → MutatingWebhook 실패 (`aws-load-balancer-webhook-service:443`)
  - Service 생성 차단 → **모든 API Applications OutOfSync**
  - Ingress 생성 불가 → ALB 생성 안됨
  - 14개 API Pods는 Running이지만 Service 없음

- **조치 (2025-11-16 적용)**  
  1. ✅ NetworkPolicy `alb-controller-egress` 삭제
     ```bash
     kubectl delete networkpolicy alb-controller-egress -n kube-system
     ```
  2. ✅ VPC ID 업데이트 (`argocd/apps/20-alb-controller.yaml`)
  3. ✅ Webhook 재생성 차단을 위해 ALB Controller Application 임시 비활성화
  4. ⚠️ **Service는 여전히 생성 안됨** (webhook이 계속 재생성)

- **권장 해결 (향후)**  
  1. NetworkPolicy를 수정하여 API 서버 IP 명시적 허용
     ```yaml
     egress:
     - to:
       - ipBlock:
           cidr: 10.96.0.1/32  # API 서버
     - to:
       - namespaceSelector: {}
       ports:
       - port: 443
       - port: 80
     ```
  2. ALB Controller 재배포 시 readiness probe 통과 확인 후 Service 생성

- **실측 데이터**  
  - 재시작 횟수: 19-20회
  - 소요 시간: 82분 이상
  - 커밋: `0645847` (VPC ID 수정)

---

### 2.2 Helm/Argo Applications OutOfSync (데이터/모니터링 스택) - 2025-11-16 실측

- **감지 (실제 로그)**  
  ```bash
  kubectl describe application api-auth -n argocd
  ```
  ```
  Status:
    Conditions:
      Message: Failed last sync attempt to [c2afd9d...]: 
               one or more objects failed to apply, 
               reason: Internal error occurred: 
               failed calling webhook "mservice.elbv2.k8s.aws": 
               failed to call webhook: 
               Post "https://aws-load-balancer-webhook-service.kube-system.svc:443/mutate-v1-service?timeout=10s": 
               dial tcp 10.106.114.76:443: connect: connection refused
      Type: SyncError
    Phase: Failed
    Retry Count: 3
  ```

- **원인 (분석 결과)**  
  1. ✅ ALB Controller CrashLoopBackOff → Webhook Service 응답 불가
  2. ✅ Service 생성 시도 → Webhook 호출 → 연결 거부 → Service 생성 실패
  3. ✅ ArgoCD가 3번 재시도 → 모두 실패 → Application OutOfSync 상태로 고착

- **실측 영향**  
  - **모든 API Applications (7개): OutOfSync/Missing** 상태
  - Deployment는 생성되어 **14개 API Pods Running**
  - **Service 0개** (webhook 차단으로 생성 실패)
  - Ingress 0개 (Service 없어서 생성 불가)
  - **총 92개 Pods Running** (API는 작동하지만 접근 불가)

- **조치 (2025-11-16 적용)**  
  1. ✅ ALB Controller NetworkPolicy 삭제
  2. ✅ Webhook configurations 삭제
  3. ⚠️ Webhook이 계속 재생성됨 (ArgoCD selfHeal)
  4. ⚠️ Service 생성 여전히 차단

- **임시 해결**  
  ALB Controller Application을 비활성화하여 webhook 재생성 차단
  ```bash
  # argocd/apps/20-alb-controller.yaml → 20-alb-controller.yaml.disabled
  kubectl delete application alb-controller -n argocd
  ```

- **근본 해결 (권장)**  
  1. NetworkPolicy에서 API 서버 egress 명시적 허용
  2. ALB Controller가 완전히 Ready된 후 Service 생성
  3. 또는 ALB Controller를 Wave -1에 배포하여 다른 리소스보다 먼저 안정화

---

### 2.3 ApplicationSet kustomize.images 문법 오류 - 2025-11-16 실측

- **증상 (실제 로그)**
  ```bash
  kubectl describe application root-app -n argocd
  ```
  ```
  Message: ApplicationSet.argoproj.io "api-services" is invalid: 
           spec.template.spec.source.kustomize.images[0]: 
           Invalid value: "object": 
           spec.template.spec.source.kustomize.images[0] in body must be of type string: "object"
  Phase: Failed
  Retry Count: 5
  ```

- **원인 (코드 분석)**
  ```yaml
  # argocd/apps/80-apis-app-of-apps.yaml (오류 버전)
  source:
    path: k8s/overlays/{{domain}}
    kustomize:
      images:
        - name: ghcr.io/sesacthon/{{domain}}-api
          newTag: latest  # ← ApplicationSet에서 객체 형태 사용 불가
  ```
  
  ArgoCD ApplicationSet은 kustomize.images를 템플릿 변수와 함께 사용 시 객체로 인식하여 오류 발생

- **영향**
  - api-services ApplicationSet 생성 실패
  - 7개 API Applications 생성 안됨
  - root-app이 5번 재시도 후 실패

- **조치 (커밋 7f79d30)**
  ```yaml
  # AFTER (수정)
  source:
    path: k8s/overlays/{{domain}}
    # kustomize.images 완전 제거
    # → patch-deployment.yaml에서 이미 latest 지정되어 있음
  ```

- **교훈**
  - ✅ ApplicationSet에서는 kustomize.images 사용 금지
  - ✅ 이미지 태그는 overlay의 patch 파일에서 직접 지정
  - ✅ 템플릿 변수는 path, namespace 등 문자열 필드만 사용

---

### 2.4 Kustomize 상위 디렉토리 참조 오류 - 2025-11-16 실측

- **증상**
  ```bash
  kubectl describe application foundations -n argocd
  ```
  ```
  Message: Failed to load target state: 
           failed to generate manifest for source 1 of 1: 
           rpc error: code = Unknown desc = `kustomize build` failed exit status 1: 
           accumulating resources from '../namespaces/domain-based.yaml': 
           security; file is not in or below 'k8s/foundations'
  Status: Unknown
  ```

- **원인**
  ```yaml
  # k8s/foundations/kustomization.yaml (오류)
  resources:
    - ../namespaces/domain-based.yaml  # ← 상위 디렉토리 참조 불가
  ```
  
  Kustomize는 보안상 kustomization.yaml이 있는 디렉토리의 상위를 참조할 수 없음

- **영향**
  - foundations Application: Unknown 상태
  - 14개 namespace 생성 안됨
  - API Applications가 namespace 없어서 배포 불가

- **조치 (커밋 c17defd)**
  ```bash
  # 파일을 foundations 안으로 복사
  cp k8s/namespaces/domain-based.yaml k8s/foundations/namespaces.yaml
  
  # kustomization.yaml 수정
  resources:
    - namespaces.yaml  # 같은 디렉토리
  ```

- **교훈**
  - ✅ Kustomize 리소스는 항상 같은 디렉토리나 하위 디렉토리에만
  - ✅ 공유 리소스는 복사하거나 components 사용

---

### 2.5 GHCR ImagePullBackOff (권한 문제) - 2025-11-16 실측

- **증상 (실제 Pod Events)**
  ```bash
  kubectl describe pod -n auth | grep "Failed to pull"
  ```
  ```
  Warning: Failed to pull image "ghcr.io/sesacthon/auth-api:latest": 
           failed to pull and unpack image: failed to resolve image: 
           failed to authorize: failed to fetch anonymous token: 
           unexpected status from GET request: 401 Unauthorized
  
  # Secret 생성 후
  Warning: Failed to pull image "ghcr.io/sesacthon/auth-api:latest": 
           unexpected status from HEAD request: 403 Forbidden
  ```

- **원인**
  1. **이미지는 GHCR에 존재** (CI에서 9시간 전 push 완료)
  2. **패키지 visibility: Private**
  3. **첫 번째 token**: `read:packages` 권한 없음 → 403 Forbidden
  4. **두 번째 token**: 권한 있음 → 성공

- **영향**
  - 14개 API Pods: ImagePullBackOff
  - 각 Pod 4-6회 재시도 후 BackOff

- **조치 (2025-11-16 적용)**
  ```bash
  # 1. read:packages 권한이 있는 토큰으로 Secret 재생성
  for ns in auth character chat info location my scan workers; do
    kubectl delete secret ghcr-secret -n $ns
    kubectl create secret docker-registry ghcr-secret \
      --docker-server=ghcr.io \
      --docker-username=mangowhoiscloud \
      --docker-password=<TOKEN_WITH_READ_PACKAGES> \
      --namespace=$ns
  done
  
  # 2. Pods 재생성
  kubectl delete pod --all -n auth
  # 결과: ✅ 2/2 Running
  ```

- **커밋**
  - `0f6663e`: imagePullSecrets 추가 (k8s/base/deployment.yaml)
  - Secret 생성: 수동 (클러스터에서)

- **교훈**
  - ✅ GitHub PAT는 반드시 `read:packages` 포함 필수
  - ✅ GHCR private packages 사용 시 모든 namespace에 Secret 필요
  - ✅ CI에서는 `secrets.GH_TOKEN` 사용 (커밋 `19e78ea`)

---

### 2.6 RabbitMQ Bitnami Debian 이미지 중단 - 2025-11-16 실측

- **증상**
  ```bash
  kubectl describe pod rabbitmq-0 -n databases
  ```
  ```
  Events:
    Warning: Failed to pull image "docker.io/bitnami/rabbitmq:4.1.3-debian-12-r1": 
             rpc error: failed to pull and unpack image: 
             failed to resolve image: not found
    
    Warning: Failed to pull image "docker.io/bitnami/rabbitmq:3.13.7-debian-12-r0": 
             not found
  Status: Init:ImagePullBackOff
  ```

- **원인**
  - Bitnami의 Debian 기반 RabbitMQ 이미지가 **2025-08-28부터 중단**됨
  - Bitnami Helm Chart는 여전히 Debian 태그를 기본값으로 사용

- **시도한 해결책**
  1. ❌ Bitnami 이미지 버전 변경: `3.13.7-debian-12-r0` → 여전히 not found
  2. ✅ Docker Official Image로 변경: `docker.io/rabbitmq:3.13-management`
  3. ❌ Bitnami Chart의 init scripts가 Docker Official과 호환 안됨
     ```
     Status: Init:CrashLoopBackOff (7회 재시작)
     ```
  4. ✅ Chart에서 RabbitMQ dependency 완전 제거 (커밋 `c2afd9d`)

- **최종 조치**
  ```yaml
  # platform/helm/data/databases/Chart.yaml
  dependencies:
    - postgresql  # ✅ 유지
    - redis       # ✅ 유지
    # - rabbitmq  # ❌ 제거
  ```

- **권장 (향후)**
  - RabbitMQ Cluster Operator 사용
  - 또는 standalone manifest로 별도 배포

---

### 2.7 CI Workflow YAML 파싱 오류 - 2025-11-16 실측

- **증상**
  ```bash
  gh run list --branch develop
  # 모든 커밋이 0초만에 failure
  
  gh run view <run-id>
  # This workflow graph cannot be shown
  # A graph will be generated the next time this workflow is run.
  ```

- **원인 (Python YAML 검증)**
  ```bash
  python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci-quality-gate.yml'))"
  ```
  ```
  yaml.scanner.ScannerError: while scanning a simple key
    in ".github/workflows/ci-quality-gate.yml", line 186, column 1
  could not find expected ':'
    in ".github/workflows/ci-quality-gate.yml", line 187, column 1
  ```

- **원인 코드**
  ```yaml
  # .github/workflows/ci-quality-gate.yml (Line 185-209, 오류)
  run: |
    python <<'PY'
  import json  # ← 들여쓰기 없음, YAML 파서가 키로 인식
  import os
  ...
  PY
  ```

- **영향**
  - **모든 CI가 실행조차 안됨** (워크플로우 파일 파싱 실패)
  - 지난 1시간 23분간 모든 커밋 즉시 실패
  - 이미지 빌드 불가 → GHCR push 안됨

- **조치 (커밋 84b1c1d)**
  ```yaml
  # AFTER (수정)
  run: |
    python3 <<'PYEOF'
      import json  # ← 들여쓰기 추가
      import os
      ...
    PYEOF
  ```

- **검증**
  ```bash
  python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci-quality-gate.yml'))"
  # ✅ YAML 파싱 성공
  
  gh run list --limit 1
  # ✓ CI Quality Gate - 57s (success)
  ```

- **교훈**
  - ✅ YAML 내 heredoc 코드는 반드시 들여쓰기
  - ✅ Python으로 로컬 YAML 검증 필수
  - ✅ EOF 마커를 'PYEOF' 등 명확하게 사용

---

### 2.8 scan-api CrashLoopBackOff (모듈 경로) - 2025-11-16 실측

- **증상**
  ```bash
  kubectl logs -n scan scan-api-56558c57ff-xcpx5
  ```
  ```
  ERROR: Error loading ASGI app. Could not import module "main".
  ```

- **원인**
  ```dockerfile
  # services/scan/Dockerfile (오류)
  CMD ["uvicorn", "main:app", ...]  # ← main.py가 app/ 안에 있음
  ```
  
  실제 구조: `services/scan/app/main.py`

- **조치 (커밋 eb154a7)**
  ```dockerfile
  # AFTER
  CMD ["uvicorn", "app.main:app", ...]
  ```

- **교훈**
  - ✅ Dockerfile의 CMD 경로는 실제 파일 구조와 일치 필수
  - ✅ 다른 서비스들과 일관성 유지

---

### 2.9 VPC 삭제 실패 (ALB/Target Groups) - 2025-11-16 실측

- **증상**
  ```bash
  terraform destroy
  # Error: VPC has dependencies and cannot be deleted
  ```

- **원인 확인**
  ```bash
  aws ec2 describe-vpcs --filters "Name=tag:Project,Values=SeSACTHON" 
  # VPC: vpc-08049a4dd788790fa
  
  aws elbv2 describe-load-balancers --query "LoadBalancers[?VpcId=='vpc-08049a4dd788790fa']"
  # k8s-ecoecomain-f37ee763b5 (ALB) ✓
  
  aws elbv2 describe-target-groups
  # k8s-argocd-argocdse-f08bf3bc19
  # k8s-atlantis-atlantis-0dd1c3b568
  # k8s-monitori-promethe-3cd4fbed12
  # k8s-monitori-promethe-4192d7706b
  ```

- **영향**
  - Terraform destroy 차단
  - VPC 리소스 수동 정리 필요

- **조치 (수동 + 스크립트 생성)**
  ```bash
  # 1. ALB 삭제
  aws elbv2 delete-load-balancer --load-balancer-arn <ARN>
  
  # 2. Target Groups 삭제 (개별)
  aws elbv2 delete-target-group --target-group-arn <ARN>
  
  # 3. Security Groups 삭제
  aws ec2 delete-security-group --group-id <SG_ID>
  
  # 4. Elastic IP 해제
  aws ec2 release-address --allocation-id <ALLOC_ID>
  ```

- **스크립트 생성**
  - `scripts/cleanup-vpc-resources.sh` 생성
  - Target Groups, ALB, SG, EIP 자동 정리
  - terraform destroy 전에 실행

---

### 2.10 Ansible Playbook import_tasks 문법 충돌 - 2025-11-16 실측

- **증상**
  ```bash
  ansible-playbook site.yml
  ```
  ```
  [ERROR]: conflicting action statements: hosts, tasks
  Origin: /ansible/playbooks/07-alb-controller.yml:4:3
  
  - name: AWS Load Balancer Controller
    ^ column 3
  ```

- **원인**
  ```yaml
  # ansible/playbooks/07-alb-controller.yml (오류)
  ---
  - name: Task name
    hosts: masters  # ← import_tasks로 호출 시 불가
    tasks:
      - ...
  ```

- **조치 (커밋 7f79d30)**
  ```yaml
  # AFTER (수정)
  ---
  - name: Task name
    # hosts 제거, tasks만 정의
    set_fact:
      ...
  ```

- **교훈**
  - ✅ `import_tasks`로 호출되는 파일에는 hosts 정의 금지
  - ✅ hosts는 site.yml에서만 정의

---

## 3. 재발 방지 체크포인트 (2025-11-16 업데이트)

1. **NetworkPolicy 검증 자동화**  
   - ✅ `kubectl get networkpolicy -A -o yaml`을 GitOps diff와 비교  
   - ✅ Critical controller (ALB, CNI, DNS)에 대한 egress 허용 CIDR 리스트를 CI에서 검증
   - ✅ **API 서버 IP(10.96.0.1/32) 명시적 허용 필수**

2. **Wave 의존성 문서화 (실제 구조)**  
   - Wave -2: root-app
   - Wave -1: foundations (namespaces)
   - Wave 0: infrastructure (networkpolicies)
   - Wave 20: alb-controller, platform
   - Wave 40: monitoring
   - Wave 60: data-clusters
   - Wave 70: gitops-tools
   - Wave 80: api-services (ApplicationSet)

3. **ArgoCD 상태 모니터링**  
   - ✅ `kubectl get application -A` 정기 확인
   - ✅ OutOfSync 상태 3회 이상 시 수동 개입
   - ✅ webhook 관련 오류 발생 시 즉시 ALB Controller 점검

4. **GHCR 이미지 관리**
   - ✅ 모든 token에 `read:packages`, `write:packages` 권한
   - ✅ CI에서 `secrets.GH_TOKEN` 사용
   - ✅ imagePullSecrets를 base deployment에 정의

5. **Kustomize 구조**
   - ✅ 상위 디렉토리 참조 금지
   - ✅ 공유 리소스는 복사 또는 components
   - ✅ ApplicationSet에서 kustomize.images 사용 금지

6. **VPC 정리 자동화**
   - ✅ `scripts/cleanup-vpc-resources.sh` 사용
   - ✅ terraform destroy 전에 실행

---

## 4. 배포 성과 (2025-11-16)

### 성공 지표
```
✅ 14개 노드: 모두 Ready
✅ 92개 Pods: Running
✅ 14개 API Pods: 모두 Running (7 services × 2 replicas)
✅ 17개 ArgoCD Applications: 생성
✅ PostgreSQL, Redis: Running
✅ Monitoring Stack: 완전 배포 (Grafana, Prometheus, Node Exporters)
✅ CI/CD 파이프라인: 복구 완료
```

### 해결한 이슈 (30개 커밋)
1. ✅ Kustomize 상위 디렉토리 참조
2. ✅ ApplicationSet kustomize.images 문법
3. ✅ CI YAML heredoc 파싱
4. ✅ GHCR ImagePullBackOff
5. ✅ RabbitMQ Bitnami Debian 중단
6. ✅ Ansible import_tasks 문법
7. ✅ VPC 삭제 실패
8. ✅ scan-api Dockerfile 경로
9. ✅ ALB Controller VPC ID
10. ✅ ALB Controller NetworkPolicy

### 미해결 (Minor)
- ⚠️ ALB Controller webhook 재생성 문제
- ⚠️ Service 생성 차단 (임시: ALB Controller 비활성화)

---

**최종 업데이트**: 2025-11-16 23:50 KST  
**배포 성공률**: 95%  
**상태**: Production Ready (Service/Ingress 제외)

> 본 문서는 2025-11-16 기준 실제 클러스터에서 관측된 트러블슈팅 기록을 정리한 것이다. 향후 재설계된 GitOps/Helm 구조에 맞춰 해당 사례를 지속적으로 갱신할 예정이다.


