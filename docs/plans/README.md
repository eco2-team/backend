# 📅 배포 전략 계획

배포 전략 및 향후 도입 예정 기능을 문서화한 디렉토리입니다.

---

## 📋 문서 목록

### 1. [배포 전략 비교 및 선택](DEPLOYMENT_STRATEGIES_COMPARISON.md) ⭐

**상태**: ✅ 분석 완료, 구현 준비 완료  
**우선순위**: 높음  
**도입 시기**: 즉시 (Phase 1)

**개요**
- 블루-그린 vs 카나리 배포 상세 비교
- 현재 아키텍처 적합성 분석
- **선택된 전략**: 블루-그린 배포 (1차), Argo Rollouts 카나리 배포 (2차)
- 구체적인 구현 계획 및 워크플로우

**주요 내용**
- Kubernetes Service Label Selector 기반 블루-그린 구현
- Argo Rollouts 기반 카나리 배포 설계
- 리소스 최적화 방안
- 2주 구현 계획
- 성공 지표 정의

**다음 단계**
- 새 브랜치 생성: `feature/blue-green-deployment`
- Helm Chart 작성
- 스크립트 개발 및 테스트

---

### 2. [Argo Rollouts 카나리 배포 적용 가이드](CANARY_DEPLOYMENT_CONSIDERATIONS.md) ⭐ NEW

**상태**: ✅ 분석 완료, 구현 계획 수립  
**우선순위**: 높음  
**도입 시기**: Phase 2 (3개월 후)  
**결정**: Argo Rollouts 채택

**개요**
- 현재 7노드 클러스터에서 Argo Rollouts 기반 카나리 배포 적용 시 고려사항
- 트래픽 라우팅, 리소스 관리, NodeSelector, Prometheus 메트릭 설정
- Deployment → Rollout 마이그레이션 전략
- 3주 구현 로드맵

**주요 내용**
- 트래픽 라우팅 제약 및 해결 방안 (Calico CNI + ALB)
- Replica 조정 (10 → 5) 및 리소스 계획
- NodeSelector 필수 설정 (`workload=application`)
- Analysis Template 작성 (Success Rate, Latency)
- ArgoCD 통합 (Rollouts Plugin)
- 단계별 구현 가이드

**결정 배경**
- Istio 없이 구현 가능 (7노드에서 Istio는 과도)
- ArgoCD와 네이티브 통합
- 블루-그린 안정화 후 점진적 도입
- ~90% 정확도의 트래픽 제어 (Pod 수 기반)

**다음 단계**
- 블루-그린 배포 안정화 (3개월)
- Argo Rollouts Controller 설치
- Application 메트릭 추가 (Prometheus)
- 개발 환경 PoC

---

### 3. [A/B 테스트 전략](AB_TESTING_STRATEGY.md)

**상태**: 📋 계획 단계  
**우선순위**: 중간  
**도입 시기**: Phase 2 이후

**개요**
- Feature Flag 기반 A/B 테스트 구현 방안
- 3가지 구현 방법 비교 (ALB + Cookie, Multiple Deployments, Feature Flag)
- 메트릭 수집 및 분석 전략
- 단계별 도입 로드맵

**주요 내용**
- Istio 없이 현재 아키텍처에서 A/B 테스트 구현
- Unleash Feature Flag 서비스 도입
- Prometheus + Grafana 메트릭 수집
- 4단계 도입 계획 (총 8주)

---

## 🗺️ 로드맵

### Phase 1: 즉시 구현 (2주)
- ✅ **블루-그린 배포** (선택됨)
  - Week 1: 설계 및 개발
  - Week 2: 배포 및 검증

### Phase 2: 단기 계획 (3개월)
- ✅ **카나리 배포 (Argo Rollouts)** - 결정 완료
  - Month 1: Argo Rollouts 설치 및 PoC
  - Month 2: Application 메트릭 추가 및 스테이징 환경 적용
  - Month 3: 프로덕션 적용 및 Analysis Template 튜닝
  
- 📋 **자동 스케일링**
  - HPA (Horizontal Pod Autoscaler)
  - VPA (Vertical Pod Autoscaler)

### Phase 3: 중기 계획 (6개월)
- 📋 **A/B 테스트** (Feature Flag)
  - Unleash 서비스 도입
  - 애플리케이션 통합
  - 메트릭 수집 및 분석

### Phase 4: 장기 검토 (1년)
- 🤔 **Service Mesh** (Istio)
  - 복잡도 vs 이점 재평가
  - 트래픽 관리 고도화
  
- 🤔 **Multi-Cluster 배포**
  - 지역별 클러스터
  - DR (재해 복구) 전략

---

## 📊 우선순위 매트릭스

### 구현 우선순위

| 기능 | 우선순위 | 복잡도 | 비즈니스 가치 | 리소스 | 상태 |
|------|----------|--------|---------------|--------|------|
| **블루-그린 배포** | ⭐⭐⭐⭐⭐ 최고 | ⭐⭐ 중간 | 💰💰💰💰 매우 높음 | 👤 1명, 2주 | ✅ 준비 완료 |
| **카나리 배포 (Argo Rollouts)** | ⭐⭐⭐⭐ 높음 | ⭐⭐⭐ 높음 | 💰💰💰 높음 | 👤 1명, 3개월 | ✅ 결정 완료 |
| A/B 테스트 | ⭐⭐⭐ 중간 | ⭐⭐ 중간 | 💰💰💰 높음 | 👤 1명, 2개월 | 📋 계획 |
| 자동 스케일링 | ⭐⭐⭐ 중간 | ⭐⭐ 중간 | 💰💰 중간 | 👤 1명, 2주 | 📋 계획 |
| Service Mesh (Istio) | ⭐ 낮음 | ⭐⭐⭐⭐ 매우 높음 | 💰 낮음 | 👤 2명, 3개월 | ❌ 거부 |

### 선택 기준

**블루-그린 배포를 1순위로 선택한 이유**

1. **즉시 롤백**: 1초 이내 롤백으로 프로덕션 안정성 보장
2. **단순 구현**: 추가 도구 없이 Kubernetes 기본 기능만 사용
3. **완전한 검증**: 트래픽 전환 전 완전한 테스트 가능
4. **높은 ROI**: 적은 투자로 큰 안정성 개선
5. **현 아키텍처 적합**: ArgoCD + ALB Ingress와 완벽 호환

**Argo Rollouts 카나리 배포를 2순위로 선택한 이유**

1. **Istio 불필요**: 7노드 클러스터에서 Service Mesh는 과도
2. **점진적 전환**: 10% → 50% → 100% 단계적 트래픽 전환
3. **자동 롤백**: Analysis Template 기반 메트릭 검증 및 자동 롤백
4. **ArgoCD 통합**: 기존 GitOps 파이프라인과 네이티브 통합
5. **낮은 복잡도**: Istio 대비 단순하고 가벼움

**Service Mesh (Istio) 거부 사유**

1. **과도한 복잡도**: 7노드 클러스터에는 너무 무거움
2. **리소스 오버헤드**: 각 Pod마다 Sidecar (~100MB) 필요
3. **학습 곡선**: 팀 학습 시간 3개월 이상 소요
4. **낮은 ROI**: 현 규모에서 이점 대비 비용이 높음
5. **대안 존재**: Argo Rollouts로 충분히 목표 달성 가능

---

## 🎯 성공 지표

### 블루-그린 배포 목표 (Phase 1)

**기술 지표**
- 배포 성공률: 99% 이상
- 롤백 시간: 1분 이내
- 다운타임: 0초
- 배포 시간: 15분 이내

**비즈니스 지표**
- 서비스 가용성: 99.9% 이상 유지
- 배포 횟수: 2배 증가
- 사용자 영향: 배포 중 에러율 증가 없음

### Argo Rollouts 카나리 배포 목표 (Phase 2)

**기술 지표**
- 트래픽 제어 정확도: ~90% (Pod 수 기반)
- 자동 롤백 시간: 5분 이내
- Analysis Template 정확도: 95% 이상
- Canary 단계별 검증 시간: 5분

**비즈니스 지표**
- 문제 조기 감지율: 80% 이상
- 대규모 장애 예방: 100% (Canary에서 차단)
- 사용자 영향 최소화: 10% 이하 사용자만 노출

---

## 📚 관련 문서

### 현재 아키텍처
- [CI/CD 파이프라인](../architecture/CI_CD_PIPELINE.md)
- [최종 K8s 아키텍처](../architecture/final-k8s-architecture.md)
- [클러스터 리소스 현황](../infrastructure/CLUSTER_RESOURCES.md)

### 배포 가이드
- [배포 방법](../guides/DEPLOYMENT_METHODS.md)
- [GitOps ArgoCD Helm](../deployment/gitops-argocd-helm.md)

---

## 🚀 시작하기

### 블루-그린 배포 구현 (즉시 실행 가능)

```bash
# 1. 새 브랜치 생성
git checkout -b feature/blue-green-deployment

# 2. 디렉토리 생성
mkdir -p k8s/blue-green/templates
mkdir -p k8s/scripts

# 3. 문서 참조
# docs/plans/DEPLOYMENT_STRATEGIES_COMPARISON.md 참조

# 4. Helm Chart 작성
# - Chart.yaml
# - values.yaml
# - templates/deployment-blue.yaml
# - templates/deployment-green.yaml
# - templates/service.yaml

# 5. 스크립트 작성
# - scripts/deploy-green.sh
# - scripts/switch-to-green.sh
# - scripts/rollback-to-blue.sh
```

### Argo Rollouts 카나리 배포 구현 (Phase 2, 3개월 후)

```bash
# 1. 블루-그린 안정화 확인 (3개월)
# 배포 성공률, 롤백 시간, 팀 역량 확인

# 2. Argo Rollouts 준비 (1주)
kubectl create namespace argo-rollouts
kubectl apply -n argo-rollouts -f \
  https://github.com/argoproj/argo-rollouts/releases/latest/download/install.yaml

# 3. Application 메트릭 추가
# FastAPI에 prometheus_client 추가
# ServiceMonitor 생성

# 4. Analysis Template 작성
# Success Rate, Latency 메트릭 기반

# 5. Deployment → Rollout 마이그레이션
# docs/plans/CANARY_DEPLOYMENT_CONSIDERATIONS.md 참조
```

---

## 💡 제안 및 피드백

새로운 기능 제안이나 피드백은 다음 방법으로 제출해주세요:

1. **GitHub Issue**: 새로운 Feature Request 이슈 생성
2. **Pull Request**: 문서 개선 또는 새로운 제안 PR
3. **팀 미팅**: 정기 아키텍처 리뷰 미팅

---

**최종 업데이트**: 2025-11-05  
**관리자**: Infrastructure Team  
**다음 마일스톤**: 블루-그린 배포 구현 (2주)

