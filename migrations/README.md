# Schema Migrations

도메인별 스키마 버전 관리를 위한 Alembic 마이그레이션 디렉토리입니다.

## 구조

```
migrations/
├── README.md              # 이 문서
├── character/             # character 스키마 (Alembic)
│   ├── alembic.ini
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── users/                 # users 스키마 (Alembic) - 통합 스키마
│   ├── alembic.ini
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── auth/                  # auth 스키마 (Alembic) - DEPRECATED
│   ├── alembic.ini
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── schemas/               # 레거시 SQL 스키마 (참고용)
│   ├── auth_schema.sql
│   └── users_schema.sql
└── V003__*.sql            # 레거시 마이그레이션 (Flyway 형식)
```

## 설계 원칙

### 1. 도메인 독립성

각 도메인 스키마는 독립적으로 버전 관리됩니다:

```
character.characters          → migrations/character/
character.character_ownerships

users.accounts                → migrations/users/
users.social_accounts
users.user_characters

auth.users                    → migrations/auth/ (DEPRECATED)
auth.user_social_accounts
auth.login_audits
```

### 2. 서비스 코드와 분리

마이그레이션은 애플리케이션 코드(`apps/`, `domains/`)와 분리됩니다:

- **이유**: `apps/character`와 `apps/character_worker`가 같은 스키마를 사용
- **이점**: 배포 전 별도 파이프라인에서 마이그레이션 실행 가능
- **유연성**: DBA나 다른 팀원이 앱 코드 몰라도 스키마 관리 가능

### 3. 버전 테이블 격리

각 도메인은 자체 `alembic_version` 테이블을 가집니다:

```sql
-- character 도메인
character.alembic_version

-- users 도메인
users.alembic_version
```

## 사용법

### 특정 도메인 마이그레이션

```bash
# character 스키마
cd migrations/character
alembic upgrade head

# users 스키마 (예정)
cd migrations/users
alembic upgrade head
```

### 전체 마이그레이션 (스크립트)

```bash
#!/bin/bash
# scripts/migrate-all.sh

set -e

DOMAINS=("character" "users" "auth")

for domain in "${DOMAINS[@]}"; do
    if [ -d "migrations/$domain" ]; then
        echo "Migrating $domain..."
        cd migrations/$domain
        alembic upgrade head
        cd ../..
    fi
done
```

## CI/CD 통합

```yaml
# .github/workflows/migrate.yml
name: Database Migrations

on:
  push:
    paths:
      - 'migrations/**'

jobs:
  migrate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run migrations
        run: |
          for dir in migrations/*/; do
            if [ -f "$dir/alembic.ini" ]; then
              echo "Migrating $(basename $dir)..."
              cd $dir
              alembic upgrade head
              cd ../..
            fi
          done
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
```

## 새 도메인 추가

```bash
# 1. 디렉토리 생성
mkdir -p migrations/new_domain/versions

# 2. alembic.ini 복사 및 수정
cp migrations/character/alembic.ini migrations/new_domain/
# version_table_schema 변경

# 3. env.py 복사 및 수정
cp migrations/character/env.py migrations/new_domain/
# 모델 import 경로 변경

# 4. 템플릿 복사
cp migrations/character/script.py.mako migrations/new_domain/

# 5. 초기 마이그레이션 생성
cd migrations/new_domain
alembic revision --autogenerate -m "initial schema"
```

## 주의사항

1. **프로덕션 롤백**: 항상 백업 후 진행
2. **순서 의존성**: 도메인 간 FK가 있으면 순서 고려
3. **Zero-downtime**: 컬럼 추가 시 nullable → 데이터 채우기 → NOT NULL 순서
