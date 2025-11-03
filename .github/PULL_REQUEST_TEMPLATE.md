# Pull Request

## 📋 변경 사항 요약

<!-- 이 PR에서 변경된 내용을 간단히 요약해주세요 -->

- [ ] Terraform 인프라 변경
- [ ] Ansible Playbook 변경
- [ ] 스크립트 변경
- [ ] 문서 업데이트
- [ ] 기타: _______________

### 주요 변경 내용

<!-- 주요 변경 사항을 3-5줄로 요약 -->

1.
2.
3.

---

## 🎯 변경 이유 / 동기

<!-- 왜 이 변경이 필요한지, 어떤 문제를 해결하는지 설명 -->

- 

---

## 📝 변경 세부 사항

### Terraform 변경 사항
<!-- Terraform 관련 변경이 있다면 -->

- [ ] VPC/네트워크 설정 변경
- [ ] EC2 인스턴스 타입/개수 변경
- [ ] IAM 역할/정책 변경
- [ ] 보안 그룹 규칙 변경
- [ ] 기타: _______________

**변경된 파일**:
- `terraform/...`

**주요 변경 내용**:
```hcl
# 예시 코드 또는 변경 내용 설명
```

**비용 영향**:
- 예상 비용 증가/감소: $___/월
- 비용 변경 사유: 

### Ansible Playbook 변경 사항
<!-- Ansible 관련 변경이 있다면 -->

- [ ] Kubernetes 클러스터 설정 변경
- [ ] Add-ons 설치/설정 변경 (Cert-manager, EBS CSI Driver, ALB Controller)
- [ ] 애플리케이션 Stack 변경 (ArgoCD, Prometheus, RabbitMQ, Redis)
- [ ] 노드 레이블/테인트 변경
- [ ] 기타: _______________

**변경된 파일**:
- `ansible/...`

**주요 변경 내용**:
```yaml
# 예시 코드 또는 변경 내용 설명
```

### 스크립트 변경 사항
<!-- 스크립트 관련 변경이 있다면 -->

- [ ] 자동화 스크립트 수정 (auto-rebuild.sh, build-cluster.sh, cleanup.sh)
- [ ] 유틸리티 스크립트 추가/수정
- [ ] 버그 수정
- [ ] 기능 개선
- [ ] 기타: _______________

**변경된 파일**:
- `scripts/...`

### 문서 변경 사항
<!-- 문서 관련 변경이 있다면 -->

- [ ] README 업데이트
- [ ] Architecture 문서 업데이트
- [ ] Troubleshooting 가이드 추가/수정
- [ ] Deployment 가이드 추가/수정
- [ ] 기타: _______________

**변경된 파일**:
- `*.md`

---

## 🧪 테스트 방법

<!-- 이 변경사항을 어떻게 테스트했는지, 또는 어떻게 테스트해야 하는지 -->

### 테스트 시나리오

1. **인프라 구축 테스트** (Terraform 변경 시)
   ```bash
   cd terraform
   terraform init
   terraform plan
   terraform apply
   ```
   - [ ] Terraform plan 출력 확인 완료
   - [ ] 인프라 생성 성공 확인
   - [ ] 생성된 리소스 검증 완료

2. **클러스터 구축 테스트** (Ansible 변경 시)
   ```bash
   ./scripts/build-cluster.sh
   # 또는
   cd ansible
   ansible-playbook -i inventory/hosts.ini site.yml
   ```
   - [ ] 모든 노드 Ready 상태 확인
   - [ ] 시스템 Pod 정상 실행 확인
   - [ ] Add-ons 정상 설치 확인
   - [ ] 애플리케이션 Stack 정상 배포 확인

3. **전체 자동화 테스트** (스크립트 변경 시)
   ```bash
   ./scripts/auto-rebuild.sh
   ```
   - [ ] 전체 구축 프로세스 성공 확인
   - [ ] 클러스터 상태 점검 스크립트 실행
   - [ ] 정상 동작 확인

4. **클린업 테스트** (삭제 로직 변경 시)
   ```bash
   ./scripts/cleanup.sh
   ```
   - [ ] Kubernetes 리소스 정상 삭제 확인
   - [ ] AWS 리소스 정상 삭제 확인
   - [ ] Terraform destroy 성공 확인

### 검증 명령어

```bash
# 클러스터 상태 확인
./scripts/check-cluster-health.sh

# 노드 상태 확인
kubectl get nodes -o wide

# Pod 상태 확인
kubectl get pods -A

# Helm Release 확인
helm list -A

# PVC 상태 확인
kubectl get pvc -A

# Ingress 확인
kubectl get ingress -A
```

---

## ✅ 체크리스트

<!-- PR 전에 확인해야 할 항목들 -->

### 코드 품질
- [ ] 코드 스타일 가이드 준수
- [ ] 불필요한 주석 제거
- [ ] 임시 파일/디버그 코드 제거

### 문서
- [ ] 관련 README 업데이트
- [ ] 변경 사항에 대한 문서 추가/수정
- [ ] Troubleshooting 가이드 업데이트 (필요 시)

### 테스트
- [ ] 로컬 환경에서 테스트 완료
- [ ] Terraform plan/validate 성공
- [ ] Ansible syntax check 통과
- [ ] 실제 클러스터 구축 테스트 완료 (선택)

### 보안
- [ ] 민감 정보 (비밀번호, 키 등) 하드코딩 없음
- [ ] 환경 변수 또는 Secret 사용 확인
- [ ] 보안 그룹 규칙 적절성 확인

### 비용
- [ ] 비용 영향 분석 완료
- [ ] 불필요한 리소스 생성 없음
- [ ] 예상 비용 문서화 (필요 시)

### Breaking Changes
- [ ] 기존 클러스터에 영향 없음
- [ ] 마이그레이션 가이드 제공 (Breaking Change인 경우)
- [ ] 롤백 방법 문서화

---

## 📸 스크린샷 / 로그

<!-- 변경 사항을 보여주는 스크린샷, 로그, 또는 출력 결과 -->

### Before (변경 전)
```
# 변경 전 상태 또는 스크린샷
```

### After (변경 후)
```
# 변경 후 상태 또는 스크린샷
```

### 테스트 결과
```
# 테스트 실행 결과 로그
```

---

## 🔗 관련 이슈

<!-- 관련 GitHub Issue가 있다면 -->

- Fixes #
- Closes #
- Related to #

---

## 💬 추가 정보

<!-- 리뷰어가 알아야 할 추가 정보, 주의사항, 특별 고려사항 등 -->

### 주의사항
- 

### 향후 계획
- 

### 질문 / 검토 요청 사항
- 

---

## 📚 참고 자료

<!-- 관련 문서, 설계 문서, 또는 참고한 자료 -->

- 

---

## 👥 리뷰어

<!-- 코드 리뷰를 요청할 리뷰어 -->

@reviewer-name

---

**작성일**: YYYY-MM-DD  
**작성자**: @your-username

