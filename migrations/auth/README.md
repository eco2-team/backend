# Auth Domain - Schema Migrations

Auth 스키마 버전 관리를 위한 Alembic 설정입니다.

> ⚠️ **DEPRECATED**: auth 스키마는 users 스키마로 통합 진행 중입니다.
> 이 마이그레이션은 롤백 및 레거시 호환성을 위해 유지됩니다.

## 마이그레이션 전략

```
Phase 1 (현재): auth + users 스키마 공존
Phase 2: users 스키마로 전환, auth는 읽기 전용
Phase 3: auth 스키마 DROP
```

## 디렉토리 구조

```
migrations/auth/
├── alembic.ini
├── env.py
├── script.py.mako
├── README.md
└── versions/
    └── 20260103_0001_initial_auth_schema.py
```

## 사용법

```bash
# 환경변수 설정
export AUTH_DATABASE_URL="postgresql://user:pass@host:5432/dbname"

# 작업 디렉토리 이동
cd migrations/auth

# 현재 버전 확인
alembic current

# 최신 버전으로 업그레이드
alembic upgrade head

# 롤백
alembic downgrade -1
```

## 버전 히스토리

| Revision | Description | Date |
|----------|-------------|------|
| 0001 | Initial auth schema (users, social_accounts, login_audits) | 2026-01-03 |

## 기존 환경에 적용

```bash
# 테이블이 이미 있는 경우
alembic stamp 0001
```
