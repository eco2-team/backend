# Users Domain - Schema Migrations

Users 스키마 버전 관리를 위한 Alembic 설정입니다.

## 스키마 통합

```
auth.users + user_profile.users → users.accounts
auth.user_social_accounts       → users.social_accounts
user_profile.user_characters    → users.user_characters
```

## 디렉토리 구조

```
migrations/users/
├── alembic.ini
├── env.py
├── script.py.mako
├── README.md
└── versions/
    └── 20260103_0001_initial_users_schema.py
```

## 사용법

```bash
# 환경변수 설정
export USERS_DATABASE_URL="postgresql://user:pass@host:5432/dbname"

# 작업 디렉토리 이동
cd migrations/users

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
| 0001 | Initial users schema (accounts, social_accounts, user_characters) | 2026-01-03 |

## 기존 환경에 적용

```bash
# 테이블이 이미 있는 경우
alembic stamp 0001
alembic upgrade head
```
