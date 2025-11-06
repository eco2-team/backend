# 🔧 [Services] 마이크로서비스 스켈레톤 구조

## 📋 변경 사항 요약

6개 도메인별 API 서비스의 기본 디렉토리 구조와 스켈레톤 코드를 추가했습니다.

### 주요 변경사항

#### 1. 서비스 디렉토리 구조
```
services/
├── README.md                      # 서비스 가이드
├── auth-api/                      # 인증/인가 서비스
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       └── main.py
├── userinfo-api/                  # 사용자 정보 서비스
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       └── main.py
├── location-api/                  # 지도/위치 서비스
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       └── main.py
├── recycle-info-api/              # 재활용 정보 서비스
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       └── main.py
└── chat-llm-api/                  # LLM 채팅 서비스
    ├── Dockerfile
    ├── requirements.txt
    └── app/
        └── main.py
```

#### 2. FastAPI 스켈레톤
- **기본 엔드포인트**: `/health`, `/ready`
- **API 라우터 구조**: `/api/v1/{domain}`
- **환경 변수 설정**: 서비스별 설정 파일

#### 3. Dockerfile
- **Multi-stage Build**: 빌드 최적화
- **경량 이미지**: `python:3.11-slim`
- **비 root 사용자**: 보안 강화

#### 4. Requirements
- **공통 의존성**: FastAPI, Uvicorn, Pydantic
- **확장 가능**: 서비스별 추가 의존성 관리

---

## 📦 각 서비스별 상세

### 1. auth-api (인증/인가)
```yaml
경로: /api/v1/auth
기능:
  - JWT 토큰 발급
  - 사용자 인증
  - 권한 관리
노드: k8s-api-auth (t3.micro)
```

### 2. userinfo-api (사용자 정보)
```yaml
경로: /api/v1/users
기능:
  - 사용자 프로필 관리
  - 개인정보 CRUD
노드: k8s-api-userinfo (t3.micro)
```

### 3. location-api (지도/위치)
```yaml
경로: /api/v1/locations
기능:
  - 지도 API 연동
  - 위치 기반 검색
  - 수거함 위치 조회
노드: k8s-api-location (t3.micro)
```

### 4. recycle-info-api (재활용 정보)
```yaml
경로: /api/v1/recycle
기능:
  - 재활용 품목 정보
  - 분리배출 가이드
  - 지역별 규정 조회
노드: k8s-api-recycle-info (t3.micro)
```

### 5. chat-llm-api (LLM 채팅)
```yaml
경로: /api/v1/chat
기능:
  - GPT-4o mini 채팅
  - 대화 이력 관리
  - 컨텍스트 유지
노드: k8s-api-chat-llm (t3.small)
```

---

## 🔧 개발 가이드

### 1. 로컬 개발 환경 설정
```bash
# 특정 서비스 디렉토리로 이동
cd services/auth-api

# 가상환경 생성
python3 -m venv venv
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# 개발 서버 실행
uvicorn app.main:app --reload --port 8000
```

### 2. Docker 빌드 테스트
```bash
# 이미지 빌드
docker build -t auth-api:test .

# 컨테이너 실행
docker run -p 8000:8000 auth-api:test

# Health Check
curl http://localhost:8000/health
```

### 3. 새 엔드포인트 추가
```python
# app/main.py
@app.get("/api/v1/auth/login")
async def login(username: str, password: str):
    # 로직 구현
    return {"token": "..."}
```

---

## 🚀 배포 플로우

### 자동 배포
```bash
# 1. 코드 수정
vim services/auth-api/app/main.py

# 2. Git 커밋
git add services/auth-api
git commit -m "feat(auth): Add login endpoint"
git push origin main

# 3. 자동 실행
# → GitHub Actions: Docker 빌드
# → GHCR Push: ghcr.io/sesacthon/auth-api:abc123
# → ArgoCD Sync: Kubernetes 배포 (3분 내)

# 4. 배포 확인
kubectl get pods -n api -l app=auth-api
```

---

## 📊 서비스별 리소스

| 서비스 | CPU 요청 | 메모리 요청 | Replicas | 노드 |
|--------|---------|------------|----------|------|
| auth-api | 100m | 256Mi | 2 | k8s-api-auth |
| userinfo-api | 100m | 256Mi | 2 | k8s-api-userinfo |
| location-api | 100m | 256Mi | 2 | k8s-api-location |
| recycle-info-api | 100m | 256Mi | 1 | k8s-api-recycle-info |
| chat-llm-api | 200m | 512Mi | 2 | k8s-api-chat-llm |

---

## 🎯 주요 특징

### 1. 도메인 기반 분리
- 각 도메인별 독립 개발
- 팀 간 의존성 최소화

### 2. 확장 가능한 구조
- 새 서비스 추가 용이
- 동일한 패턴 재사용

### 3. 독립 배포
- 서비스별 CI/CD 파이프라인
- 다른 서비스에 영향 없음

### 4. 표준화된 인터페이스
- 일관된 API 구조
- Health Check 표준화

---

## 📚 새로운 문서

### 1. `services/README.md`
- 서비스 디렉토리 가이드
- 개발 및 배포 절차
- 디렉토리 구조 설명

---

## ✅ 체크리스트

- [x] 6개 서비스 디렉토리 생성
- [x] FastAPI 스켈레톤 코드
- [x] Dockerfile 작성
- [x] requirements.txt 작성
- [x] 서비스 가이드 문서
- [ ] 각 서비스 비즈니스 로직 구현 (개발 시)
- [ ] 환경 변수 설정 (배포 시)
- [ ] 데이터베이스 연동 (개발 시)

---

## 🔗 의존성

- **선행 작업**: 
  - #11 (feature/infra-13nodes)
  - #12 (feature/helm-argocd-cicd)
- **후속 작업**: 각 도메인 기능 개발

---

## 👥 리뷰어

@backend-team

---

## 📝 참고사항

- 이 PR은 스켈레톤 구조만 포함합니다
- 실제 비즈니스 로직은 각 팀에서 개발합니다
- API 명세는 별도 문서로 작성 예정입니다
- 데이터베이스 스키마는 별도 마이그레이션에서 처리합니다

