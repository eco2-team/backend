# auto-rebuild.sh 스크립트 분석 및 요구사항 확인

## 📋 현재 구조

### auto-rebuild.sh
```bash
1. destroy-with-cleanup.sh 실행 (리소스 정리)
2. rebuild-cluster.sh 실행 (재구축)
```

### 실행 흐름
1. **destroy-with-cleanup.sh**:
   - Kubernetes 리소스 정리 (Ingress, PVC, Helm Releases, RabbitMQ CR)
   - AWS 리소스 정리 (EBS 볼륨, 보안 그룹, Load Balancer, ENI)
   - **Terraform destroy** ⚠️
   
2. **rebuild-cluster.sh**:
   - **Terraform destroy** ⚠️ (중복!)
   - Terraform apply (새 인프라 생성)
   - Ansible inventory 생성
   - Ansible playbook 실행

---

## ⚠️ 발견된 문제점

### 1. Terraform destroy 중복 실행

**문제**:
- `destroy-with-cleanup.sh`에서 이미 `terraform destroy`를 수행함 (298라인)
- `rebuild-cluster.sh`에서도 다시 `terraform destroy`를 수행함 (124라인)
- 결과적으로 Terraform destroy가 두 번 실행됨

**영향**:
- 첫 번째 destroy 후 State 파일이 비어있으면 두 번째 destroy에서 오류 발생 가능
- 불필요한 시간 소모

**현재 동작**:
```bash
# destroy-with-cleanup.sh
terraform destroy -auto-approve  # 1차 삭제

# rebuild-cluster.sh (이후 실행)
terraform destroy -auto-approve  # 2차 삭제 시도 (이미 삭제됨)
```

---

### 2. destroy-with-cleanup.sh 실패 시 처리

**현재 코드** (auto-rebuild.sh:32-37):
```bash
if [ $? -ne 0 ]; then
    echo ""
    echo "⚠️  destroy-with-cleanup.sh 실패"
    echo "   Kubernetes 리소스 정리 없이 진행합니다..."
    echo ""
fi
```

**문제**:
- `set -e`가 설정되어 있어서 실패 시 스크립트가 중단되어야 하지만, `if [ $? -ne 0 ]`로 체크하므로 계속 진행됨
- 하지만 `set -e`가 있으면 실패한 명령어 이후의 코드가 실행되지 않을 수 있음

**권장 수정**:
```bash
set +e  # 일시적으로 에러 무시
"$SCRIPT_DIR/destroy-with-cleanup.sh"
DESTROY_EXIT_CODE=$?
set -e  # 다시 에러 체크 활성화

if [ $DESTROY_EXIT_CODE -ne 0 ]; then
    echo ""
    echo "⚠️  destroy-with-cleanup.sh 실패 (exit code: $DESTROY_EXIT_CODE)"
    echo "   Kubernetes 리소스 정리 없이 진행합니다..."
    echo ""
fi
```

---

### 3. rebuild-cluster.sh의 중복 Terraform destroy

**현재 코드** (rebuild-cluster.sh:123-124):
```bash
echo "🗑️  Terraform destroy 실행..."
terraform destroy -auto-approve
```

**문제**:
- `destroy-with-cleanup.sh`에서 이미 Terraform destroy를 수행했으므로, State 파일이 비어있을 가능성이 높음
- 빈 State 파일에 대해 destroy를 실행하면 에러가 발생할 수 있음

**권장 수정**:
```bash
# State 파일 존재 및 리소스 확인
if terraform state list >/dev/null 2>&1; then
    RESOURCE_COUNT=$(terraform state list 2>/dev/null | wc -l | tr -d ' ')
    
    if [ "$RESOURCE_COUNT" -gt 0 ]; then
        echo "🗑️  Terraform destroy 실행..."
        terraform destroy -auto-approve
    else
        echo "ℹ️  Terraform State에 리소스가 없습니다 (이미 삭제됨)"
        echo "   destroy-with-cleanup.sh에서 이미 삭제되었습니다."
    fi
else
    echo "ℹ️  Terraform State 파일이 없습니다"
fi
```

---

### 4. AUTO_MODE 전파

**현재 상태**: ✅ 올바름
- `auto-rebuild.sh`에서 `export AUTO_MODE=true` 설정
- 하위 스크립트들이 `AUTO_MODE` 환경 변수를 올바르게 체크함

---

## ✅ 올바르게 구현된 부분

1. **스크립트 실행 순서**: destroy-with-cleanup.sh → rebuild-cluster.sh ✅
2. **AUTO_MODE 지원**: 모든 스크립트에서 AUTO_MODE 체크 ✅
3. **에러 처리**: 각 스크립트에서 적절한 에러 메시지 출력 ✅
4. **리소스 정리**: Kubernetes 리소스 → AWS 리소스 → Terraform 순서 ✅

---

## 🔧 권장 수정 사항

### Option 1: destroy-with-cleanup.sh에서 Terraform destroy 제거 (권장)

`destroy-with-cleanup.sh`의 마지막 부분에서 Terraform destroy를 제거하고, `rebuild-cluster.sh`에서만 수행하도록 변경:

**destroy-with-cleanup.sh**:
```bash
# 3️⃣ Terraform 인프라 삭제 섹션 제거
# 대신 rebuild-cluster.sh에서 처리
```

**장점**:
- 책임 분리 명확 (destroy-with-cleanup.sh = K8s/AWS 정리만)
- 중복 실행 방지
- auto-rebuild.sh 워크플로우와 일관성

---

### Option 2: rebuild-cluster.sh에서 Terraform destroy 제거

`rebuild-cluster.sh`에서 Terraform destroy를 제거하고, `destroy-with-cleanup.sh`에서만 수행:

**rebuild-cluster.sh**:
```bash
# 1️⃣ Terraform Destroy 섹션 제거
# destroy-with-cleanup.sh에서 이미 삭제됨

# 바로 2️⃣ Terraform Apply로 진행
```

**장점**:
- destroy-with-cleanup.sh가 완전한 삭제를 담당
- rebuild-cluster.sh는 재구축만 담당

---

## 📊 현재 요구사항 확인

### 이전 요구사항 (대화 내용)
> "그럼 destroy-with-cleanup.sh을 실행하고 auto-rebuild를 시행하는 방식으로 작업할테니 auto-rebuild에서 리소스 삭제 로직 및 대기를 제거해 줄 수 있어?"

**현재 상태**:
- ✅ auto-rebuild.sh에서 destroy-with-cleanup.sh를 먼저 호출
- ✅ 리소스 삭제 로직은 destroy-with-cleanup.sh에 있음
- ⚠️ 하지만 rebuild-cluster.sh에서도 Terraform destroy를 다시 수행 (중복)

---

## 💡 최종 권장 사항

### Option 1 선택 (destroy-with-cleanup.sh에서 Terraform destroy 제거)

**이유**:
1. **책임 분리**: 
   - `destroy-with-cleanup.sh` = Kubernetes/AWS 리소스 정리만
   - `rebuild-cluster.sh` = Terraform 관리 (destroy + apply)
   
2. **사용성**:
   - `destroy-with-cleanup.sh`를 단독으로 실행해도 완전 삭제 가능 (Terraform destroy 포함)
   - 하지만 `auto-rebuild.sh` 워크플로우에서는 중복 방지

3. **유연성**:
   - 필요시 `destroy-with-cleanup.sh` + `terraform destroy` 수동 실행 가능

### 수정 내용

**destroy-with-cleanup.sh**:
- 마지막 Terraform destroy 섹션 제거
- 또는 조건부로 실행 (AUTO_MODE가 아닐 때만)

**rebuild-cluster.sh**:
- Terraform destroy 섹션 유지
- State 파일 확인 후 실행 (중복 방지)

---

## 🧪 테스트 시나리오

### 시나리오 1: auto-rebuild.sh 실행
```bash
./scripts/auto-rebuild.sh
```
**예상 동작**:
1. destroy-with-cleanup.sh: K8s/AWS 리소스 정리 (Terraform destroy 없음)
2. rebuild-cluster.sh: Terraform destroy → apply → Ansible

### 시나리오 2: destroy-with-cleanup.sh 단독 실행
```bash
./scripts/destroy-with-cleanup.sh
```
**예상 동작**:
1. K8s/AWS 리소스 정리
2. Terraform destroy (옵션 또는 자동)

### 시나리오 3: rebuild-cluster.sh 단독 실행
```bash
./scripts/rebuild-cluster.sh
```
**예상 동작**:
1. Terraform destroy (State 확인 후)
2. Terraform apply
3. Ansible 실행

---

## 📝 요약

**현재 상태**: ⚠️ **대부분 올바르지만 Terraform destroy 중복 문제 있음**

**수정 필요**:
1. ✅ destroy-with-cleanup.sh와 rebuild-cluster.sh 간 Terraform destroy 중복 제거
2. ✅ destroy-with-cleanup.sh 실패 시 에러 처리 개선 (set +e/set -e)

**권장 수정**:
- Option 1: destroy-with-cleanup.sh에서 Terraform destroy를 조건부로 실행하거나 제거
- rebuild-cluster.sh에서 State 파일 확인 후 destroy 실행

