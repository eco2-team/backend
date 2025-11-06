# 🏗️ [Infra] 13노드 마이크로서비스 인프라 구축

## 📋 변경 사항 요약

13노드 마이크로서비스 아키텍처로 인프라를 재구축했습니다.

### 주요 변경사항

#### 1. Terraform 인프라 코드
- **13노드 구성**: 1 Master + 6 API + 2 Worker + 4 Infra
- **API 노드 분리**: 각 도메인별 독립 노드 할당
  - `k8s-api-waste` (t3.small) - 메인 폐기물 분석
  - `k8s-api-auth` (t3.micro) - 인증/인가
  - `k8s-api-userinfo` (t3.micro) - 사용자 정보
  - `k8s-api-location` (t3.micro) - 지도/위치
  - `k8s-api-recycle-info` (t3.micro) - 재활용 정보
  - `k8s-api-chat-llm` (t3.small) - LLM 채팅
- **Worker 노드**: Storage (t3.medium), AI (t3.medium)
- **인프라 노드**: RabbitMQ, PostgreSQL, Redis, Monitoring

#### 2. Ansible 자동화
- **노드 라벨링 플레이북 추가**: `ansible/playbooks/label-nodes.yml`
  - 각 노드에 `workload`, `service`, `type`, `traffic` 라벨 자동 할당
  - Kubernetes 스케줄링 최적화
- **통합 플레이북 업데이트**: `ansible/site.yml`에 라벨링 단계 추가

#### 3. 호스트 템플릿
- 13노드 인벤토리 구조 정의
- 노드별 메타데이터 자동 생성
- Public/Private IP 관리

---

## 📊 인프라 구성

### 전체 리소스
- **총 노드**: 13개
- **총 vCPU**: 18 cores
- **총 메모리**: 26GB
- **예상 비용**: ~$180/월

### 노드별 상세 구성

#### Control Plane
- **k8s-master** (t3.large): 2 vCPU, 8GB RAM

#### API Nodes (독립 노드)
| 노드 | 인스턴스 | vCPU | RAM | 트래픽 | 서비스 |
|------|---------|------|-----|--------|--------|
| k8s-api-waste | t3.small | 2 | 2GB | high | 폐기물 분석 |
| k8s-api-auth | t3.micro | 2 | 1GB | high | 인증 |
| k8s-api-userinfo | t3.micro | 2 | 1GB | medium | 사용자 정보 |
| k8s-api-location | t3.micro | 2 | 1GB | medium | 지도/위치 |
| k8s-api-recycle-info | t3.micro | 2 | 1GB | low | 재활용 정보 |
| k8s-api-chat-llm | t3.small | 2 | 2GB | high | LLM 채팅 |

#### Worker Nodes
- **k8s-worker-storage** (t3.medium): 2 vCPU, 4GB RAM
- **k8s-worker-ai** (t3.medium): 2 vCPU, 4GB RAM

#### Infrastructure Nodes
- **k8s-rabbitmq** (t3.small): 2 vCPU, 2GB RAM
- **k8s-postgresql** (t3.small): 2 vCPU, 2GB RAM
- **k8s-redis** (t3.small): 2 vCPU, 2GB RAM
- **k8s-monitoring** (t3.large): 2 vCPU, 8GB RAM

---

## 📚 새로운 문서

### 1. `13NODES_COMPLETE_SUMMARY.md`
- 13노드 아키텍처 전체 요약
- 리소스 분배 및 비용 분석

### 2. `MICROSERVICES_ARCHITECTURE_13_NODES.md`
- 마이크로서비스 아키텍처 설계 상세
- 각 노드별 역할 및 책임
- Mermaid 다이어그램 포함

### 3. `DEPLOYMENT_GUIDE_13NODES.md`
- 13노드 배포 가이드
- Terraform + Ansible 실행 절차
- 검증 체크리스트

### 4. `CLEAR_NODE_NAMING.md`
- 명확한 노드 네이밍 컨벤션
- 넘버링 대신 용도 기반 이름 사용

### 5. `COMPLETE_SERVICE_NODE_LAYOUT.md`
- 전체 서비스-노드 매핑
- 리소스 할당 계획

---

## 🎯 주요 이점

### 1. 장애 격리 (Fault Isolation)
- API 서비스별 독립 노드
- 한 서비스 장애가 다른 서비스에 영향 없음

### 2. 독립적 스케일링
- 서비스별 트래픽 패턴에 따른 개별 스케일링
- 리소스 최적화

### 3. 명확한 모니터링
- 노드 수준 메트릭 수집
- 서비스별 성능 추적 용이

### 4. 비용 최적화
- 트래픽이 낮은 서비스는 t3.micro
- 트래픽이 높은 서비스는 t3.small
- 전체적으로 이전보다 약간 저렴

---

## 🔧 배포 방법

### 1. Terraform 적용
```bash
cd terraform
terraform init
terraform plan
terraform apply
```

### 2. Ansible 실행
```bash
cd ansible
ansible-playbook -i inventory.ini site.yml
```

### 3. 노드 확인
```bash
kubectl get nodes --show-labels
```

---

## ✅ 체크리스트

- [x] Terraform 13노드 정의
- [x] Ansible 노드 라벨링 플레이북
- [x] 호스트 템플릿 업데이트
- [x] 출력 변수 업데이트
- [x] 문서 작성 완료
- [ ] Terraform apply 실행 (배포 시)
- [ ] Ansible playbook 실행 (배포 시)
- [ ] 노드 라벨 검증 (배포 시)

---

## 🔗 관련 이슈

- 마이크로서비스 아키텍처 구축
- API 서비스 분리
- 인프라 코드 개선

---

## 👥 리뷰어

@backend-team @devops-team

---

## 📝 참고사항

- 이 PR은 인프라 코드만 포함합니다
- 실제 배포는 리뷰 및 승인 후 진행합니다
- Helm Chart 및 ArgoCD 설정은 별도 PR에서 진행됩니다

