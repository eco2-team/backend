# ArgoCD Deployment 트러블슈팅

> **작성일**: 2025-11-19  
> **목적**: ArgoCD 배포 시 발생하는 일반적인 문제와 해결 방법을 문서화하여 재발 방지

---

## 📋 목차

1. [CrashLoopBackOff: Command/Args 충돌](#1-crashloopbackoff-commandargs-충돌)
2. [ERR_TOO_MANY_REDIRECTS: ALB HTTPS 종료 문제](#2-err_too_many_redirects-alb-https-종료-문제)
3. [예방 조치: Ansible Role 개선](#3-예방-조치-ansible-role-개선)

---

## 1. CrashLoopBackOff: Command/Args 충돌

### 🚨 증상

```bash
$ kubectl get pods -n argocd
NAME                                READY   STATUS             RESTARTS   AGE
argocd-server-58d469d955-kmdd6     0/1     CrashLoopBackOff   4          2m

$ kubectl logs argocd-server-58d469d955-kmdd6 -n argocd
Error: unknown command "/usr/local/bin/argocd-server" for "argocd-server"
```

### 🔍 원인 분석

Ansible playbook에서 `kubectl patch`를 사용하여 Deployment의 `command`만 변경했으나, 원래 있던 `args`는 그대로 남아 있어 충돌 발생:

**잘못된 상태:**
```yaml
containers:
  - name: argocd-server
    command: ["argocd-server", "--insecure"]  # Ansible이 패치한 부분
    args: ["/usr/local/bin/argocd-server"]    # 원래 있던 args (그대로 남음)
```

**실제 실행된 명령어:**
```bash
argocd-server --insecure /usr/local/bin/argocd-server
# → Error: unknown command "/usr/local/bin/argocd-server"
```

### ✅ 해결 방법

#### Option 1: ConfigMap 사용 (권장)

ArgoCD는 `argocd-cmd-params-cm` ConfigMap을 통해 설정을 관리하는 것이 표준 방식입니다.

```bash
# 1. ConfigMap에 insecure 설정 추가
kubectl patch configmap argocd-cmd-params-cm -n argocd \
  --type merge \
  -p '{"data":{"server.insecure":"true"}}'

# ConfigMap이 없는 경우 생성
kubectl create configmap argocd-cmd-params-cm -n argocd \
  --from-literal=server.insecure=true

# 2. Deployment의 잘못된 command 패치 제거 (있다면)
kubectl -n argocd patch deployment argocd-server --type json \
  -p '[{"op": "remove", "path": "/spec/template/spec/containers/0/command"}]'

# 3. 파드 재시작
kubectl rollout restart deployment argocd-server -n argocd

# 4. 상태 확인
kubectl rollout status deployment argocd-server -n argocd --timeout=300s
```

#### Option 2: Command와 Args를 명시적으로 설정

```bash
kubectl -n argocd patch deployment argocd-server --type json \
  -p '[
    {"op": "add", "path": "/spec/template/spec/containers/0/command", "value": ["argocd-server"]},
    {"op": "add", "path": "/spec/template/spec/containers/0/args", "value": ["--insecure"]}
  ]'
```

### 📊 검증

```bash
# 1. 파드 상태 확인
kubectl get pods -n argocd -l app.kubernetes.io/name=argocd-server

# 2. 로그에서 에러 없는지 확인
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-server --tail=50

# 3. ConfigMap 확인
kubectl get configmap argocd-cmd-params-cm -n argocd -o yaml | grep insecure

# 4. Deployment 설정 확인
kubectl get deployment argocd-server -n argocd -o yaml | grep -A 5 "command:"
```

**정상 상태:**
```yaml
# ConfigMap 사용 시
containers:
  - name: argocd-server
    image: quay.io/argoproj/argocd:v3.2.0
    # command/args 없음 (기본값 사용)
    env:
      - name: ARGOCD_SERVER_INSECURE
        valueFrom:
          configMapKeyRef:
            name: argocd-cmd-params-cm
            key: server.insecure
```

---

## 2. ERR_TOO_MANY_REDIRECTS: ALB HTTPS 종료 문제

### 🚨 증상

웹 브라우저에서 ArgoCD URL 접속 시:
```
ERR_TOO_MANY_REDIRECTS
argocd.dev.growbin.app에서 리디렉션한 횟수가 너무 많습니다.
```

### 🔍 원인 분석

ALB(Application Load Balancer)가 HTTPS를 종료하고 HTTP로 ArgoCD에 전달하는데, ArgoCD는 HTTPS가 아니라고 판단하여 계속 HTTPS로 리디렉션 시도 → 무한 루프 발생

```
사용자 브라우저 (HTTPS)
    ↓
ALB (HTTPS 종료)
    ↓
ArgoCD (HTTP 수신) → "HTTPS 아니네? HTTPS로 리디렉션!" → 무한 루프
```

### ✅ 해결 방법

ArgoCD를 **insecure 모드**로 실행하여 HTTP 트래픽을 정상적으로 처리하도록 설정:

```bash
# ConfigMap에 insecure 설정
kubectl patch configmap argocd-cmd-params-cm -n argocd \
  --type merge \
  -p '{"data":{"server.insecure":"true"}}'

# 파드 재시작
kubectl rollout restart deployment argocd-server -n argocd
```

### 🔧 Ingress 설정 확인

Ingress에 다음 annotation이 반드시 필요합니다:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: argocd-server
  namespace: argocd
  annotations:
    # 중요: ArgoCD와 통신 시 HTTP 프로토콜 사용
    alb.ingress.kubernetes.io/backend-protocol: HTTP
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}, {"HTTPS": 443}]'
    alb.ingress.kubernetes.io/ssl-redirect: '443'
```

### 📊 검증

```bash
# 1. ArgoCD 서버가 HTTP로 응답하는지 확인
kubectl exec -n argocd deployment/argocd-server -- curl -s http://localhost:8080/healthz
# 응답: ok

# 2. 포트포워딩으로 로컬 테스트
kubectl port-forward svc/argocd-server -n argocd 8080:80
# 브라우저에서 http://localhost:8080 접속

# 3. Ingress 확인
kubectl describe ingress argocd-server -n argocd | grep -A 5 "Annotations"
```

---

## 3. 예방 조치: Ansible Role 개선

### 🎯 핵심 원칙

1. **Deployment를 직접 패치하지 않는다** - ArgoCD의 기본 구조를 건드리지 않음
2. **ConfigMap을 사용한다** - ArgoCD의 표준 설정 방식 준수
3. **멱등성을 보장한다** - 여러 번 실행해도 동일한 결과 보장

### 📝 개선된 Ansible Task

**Before (문제 있는 버전):**
```yaml
- name: ArgoCD Server를 insecure 모드로 설정 (ALB HTTPS 종료 대응)
  command: >
    kubectl -n {{ argocd_namespace }}
    patch deployment argocd-server
    --type json
    -p '[{"op": "replace", "path": "/spec/template/spec/containers/0/command", "value": ["argocd-server", "--insecure"]}]'
  register: argocd_insecure_result
  changed_when: "'patched' in argocd_insecure_result.stdout"
  when: argocd_install is succeeded
```

**After (개선된 버전):**
```yaml
- name: ArgoCD Server를 insecure 모드로 설정 (ALB HTTPS 종료 대응)
  command: >
    kubectl -n {{ argocd_namespace }}
    patch configmap argocd-cmd-params-cm
    --type merge
    -p '{"data":{"server.insecure":"true"}}'
  register: argocd_insecure_result
  changed_when: "'patched' in argocd_insecure_result.stdout or 'configured' in argocd_insecure_result.stdout"
  when: argocd_install is succeeded

- name: ArgoCD Server 파드 재시작 (insecure 모드 적용)
  command: kubectl rollout restart deployment argocd-server -n {{ argocd_namespace }}
  when: argocd_insecure_result is changed

- name: ArgoCD Server 파드 재시작 대기 (insecure 모드 적용)
  command: kubectl rollout status deployment argocd-server -n {{ argocd_namespace }} --timeout=300s
  when: argocd_insecure_result is changed
```

### 🔒 개선 사항

| 항목 | Before | After |
|------|--------|-------|
| **설정 방법** | Deployment 직접 패치 | ConfigMap 사용 |
| **ArgoCD 호환성** | 비표준 방식 | 공식 표준 방식 |
| **재시작 처리** | 자동 재시작 (불확실) | 명시적 재시작 + 대기 |
| **멱등성** | 제한적 | 완전 보장 |
| **위험도** | 높음 (command/args 충돌) | 낮음 |

### 📚 참고 자료

- [ArgoCD Ingress Configuration](https://argo-cd.readthedocs.io/en/stable/operator-manual/ingress/)
- [ArgoCD Server Parameters](https://argo-cd.readthedocs.io/en/stable/operator-manual/server-commands/argocd-server/)
- [AWS ALB Ingress Controller Annotations](https://kubernetes-sigs.github.io/aws-load-balancer-controller/v2.4/guide/ingress/annotations/)

---

## 🔍 추가 트러블슈팅

### ArgoCD 서버가 계속 재시작되는 경우

```bash
# 1. 리소스 부족 확인
kubectl top nodes
kubectl describe pod -n argocd -l app.kubernetes.io/name=argocd-server

# 2. 이벤트 확인
kubectl get events -n argocd --sort-by='.lastTimestamp' | tail -20

# 3. 상세 로그 확인
kubectl logs -n argocd deployment/argocd-server --previous
```

### ConfigMap 변경이 적용되지 않는 경우

```bash
# 파드를 강제로 재생성
kubectl delete pod -n argocd -l app.kubernetes.io/name=argocd-server

# 또는 Deployment 재시작
kubectl rollout restart deployment argocd-server -n argocd
```

### Ingress가 생성되었으나 ALB가 생성되지 않는 경우

```bash
# ALB Controller 로그 확인
kubectl logs -n kube-system deployment/aws-load-balancer-controller

# Ingress 이벤트 확인
kubectl describe ingress argocd-server -n argocd
```

---

## ✅ 체크리스트

ArgoCD 배포 후 반드시 확인:

- [ ] ArgoCD 파드가 `Running` 상태
- [ ] `server.insecure=true` ConfigMap 설정 확인
- [ ] Deployment에 잘못된 `command` 패치가 없음
- [ ] Ingress에 `backend-protocol: HTTP` annotation 존재
- [ ] 웹 브라우저에서 리디렉션 없이 정상 접속
- [ ] 초기 admin 비밀번호 획득 가능

```bash
# 한 번에 모든 항목 확인
kubectl get pods -n argocd -l app.kubernetes.io/name=argocd-server
kubectl get configmap argocd-cmd-params-cm -n argocd -o yaml | grep insecure
kubectl get deployment argocd-server -n argocd -o yaml | grep -A 3 "command:"
kubectl get ingress -n argocd -o yaml | grep backend-protocol
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```

---

**문서 버전**: v1.0.0  
**최종 수정**: 2025-11-19  
**담당자**: DevOps Team


