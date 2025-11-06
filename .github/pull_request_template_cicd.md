# 🚀 [CI/CD] Helm Charts, ArgoCD, GitHub Actions 배포 자동화

## 📋 변경 사항 요약

Helm Chart 기반 GitOps 배포 파이프라인을 구축했습니다.

### 주요 변경사항

#### 1. Helm Chart 구축
- **Chart 이름**: `growbin-backend`
- **6개 API 서비스** Deployment 템플릿
  - waste-api, auth-api, userinfo-api
  - location-api, recycle-info-api, chat-llm-api
- **5개 Celery Worker** Deployment 템플릿
  - image-uploader, gpt5-analyzer, rule-retriever
  - response-generator, task-scheduler
- **Ingress 템플릿**: ALB Ingress Controller 기반
- **values.yaml**: 13노드 아키텍처 대응

#### 2. ArgoCD GitOps
- **Application 정의**: `argocd/application-13nodes.yaml`
- **자동 동기화**: Git Push → 자동 배포
- **Self-Healing**: Pod 장애 시 자동 복구
- **Health Check**: Readiness/Liveness 통합

#### 3. GitHub Actions CI/CD
- **워크플로우**: `.github/workflows/api-deploy.yml`
- **트리거**: `main`, `develop` 브랜치 Push
- **빌드**: Docker 이미지 자동 빌드
- **GHCR**: GitHub Container Registry에 Push
- **업데이트**: `values.yaml` 자동 업데이트

#### 4. GHCR 설정
- **스크립트**: `scripts/push-to-ghcr.sh`
- **이미지 경로**: `ghcr.io/sesacthon/{service}:tag`
- **태그 전략**: `latest`, `{git-sha}`

---

## 📦 Helm Chart 구조

```
charts/growbin-backend/
├── Chart.yaml                    # Chart 메타데이터
├── values.yaml                   # 기본 values
├── values-13nodes.yaml           # 13노드 전용 values
└── templates/
    ├── _helpers.tpl              # 헬퍼 함수
    ├── api/
    │   ├── waste-deployment.yaml
    │   ├── auth-deployment.yaml
    │   ├── userinfo-deployment.yaml
    │   ├── location-deployment.yaml
    │   ├── recycle-info-deployment.yaml
    │   └── chat-llm-deployment.yaml
    ├── workers/
    │   ├── image-uploader-deployment.yaml
    │   ├── gpt5-analyzer-deployment.yaml
    │   ├── rule-retriever-deployment.yaml
    │   ├── response-generator-deployment.yaml
    │   └── task-scheduler-deployment.yaml
    └── ingress/
        └── api-ingress.yaml
```

---

## 🔄 배포 플로우

### 자동 배포 흐름
```
1. 개발자 코드 Push (main/develop)
   ↓
2. GitHub Actions 실행
   - 변경된 서비스 감지
   - Docker 이미지 빌드
   - GHCR에 Push
   - values.yaml 업데이트 & Commit
   ↓
3. ArgoCD 감지 (3분 이내)
   - Git 변경사항 감지
   - Helm Chart Sync
   - Kubernetes 리소스 적용
   ↓
4. 배포 완료
   - Health Check 통과
   - 서비스 가용
```

### NodeSelector 자동 할당
```yaml
# API 서비스 → 해당 노드에 자동 배치
waste-api → service: waste
auth-api → service: auth
userinfo-api → service: userinfo
...

# Worker → 워크로드 타입별 배치
image-uploader → type: storage
gpt5-analyzer → type: ai
```

---

## 📊 주요 기능

### 1. GitOps 자동화
- **Single Source of Truth**: Git 저장소가 배포 상태 관리
- **자동 동기화**: 코드 변경 → 자동 배포
- **Rollback 용이**: Git Revert로 즉시 이전 버전 복구

### 2. 서비스별 독립 배포
- API 서비스별 독립 Deployment
- 한 서비스 배포가 다른 서비스에 영향 없음
- Blue-Green, Canary 배포 준비 완료

### 3. 리소스 최적화
```yaml
# 트래픽별 차등 리소스 할당
waste-api:     300m CPU, 512Mi RAM (high)
auth-api:      100m CPU, 256Mi RAM (high)
recycle-info:  100m CPU, 256Mi RAM (low)
```

### 4. 모니터링 통합
- Prometheus ServiceMonitor 준비
- Grafana 대시보드 연동 준비
- 서비스별 메트릭 수집

---

## 🔧 사용 방법

### 1. ArgoCD 설치
```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

### 2. ArgoCD Application 배포
```bash
kubectl apply -f argocd/application-13nodes.yaml
```

### 3. 자동 배포 확인
```bash
# ArgoCD UI 접속
kubectl port-forward svc/argocd-server -n argocd 8080:443

# Sync 상태 확인
argocd app get growbin-backend-13nodes
```

### 4. 서비스 배포 확인
```bash
# API Pods 확인
kubectl get pods -n api

# Worker Pods 확인
kubectl get pods -n workers

# Ingress 확인
kubectl get ingress -n api
```

---

## 📚 새로운 문서

### 1. `HELM_ARGOCD_DEPLOY_GUIDE.md`
- Helm + ArgoCD 통합 가이드
- 배포 프로세스 상세 설명

### 2. `GHCR_SETUP_GUIDE.md`
- GitHub Container Registry 설정
- 로그인 및 이미지 Push 방법

### 3. `GHCR_SETUP_COMPLETE.md`
- GHCR 세팅 완료 체크리스트
- 이미지 Public 설정 방법

### 4. `DEVELOPMENT_READY.md`
- 개발 시작 가이드
- Git Push → 자동 배포 워크플로우

---

## 🎯 주요 이점

### 1. 개발 속도 향상
- 코드 Push만으로 자동 배포
- 수동 작업 최소화

### 2. 배포 안정성
- GitOps로 배포 이력 추적
- Rollback 용이

### 3. 환경 일관성
- Helm Chart로 환경 통일
- Staging/Production 동일 구조

### 4. 확장성
- 새 서비스 추가: `values.yaml` 수정만
- HPA, VPA 통합 준비 완료

---

## ✅ 체크리스트

- [x] Helm Chart 작성
- [x] ArgoCD Application 정의
- [x] GitHub Actions 워크플로우
- [x] GHCR 이미지 경로 설정
- [x] 문서 작성 완료
- [ ] ArgoCD 설치 (배포 시)
- [ ] Application 배포 (배포 시)
- [ ] GitHub Actions Secrets 설정 (배포 시)

---

## 🔗 의존성

- **선행 작업**: #11 (feature/infra-13nodes)
- **후속 작업**: feature/microservices-skeleton

---

## 👥 리뷰어

@backend-team @devops-team

---

## 📝 참고사항

- GitHub Actions는 `GITHUB_TOKEN`을 자동 사용합니다
- GHCR 이미지를 Public으로 설정해야 Pull 가능합니다
- ArgoCD Sync Interval은 기본 3분입니다

