# 🚀 배포 가이드

> ⚠️ **이 문서는 레거시입니다.**  
> **최신 문서**: [docs/deployment/gitops-argocd-helm.md](docs/deployment/gitops-argocd-helm.md)

---

## 📌 빠른 링크

**→ [GitOps 배포 가이드 (ArgoCD + Helm)](docs/deployment/gitops-argocd-helm.md)** ⭐

**→ [K8s 클러스터 구축](docs/infrastructure/k8s-cluster-setup.md)** ⭐

**→ [IaC 구성 (Terraform + Ansible)](docs/infrastructure/iac-terraform-ansible.md)** ⭐

**→ [구축 체크리스트](docs/guides/setup-checklist.md)** ⭐

---

## 📋 목차 (레거시 - Docker Compose 기반)
1. [배포 아키텍처](#배포-아키텍처)
2. [로컬 개발 환경](#로컬-개발-환경)
3. [Docker 배포](#docker-배포)
4. [AWS EC2 배포](#aws-ec2-배포)
5. [AWS ECS 배포](#aws-ecs-배포-선택)
6. [CI/CD 파이프라인](#cicd-파이프라인)
7. [환경변수 설정](#환경변수-설정)
8. [트러블슈팅](#트러블슈팅)

**이하 내용은 Docker Compose 기반입니다. Kubernetes 배포는 docs/deployment/ 참고하세요.**

---

## 🏗️ 배포 아키텍처

### 전체 구조

```mermaid
flowchart TD
    A["GitHub Repository<br/>- 코드 저장<br/>- GitHub Actions"] -->|Push/PR 이벤트| B
    
    subgraph GHA["GitHub Actions"]
        B["ci.yml<br/>Lint & Test"]
        C["build-push.yml<br/>Docker Build"]
        D["deploy.yml<br/>Deploy to Server"]
    end
    
    B --> C
    C --> D
    
    D -->|Deploy| E
    
    subgraph AWS["AWS EC2 / ECS"]
        E["Docker Compose"]
        
        subgraph Services["Services"]
            F1["Nginx<br/>(리버스 프록시)"]
            F2["FastAPI Backend"]
            F3["PostgreSQL"]
            F4["Redis"]
        end
        
        E --> F1
        E --> F2
        E --> F3
        E --> F4
    end
    
    style A fill:#e1f5ff,stroke:#0066cc
    style B fill:#ffe1e1,stroke:#ff3333
    style C fill:#ffe1e1,stroke:#ff3333
    style D fill:#ffe1e1,stroke:#ff3333
    style E fill:#e1ffe1,stroke:#00cc66
    style F1 fill:#fff4e1,stroke:#ff9900
    style F2 fill:#e1f5ff,stroke:#0066cc
    style F3 fill:#e1f0ff,stroke:#3366ff
    style F4 fill:#ffe1e1,stroke:#ff3333
```

---

## 💻 로컬 개발 환경

### 1. 기본 설정

```bash
# 1. 저장소 클론
git clone <repository-url>
cd backend

# 2. 개발 환경 자동 설정
make dev-setup

# 3. 가상환경 활성화
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# 4. 환경변수 설정
cp .env.example .env
# .env 파일을 열어 실제 값으로 수정
```

### 2. 로컬 서버 실행

```bash
# Python 가상환경에서 직접 실행
make run

# 또는
uvicorn app.main:app --reload
```

접속: http://localhost:8000/docs

### 3. Docker Compose로 개발 (권장)

```bash
# 개발 환경 실행 (Hot Reload)
make docker-up-dev

# 또는
docker-compose -f docker-compose.dev.yml up
```

**장점:**
- ✅ 데이터베이스, Redis 자동 실행
- ✅ 코드 변경 시 자동 리로드
- ✅ 프로덕션 환경과 동일한 설정

---

## 🐳 Docker 배포

### 1. Docker 이미지 빌드

```bash
# 프로덕션 이미지 빌드
make docker-build

# 또는
docker build -t sesacthon-backend:latest .
```

### 2. Docker Compose로 실행

```bash
# 전체 스택 실행
make docker-up

# 또는
docker-compose up -d
```

### 3. 로그 확인

```bash
# 전체 로그
docker-compose logs -f

# 특정 서비스 로그
docker-compose logs -f backend
docker-compose logs -f nginx
```

### 4. 상태 확인

```bash
# 컨테이너 상태
make docker-ps

# 헬스 체크
make health-check
```

---

## ☁️ AWS EC2 배포

### 사전 준비

1. **AWS EC2 인스턴스 생성**
   - Ubuntu 22.04 LTS
   - t3.medium 이상 권장
   - 보안 그룹: 80, 443, 22 포트 개방

2. **EC2에 Docker 설치**

```bash
# EC2 인스턴스 접속
ssh -i your-key.pem ubuntu@your-ec2-ip

# Docker 설치 스크립트
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Docker Compose 설치
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 현재 사용자를 docker 그룹에 추가
sudo usermod -aG docker $USER
```

### 배포 방법 1: 수동 배포

```bash
# 1. EC2 인스턴스 접속
ssh -i your-key.pem ubuntu@your-ec2-ip

# 2. 프로젝트 클론
cd /home/ubuntu
git clone <repository-url> sesacthon-backend
cd sesacthon-backend

# 3. 환경변수 설정
cp .env.example .env
nano .env  # 실제 값으로 수정

# 4. Docker Compose 실행
docker-compose up -d

# 5. 배포 확인
curl http://localhost:8000/
```

### 배포 방법 2: GitHub Actions 자동 배포

**1. GitHub Secrets 설정**

`Repository → Settings → Secrets and variables → Actions`에서 추가:

```
EC2_HOST: your-ec2-public-ip
EC2_USER: ubuntu
EC2_SSH_KEY: -----BEGIN RSA PRIVATE KEY-----
            (your-private-key-content)
            -----END RSA PRIVATE KEY-----
```

**2. Push하면 자동 배포**

```bash
git push origin main
```

`.github/workflows/deploy.yml`이 자동으로 실행되어 배포됩니다.

---

## 🚢 AWS ECS 배포 (선택)

더 확장성 있는 배포를 원하면 AWS ECS Fargate를 사용하세요.

### 1. ECR 레포지토리 생성

```bash
aws ecr create-repository \
    --repository-name sesacthon-backend \
    --region ap-northeast-2
```

### 2. ECS 클러스터 생성

AWS 콘솔에서:
1. ECS → 클러스터 → 생성
2. Fargate 선택
3. 클러스터 이름: `sesacthon-cluster`

### 3. Task Definition 작성

`task-definition.json` 파일 생성 (필요 시 제공)

### 4. GitHub Secrets 설정

```
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
```

### 5. 배포

`.github/workflows/deploy-aws-ecs.yml` 활성화 후 Push

---

## 🔄 CI/CD 파이프라인

### Workflow 구조

```mermaid
flowchart TD
    A["PR 생성 / Push"] --> B
    
    subgraph CI["ci.yml - 코드 품질 검사"]
        B["Black 포맷 검사"]
        B1["isort Import 정렬"]
        B2["Flake8 린트"]
        B3["pytest 테스트"]
        B4["보안 취약점 스캔"]
    end
    
    B --> B1 --> B2 --> B3 --> B4
    B4 -->|✅ Pass| C
    
    subgraph Build["build-push.yml - 이미지 빌드"]
        C["Docker 이미지 빌드"]
        C1["GHCR/ECR에 푸시"]
    end
    
    C --> C1
    C1 -->|✅ Pass| D
    
    subgraph Deploy["deploy.yml - 배포"]
        D["EC2에 SSH 접속"]
        D1["Docker Compose 재배포"]
        D2["헬스 체크"]
    end
    
    D --> D1 --> D2
    
    style A fill:#e1f5ff,stroke:#0066cc,stroke-width:3px
    style B fill:#ffe1e1,stroke:#ff3333
    style B1 fill:#ffe1e1,stroke:#ff3333
    style B2 fill:#ffe1e1,stroke:#ff3333
    style B3 fill:#ffe1e1,stroke:#ff3333
    style B4 fill:#ffe1e1,stroke:#ff3333
    style C fill:#fff4e1,stroke:#ff9900
    style C1 fill:#fff4e1,stroke:#ff9900
    style D fill:#e1ffe1,stroke:#00cc66
    style D1 fill:#e1ffe1,stroke:#00cc66
    style D2 fill:#e1ffe1,stroke:#00cc66
```

### 주요 Workflows

| 파일 | 트리거 | 용도 |
|------|--------|------|
| `ci.yml` | PR, Push to develop/main | 린트, 테스트 |
| `build-push.yml` | Push to main | Docker 이미지 빌드 |
| `deploy.yml` | Push to main | EC2 배포 |
| `deploy-aws-ecs.yml` | 수동 또는 Push | ECS 배포 (선택) |

---

## 🔧 환경변수 설정

### 필수 환경변수

```bash
# .env 파일
APP_NAME="AI Waste Coach Backend"
DEBUG=False
DATABASE_URL=postgresql://user:password@db:5432/sesacthon_db

# JWT
SECRET_KEY=your-super-secret-key-here-change-this
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# OAuth
KAKAO_CLIENT_ID=your-kakao-client-id
KAKAO_CLIENT_SECRET=your-kakao-client-secret

NAVER_CLIENT_ID=your-naver-client-id
NAVER_CLIENT_SECRET=your-naver-client-secret

GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# AI APIs
AI_VISION_API_URL=http://ai-server:5000/predict
OPENAI_API_KEY=sk-...

# CORS
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

### GitHub Secrets 설정 목록

배포 자동화를 위해 필요한 Secrets:

```
# EC2 배포용
EC2_HOST
EC2_USER
EC2_SSH_KEY

# AWS ECS 배포용 (선택)
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY

# Slack 알림용 (선택)
SLACK_WEBHOOK_URL
```

---

## 🛠️ 트러블슈팅

### 1. Docker 빌드 실패

**문제:** `ERROR [internal] load metadata for docker.io/library/python:3.11`

**해결:**
```bash
docker buildx prune
docker build --no-cache -t sesacthon-backend:latest .
```

### 2. 데이터베이스 연결 실패

**문제:** `could not connect to server: Connection refused`

**해결:**
```bash
# PostgreSQL 컨테이너 상태 확인
docker-compose ps

# PostgreSQL 로그 확인
docker-compose logs db

# DATABASE_URL 확인
docker-compose exec backend env | grep DATABASE_URL
```

### 3. Nginx 502 Bad Gateway

**문제:** Nginx가 백엔드에 연결할 수 없음

**해결:**
```bash
# 백엔드 컨테이너 확인
docker-compose ps backend

# 백엔드 로그 확인
docker-compose logs backend

# 네트워크 확인
docker network inspect sesacthon_backend_network
```

### 4. GitHub Actions 배포 실패

**문제:** SSH 연결 실패

**해결:**
1. EC2 보안 그룹에서 SSH(22) 포트 개방 확인
2. GitHub Secrets의 SSH 키 확인
3. EC2 인스턴스 상태 확인

---

## 📊 모니터링 및 로깅

### Docker Compose 로그

```bash
# 전체 로그
docker-compose logs -f

# 최근 100줄만 보기
docker-compose logs --tail=100 backend

# 특정 시간 이후 로그
docker-compose logs --since 30m backend
```

### 애플리케이션 로그

```bash
# 컨테이너 내부 로그 파일
docker-compose exec backend tail -f /var/log/app.log
```

### Nginx 로그

```bash
# Access 로그
docker-compose exec nginx tail -f /var/log/nginx/access.log

# Error 로그
docker-compose exec nginx tail -f /var/log/nginx/error.log
```

---

## ✅ 배포 체크리스트

배포 전 확인사항:

- [ ] 모든 테스트 통과 (`make test`)
- [ ] 린트 검사 통과 (`make lint`)
- [ ] `.env` 파일 설정 완료
- [ ] Docker 이미지 빌드 성공
- [ ] 로컬에서 Docker Compose 실행 확인
- [ ] 데이터베이스 마이그레이션 적용
- [ ] 환경변수에 민감정보 노출 여부 확인
- [ ] CORS 설정 확인
- [ ] GitHub Secrets 설정 완료
- [ ] SSL 인증서 설정 (프로덕션)

```bash
# 자동 체크
make deploy-check
```

---

## 🔗 참고 자료

- [Docker 공식 문서](https://docs.docker.com/)
- [FastAPI 배포 가이드](https://fastapi.tiangolo.com/deployment/)
- [GitHub Actions 문서](https://docs.github.com/en/actions)
- [AWS EC2 문서](https://docs.aws.amazon.com/ec2/)
- [Nginx 설정 가이드](https://nginx.org/en/docs/)

---

**작성일**: 2025-10-30  
**작성자**: SeSACTHON Backend Team

