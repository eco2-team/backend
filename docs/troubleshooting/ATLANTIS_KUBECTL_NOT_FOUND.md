# Atlantis Pod에서 kubectl을 찾을 수 없는 문제

## 📋 증상

Atlantis Pod에서 kubectl을 실행하려고 할 때 다음 에러 발생:

```
error: Internal error occurred: error executing command in container: 
failed to exec in container: failed to start exec: 
exec: "kubectl": executable file not found in $PATH
```

---

## 🔍 원인 분석

### 문제점

1. **Init Container에서 kubectl 설치 위치**: `/shared/kubectl`
2. **Main Container 마운트 경로**: `/usr/local/bin/kubectl` (subPath 사용)
3. **결과**: subPath로 단일 파일을 마운트하려 했지만 디렉토리 구조가 맞지 않음

### 근본 원인

- Init Container에서 `/shared/kubectl`에 복사
- Main Container에서 `/usr/local/bin/kubectl`에 subPath로 마운트 시도
- subPath는 파일이 아니라 디렉토리 구조를 유지해야 함

---

## ✅ 해결 방법

### 수정된 구조

1. **Init Container**: `/shared/usr/local/bin/kubectl`에 복사
2. **Main Container**: `/shared/usr/local/bin`을 `/usr/local/bin`에 subPath로 마운트
3. **PATH 환경 변수**: `/usr/local/bin` 포함 확인

### 적용

```bash
# 1. 수정된 Deployment 적용
kubectl apply -f k8s/atlantis/atlantis-deployment.yaml

# 2. StatefulSet 재시작
kubectl rollout restart statefulset/atlantis -n atlantis

# 3. Pod 재시작 대기
kubectl rollout status statefulset/atlantis -n atlantis

# 4. kubectl 확인
kubectl exec -n atlantis atlantis-0 -- kubectl version --client
```

---

## 🔧 수정된 설정

### Init Container

```yaml
initContainers:
  - name: install-kubectl
    image: bitnami/kubectl:latest
    command:
      - /bin/sh
      - -c
      - |
        cp /opt/bitnami/kubectl/bin/kubectl /shared/usr/local/bin/kubectl
        chmod +x /shared/usr/local/bin/kubectl
        /shared/usr/local/bin/kubectl version --client
    volumeMounts:
      - name: kubectl
        mountPath: /shared
```

### Main Container

```yaml
volumeMounts:
  - name: kubectl
    mountPath: /usr/local/bin
    subPath: usr/local/bin
    readOnly: true

env:
  - name: PATH
    value: "/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
```

### Volume

```yaml
volumes:
  - name: kubectl
    emptyDir: {}
```

---

## 🧪 검증

### 1. Init Container 로그 확인

```bash
kubectl logs -n atlantis atlantis-0 -c install-kubectl
```

**예상 결과**:
```
Client Version: version.Info{Major:"1", Minor:"28", ...}
✅ kubectl installed to /shared/usr/local/bin/kubectl
```

### 2. Main Container에서 kubectl 확인

```bash
# kubectl 경로 확인
kubectl exec -n atlantis atlantis-0 -- which kubectl

# kubectl 버전 확인
kubectl exec -n atlantis atlantis-0 -- kubectl version --client

# PATH 확인
kubectl exec -n atlantis atlantis-0 -- echo $PATH
```

**예상 결과**:
```
/usr/local/bin/kubectl
Client Version: version.Info{Major:"1", Minor:"28", ...}
/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
```

### 3. ConfigMap 생성 테스트

```bash
# Atlantis Pod에서 ConfigMap 생성 테스트
kubectl exec -n atlantis atlantis-0 -- kubectl create configmap test-config \
  --from-literal=test=value \
  --namespace=argocd \
  --dry-run=client -o yaml
```

---

## 📝 관련 파일

- `k8s/atlantis/atlantis-deployment.yaml`: Init Container 및 Volume 설정
- `atlantis.yaml`: Workflow에서 kubectl 사용

---

## 🔗 관련 문서

- [Phase 3 구현 가이드](../deployment/PHASE3_IMPLEMENTATION.md)
- [Atlantis 현재 상태](../deployment/ATLANTIS_CURRENT_STATUS.md)

---

**작성일**: 2025-11-09  
**해결 버전**: v0.7.0 (Phase 3)

