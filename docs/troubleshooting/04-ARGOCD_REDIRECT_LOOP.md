# ArgoCD 리디렉션 루프 문제 해결

## 📊 문제 상황

### 증상
```
브라우저 접속: https://argocd.growbin.app
→ "리디렉션한 횟수가 너무 많습니다" 에러
→ 페이지가 작동하지 않습니다
```

### HTTP 응답
```bash
curl -I https://argocd.growbin.app
# HTTP/2 307 (Temporary Redirect) 반복
```

---

## 🔍 원인 분석

### 1. Ingress 설정 확인

```bash
kubectl get ingress -n argocd argocd-ingress -o yaml
```

**문제점:**
- `backend-protocol`이 설정되지 않음 (기본값: HTTP)
- Service Port: `443` (HTTPS)
- ArgoCD는 실제로 HTTP(8080)로만 동작

### 2. ArgoCD Service 확인

```bash
kubectl get svc -n argocd argocd-server -o yaml
```

**결과:**
```yaml
ports:
  - name: http
    port: 80
    targetPort: 8080
  - name: https
    port: 443
    targetPort: 8080  # ← HTTP로 동작!
```

### 3. ArgoCD ConfigMap 확인

```bash
kubectl get configmap -n argocd argocd-cmd-params-cm -o yaml
```

**결과:**
- `server.insecure: true` (ALB에서 HTTPS 종료)

### 4. 문제 식별

```
ALB (HTTPS) → Ingress (backend-protocol 미설정) → Service:443
                                                      ↓
                                              ArgoCD: HTTP 8080
                                                      ↓
                                              프로토콜 불일치!
                                                      ↓
                                              리디렉션 루프 발생
```

**핵심 문제:**
1. Ingress가 포트 443을 사용하지만 `backend-protocol: HTTPS`가 설정되지 않음
2. ALB가 HTTPS로 연결 시도하지만 ArgoCD는 HTTP만 지원
3. Health Check 실패로 Target Group이 unhealthy 상태

---

## ✅ 해결 방법

### 즉시 적용 (현재 클러스터)

```bash
# 1. Ingress backend-protocol을 HTTP로 변경
kubectl annotate ingress -n argocd argocd-ingress \
  alb.ingress.kubernetes.io/backend-protocol=HTTP \
  alb.ingress.kubernetes.io/healthcheck-protocol=HTTP \
  --overwrite

# 2. Service Port를 443 → 80으로 변경
kubectl patch ingress -n argocd argocd-ingress --type json -p='[
  {"op": "replace", "path": "/spec/rules/0/http/paths/0/backend/service/port/number", "value": 80}
]'

# 3. Health Check 경로 설정
kubectl annotate ingress -n argocd argocd-ingress \
  alb.ingress.kubernetes.io/healthcheck-path=/healthz \
  --overwrite

# 4. ArgoCD ConfigMap에 insecure 모드 설정 (ALB에서 HTTPS 종료)
kubectl patch configmap -n argocd argocd-cmd-params-cm --type merge -p '{"data":{"server.insecure":"true"}}'

# 5. ArgoCD Server 재시작
kubectl rollout restart deployment -n argocd argocd-server

# 6. ALB 재구성 대기 (60초)
sleep 60
```

### 최종 확인

```bash
# Target Group Health 확인
ALB_ARN="arn:aws:elasticloadbalancing:ap-northeast-2:721622471953:loadbalancer/app/k8s-ecoecomain-f37ee763b5/25cd1a7b2f4ccbbc"
TG_ARN=$(aws elbv2 describe-target-groups --load-balancer-arn "$ALB_ARN" --region ap-northeast-2 \
  --query "TargetGroups[?contains(TargetGroupName, 'argocd')].TargetGroupArn" --output text)
aws elbv2 describe-target-health --target-group-arn "$TG_ARN" --region ap-northeast-2

# 접속 테스트
curl -I https://argocd.growbin.app
# 예상 결과: HTTP/2 200
```

---

## 📋 변경 사항 요약

### Ingress 설정 변경

**변경 전:**
```yaml
annotations:
  # backend-protocol 미설정 (기본값: HTTP)
spec:
  rules:
  - host: argocd.growbin.app
    http:
      paths:
      - backend:
          service:
            name: argocd-server
            port:
              number: 443  # ← HTTPS 포트
```

**변경 후:**
```yaml
annotations:
  alb.ingress.kubernetes.io/backend-protocol: HTTP  # ← 명시적 설정
  alb.ingress.kubernetes.io/healthcheck-protocol: HTTP
  alb.ingress.kubernetes.io/healthcheck-path: /healthz
spec:
  rules:
  - host: argocd.growbin.app
    http:
      paths:
      - backend:
          service:
            name: argocd-server
            port:
              number: 80  # ← HTTP 포트
```

### ArgoCD ConfigMap 변경

**추가:**
```yaml
data:
  server.insecure: "true"  # ALB에서 HTTPS 종료
```

---

## 🔍 진단 과정

### 1. Ingress 설정 확인
```bash
kubectl get ingress -n argocd argocd-ingress -o yaml | grep -A 10 "annotations:"
```

### 2. Service 포트 확인
```bash
kubectl get svc -n argocd argocd-server -o yaml | grep -A 10 "ports:"
```

### 3. Target Group Health 확인
```bash
# AWS CLI로 확인
aws elbv2 describe-target-health --target-group-arn <TG_ARN> --region ap-northeast-2
```

**결과:**
- 모든 Target이 `unhealthy` 상태
- Reason: `Target.FailedHealthChecks`

### 4. HTTP 응답 확인
```bash
curl -v https://argocd.growbin.app 2>&1 | grep -E "< HTTP|< Location"
```

**결과:**
- `HTTP/2 307` 반복 (리디렉션 루프)

---

## 📊 프로토콜 흐름도

### 수정 전 (리디렉션 루프)
```
Browser (HTTPS) → ALB (HTTPS) → Ingress (미설정) → Service:443
                                                      ↓
                                              ArgoCD: HTTP 8080
                                                      ↓
                                              프로토콜 불일치
                                                      ↓
                                              Health Check 실패
                                                      ↓
                                              리디렉션 루프
```

### 수정 후 (정상)
```
Browser (HTTPS) → ALB (HTTPS) → Ingress (backend: HTTP) → Service:80
                                                              ↓
                                                      ArgoCD: HTTP 8080
                                                              ↓
                                                      정상 연결 ✅
```

---

## 🎯 핵심 교훈

### 1. ALB Backend Protocol 설정

| 서비스 | TLS 지원 | Backend Protocol | Service Port |
|--------|---------|------------------|--------------|
| ArgoCD | ❌ (insecure: true) | **HTTP** | **80** |
| Grafana | ❌ | HTTP | 80 |
| API | ❌ | HTTP | 80 |

**중요:** `server.insecure: true`로 설정된 ArgoCD는 HTTP만 지원!

### 2. Health Check 설정

- **경로:** `/healthz`
- **프로토콜:** HTTP (backend-protocol과 동일)
- **간격:** 30초 (기본값)

### 3. Service Type

ALB `target-type: instance` 사용 시:
- Service는 **반드시 NodePort** 타입
- 포트는 HTTP(80) 사용

---

## 🔗 관련 문서

- [AWS ALB Controller Annotations](https://kubernetes-sigs.github.io/aws-load-balancer-controller/v2.4/guide/ingress/annotations/)
- [ArgoCD Ingress Configuration](https://argo-cd.readthedocs.io/en/stable/operator-manual/ingress/)
- [ArgoCD Server Configuration](https://argo-cd.readthedocs.io/en/stable/operator-manual/server-commands/argocd-server/)

---

## 📝 추가 참고

### Grafana 설정 비교 (정상 작동)

Grafana는 처음부터 올바르게 설정되어 정상 작동:

```yaml
annotations:
  alb.ingress.kubernetes.io/backend-protocol: HTTP  # ✅
spec:
  rules:
  - host: grafana.growbin.app
    http:
      paths:
      - backend:
          service:
            name: prometheus-grafana
            port:
              number: 80  # ✅
```

ArgoCD도 동일한 패턴으로 설정하면 정상 작동!

---

**작성일:** 2025-11-09  
**적용 버전:** ArgoCD v3.1.9+  
**클러스터:** 14-Node Architecture

