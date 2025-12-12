# MQ Migration & Database Separation Plan (CQRS)

## 1. 개요 (Overview)

현재 Eco2 프로젝트는 도메인별로 코드가 분리된 MSA 구조를 지향하고 있으나, 데이터베이스 레벨에서는 **단일 인스턴스 내의 스키마 분리(Shared Database)** 패턴을 사용하고 있습니다. 특히 `my` 도메인이 `auth` 도메인의 테이블을 직접 참조(Read-only Mirror)하는 강한 결합이 존재하여, 진정한 의미의 서비스 독립성을 달성하기 어렵습니다.

이 문서는 **RabbitMQ 도입**과 **CQRS 패턴** 적용을 통해 데이터베이스를 물리적으로 분리하고, 서비스 간 느슨한 결합(Loose Coupling)을 달성하기 위한 마이그레이션 계획입니다.

## 2. 현재 아키텍처 분석 (AS-IS)

### 2.1 데이터베이스 구조
- **Physical**: 단일 PostgreSQL 인스턴스 (`ecoeco`)
- **Logical**: 도메인별 Schema (`auth`, `character`, `my` 등) 사용

### 2.2 의존성 문제 (`my` -> `auth`)
- **코드**: `domains/my/models/auth_user.py`
- **방식**: `__table_args__ = {"schema": "auth"}`를 통해 타 도메인의 테이블을 직접 매핑.
- **제약**: DB가 물리적으로 분리되면 `my` 서비스는 `auth.users` 테이블에 접근할 수 없어 쿼리 실패 발생.
- **다행인 점**: `character` 도메인 등은 `ForeignKey` 제약조건 없이 `UUID`로만 참조하고 있어 분리가 용이함.

---

## 3. 목표 아키텍처 (TO-BE)

### 3.1 Database per Service
각 서비스는 자신만의 독립적인 데이터 저장소를 가집니다.
- `auth-service` -> `auth_db` (Write Model, Source of Truth)
- `my-service` -> `my_db` (Read Model)
- `character-service` -> `character_db`

### 3.2 CQRS & Event Sourcing
데이터의 변경(Command)과 조회(Query)를 분리하여 처리합니다.

1.  **Command Side (`auth`)**:
    - 사용자 생성/수정/삭제 트랜잭션 처리.
    - 변경 완료 후 `UserCreated`, `UserUpdated` 이벤트 발행.
2.  **Event Bus (RabbitMQ)**:
    - 도메인 이벤트를 신뢰성 있게 전달.
    - Exchange: `domain.events` (Topic)
    - Routing Key: `auth.user.created`, `auth.user.updated`
3.  **Query Side (`my`, `character`)**:
    - 이벤트를 구독(Subscribe)하여 자신의 로컬 DB에 필요한 데이터를 복제(Replication).
    - `my` 서비스는 `auth.users`의 복제본 테이블(`my.users_view`)을 로컬에 보유.
    - 조회 요청 시 로컬 DB에서 즉시 반환 (Join 불필요, 성능 향상).

---

## 4. 마이그레이션 단계 (Phased Migration)

### Phase 1: 메시징 인프라 구축 & 이벤트 발행 (Messaging Foundation)
DB 분리 전, 메시징 시스템을 먼저 안정화합니다.

1.  **RabbitMQ 배포**:
    - `platform/helm` 또는 `terraform`을 통해 고가용성 RabbitMQ 클러스터 구축.
2.  **Publisher 구현 (`auth`)**:
    - `auth` 서비스에 RabbitMQ Publisher 연동.
    - 회원가입(`signup`), 프로필 수정(`update_profile`) 시 이벤트 발행 로직 추가.
    - **Transactional Outbox Pattern** 고려: DB 트랜잭션과 메시지 발행의 원자성 보장 (일단 단순 발행으로 시작 후 고도화).

### Phase 2: 컨슈머 구현 및 로컬 캐시 구축 (Consumer & Read Model)
`my` 서비스가 `auth` 테이블을 직접 조회하지 않도록 로직을 변경합니다.

1.  **로컬 테이블 생성 (`my`)**:
    - `my` 스키마 내에 `users_view` (또는 `cached_users`) 테이블 생성.
    - `auth.users`와 동일하거나 필요한 컬럼(id, nickname, profile_image)만 포함.
2.  **Consumer 구현 (`my`)**:
    - `UserCreated`, `UserUpdated` 이벤트를 수신하여 `users_view` 테이블 갱신 (Upsert).
3.  **초기 데이터 동기화 (Bootstrap)**:
    - 기존 `auth.users` 데이터를 `my.users_view`로 한 번 몽땅 복사하는 마이그레이션 스크립트 실행.
4.  **조회 로직 변경**:
    - `my` 서비스 코드가 `auth.models.User` 대신 로컬 `my.models.UserView`를 조회하도록 리팩토링.

### Phase 3: 데이터베이스 물리적 분리 (Physical Separation)
애플리케이션 레벨에서 의존성이 제거되었으므로, 물리적 분리를 감행합니다.

1.  **신규 DB 프로비저닝**:
    - `ecoeco_auth`, `ecoeco_my`, `ecoeco_character` 등 별도 DB 생성.
2.  **데이터 이관**:
    - `pg_dump`를 사용하여 스키마별로 데이터를 백업 및 신규 DB에 복원.
3.  **서비스 설정 변경**:
    - 각 서비스의 `DATABASE_URL`을 신규 DB 주소로 변경하여 배포.
4.  **검증**:
    - 서비스 간 통신이 API(gRPC) 또는 MQ로만 이루어지는지 확인.

---

## 5. 기술적 고려사항

### 5.1 데이터 일관성 (Eventual Consistency)
- CQRS 적용 시 `auth`에서 변경된 내용이 `my`에 반영되기까지 미세한 지연(Lag)이 발생합니다.
- UI/UX 설계 시 이를 고려해야 합니다 (예: "저장되었습니다" 후 즉시 리프레시해도 구 데이터가 보일 수 있음을 인지하거나, 클라이언트 측 낙관적 업데이트 활용).

### 5.2 장애 격리 및 재처리 (DLQ)
- 메시지 처리 실패 시 재시도(Retry) 정책 수립.
- 최종 실패 메시지는 **Dead Letter Queue (DLQ)**로 보내어 추후 수동/자동 복구 가능하도록 설계.

### 5.3 스키마 관리
- 각 마이크로서비스는 자신의 DB 스키마 변경을 스스로 관리(Alembic 등)하며, 타 서비스의 스키마 변경에 영향받지 않아야 합니다.

## 6. Action Items
- [ ] RabbitMQ Helm Chart 배포 및 `clusters/dev` 등록.
- [ ] `domains/_shared` 라이브러리에 RabbitMQ Publisher/Consumer 공통 모듈 구현.
- [ ] `auth` 도메인에 이벤트 발행 로직 추가.
- [ ] `my` 도메인에 `Read Model` 테이블 설계 및 Consumer 구현.
