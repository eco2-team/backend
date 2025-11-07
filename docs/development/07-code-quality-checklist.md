# ✅ 코드 품질 체크리스트

PR 제출 전 확인해야 할 항목들입니다.

## 📋 필수 검사 항목

### 1. PEP 8 준수 ✅

```bash
# 검사
pycodestyle app/ --max-line-length=100

# 예상 결과: 에러 0개
```

- [ ] 들여쓰기 4칸 스페이스
- [ ] 줄 길이 100자 이내
- [ ] Import 순서 준수
- [ ] 네이밍 규칙 준수
- [ ] 빈 줄 규칙 준수

### 2. 코드 포맷팅 ✅

```bash
# Black 검사
black --check .

# isort 검사
isort --check-only .

# 자동 수정
make lint-fix
```

- [ ] Black 포맷팅 통과
- [ ] Import 정렬 완료

### 3. 린트 검사 ✅

```bash
# Flake8
flake8 app/
```

- [ ] Flake8 에러 0개
- [ ] 사용하지 않는 import 제거
- [ ] 미사용 변수 제거

### 4. 테스트 ✅

```bash
# 테스트 실행
pytest --cov=app

# 목표: 커버리지 80% 이상
```

- [ ] 모든 테스트 통과
- [ ] 새 기능 테스트 추가
- [ ] 커버리지 80% 이상

### 5. 타입 힌트 ⭐ (권장)

```bash
# MyPy 검사
mypy app/
```

- [ ] 주요 함수에 타입 힌트 추가
- [ ] MyPy 에러 해결

### 6. 문서화 ✅

- [ ] Docstring 작성 (공개 함수/클래스)
- [ ] README 업데이트 (필요 시)
- [ ] CHANGELOG 업데이트 (필요 시)

## 🚀 빠른 검사

```bash
# 모든 검사 한 번에
make lint && make test

# 또는 배포 전 전체 검사
make deploy-check
```

## 📊 품질 등급

### 🥇 Gold (최우수)
- ✅ PEP 8 100% 준수
- ✅ Pylint 9.0 이상
- ✅ 테스트 커버리지 90% 이상
- ✅ MyPy 타입 체크 통과
- ✅ Docstring 완벽

### 🥈 Silver (우수)
- ✅ PEP 8 100% 준수
- ✅ 모든 테스트 통과
- ✅ 테스트 커버리지 80% 이상
- ⭐ Pylint 8.0 이상

### 🥉 Bronze (합격)
- ✅ PEP 8 준수
- ✅ Black, Flake8 통과
- ✅ 모든 테스트 통과
- ✅ PR 머지 가능

---

**문서 버전**: 1.0.0  
**최종 업데이트**: 2025-10-30
