# ArgoCD 502 Bad Gateway 문제 해결

## 📊 문제 상황

### 증상
```
https://growbin.app/argocd
→ 502 Bad Gateway
```

### ALB Target Health
```bash
aws elbv2 describe-target-health --target-group-arn <TG_ARN>

# 결과:
# 모든 Target이 Unhealthy
# Reason: Target.FailedHealthChecks
```

---

## 🔍 원인 분석

### 1. 설정 확인

```bash
# ArgoCD ConfigMap 확인
kubectl get configmap argocd-cmd-params-cm -n argocd -o yaml

# 결과:
# server.rootpath: /argocd
# server.basehref: /argocd
# server.insecure: "true"  ← TLS: false
```

### 2. Ingress 설정 확인

```bash
kubectl describe ingress argocd-ingress -n argocd

# 결과:
# backend-protocol: HTTPS  ← ❌ 문제!
# Service Port: 443
```

### 3. ArgoCD 실제 동작 확인

```bash
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-server --tail=20

# 로그 출력:
# "argocd v3.1.9+8665140 serving on port 8080 (url: , tls: false)"
#                                                           ^^^^^^^^
```

### 4. 문제 식별

```
Ingress → backend-protocol: HTTPS → Service:443
           ↓
       ArgoCD Pod: HTTP 8080 (tls: false)
           ↓
       프로토콜 불일치! ❌
```

**ALB가 HTTPS로 연결 시도 → ArgoCD는 HTTP만 지원 → Health Check 실패 → 502**

---

## ✅ 해결 방법

### 즉시 적용 (현재 클러스터)

```bash
# 1. Ingress backend-protocol을 HTTP로 변경
kubectl annotate ingress argocd-ingress -n argocd \
  alb.ingress.kubernetes.io/backend-protocol=HTTP \
  --overwrite

# 2. Service Port를 443 → 80으로 변경
kubectl patch ingress argocd-ingress -n argocd --type json -p '[
  {
    "op": "replace",
    "path": "/spec/rules/0/http/paths/0/backend/service/port/number",
    "value": 80
  }
]'

# 3. 확인
kubectl describe ingress argocd-ingress -n argocd | grep -A5 "backend-protocol"
```

### Ansible 설정 업데이트

**파일:** `ansible/playbooks/07-ingress-resources.yml`

**변경 전:**
```yaml
- name: "ArgoCD Ingress 생성 (/argocd)"
  shell: |
    kubectl patch svc argocd-server -n argocd -p '{"spec":{"type":"NodePort"}}'
    
    kubectl apply -f - <<EOF
    apiVersion: networking.k8s.io/v1
    kind: Ingress
    metadata:
      name: argocd-ingress
      namespace: argocd
      annotations:
        alb.ingress.kubernetes.io/backend-protocol: HTTPS  ← ❌
    spec:
      rules:
      - host: {{ domain_name }}
        http:
          paths:
          - path: /argocd
            backend:
              service:
                name: argocd-server
                port:
                  number: 443  ← ❌
    EOF
```

**변경 후:**
```yaml
- name: "ArgoCD Ingress 생성 (/argocd)"
  shell: |
    kubectl patch svc argocd-server -n argocd -p '{"spec":{"type":"NodePort"}}'
    
    kubectl apply -f - <<EOF
    apiVersion: networking.k8s.io/v1
    kind: Ingress
    metadata:
      name: argocd-ingress
      namespace: argocd
      annotations:
        alb.ingress.kubernetes.io/backend-protocol: HTTP  ← ✅
    spec:
      rules:
      - host: {{ domain_name }}
        http:
          paths:
          - path: /argocd
            backend:
              service:
                name: argocd-server
                port:
                  number: 80  ← ✅
    EOF
```

---

## 📋 검증

### 1. Target Health 확인 (1-2분 후)

```bash
# AWS CLI로 확인
ALB_ARN=$(aws elbv2 describe-load-balancers --region ap-northeast-2 \
  --query 'LoadBalancers[?contains(LoadBalancerName, `k8s-growbinalb`)].LoadBalancerArn' \
  --output text)

TG_ARN=$(aws elbv2 describe-target-groups --region ap-northeast-2 \
  --query 'TargetGroups[?contains(TargetGroupName, `argocd`)].TargetGroupArn' \
  --output text)

aws elbv2 describe-target-health --target-group-arn "$TG_ARN" --region ap-northeast-2

# 예상 결과:
# TargetHealth.State: healthy (6/6)
```

### 2. 웹 접속 테스트

```bash
curl -I https://growbin.app/argocd

# 예상 결과:
# HTTP/2 200
```

브라우저: `https://growbin.app/argocd`

### 3. ArgoCD 로그인

```bash
# 비밀번호 확인
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d
```

**User:** `admin`  
**Password:** (위 명령어 결과)

---

## 🔍 진단 과정

### 1. ArgoCD ConfigMap 확인
```bash
kubectl get configmap argocd-cmd-params-cm -n argocd -o yaml | grep -E '(rootpath|basehref|insecure)'
```

✅ rootpath/basehref 설정 확인  
✅ server.insecure = true 확인

### 2. ArgoCD Pod 상태
```bash
kubectl get pods -n argocd -l app.kubernetes.io/name=argocd-server
```

✅ Running 확인

### 3. ArgoCD 로그
```bash
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-server --tail=20
```

✅ "serving on port 8080 (tls: false)" 확인

### 4. Service Endpoints
```bash
kubectl get endpoints argocd-server -n argocd
```

✅ Endpoints: `192.168.x.x:8080` 확인

### 5. Ingress 설정
```bash
kubectl describe ingress argocd-ingress -n argocd | grep -A5 annotations
```

❌ **backend-protocol: HTTPS** 발견! → 문제 원인 식별

---

## 📊 프로토콜 흐름도

### 수정 전 (502 에러)
```
Browser (HTTPS) → ALB (HTTPS) → Ingress (backend: HTTPS) → Service:443
                                                              ↓
                                                         ArgoCD: HTTP 8080
                                                              ❌ 프로토콜 불일치
```

### 수정 후 (정상)
```
Browser (HTTPS) → ALB (HTTPS) → Ingress (backend: HTTP) → Service:80
                                                            ↓
                                                       ArgoCD: HTTP 8080
                                                            ✅ 정상 연결
```

---

## 🎯 핵심 교훈

### 1. ALB Backend Protocol 설정

| 서비스 | TLS 지원 | Backend Protocol | Service Port |
|--------|---------|------------------|--------------|
| ArgoCD | ❌ (insecure: true) | HTTP | 80 |
| Grafana | ❌ | HTTP | 80 |
| API | ❌ | HTTP | 80 |

**중요:** `server.insecure: true`로 설정된 ArgoCD는 HTTP만 지원!

### 2. Health Check 경로

ArgoCD는 `/argocd/api/version` 경로를 Health Check로 사용 가능하지만,  
backend-protocol이 HTTP여야 정상 응답.

### 3. Service Type

ALB `target-type: instance` 사용 시:
- Service는 **반드시 NodePort** 타입
- Ansible에서 자동으로 patch 적용:
  ```yaml
  kubectl patch svc argocd-server -n argocd -p '{"spec":{"type":"NodePort"}}'
  ```

---

## 🔗 관련 문서

- [ArgoCD Ingress Configuration](https://argo-cd.readthedocs.io/en/stable/operator-manual/ingress/)
- [AWS ALB Controller Annotations](https://kubernetes-sigs.github.io/aws-load-balancer-controller/v2.4/guide/ingress/annotations/)
- [ArgoCD Sub-path Configuration](https://argo-cd.readthedocs.io/en/stable/operator-manual/server-commands/argocd-server/)

---

## 📝 추가 참고

### Grafana 설정 비교 (정상 작동)

Grafana는 처음부터 올바르게 설정되어 정상 작동:

```yaml
annotations:
  alb.ingress.kubernetes.io/backend-protocol: HTTP  ← ✅
spec:
  rules:
  - host: growbin.app
    http:
      paths:
      - path: /grafana
        backend:
          service:
            name: prometheus-grafana
            port:
              number: 80  ← ✅
```

**Grafana ConfigMap 서브 경로 설정:**
```ini
[server]
root_url = https://growbin.app/grafana
serve_from_sub_path = true
```

ArgoCD도 동일한 패턴으로 설정하면 정상 작동!

---

**작성일:** 2025-11-04  
**적용 버전:** ArgoCD v3.1.9  
**클러스터:** k8s-worker-1 (ArgoCD Server Pod 위치)

