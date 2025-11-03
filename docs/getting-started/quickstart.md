# ⚡ 빠른 시작 가이드

이 가이드를 따라하면 **5분 안에** 서버를 실행하고 첫 API를 호출할 수 있습니다!

## 🎯 목표

- ✅ 개발 서버 실행
- ✅ Swagger UI로 API 테스트
- ✅ 첫 API 호출 성공

---

## 🚀 가장 빠른 방법 (Docker)

### 1단계: 저장소 클론

```bash
git clone <repository-url>
cd backend
```

### 2단계: 환경변수 설정

```bash
cp .env.example .env
```

### 3단계: 서버 실행

```bash
docker-compose -f docker-compose.dev.yml up
```

### 4단계: 접속 확인

브라우저에서 http://localhost:8000/docs 접속!

🎉 **완료!** Swagger UI가 보이면 성공입니다.

---

## 💻 Python 가상환경 사용

### 1단계: 자동 설정

```bash
git clone <repository-url>
cd backend
make dev-setup
```

### 2단계: 가상환경 활성화

```bash
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows
```

### 3단계: 서버 실행

```bash
make run
```

### 4단계: 접속 확인

http://localhost:8000/docs 접속!

---

## 🧪 첫 API 호출하기

### 방법 1: Swagger UI 사용

1. http://localhost:8000/docs 접속
2. `GET /` 엔드포인트 클릭
3. **"Try it out"** 버튼 클릭
4. **"Execute"** 버튼 클릭

**응답 예시:**
```json
{
  "status": "OK",
  "message": "AI Waste Coach Backend is running",
  "version": "1.0.0"
}
```

### 방법 2: cURL 사용

```bash
curl http://localhost:8000/
```

### 방법 3: Python으로 호출

```python
import requests

response = requests.get("http://localhost:8000/")
print(response.json())
```

---

## 📊 개발 도구

### Swagger UI
- **URL**: http://localhost:8000/docs
- **용도**: 인터랙티브 API 테스트

### ReDoc
- **URL**: http://localhost:8000/redoc
- **용도**: 읽기 쉬운 API 문서

### 데이터베이스 관리
```bash
# 마이그레이션 적용
make db-upgrade

# 데이터베이스 상태 확인
docker-compose exec db psql -U sesacthon -d sesacthon_dev -c "\dt"
```

---

## 🔍 자주 사용하는 명령어

```bash
# 서버 실행
make run                    # Python으로 실행
make docker-up-dev         # Docker로 실행

# 코드 품질
make format                # 코드 포맷팅
make lint                  # 린트 검사
make test                  # 테스트 실행

# 데이터베이스
make db-migrate msg="설명"  # 마이그레이션 생성
make db-upgrade            # 마이그레이션 적용

# Docker
make docker-logs           # 로그 확인
make docker-ps             # 컨테이너 상태
make docker-down           # 중지
```

전체 명령어는 `make help` 로 확인하세요.

---

## 🎓 다음 단계

기본 설정이 완료되었나요? 이제 개발을 시작해봅시다!

1. [프로젝트 구조 이해하기](project-structure.md)
2. [첫 API 만들기](../development/first-api.md)
3. [데이터베이스 모델 작성하기](../development/database.md)

---

## 🐛 문제가 발생했나요?

### 포트가 이미 사용 중입니다

```bash
# 다른 포트로 실행
uvicorn app.main:app --reload --port 8001
```

### Docker 컨테이너가 시작되지 않습니다

```bash
# 로그 확인
docker-compose logs

# 컨테이너 재시작
docker-compose down
docker-compose -f docker-compose.dev.yml up --build
```

### 데이터베이스 연결 실패

```bash
# .env 파일의 DATABASE_URL 확인
cat .env | grep DATABASE_URL

# PostgreSQL 컨테이너 상태 확인
docker-compose ps db
```

더 많은 해결 방법은 [트러블슈팅 가이드](../deployment/troubleshooting.md)를 참고하세요.

---

**문서 버전**: 1.0.0  
**최종 업데이트**: 2025-10-30

