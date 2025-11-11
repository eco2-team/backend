# Atlantis 실행 파일을 찾을 수 없는 문제

## 📋 증상

Atlantis Pod가 시작되지 않고 다음 에러 발생:

```
Error: failed to create containerd task: failed to create shim task: OCI runtime create failed: 
runc create failed: unable to start container process: error during container init: 
exec: "atlantis": executable file not found in $PATH: unknown
```

### Pod 이벤트

```
Warning  Failed     55s (x4 over 87s)  kubelet  Error: failed to create containerd task: 
failed to create shim task: OCI runtime create failed: runc create failed: 
unable to start container process: error during container init: 
exec: "atlantis": executable file not found in $PATH: unknown
```

---

## 🔍 원인 분석

### 문제점

1. **command 지정 오류**: `command: ["atlantis"]`로 지정했지만, 컨테이너 내부에서 `atlantis` 실행 파일을 찾을 수 없음
2. **이미지 ENTRYPOINT**: Atlantis 공식 이미지(`ghcr.io/runatlantis/atlantis:v0.27.0`)는 이미 ENTRYPOINT가 설정되어 있음
3. **PATH 문제**: `atlantis` 실행 파일이 `$PATH`에 없거나, `command`를 지정하면 이미지의 기본 ENTRYPOINT가 무시됨

### 근본 원인

- Atlantis 이미지는 이미 ENTRYPOINT가 `/usr/local/bin/atlantis` 또는 `/bin/atlantis`로 설정되어 있음
- `command`를 명시적으로 지정하면 이미지의 기본 ENTRYPOINT가 무시되고, 지정한 `command`를 찾으려고 시도
- 하지만 `command: ["atlantis"]`는 상대 경로이므로 `$PATH`에서 찾으려고 하는데, 실제 실행 파일 경로와 다를 수 있음

---

## ✅ 해결 방법

### 방법 1: command 제거 (권장)

이미지의 기본 ENTRYPOINT를 사용하도록 `command`를 제거:

```yaml
containers:
  - name: atlantis
    image: ghcr.io/runatlantis/atlantis:v0.27.0
    # command 제거 (이미지의 기본 ENTRYPOINT 사용)
    args:
      - server
      - --atlantis-url=https://atlantis.growbin.app
      - --repo-allowlist=github.com/SeSACTHON/*
      - --gh-user=SeSACTHON
      - --hide-prev-plan-comments
      - --port=4141
```

### 방법 2: 전체 경로 지정

전체 경로를 명시적으로 지정:

```yaml
containers:
  - name: atlantis
    image: ghcr.io/runatlantis/atlantis:v0.27.0
    command: ["/usr/local/bin/atlantis"]  # 또는 ["/bin/atlantis"]
    args:
      - server
      - --atlantis-url=https://atlantis.growbin.app
      # ... 나머지 args
```

---

## 🔧 적용된 수정사항

### `k8s/atlantis/atlantis-deployment.yaml`

```yaml
# 수정 전
command: ["atlantis"]
args:
  - server
  # ...

# 수정 후
# command는 제거 (이미지의 기본 ENTRYPOINT 사용)
args:
  - server
  # ...
```

---

## 🧪 검증

### 1. Deployment 적용

```bash
# Master 노드에서
kubectl apply -f /tmp/atlantis-deployment.yaml

# 또는 Ansible 재실행
ansible-playbook -i ansible/inventory/hosts.ini ansible/playbooks/09-atlantis.yml
```

### 2. Pod 상태 확인

```bash
kubectl get pods -n atlantis
kubectl describe pod atlantis-0 -n atlantis
```

**예상 결과**:
```
NAME          READY   STATUS    RESTARTS   AGE
atlantis-0    1/1     Running   0          30s
```

### 3. Pod 로그 확인

```bash
kubectl logs -n atlantis atlantis-0
```

**예상 결과**:
```
2025/11/11 02:34:53+0000 [INFO] server: Starting server...
2025/11/11 02:34:53+0000 [INFO] server: Atlantis started - listening on port 4141
```

### 4. Health Check 확인

```bash
kubectl exec -n atlantis atlantis-0 -- curl -s http://localhost:4141/healthz
```

**예상 결과**:
```
ok
```

---

## 📝 관련 파일

- `k8s/atlantis/atlantis-deployment.yaml`: Container command/args 설정
- `ansible/playbooks/09-atlantis.yml`: Atlantis 배포 Playbook

---

## 🔗 관련 문서

- [Atlantis 공식 문서](https://www.runatlantis.io/docs/)
- [Kubernetes Container Command/Args](https://kubernetes.io/docs/tasks/inject-data-application/define-command-argument-container/)
- [Atlantis Pod CrashLoopBackOff 문제](./ATLANTIS_POD_CRASHLOOPBACKOFF.md)

---

## 💡 참고사항

### Docker 이미지 ENTRYPOINT 확인

```bash
# 이미지의 ENTRYPOINT 확인
docker inspect ghcr.io/runatlantis/atlantis:v0.27.0 | grep -A 5 Entrypoint
```

**예상 결과**:
```json
"Entrypoint": [
    "/usr/local/bin/atlantis"
]
```

### Kubernetes에서 ENTRYPOINT 사용

- Kubernetes의 `command`는 Docker의 ENTRYPOINT를 덮어씀
- `command`를 지정하지 않으면 이미지의 기본 ENTRYPOINT 사용
- `args`는 `command`(또는 ENTRYPOINT)에 전달되는 인자

---

**작성일**: 2025-11-11  
**해결 버전**: v0.7.0 (Phase 3)

