# 배포 전 최종 점검 요약
**작성일:** 2025-11-15

---

## ✅ 점검 완료 사항

### 1. 코드베이스 검증 ✅
- **Terraform:** 14노드 인프라 정의 완료
- **Ansible:** 완전한 부트스트랩 + ArgoCD 자동 배포 구성
- **ArgoCD Apps:** App-of-Apps 패턴으로 완성
- **K8s Manifests:** Foundations, Overlays 준비 완료
- **Helm Charts:** databases umbrella chart 준비

### 2. 현재 클러스터 상태 분석 ✅
```
ArgoCD: 설치되었으나 Applications 없음 (수동 배포 상태)
API Services: 배포 안됨
Workers: 배포 안됨
PostgreSQL: Secret 이름 불일치로 실패
기타 인프라: 정상 동작
```

**결론:** GitOps 미적용 상태, 클린 재배포 필요

---

## ⚠️ 해결 필요 사항

### 1. 브랜치 전략 (중요!)

**현재 상황:**
- ArgoCD 설정: `targetRevision: develop`
- main과 develop 차이:
  ```
  develop에만 존재:
  - app/health.py (188줄)
  - app/postgres_sync.py (376줄)
  - app/wal.py (524줄)
  ```

**선택지:**

#### Option A: develop 브랜치 사용 (권장) ✅
```bash
git checkout develop
git pull origin develop
# develop 브랜치에서 배포 진행
```

**장점:**
- ArgoCD 설정 변경 불필요
- develop 브랜치의 추가 기능 포함
- 브랜치 전략에 맞음 (develop → staging → main)

**단점:**
- main과 develop 동기화 필요

#### Option B: main 브랜치로 ArgoCD 설정 변경
```bash
# root-app.yaml 및 모든 apps/*.yaml의 targetRevision 변경
find argocd -name "*.yaml" -exec sed -i '' 's/targetRevision: develop/targetRevision: main/g' {} \;
git commit -am "chore: switch argocd to main branch"
git push origin main
```

**장점:**
- 현재 main 브랜치 그대로 사용

**단점:**
- develop 브랜치의 추가 기능 누락
- 모든 ArgoCD 설정 파일 수정 필요

### 2. Helm Dependencies

**문제:**
- `charts/data/databases/Chart.lock` 없음
- Helm이 로컬에 설치 안됨

**해결:**
ArgoCD가 Helm chart를 배포할 때 자동으로 dependencies를 해결하므로 문제없음.
단, Chart.yaml의 dependencies 정의가 올바른지 확인 필요.

**검증 완료:**
```yaml
dependencies:
  - name: postgresql
    alias: postgres
    version: ">=12.12.0"
    repository: https://charts.bitnami.com/bitnami
  - name: redis
    version: ">=18.4.0"
    repository: https://charts.bitnami.com/bitnami
  - name: rabbitmq
    version: ">=12.0.0"
    repository: https://charts.bitnami.com/bitnami
```
✅ 정상

### 3. 환경 변수 준비

**필수 환경 변수:**
```bash
export POSTGRES_PASSWORD="<strong-password>"
export RABBITMQ_PASSWORD="<strong-password>"
export GRAFANA_PASSWORD="<admin-password>"
```

**생성 스크립트:**
```bash
export POSTGRES_PASSWORD=$(openssl rand -base64 32)
export RABBITMQ_PASSWORD=$(openssl rand -base64 32)
export GRAFANA_PASSWORD=$(openssl rand -base64 20)

# 안전하게 저장
cat > ~/.env.sesacthon << EOF
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
RABBITMQ_PASSWORD=${RABBITMQ_PASSWORD}
GRAFANA_PASSWORD=${GRAFANA_PASSWORD}
EOF
chmod 600 ~/.env.sesacthon
```

---

## 🚀 배포 실행 계획

### 브랜치 전략 결정 후 진행

#### 선택: Option A (develop 브랜치 사용)

```bash
# 1. develop 브랜치로 전환
git checkout develop
git pull origin develop

# 2. 환경 변수 설정
source ~/.env.sesacthon 2>/dev/null || {
  export POSTGRES_PASSWORD=$(openssl rand -base64 32)
  export RABBITMQ_PASSWORD=$(openssl rand -base64 32)
  export GRAFANA_PASSWORD=$(openssl rand -base64 20)
}

# 3. 현재 클러스터 파괴
cd terraform
terraform destroy -auto-approve
cd ..

# 4. 인프라 생성
cd terraform
terraform init
terraform apply -auto-approve
cd ..

# 5. Ansible inventory 생성
cd terraform
terraform output -raw hosts > ../ansible/inventory/hosts.ini
cd ..

# 6. 클러스터 부트스트랩
cd ansible
ansible-playbook -i inventory/hosts.ini site.yml \
  -e "postgres_password=${POSTGRES_PASSWORD}" \
  -e "rabbitmq_password=${RABBITMQ_PASSWORD}" \
  -e "grafana_admin_password=${GRAFANA_PASSWORD}"
cd ..

# 7. 배포 확인
MASTER_IP=$(cd terraform && terraform output -raw master_public_ip)
ssh -i ~/.ssh/sesacthon.pem ubuntu@${MASTER_IP} "kubectl get applications -n argocd"
```

---

## 📊 예상 배포 타임라인

| 단계 | 작업 | 시간 |
|------|------|------|
| 0 | 브랜치 전환 + 환경변수 설정 | 2분 |
| 1 | terraform destroy | 5-10분 |
| 2 | terraform apply | 5-7분 |
| 3 | ansible playbook | 30-45분 |
| 4 | ArgoCD 자동 배포 대기 | 10-15분 |
| **합계** | | **52-79분** |

---

## 🎯 배포 성공 기준

### 필수 검증 항목
1. [ ] 14개 노드 모두 Ready
2. [ ] ArgoCD Pod Running
3. [ ] root-app Application 존재
4. [ ] Wave별 Applications 생성
   - [ ] namespaces (Wave -1)
   - [ ] alb-controller (Wave 20)
   - [ ] monitoring (Wave 40)
   - [ ] data-operators (Wave 50)
   - [ ] data-clusters (Wave 60)
   - [ ] gitops-tools (Wave 70)
   - [ ] api-services ApplicationSet (Wave 80)
5. [ ] ApplicationSet이 7개 API Application 생성
6. [ ] 모든 API Pods Running
7. [ ] PostgreSQL/Redis/RabbitMQ Running
8. [ ] Ingress 접근 가능

### 검증 명령어
```bash
# 노드 확인
kubectl get nodes

# Applications 확인
kubectl get applications -n argocd

# ApplicationSets 확인
kubectl get applicationsets -n argocd

# API Services 확인
kubectl get pods -l tier=business-logic -A

# 데이터 계층 확인
kubectl get pods -n data
kubectl get pods -n messaging

# Ingress 확인
kubectl get ingress -A
```

---

## 🔧 롤백 계획

배포 실패 시:

```bash
# 1. 로그 수집
kubectl get events -A --sort-by='.lastTimestamp' > events.log
kubectl get pods -A -o yaml > pods-state.yaml
kubectl describe applications -n argocd > argocd-apps.log

# 2. 현재 상태 파괴
cd terraform
terraform destroy -auto-approve

# 3. 문제 분석 후 재시도
```

---

## 📝 다음 단계

### 사용자 결정 필요:

1. **브랜치 선택**
   - [ ] Option A: develop 브랜치 사용 (권장)
   - [ ] Option B: main 브랜치로 ArgoCD 설정 변경

2. **배포 승인**
   - [ ] 배포 진행
   - [ ] 추가 검토 필요

### 배포 준비 완료!

모든 점검이 완료되었습니다. 브랜치 전략을 결정하고 배포를 진행하세요.

**권장사항:** develop 브랜치를 사용하여 배포 (Option A)

