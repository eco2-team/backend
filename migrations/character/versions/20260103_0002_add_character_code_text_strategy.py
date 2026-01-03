"""Add character_code to character_ownerships, change unique constraint, and apply TEXT strategy.

Revision ID: 20260103_character_code
Revises: (이전 revision)
Create Date: 2026-01-03

변경 사항:
1. 멱등성 판단 기준: (user_id, character_id) → (user_id, character_code)
   - users.user_characters와 동일한 기준 사용

2. String 타입 전략 (PostgreSQL TEXT 기본):
   - characters.name: VARCHAR(120) → TEXT
   - characters.type_label: VARCHAR(120) → TEXT
   - characters.match_label: VARCHAR(120) → TEXT
   - character_ownerships.source: VARCHAR(120) → TEXT

Ref: https://rooftopsnow.tistory.com/132
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "0002"
down_revision: str | None = "0001"  # initial_character_schema
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """character_code 컬럼 추가, UNIQUE 제약 변경, TEXT 전략 적용.

    Note: 이미 적용된 환경에서는 조건부로 스킵됩니다.
    """
    from sqlalchemy import inspect
    from alembic import op

    bind = op.get_bind()
    inspector = inspect(bind)

    # ===========================================
    # Part 1: character_code 기준 멱등성 변경
    # ===========================================

    # character_code 컬럼이 이미 존재하는지 확인
    columns = [col["name"] for col in inspector.get_columns("character_ownerships", schema="character")]
    has_character_code = "character_code" in columns

    if not has_character_code:
        # 1. character_code 컬럼 추가
        op.add_column(
            "character_ownerships",
            sa.Column("character_code", sa.String(64), nullable=True),
            schema="character",
        )

        # 2. 기존 데이터 마이그레이션: character.characters에서 code 복사
        op.execute("""
            UPDATE character.character_ownerships co
            SET character_code = c.code
            FROM character.characters c
            WHERE co.character_id = c.id
        """)

        # 3. NOT NULL 제약 추가
        op.alter_column(
            "character_ownerships",
            "character_code",
            nullable=False,
            schema="character",
        )

    # 기존 UNIQUE 제약 확인 및 변경
    constraints = inspector.get_unique_constraints("character_ownerships", schema="character")
    constraint_names = [c["name"] for c in constraints]

    if "uq_character_ownership_user_character" in constraint_names:
        # 4. 기존 UNIQUE 제약 삭제
        op.drop_constraint(
            "uq_character_ownership_user_character",
            "character_ownerships",
            schema="character",
            type_="unique",
        )

    if "uq_character_ownership_user_code" not in constraint_names:
        # 5. 새 UNIQUE 제약 추가 (user_id, character_code)
        op.create_unique_constraint(
            "uq_character_ownership_user_code",
            "character_ownerships",
            ["user_id", "character_code"],
            schema="character",
        )

    # 인덱스 확인 및 추가
    indexes = inspector.get_indexes("character_ownerships", schema="character")
    index_names = [idx["name"] for idx in indexes]

    if "ix_character_ownerships_character_code" not in index_names:
        # 6. character_code 인덱스 추가
        op.create_index(
            "ix_character_ownerships_character_code",
            "character_ownerships",
            ["character_code"],
            schema="character",
        )

    # ===========================================
    # Part 2: TEXT 기본 전략 적용
    # PostgreSQL에서 VARCHAR(n) → TEXT는 성능 동일
    # ===========================================

    # characters 테이블: VARCHAR → TEXT (항상 안전하게 적용 가능)
    op.alter_column(
        "characters",
        "name",
        type_=sa.Text(),
        existing_type=sa.String(120),
        schema="character",
    )
    op.alter_column(
        "characters",
        "type_label",
        type_=sa.Text(),
        existing_type=sa.String(120),
        schema="character",
    )
    op.alter_column(
        "characters",
        "match_label",
        type_=sa.Text(),
        existing_type=sa.String(120),
        schema="character",
    )

    # character_ownerships 테이블: source VARCHAR → TEXT
    op.alter_column(
        "character_ownerships",
        "source",
        type_=sa.Text(),
        existing_type=sa.String(120),
        schema="character",
    )


def downgrade() -> None:
    """롤백: 원래 상태로 복원."""

    # ===========================================
    # Part 2 롤백: TEXT → VARCHAR
    # ===========================================

    op.alter_column(
        "character_ownerships",
        "source",
        type_=sa.String(120),
        existing_type=sa.Text(),
        schema="character",
    )
    op.alter_column(
        "characters",
        "match_label",
        type_=sa.String(120),
        existing_type=sa.Text(),
        schema="character",
    )
    op.alter_column(
        "characters",
        "type_label",
        type_=sa.String(120),
        existing_type=sa.Text(),
        schema="character",
    )
    op.alter_column(
        "characters",
        "name",
        type_=sa.String(120),
        existing_type=sa.Text(),
        schema="character",
    )

    # ===========================================
    # Part 1 롤백: character_code 제거
    # ===========================================

    # 1. 인덱스 삭제
    op.drop_index(
        "ix_character_ownerships_character_code",
        "character_ownerships",
        schema="character",
    )

    # 2. 새 UNIQUE 제약 삭제
    op.drop_constraint(
        "uq_character_ownership_user_code",
        "character_ownerships",
        schema="character",
        type_="unique",
    )

    # 3. 기존 UNIQUE 제약 복원
    op.create_unique_constraint(
        "uq_character_ownership_user_character",
        "character_ownerships",
        ["user_id", "character_id"],
        schema="character",
    )

    # 4. character_code 컬럼 삭제
    op.drop_column("character_ownerships", "character_code", schema="character")
