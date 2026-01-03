# Character Domain - Schema Migrations

Character 스키마 버전 관리를 위한 Alembic 설정입니다.

## 디렉토리 구조

```
migrations/character/
├── alembic.ini          # Alembic 설정
├── env.py               # 환경 설정 (DB 연결, 메타데이터)
├── script.py.mako       # 마이그레이션 템플릿
├── README.md            # 이 문서
└── versions/            # 마이그레이션 파일들
    ├── 20260101_0001_initial_character_schema.py
    └── 20260103_0002_add_character_code_text_strategy.py
```

## 사용법

### 환경 설정

```bash
# DB URL 설정 (필수)
export CHARACTER_DATABASE_URL="postgresql://user:pass@host:5432/dbname"

# 또는 일반 DATABASE_URL 사용
export DATABASE_URL="postgresql://user:pass@host:5432/dbname"
```

### 마이그레이션 실행

```bash
# 작업 디렉토리 이동
cd migrations/character

# 현재 버전 확인
alembic current

# 최신 버전으로 업그레이드
alembic upgrade head

# 특정 버전으로 업그레이드
alembic upgrade 0002

# 한 단계 롤백
alembic downgrade -1

# 특정 버전으로 롤백
alembic downgrade 0001

# SQL만 출력 (실행 없이)
alembic upgrade head --sql
```

### 새 마이그레이션 생성

```bash
# 자동 생성 (모델 변경 감지)
alembic revision --autogenerate -m "add new column"

# 빈 마이그레이션 생성
alembic revision -m "manual migration"
```

### 마이그레이션 히스토리 확인

```bash
# 모든 버전 목록
alembic history

# 상세 히스토리
alembic history --verbose
```

## 버전 히스토리

| Revision | Description | Date |
|----------|-------------|------|
| 0001 | Initial character schema | 2026-01-01 |
| 0002 | Add character_code, TEXT strategy | 2026-01-03 |

## 주의사항

### 기존 환경에 적용

기존 DB에 처음 적용할 때:

```bash
# 1. 현재 스키마 상태를 0001로 마킹 (테이블이 이미 있는 경우)
alembic stamp 0001

# 2. 이후 마이그레이션 적용
alembic upgrade head
```

### 롤백 주의

- `downgrade`는 데이터 손실을 유발할 수 있습니다
- 프로덕션에서는 백업 후 실행하세요

### CI/CD 통합

```yaml
# GitHub Actions 예시
- name: Run character migrations
  run: |
    cd migrations/character
    alembic upgrade head
  env:
    CHARACTER_DATABASE_URL: ${{ secrets.DATABASE_URL }}
```

## Clean Architecture 전환

`env.py`는 모델 import를 유연하게 처리합니다:

```python
try:
    # Clean Architecture (apps/) - 우선
    from apps.character.infrastructure.persistence_postgres.models import ...
except ImportError:
    # Legacy (domains/) - 폴백
    from domains.character.models.character import ...
```

`domains/` 삭제 후에는 `apps/` 경로만 남습니다.

## 트러블슈팅

### "Target database is not up to date"

```bash
# 현재 상태 확인
alembic current

# 강제로 특정 버전으로 마킹
alembic stamp <revision>
```

### "Can't locate revision"

```bash
# 버전 테이블 초기화
alembic stamp head --purge
alembic stamp base
alembic upgrade head
```

### Import 에러

프로젝트 루트에서 실행 중인지 확인:

```bash
cd /path/to/backend
cd database/character
alembic current
```
