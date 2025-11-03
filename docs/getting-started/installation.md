# 🔧 설치 가이드

이 문서는 AI Waste Coach Backend 개발 환경을 설정하는 방법을 안내합니다.

## 📋 목차

1. [시스템 요구사항](#시스템-요구사항)
2. [사전 준비](#사전-준비)
3. [설치 방법](#설치-방법)
4. [환경변수 설정](#환경변수-설정)
5. [데이터베이스 설정](#데이터베이스-설정)
6. [검증](#검증)

---

## 💻 시스템 요구사항

### 필수 요구사항

- **OS**: macOS, Linux, Windows 10/11
- **Python**: 3.11 이상
- **메모리**: 최소 4GB RAM (8GB 권장)
- **디스크**: 최소 5GB 여유 공간

### 선택 사항 (Docker 사용 시)

- **Docker**: 20.10 이상
- **Docker Compose**: 2.0 이상

---

## 🛠️ 사전 준비

### 1. Python 설치

**macOS (Homebrew 사용)**
```bash
brew install python@3.11
```

**Ubuntu/Debian**
```bash
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip
```

**Windows**
- [Python 공식 웹사이트](https://www.python.org/downloads/)에서 설치

### 2. Git 설치

**macOS**
```bash
brew install git
```

**Ubuntu/Debian**
```bash
sudo apt install git
```

**Windows**
- [Git for Windows](https://git-scm.com/download/win) 다운로드

### 3. Docker 설치 (선택)

**macOS**
- [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop) 설치

**Ubuntu**
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

**Windows**
- [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop) 설치

---

## 📦 설치 방법

### 방법 1: 자동 설정 (권장 ⭐)

```bash
# 1. 저장소 클론
git clone <repository-url>
cd backend

# 2. 자동 설정 스크립트 실행
make dev-setup
```

이 명령어는 다음을 자동으로 수행합니다:
- ✅ Python 가상환경 생성
- ✅ 의존성 패키지 설치
- ✅ .env 파일 생성
- ✅ pre-commit hook 설치

### 방법 2: 수동 설정

```bash
# 1. 저장소 클론
git clone <repository-url>
cd backend

# 2. 가상환경 생성
python3.11 -m venv venv

# 3. 가상환경 활성화
# macOS/Linux
source venv/bin/activate

# Windows
venv\Scripts\activate

# 4. pip 업그레이드
pip install --upgrade pip

# 5. 의존성 설치
pip install -r requirements.txt

# 6. 환경변수 파일 생성
cp .env.example .env

# 7. pre-commit hook 설치
pre-commit install
```

### 방법 3: Docker 사용

```bash
# 1. 저장소 클론
git clone <repository-url>
cd backend

# 2. 환경변수 설정
cp .env.example .env

# 3. Docker Compose로 실행
docker-compose -f docker-compose.dev.yml up
```

---

## 🔑 환경변수 설정

### 1. .env 파일 생성

```bash
cp .env.example .env
```

### 2. 필수 환경변수 설정

`.env` 파일을 열어 다음 값들을 수정하세요:

```bash
# 데이터베이스
DATABASE_URL=postgresql://user:password@localhost:5432/sesacthon_db

# JWT Secret (보안을 위해 반드시 변경!)
SECRET_KEY=your-super-secret-key-here-change-this-in-production

# OAuth (실제 값으로 변경)
KAKAO_CLIENT_ID=your-kakao-client-id
KAKAO_CLIENT_SECRET=your-kakao-client-secret

NAVER_CLIENT_ID=your-naver-client-id
NAVER_CLIENT_SECRET=your-naver-client-secret

GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# AI APIs
OPENAI_API_KEY=sk-your-openai-api-key
```

상세한 환경변수 설명은 [환경변수 가이드](../deployment/environment.md)를 참고하세요.

---

## 🗄️ 데이터베이스 설정

### PostgreSQL 설치 및 설정

**방법 1: Docker 사용 (권장)**

```bash
# docker-compose.dev.yml이 자동으로 PostgreSQL 실행
docker-compose -f docker-compose.dev.yml up -d db
```

**방법 2: 로컬 설치**

**macOS**
```bash
brew install postgresql@15
brew services start postgresql@15
createdb sesacthon_db
```

**Ubuntu**
```bash
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo -u postgres createdb sesacthon_db
```

### 마이그레이션 실행

```bash
# 데이터베이스 마이그레이션 적용
make db-upgrade

# 또는
alembic upgrade head
```

---

## ✅ 검증

### 1. 패키지 설치 확인

```bash
pip list | grep fastapi
# 출력: fastapi        0.109.0
```

### 2. 서버 실행 테스트

```bash
# 개발 서버 실행
make run

# 또는
uvicorn app.main:app --reload
```

브라우저에서 http://localhost:8000/docs 접속 → Swagger UI가 표시되면 성공!

### 3. 데이터베이스 연결 확인

```bash
# Python 셸에서 테스트
python -c "from app.core.database import engine; print(engine.connect())"
```

에러가 없으면 데이터베이스 연결 성공!

### 4. 테스트 실행

```bash
make test

# 또는
pytest
```

모든 테스트가 통과하면 설치 완료! ✅

---

## 🐛 문제 해결

### Python 버전 오류

**문제**: `python: command not found`

**해결**:
```bash
# Python 3.11이 설치되어 있는지 확인
python3.11 --version

# python3.11로 가상환경 생성
python3.11 -m venv venv
```

### 패키지 설치 실패

**문제**: `error: could not build wheels for X`

**해결**:
```bash
# macOS
brew install python@3.11

# Ubuntu
sudo apt install python3.11-dev build-essential libpq-dev
```

### 데이터베이스 연결 실패

**문제**: `could not connect to server`

**해결**:
```bash
# PostgreSQL이 실행 중인지 확인
# macOS
brew services list | grep postgresql

# Ubuntu
sudo systemctl status postgresql

# Docker
docker-compose ps db
```

### 포트 충돌

**문제**: `Address already in use`

**해결**:
```bash
# 8000번 포트를 사용 중인 프로세스 확인
lsof -i :8000

# 프로세스 종료
kill -9 <PID>

# 또는 다른 포트 사용
uvicorn app.main:app --reload --port 8001
```

---

## 📚 다음 단계

설치가 완료되었나요? 이제 다음 단계로 넘어가세요!

1. ✅ [빠른 시작 가이드](quickstart.md) - 5분 만에 첫 API 호출하기
2. ✅ [프로젝트 구조](project-structure.md) - 코드베이스 이해하기
3. ✅ [코딩 컨벤션](../development/conventions.md) - 코드 작성 규칙

---

## 🔗 관련 문서

- [환경변수 가이드](../deployment/environment.md)
- [데이터베이스 가이드](../development/database.md)
- [트러블슈팅](../deployment/troubleshooting.md)

---

**문서 버전**: 1.0.0  
**최종 업데이트**: 2025-10-30

