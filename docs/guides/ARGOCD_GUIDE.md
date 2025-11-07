# 🔄 ArgoCD 운영 가이드

> **현재 상태**: ArgoCD v2.12.6이 Master Node에 배포되어 실행 중  
> **접근 방법**: Port-forward, ALB Ingress (https://ecoeco.app/argocd)  
> **날짜**: 2025-11-06

---

## 📋 목차

1. [ArgoCD 상태 확인](#argocd-상태-확인)
2. [ArgoCD 접근 방법](#argocd-접근-방법)
3. [초기 비밀번호 확인](#초기-비밀번호-확인)
4. [ArgoCD CLI 설치 및 로그인](#argocd-cli-설치-및-로그인)
5. [Application 관리](#application-관리)
6. [트러블슈팅](#트러블슈팅)

---

## 🔍 ArgoCD 상태 확인

### Pod 상태 확인

```bash
# ArgoCD 네임스페이스의 모든 Pod 확인
ubuntu@k8s-master:~$ kubectl get pods -n argocd
NAME                                                READY   STATUS    RESTARTS      AGE
argocd-application-controller-0                     1/1     Running   0             39h
argocd-applicationset-controller-59dcb85f8c-dwrwk   1/1     Running   0             39h
argocd-dex-server-7698666d64-2hflw                  1/1     Running   2 (39h ago)   39h
argocd-notifications-controller-784f76bb54-5dlpt    1/1     Running   0             39h
argocd-redis-7d8d6c76b6-6wpfr                       1/1     Running   0             39h
argocd-repo-server-6bfcf8997b-glsq4                 1/1     Running   0             39h
argocd-server-5bc8b8c979-p5dnz                      1/1     Running   0             38h

```

### Service 확인

```bash
# ArgoCD 서비스 확인
ubuntu@k8s-master:~$ kubectl get svc -n argocd
NAME                                      TYPE        CLUSTER-IP       EXTERNAL-IP   PORT(S)                      AGE
argocd-applicationset-controller          ClusterIP   10.109.75.57     <none>        7000/TCP,8080/TCP            39h
argocd-dex-server                         ClusterIP   10.100.65.171    <none>        5556/TCP,5557/TCP,5558/TCP   39h
argocd-metrics                            ClusterIP   10.108.172.227   <none>        8082/TCP                     39h
argocd-notifications-controller-metrics   ClusterIP   10.103.185.146   <none>        9001/TCP                     39h
argocd-redis                              ClusterIP   10.108.99.194    <none>        6379/TCP                     39h
argocd-repo-server                        ClusterIP   10.99.82.23      <none>        8081/TCP,8084/TCP            39h
argocd-server                             NodePort    10.107.153.190   <none>        80:30300/TCP,443:30464/TCP   39h
argocd-server-metrics                     ClusterIP   10.105.7.129     <none>        8083/TCP                     39h

# ArgoCD Server 서비스 타입 확인 (NodePort인지 ClusterIP인지)
ubuntu@k8s-master:~$ kubectl get svc argocd-server -n argocd -o yaml | grep -A 5 "type:"
  type: NodePort
status:
  loadBalancer: {}
```

### Ingress 확인

```bash
# ArgoCD Ingress 확인
ubuntu@k8s-master:~$ kubectl get ingress -n argocd
NAME             CLASS   HOSTS         ADDRESS                                                                 PORTS   AGE
argocd-ingress   alb     ecoeco.app   k8s-ecoecoalb-18c99b272a-1896386009.ap-northeast-2.elb.amazonaws.com   80      39h

# Ingress 상세 정보
ubuntu@k8s-master:~$ kubectl describe ingress argocd-ingress -n argocd
Name:             argocd-ingress
Labels:           <none>
Namespace:        argocd
Address:          k8s-ecoecoalb-18c99b272a-1896386009.ap-northeast-2.elb.amazonaws.com
Ingress Class:    alb
Default backend:  <default>
Rules:
  Host         Path  Backends
  ----         ----  --------
  ecoeco.app  
               /argocd   argocd-server:80 (192.168.230.8:8080)
Annotations:   alb.ingress.kubernetes.io/backend-protocol: HTTP
               alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:ap-northeast-2:721622471953:certificate/fed2966c-7f9e-4849-ae20-0592ec04a373
               alb.ingress.kubernetes.io/group.name: ecoeco-alb
               alb.ingress.kubernetes.io/group.order: 10
               alb.ingress.kubernetes.io/healthcheck-interval-seconds: 15
               alb.ingress.kubernetes.io/healthcheck-path: /argocd/api/version
               alb.ingress.kubernetes.io/healthcheck-timeout-seconds: 5
               alb.ingress.kubernetes.io/healthy-threshold-count: 2
               alb.ingress.kubernetes.io/listen-ports: [{"HTTP": 80}, {"HTTPS": 443}]
               alb.ingress.kubernetes.io/scheme: internet-facing
               alb.ingress.kubernetes.io/ssl-redirect: 443
               alb.ingress.kubernetes.io/success-codes: 200
               alb.ingress.kubernetes.io/target-type: instance
               alb.ingress.kubernetes.io/unhealthy-threshold-count: 2
Events:        <none>
```

---

## 🚪 ArgoCD 접근 방법

### 방법 1: Port Forward (로컬 개발용) ⭐ 추천

**가장 간단하고 빠른 방법입니다.**

```bash
# 1. Master Node에서 Port Forward
kubectl port-forward svc/argocd-server -n argocd 8080:443

# 2. 로컬 브라우저에서 접속
# https://localhost:8080
```

**로컬 머신에서 접속 (SSH 터널링):**

```bash
# 1. 로컬 터미널에서 SSH 터널 생성
ssh -L 8080:localhost:8080 -i ~/.ssh/sesacthon.pem ubuntu@<MASTER_PUBLIC_IP>

# 2. Master Node에서 Port Forward (위 명령 실행)
kubectl port-forward svc/argocd-server -n argocd 8080:443

# 3. 로컬 브라우저에서 접속
# https://localhost:8080
```

**주의사항:**
- 자체 서명 인증서 경고가 나타나면 "고급" → "계속 진행" 클릭
- Chrome의 경우 페이지에서 `thisisunsafe` 타이핑

### 방법 2: NodePort (테스트용)

```bash
# ArgoCD Server를 NodePort로 변경
kubectl patch svc argocd-server -n argocd -p '{"spec":{"type":"NodePort"}}'

# NodePort 확인
kubectl get svc argocd-server -n argocd
# 예: 30000-32767 범위의 포트

# 브라우저에서 접속
# https://<MASTER_PUBLIC_IP>:<NODE_PORT>
```

### 방법 3: ALB Ingress (프로덕션용) ✅ 현재 설정

**현재 Ansible에서 자동 구성됨**

```bash
# Ingress 확인
ubuntu@k8s-master:~$ kubectl get ingress argocd-ingress -n argocd
NAME             CLASS   HOSTS         ADDRESS                                                                 PORTS   AGE
argocd-ingress   alb     ecoeco.app   k8s-ecoecoalb-18c99b272a-1896386009.ap-northeast-2.elb.amazonaws.com   80      39h

# ALB DNS 확인
ubuntu@k8s-master:~$ kubectl get ingress argocd-ingress -n argocd -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
k8s-ecoecoalb-18c99b272a-1896386009.ap-northeast-2.elb.amazonaws.com

# 브라우저에서 접속
# https://ecoeco.app/argocd
```

**ALB Ingress 설정 확인:**

```bash
ubuntu@k8s-master:~$ kubectl get ingress argocd-ingress -n argocd -o yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  annotations:
    alb.ingress.kubernetes.io/backend-protocol: HTTP
    alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:ap-northeast-2:721622471953:certificate/fed2966c-7f9e-4849-ae20-0592ec04a373
    alb.ingress.kubernetes.io/group.name: ecoeco-alb
    alb.ingress.kubernetes.io/group.order: "10"
    alb.ingress.kubernetes.io/healthcheck-interval-seconds: "15"
    alb.ingress.kubernetes.io/healthcheck-path: /argocd/api/version
    alb.ingress.kubernetes.io/healthcheck-timeout-seconds: "5"
    alb.ingress.kubernetes.io/healthy-threshold-count: "2"
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}, {"HTTPS": 443}]'
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/ssl-redirect: "443"
    alb.ingress.kubernetes.io/success-codes: "200"
    alb.ingress.kubernetes.io/target-type: instance
    alb.ingress.kubernetes.io/unhealthy-threshold-count: "2"
    kubectl.kubernetes.io/last-applied-configuration: |
      {"apiVersion":"networking.k8s.io/v1","kind":"Ingress","metadata":{"annotations":{"alb.ingress.kubernetes.io/backend-protocol":"HTTPS","alb.ingress.kubernetes.io/certificate-arn":"arn:aws:acm:ap-northeast-2:721622471953:certificate/fed2966c-7f9e-4849-ae20-0592ec04a373","alb.ingress.kubernetes.io/group.name":"ecoeco-alb","alb.ingress.kubernetes.io/group.order":"10","alb.ingress.kubernetes.io/healthcheck-interval-seconds":"15","alb.ingress.kubernetes.io/healthcheck-path":"/argocd/health","alb.ingress.kubernetes.io/healthcheck-timeout-seconds":"5","alb.ingress.kubernetes.io/healthy-threshold-count":"2","alb.ingress.kubernetes.io/listen-ports":"[{\"HTTP\": 80}, {\"HTTPS\": 443}]","alb.ingress.kubernetes.io/scheme":"internet-facing","alb.ingress.kubernetes.io/ssl-redirect":"443","alb.ingress.kubernetes.io/target-type":"instance","alb.ingress.kubernetes.io/unhealthy-threshold-count":"2"},"name":"argocd-ingress","namespace":"argocd"},"spec":{"ingressClassName":"alb","rules":[{"host":"ecoeco.app","http":{"paths":[{"backend":{"service":{"name":"argocd-server","port":{"number":443}}},"path":"/argocd","pathType":"Prefix"}]}}]}}
  creationTimestamp: "2025-11-04T13:02:14Z"
  finalizers:
  - group.ingress.k8s.aws/ecoeco-alb
  generation: 2
  name: argocd-ingress
  namespace: argocd
  resourceVersion: "22868"
  uid: 3e2ee629-0581-447d-9c5d-0aa870b866dd
spec:
  ingressClassName: alb
  rules:
  - host: ecoeco.app
    http:
      paths:
      - backend:
          service:
            name: argocd-server
            port:
              number: 80
        path: /argocd
        pathType: Prefix
status:
  loadBalancer:
    ingress:
    - hostname: k8s-ecoecoalb-18c99b272a-1896386009.ap-northeast-2.elb.amazonaws.com
```

**주요 annotation:**
- `alb.ingress.kubernetes.io/scheme: internet-facing`
- `alb.ingress.kubernetes.io/target-type: instance`
- `alb.ingress.kubernetes.io/backend-protocol: HTTPS`
- `alb.ingress.kubernetes.io/certificate-arn: <ACM_ARN>`

---

## 🔑 초기 비밀번호 확인

### 방법 1: kubectl로 직접 확인 ⭐

```bash
# 초기 admin 비밀번호 확인
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d && echo

# 출력: 초기 비밀번호 (예: gXh2kP9vL3mN5qR8)
```

### 방법 2: Secret 전체 확인

```bash
# Secret 확인
kubectl get secret -n argocd argocd-initial-admin-secret -o yaml

# data.password 필드를 base64 디코딩
echo "<password_base64>" | base64 -d
```

### 로그인 정보

```
Username: admin
Password: <위에서 확인한 비밀번호>
```

**보안 권장사항:**

```bash
# 초기 비밀번호를 사용한 첫 로그인 후 즉시 변경
argocd account update-password

# 또는 Web UI에서 User Info → Update Password
```

---

## 💻 ArgoCD CLI 설치 및 로그인

### CLI 설치

**Linux (Master Node):**

```bash
# 최신 버전 다운로드
curl -sSL -o /usr/local/bin/argocd https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64

# 실행 권한 부여
chmod +x /usr/local/bin/argocd

# 버전 확인
argocd version --client
```

**macOS (로컬):**

```bash
# Homebrew로 설치
brew install argocd

# 또는 직접 다운로드
curl -sSL -o /usr/local/bin/argocd https://github.com/argoproj/argo-cd/releases/latest/download/argocd-darwin-amd64
chmod +x /usr/local/bin/argocd
```

### CLI 로그인

**Port Forward 사용:**

```bash
# 1. Port Forward 실행 (별도 터미널)
kubectl port-forward svc/argocd-server -n argocd 8080:443

# 2. CLI 로그인 (다른 터미널)
argocd login localhost:8080 \
  --username admin \
  --password $(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d) \
  --insecure

# 로그인 성공 메시지
# 'admin:login' logged in successfully
```

**ALB Ingress 사용:**

```bash
# ALB 도메인으로 로그인
argocd login ecoeco.app/argocd \
  --username admin \
  --password <초기_비밀번호>

# 또는 GRPC 사용 (더 빠름)
argocd login ecoeco.app:443 \
  --grpc-web \
  --username admin \
  --password <초기_비밀번호>
```

### 비밀번호 변경

```bash
# CLI로 비밀번호 변경
argocd account update-password

# 현재 비밀번호: <초기_비밀번호>
# 새 비밀번호: <새_비밀번호>
# 새 비밀번호 확인: <새_비밀번호>
```

---

## 📦 Application 관리

### Application 목록 확인

```bash
# 모든 Application 확인
argocd app list

# 특정 Application 상세 정보
argocd app get <app-name>

# Application 상태 확인
argocd app get <app-name> --show-operation
```

### Application 생성

**방법 1: CLI로 생성**

```bash
argocd app create backend-auth \
  --repo https://github.com/SeSACTHON/backend.git \
  --path charts/auth \
  --dest-server https://kubernetes.default.svc \
  --dest-namespace default \
  --sync-policy automated \
  --auto-prune \
  --self-heal
```

**방법 2: YAML 매니페스트**

```yaml
# argocd/applications/backend-auth.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: backend-auth
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/SeSACTHON/backend.git
    targetRevision: main
    path: charts/auth
    helm:
      valueFiles:
        - values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: default
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
```

```bash
# 적용
kubectl apply -f argocd/applications/backend-auth.yaml
```

### Sync 및 배포

```bash
# 수동 Sync
argocd app sync <app-name>

# 강제 Sync (리소스 재생성)
argocd app sync <app-name> --force

# Sync 상태 확인
argocd app wait <app-name>

# 롤백
argocd app rollback <app-name>
```

### Application 삭제

```bash
# Application 삭제 (배포된 리소스도 함께 삭제)
argocd app delete <app-name>

# Application만 삭제 (배포된 리소스 유지)
argocd app delete <app-name> --cascade=false
```

---

## 🐛 트러블슈팅

### 1. ArgoCD Server에 접속할 수 없음

**증상:**
```
Unable to connect to argocd-server
```

**해결:**

```bash
# 1. Pod 상태 확인
kubectl get pods -n argocd

# 2. argocd-server 로그 확인
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-server

# 3. Service 확인
kubectl get svc argocd-server -n argocd

# 4. Port Forward가 제대로 실행 중인지 확인
ps aux | grep "port-forward"

# 5. Port Forward 재시작
kubectl port-forward svc/argocd-server -n argocd 8080:443
```

### 2. 초기 비밀번호가 작동하지 않음

**증상:**
```
Invalid username or password
```

**해결:**

```bash
# 1. Secret 확인
kubectl get secret argocd-initial-admin-secret -n argocd

# Secret이 없는 경우 비밀번호가 이미 변경됨
# 비밀번호 재설정 필요

# 2. Admin 비밀번호 재설정
kubectl exec -it -n argocd argocd-server-<pod-id> -- \
  argocd account update-password --account admin --current-password "" --new-password <new-password>

# 3. 또는 초기 Secret 재생성 (주의!)
kubectl delete secret argocd-initial-admin-secret -n argocd
kubectl rollout restart deployment argocd-server -n argocd
```

### 3. Ingress가 작동하지 않음

**증상:**
```
502 Bad Gateway
```

**해결:**

```bash
# 1. Ingress 상태 확인
kubectl describe ingress argocd-ingress -n argocd

# 2. Service 타입 확인 (NodePort여야 함)
kubectl get svc argocd-server -n argocd
# type: NodePort

# 3. Service를 NodePort로 변경
kubectl patch svc argocd-server -n argocd -p '{"spec":{"type":"NodePort"}}'

# 4. Backend Protocol 확인
# annotation: alb.ingress.kubernetes.io/backend-protocol: HTTPS

# 5. ALB Target Health 확인 (AWS Console)
```

### 4. SSL/TLS 인증서 오류

**증상:**
```
x509: certificate signed by unknown authority
```

**해결:**

```bash
# CLI에서 --insecure 플래그 사용
argocd login localhost:8080 --insecure

# 또는 CA 인증서 무시 설정
export ARGOCD_OPTS='--insecure'

# 브라우저에서는 "고급" → "계속 진행" 클릭
```

### 5. Application이 OutOfSync 상태

**증상:**
```
Application is OutOfSync
```

**해결:**

```bash
# 1. Diff 확인
argocd app diff <app-name>

# 2. 수동 Sync
argocd app sync <app-name>

# 3. 자동 Sync 활성화
argocd app set <app-name> --sync-policy automated

# 4. Self-Heal 활성화
argocd app set <app-name> --self-heal

# 5. Prune 활성화 (삭제된 리소스 정리)
argocd app set <app-name> --auto-prune
```

---

## 📚 유용한 명령어 모음

### 상태 확인

```bash
# 클러스터 정보
argocd cluster list

# 프로젝트 목록
argocd proj list

# 저장소 목록
argocd repo list

# 계정 정보
argocd account list

# 버전 확인
argocd version
```

### 설정

```bash
# Context 확인
argocd context

# 현재 사용자 정보
argocd account get-user-info

# 로그아웃
argocd logout localhost:8080
```

### 로그

```bash
# Application 로그
argocd app logs <app-name>

# Sync 작업 로그
argocd app logs <app-name> --kind Deployment --name <deployment-name>
```

---

## 🔐 보안 권장사항

### 1. 초기 비밀번호 즉시 변경

```bash
# 첫 로그인 후 즉시 변경
argocd account update-password
```

### 2. RBAC 설정

```bash
# 사용자 생성
argocd account create <username>

# 역할 부여
argocd account update-password --account <username> --new-password <password>

# RBAC 정책 설정 (ConfigMap 수정)
kubectl edit configmap argocd-rbac-cm -n argocd
```

### 3. SSO 통합 (선택사항)

ArgoCD는 다음 SSO 제공자를 지원합니다:
- GitHub
- Google
- OIDC
- SAML
- LDAP

### 4. 네트워크 정책

```bash
# ArgoCD 네임스페이스에 NetworkPolicy 적용
kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: argocd-network-policy
  namespace: argocd
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector: {}
  egress:
  - to:
    - namespaceSelector: {}
EOF
```

---

## 📖 참고 문서

- [ArgoCD 공식 문서](https://argo-cd.readthedocs.io/)
- [ArgoCD CLI 명령어](https://argo-cd.readthedocs.io/en/stable/user-guide/commands/argocd/)
- [ArgoCD Best Practices](https://argo-cd.readthedocs.io/en/stable/user-guide/best_practices/)
- [GitOps 배포 가이드](gitops-argocd-helm.md)

---

**문서 버전**: v0.4.1  
**최종 업데이트**: 2025-11-06  
**ArgoCD 버전**: v2.12.6

