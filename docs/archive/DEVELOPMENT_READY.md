# Ecoeco Backend - Complete Development Setup

## 🎯 완료된 작업

### ✅ 1. Helm Chart 구조 (6 API + 5 Workers)

```
charts/ecoeco-backend/
├── Chart.yaml
├── values.yaml                    # 전체 설정
└── templates/
    ├── _helpers.tpl
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

### ✅ 2. ArgoCD 자동 배포

```
argocd/application.yaml
- Git 변경 감지 (3분마다)
- 자동 동기화 & 복구
- Helm Chart 기반 배포
```

### ✅ 3. CI/CD 파이프라인

```
.github/workflows/api-deploy.yml
- 서비스별 변경 감지
- Docker 빌드 & GHCR 푸시
- values.yaml 자동 업데이트
- ArgoCD 트리거
```

### ✅ 4. 서비스 스켈레톤

```
services/
├── auth-api/              ✅ JWT 인증/인가
├── userinfo-api/          ✅ 사용자 정보 관리
├── location-api/          ✅ 지도/위치 (Kakao)
├── recycle-info-api/      ✅ 재활용 정보
└── chat-llm-api/          ✅ LLM 채팅
```

### ✅ 5. Terraform (9 노드)

```
terraform/
├── main.tf          # API 노드 2개 추가
├── outputs.tf       # 9 노드 outputs
└── templates/
    └── hosts.tpl    # Ansible inventory
```

---

## 🚀 개발 시작하기

### 1단계: 서비스 개발

```bash
# 예: auth-api 개발
cd services/auth-api

# 로컬 개발 환경
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 환경 변수 설정
export DATABASE_URL="postgresql://..."
export REDIS_URL="redis://..."
export JWT_SECRET="your-secret"

# 실행
uvicorn app.main:app --reload --port 8000

# 테스트
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/auth/me
```

### 2단계: Docker로 테스트

```bash
# 이미지 빌드
docker build -t auth-api:test .

# 실행
docker run -p 8000:8000 \
  -e DATABASE_URL="..." \
  -e REDIS_URL="..." \
  auth-api:test

# Health check
curl http://localhost:8000/health
```

### 3단계: Git Push → 자동 배포

```bash
# Feature 브랜치 생성
git checkout -b feature/auth-api

# 개발 완료 후
git add services/auth-api/
git commit -m "feat: Add JWT authentication with OAuth2"
git push origin feature/auth-api

# PR 생성 & 병합
# → main 브랜치에 병합되면 자동으로:
#   1. GitHub Actions가 Docker 빌드
#   2. GHCR에 이미지 푸시
#   3. values.yaml 업데이트
#   4. ArgoCD가 자동 배포
```

---

## 📋 서비스별 주요 엔드포인트

### 1. Auth API (`:8001`)

```
POST   /api/v1/auth/register       # 회원가입
POST   /api/v1/auth/login          # 로그인
POST   /api/v1/auth/logout         # 로그아웃
GET    /api/v1/auth/me             # 현재 사용자
POST   /api/v1/auth/refresh        # 토큰 갱신
```

### 2. Userinfo API (`:8002`)

```
GET    /api/v1/users/{id}          # 프로필 조회
PATCH  /api/v1/users/{id}          # 프로필 수정
GET    /api/v1/users/{id}/points   # 포인트 조회
GET    /api/v1/users/{id}/history  # 활동 히스토리
```

### 3. Location API (`:8003`)

```
GET    /api/v1/locations/bins      # 근처 수거함
GET    /api/v1/locations/centers   # 재활용 센터
POST   /api/v1/locations/geocode   # 주소→좌표
```

### 4. Recycle Info API (`:8004`)

```
GET    /api/v1/recycle/items/{id}  # 품목 정보
GET    /api/v1/recycle/categories  # 카테고리
POST   /api/v1/recycle/search      # 품목 검색
GET    /api/v1/recycle/faq         # FAQ
```

### 5. Chat LLM API (`:8005`)

```
POST   /api/v1/chat/messages       # 메시지 전송
GET    /api/v1/chat/sessions/{id}  # 세션 조회
GET    /api/v1/chat/suggestions    # 추천 질문
```

---

## 🔄 자동 배포 프로세스

```mermaid
graph LR
    Dev["`**개발자**`"] --> Code["`**코드 작성**
    services/auth-api/`"]
    
    Code --> Push["`**Git Push**
    feature 브랜치`"]
    
    Push --> PR["`**PR 병합**
    main 브랜치`"]
    
    PR --> CI["`**GitHub Actions**
    Docker Build`"]
    
    CI --> GHCR["`**GHCR Push**
    이미지 저장`"]
    
    GHCR --> Update["`**values.yaml**
    이미지 태그 업데이트`"]
    
    Update --> ArgoCD["`**ArgoCD**
    변경 감지`"]
    
    ArgoCD --> K8s["`**Kubernetes**
    Rolling Update`"]
    
    style Dev fill:#FFE066,stroke:#F59F00,stroke-width:2px,color:#000
    style CI fill:#7B68EE,stroke:#4B3C8C,stroke-width:3px,color:#fff
    style ArgoCD fill:#F39C12,stroke:#C87F0A,stroke-width:3px,color:#000
    style K8s fill:#4A90E2,stroke:#2E5C8A,stroke-width:3px,color:#fff
```

---

## 🏗️ 인프라 배포

### Terraform + Ansible

```bash
# 1. Terraform으로 9노드 인프라 생성
cd terraform/
terraform init
terraform plan
terraform apply

# 2. Ansible로 Kubernetes 설치
cd ../ansible/
ansible-playbook -i inventory/hosts.ini site.yml

# 3. ArgoCD 설치
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# 4. ArgoCD Application 배포
kubectl apply -f argocd/application.yaml

# 5. 확인
kubectl get pods -n api
kubectl get pods -n workers
```

---

## 📊 노드 구성 (9개)

| 노드 | 역할 | 인스턴스 | 워크로드 |
|------|------|----------|----------|
| **Master** | Control Plane | t3.large (8GB) | Control Plane + ArgoCD |
| **API-1** | High Traffic | t3.medium (4GB) | waste, chat-llm, auth |
| **API-2** | Low-Medium | t3.medium (4GB) | userinfo, location, recycle-info |
| **Worker-1** | Storage | t3.medium (4GB) | image-uploader, rule-retriever, beat |
| **Worker-2** | AI | t3.medium (4GB) | gpt5-analyzer, response-generator |
| **RabbitMQ** | Message Queue | t3.small (2GB) | RabbitMQ |
| **PostgreSQL** | Database | t3.small (2GB) | PostgreSQL |
| **Redis** | Cache | t3.small (2GB) | Redis |
| **Monitoring** | Observability | t3.large (8GB) | Prometheus + Grafana |

**총 리소스**: 18 vCPU, 38GB RAM, ~$240/월

---

## ✅ 개발 준비 완료!

### 각 팀이 할 일

**백엔드 팀**:
1. `services/{service-name}-api/` 에서 FastAPI 코드 개발
2. `/api/v1/` 엔드포인트 구현
3. PostgreSQL 모델 정의 (`app/db/models.py`)
4. 비즈니스 로직 작성 (`app/services/`)

**DevOps 팀**:
1. Terraform으로 인프라 배포 (완료 ✅)
2. Ansible로 Kubernetes 설치
3. ArgoCD Application 배포
4. Monitoring 대시보드 설정

**프론트엔드 팀**:
1. API 명세서 확인 (각 서비스의 `/docs` 엔드포인트)
2. 통합 테스트
3. 에러 핸들링

---

**결론**: 완전 자동화된 개발 환경 준비 완료! Git Push만으로 프로덕션 배포 가능! 🎯🚀

