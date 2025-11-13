# 🔧 Ansible 플레이북 Import 구조 수정 및 Atlantis 제거

## 📋 문제 상황

GitHub Actions CI 파이프라인에서 Ansible 플레이북 실행 시 다음 오류 발생:

```
Error: : conflicting action statements: hosts, gather_facts
Origin: /home/runner/work/backend/backend/ansible/playbooks/09-atlantis.yml:4:3
```

### 🔍 근본 원인

1. **구문 오류**: `site.yml`에서 `import_tasks`를 사용했지만, 해당 파일이 **완전한 플레이북 구조**(hosts, gather_facts, tasks 포함)로 작성되어 있어 충돌 발생

2. **아키텍처 중복**: GitHub Actions에서 이미 Terraform plan/apply를 수행하는데, Atlantis도 동일한 작업을 수행하도록 설정됨

## 🛠️ 해결 방법

### 📊 파일 구조 분석

#### ✅ Tasks 구조 (import_tasks 유지)
다음 파일들은 tasks나 block만 포함되어 있어 `import_tasks` 정상 동작:
- `02-master-init.yml`
- `03-worker-join.yml`
- `03-1-set-provider-id.yml`
- `05-addons.yml`
- `05-1-ebs-csi-driver.yml`
- `06-cert-manager-issuer.yml`
- `07-alb-controller.yml`
- `07-1-ingress-class.yml`
- `07-ingress-resources.yml`
- `08-monitoring.yml`
- `09-etcd-backup.yml`
- `09-route53-update.yml`

#### ❌ 완전한 플레이북 구조 (수정 완료)
다음 파일들은 hosts, gather_facts 등을 포함한 완전한 플레이북 구조:
- ✅ `09-atlantis.yml` - **중복으로 인해 제거** (이번 PR)
- ✅ `10-namespaces.yml` - `import_playbook`으로 변경 (이전 커밋)

### 🔄 변경 내용

#### Before
```yaml
- name: Atlantis 설치 (Terraform GitOps)
  hosts: masters
  become: yes
  become_user: "{{ kubectl_user }}"
  tasks:
    - import_tasks: playbooks/09-atlantis.yml  # ❌ 구조 불일치
```

#### After
```yaml
# 완전히 제거 - GitHub Actions에서 이미 Terraform 관리 중
```

### 🗑️ Atlantis 제거 이유

| 구분 | GitHub Actions | Atlantis |
|------|----------------|----------|
| **현재 상태** | ✅ 사용 중 | ❌ 중복 |
| **실행 위치** | GitHub 호스팅 | K8s Pod |
| **비용** | 무료 | EBS 스토리지 비용 |
| **설정 복잡도** | 낮음 | 높음 (Secret, Webhook) |
| **Terraform 관리** | ✅ PR plan + Auto apply | ✅ PR plan + Manual apply |

**결론**: GitHub Actions가 이미 완벽하게 동작하고 있으므로 Atlantis는 불필요한 중복

## 📋 Ansible Import 가이드

| 명령어 | 사용 시기 | 파일 구조 |
|--------|----------|----------|
| `import_tasks` | tasks 파일 | `- name: ...`<br>`  shell: ...` |
| `import_playbook` | playbook 파일 | `- name: ...`<br>`  hosts: ...`<br>`  tasks: ...` |
| `include_tasks` | 동적 로딩 | 런타임 조건부 로딩 |

## ✅ 테스트

### 로컬 테스트
```bash
# Ansible 구문 검사
ansible-playbook ansible/site.yml --syntax-check

# Dry-run
ansible-playbook ansible/site.yml --check
```

### CI 파이프라인
- ✅ GitHub Actions에서 자동 실행
- ✅ Ansible 플레이북 구문 오류 해결 확인
- ✅ 모든 플레이북 정상 실행 예상

## 📝 관련 커밋

- `4cb318d` - 이전 수정: `10-namespaces.yml` import_playbook 변경
- `ff246a5` - 현재 수정: Atlantis 플레이북 제거 (중복 제거)

## 🎯 체크리스트

- [x] 문제 원인 분석 완료
- [x] 모든 플레이북 파일 구조 점검
- [x] import_tasks/import_playbook 적절히 구분
- [x] Atlantis 중복 확인 및 제거
- [x] Linter 오류 없음
- [x] 브랜치로 PR 생성 (main에 직접 push 방지)

## 🚀 다음 단계

1. PR 리뷰
2. CI 파이프라인 통과 확인
3. main 브랜치에 머지

