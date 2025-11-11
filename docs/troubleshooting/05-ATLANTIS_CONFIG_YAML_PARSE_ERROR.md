# Atlantis ConfigMap YAML 파싱 에러

## 📋 증상

Atlantis Pod가 `CrashLoopBackOff` 상태이며, 다음과 같은 YAML 파싱 에러가 발생:

```
Error: initializing server: parsing /etc/atlantis/atlantis.yaml file: yaml: unmarshal errors:
  line 1: field version not found in type raw.GlobalCfg
  line 2: field automerge not found in type raw.GlobalCfg
  line 3: field delete_source_branch_on_merge not found in type raw.GlobalCfg
  line 4: field parallel_plan not found in type raw.GlobalCfg
  line 5: field parallel_apply not found in type raw.GlobalCfg
  line 7: field projects not found in type raw.GlobalCfg
  line 85: field hide_prev_plan_comments not found in type raw.GlobalCfg
  line 86: field silence_whitelist_errors not found in type raw.GlobalCfg
  line 87: field silence_vcs_status_no_plans not found in type raw.GlobalCfg
```

### Pod 상태

```bash
$ kubectl get pods -n atlantis
NAME         READY   STATUS             RESTARTS      AGE
atlantis-0   0/1     CrashLoopBackOff   4 (56s ago)   2m30s

$ kubectl logs -n atlantis atlantis-0
No files found in /docker-entrypoint.d/, skipping
Error: initializing server: parsing /etc/atlantis/atlantis.yaml file: yaml: unmarshal errors:
  line 1: field version not found in type raw.GlobalCfg
  ...
```

---

## 🔍 원인 분석

### 문제점

**Atlantis Config 파일의 두 가지 타입을 혼동함**

1. **Repo-level Config** (`.atlantis.yaml` 또는 `atlantis.yaml` in repository)
   - Repository 루트에 위치
   - `version`, `automerge`, `projects`, `workflows` 등을 직접 정의
   - 각 레포지토리가 자체 설정을 관리

2. **Server-side Repo Config** (`ATLANTIS_REPO_CONFIG` 환경변수)
   - Atlantis 서버에서 관리
   - `repos`와 `workflows` 두 섹션으로 구성
   - 여러 레포지토리에 대한 중앙 집중식 설정

### 근본 원인

현재 ConfigMap에 저장된 `atlantis.yaml`은 **Repo-level Config 형식**인데, `ATLANTIS_REPO_CONFIG` 환경변수로 **Server-side Repo Config**로 사용하려고 해서 파싱 에러가 발생했습니다.

### 잘못된 형식 (Repo-level Config)

```yaml
# ❌ 이것은 Repo-level Config 형식입니다
version: 3
automerge: true
delete_source_branch_on_merge: true
parallel_plan: true
parallel_apply: true

projects:
- name: terraform-infrastructure
  dir: terraform/
  workspace: default
  autoplan:
    when_modified: ["*.tf", "*.tfvars"]

workflows:
  infrastructure-workflow:
    plan:
      steps:
      - init
      - plan
```

### 올바른 형식 (Server-side Repo Config)

```yaml
# ✅ 이것은 Server-side Repo Config 형식입니다
# Repositories Configuration
repos:
- id: github.com/SeSACTHON/*
  workflow: infrastructure-workflow
  allowed_overrides:
    - workflow
    - apply_requirements
  allow_custom_workflows: true
  delete_source_branch_on_merge: true

# Workflows Configuration
workflows:
  infrastructure-workflow:
    plan:
      steps:
        - run: echo "🔍 Terraform Plan 시작..."
        - init
        - plan
    apply:
      steps:
        - run: echo "🚀 Terraform Apply 시작..."
        - apply
        - run: echo "✅ Terraform Apply 완료"
```

---

## ✅ 해결 방법

### 방법 1: 자동 스크립트 (권장)

Master 노드에서 실행:

```bash
# 로컬에서 스크립트를 Master 노드로 복사
scp -i ~/.ssh/id_rsa scripts/utilities/fix-atlantis-config.sh ubuntu@<MASTER_IP>:~/

# Master 노드에서 실행
ssh -i ~/.ssh/id_rsa ubuntu@<MASTER_IP>
chmod +x ~/fix-atlantis-config.sh
./fix-atlantis-config.sh
```

### 방법 2: 수동 수정

Master 노드에서 직접 실행:

```bash
# 1. 기존 ConfigMap 삭제
kubectl delete configmap atlantis-repo-config -n atlantis

# 2. 올바른 형식으로 재생성
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: atlantis-repo-config
  namespace: atlantis
data:
  atlantis.yaml: |
    # Atlantis Server-side Repo Config
    # https://www.runatlantis.io/docs/server-side-repo-config.html
    
    # Repositories Configuration
    repos:
    - id: github.com/SeSACTHON/*
      workflow: infrastructure-workflow
      allowed_overrides:
        - workflow
        - apply_requirements
      allow_custom_workflows: true
      delete_source_branch_on_merge: true
    
    # Workflows Configuration
    workflows:
      infrastructure-workflow:
        plan:
          steps:
            - run: echo "🔍 Terraform Plan 시작..."
            - init
            - plan
        apply:
          steps:
            - run: echo "🚀 Terraform Apply 시작..."
            - apply
            - run: echo "✅ Terraform Apply 완료"
EOF

# 3. Atlantis Pod 재시작
kubectl delete pod atlantis-0 -n atlantis

# 4. Pod 상태 확인
kubectl get pods -n atlantis -w
```

### 방법 3: Ansible Playbook 재실행

Ansible playbook이 수정되었으므로 재실행:

```bash
# 로컬에서
cd /Users/mango/workspace/SeSACTHON/backend
ansible-playbook -i ansible/inventory/hosts.ini ansible/playbooks/09-atlantis.yml
```

---

## 🔧 적용된 수정사항

### `ansible/playbooks/09-atlantis.yml`

```yaml
# 추가된 Task
- name: "Atlantis Server-side Repo Config 생성"
  shell: |
    cat <<EOF | kubectl apply -f -
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: atlantis-repo-config
      namespace: atlantis
    data:
      atlantis.yaml: |
        # Atlantis Server-side Repo Config
        # https://www.runatlantis.io/docs/server-side-repo-config.html
        
        # Repositories Configuration
        repos:
        - id: github.com/SeSACTHON/*
          workflow: infrastructure-workflow
          allowed_overrides:
            - workflow
            - apply_requirements
          allow_custom_workflows: true
          delete_source_branch_on_merge: true
        
        # Workflows Configuration
        workflows:
          infrastructure-workflow:
            plan:
              steps:
                - run: echo "🔍 Terraform Plan 시작..."
                - init
                - plan
            apply:
              steps:
                - run: echo "🚀 Terraform Apply 시작..."
                - apply
                - run: echo "✅ Terraform Apply 완료"
    EOF
  register: atlantis_repo_config
```

### 생성된 스크립트

- `scripts/utilities/fix-atlantis-config.sh`: ConfigMap 수정 및 Pod 재시작 스크립트

---

## 🧪 검증

### 1. ConfigMap 확인

```bash
kubectl get configmap atlantis-repo-config -n atlantis -o yaml
```

**예상 결과**:
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: atlantis-repo-config
  namespace: atlantis
data:
  atlantis.yaml: |
    # Atlantis Server-side Repo Config
    repos:
    - id: github.com/SeSACTHON/*
      workflow: infrastructure-workflow
    ...
```

### 2. Pod 상태 확인

```bash
kubectl get pods -n atlantis
```

**예상 결과**:
```
NAME         READY   STATUS    RESTARTS   AGE
atlantis-0   1/1     Running   0          30s
```

### 3. Pod 로그 확인

```bash
kubectl logs -n atlantis atlantis-0
```

**예상 결과**:
```
No files found in /docker-entrypoint.d/, skipping
2025/11/11 03:15:23+0000 [INFO] server: Starting server...
2025/11/11 03:15:23+0000 [INFO] cmd: Atlantis started - listening on port 4141
```

### 4. Health Check

```bash
kubectl exec -n atlantis atlantis-0 -- curl -s http://localhost:4141/healthz
```

**예상 결과**:
```
{
  "status": "ok"
}
```

---

## 📝 관련 파일

- `ansible/playbooks/09-atlantis.yml`: Atlantis 배포 Playbook
- `scripts/utilities/fix-atlantis-config.sh`: ConfigMap 수정 스크립트
- `k8s/atlantis/atlantis-deployment.yaml`: Atlantis Deployment 설정

---

## 🔗 관련 문서

- [Atlantis Server-side Repo Config](https://www.runatlantis.io/docs/server-side-repo-config.html)
- [Atlantis Repo-level Config](https://www.runatlantis.io/docs/repo-level-atlantis-yaml.html)
- [Atlantis Workflows](https://www.runatlantis.io/docs/custom-workflows.html)

---

## 💡 참고사항

### Config 타입 비교

| 특징 | Repo-level Config | Server-side Repo Config |
|------|-------------------|-------------------------|
| **위치** | Repository 루트 | Atlantis 서버 |
| **파일명** | `.atlantis.yaml` | 환경변수로 지정 |
| **관리 주체** | 각 레포지토리 | Atlantis 서버 관리자 |
| **최상위 필드** | `version`, `projects`, `workflows` | `repos`, `workflows` |
| **사용 사례** | 레포지토리별 커스터마이징 | 중앙 집중식 정책 관리 |

### 언제 어떤 Config를 사용할까?

**Repo-level Config 사용 시기**:
- 각 팀이 자체 Terraform 설정을 관리
- 레포지토리마다 다른 워크플로우 필요
- 개발자가 자율적으로 설정 변경

**Server-side Repo Config 사용 시기**:
- 조직 전체에 통일된 정책 적용
- 중앙에서 보안/규정 준수 관리
- 개발자의 설정 변경 제한

### 현재 프로젝트 선택

- **Server-side Repo Config** 사용
- 이유: GitOps 워크플로우 통일, 중앙 관리, 보안 정책 일관성

---

## ❗ 중요 사항

### ATLANTIS_REPO_CONFIG 환경변수

Deployment에서 다음과 같이 설정됨:

```yaml
env:
- name: ATLANTIS_REPO_CONFIG
  value: /etc/atlantis/atlantis.yaml
```

이 환경변수가 설정되면 Atlantis는 **Server-side Repo Config** 형식을 기대합니다.

### ConfigMap 마운트

```yaml
volumeMounts:
- name: atlantis-config-file
  mountPath: /etc/atlantis
  readOnly: true

volumes:
- name: atlantis-config-file
  configMap:
    name: atlantis-repo-config
```

`atlantis-repo-config` ConfigMap이 `/etc/atlantis/atlantis.yaml`로 마운트됩니다.

---

**작성일**: 2025-11-11  
**해결 버전**: v0.7.0 (Phase 3)  
**관련 이슈**: CrashLoopBackOff - YAML Parsing Error

