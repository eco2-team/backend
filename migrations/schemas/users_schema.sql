-- ============================================================================
-- Users 스키마 DDL (Target)
--
-- 상태: 신규 통합 스키마 (마이그레이션 대상)
--
-- 마이그레이션 전략 (Parallel Running):
--   Phase 1 (현재): auth + users 스키마 공존, 데이터 복제
--   Phase 2: users 스키마가 주 스키마로 전환
--   Phase 3: auth 스키마 DROP, users만 유지
--
-- 통합 내용:
--   - auth.users + user_profile.users → users.accounts
--   - auth.user_social_accounts → users.social_accounts
--   - user_profile.user_characters → users.user_characters
--
-- 타입 규칙 (Unbounded String 기본 전략):
--   - TEXT: 기본 문자열 타입 (PostgreSQL에서 VARCHAR와 성능 동일)
--   - VARCHAR: 표준 규격이 명확한 경우만 사용
--       - email: VARCHAR(320) - RFC 5321 표준
--       - phone_number: VARCHAR(20) - E.164 표준
--   - ENUM: 고정 값 집합
--       - oauth_provider: google, kakao, naver
--       - user_character_status: owned, burned, traded
-- ============================================================================

-- ============================================
-- 스키마 및 ENUM 타입 생성
-- ============================================
CREATE SCHEMA IF NOT EXISTS users;

-- 타임존 설정 (KST)
SET timezone = 'Asia/Seoul';

-- ENUM 타입 정의
CREATE TYPE oauth_provider AS ENUM ('google', 'kakao', 'naver');
CREATE TYPE user_character_status AS ENUM ('owned', 'burned', 'traded');

-- ============================================
-- users.accounts 테이블 (통합)
-- 사용자 기본 정보
-- ============================================
CREATE TABLE users.accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nickname TEXT,
    name TEXT,
    email VARCHAR(320),                     -- RFC 5321
    phone_number VARCHAR(20),               -- E.164
    profile_image_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ,

    CONSTRAINT uq_accounts_phone UNIQUE (phone_number)
);

-- Partial indexes (NULL 제외로 인덱스 크기 최적화)
CREATE INDEX idx_accounts_nickname ON users.accounts(nickname)
    WHERE nickname IS NOT NULL;  -- 닉네임 검색
CREATE INDEX idx_accounts_phone ON users.accounts(phone_number)
    WHERE phone_number IS NOT NULL;  -- 전화번호 검색
CREATE INDEX idx_accounts_email ON users.accounts(email)
    WHERE email IS NOT NULL;  -- 이메일 검색

-- ============================================
-- users.social_accounts 테이블
-- OAuth 소셜 계정 연동 정보
-- ============================================
CREATE TABLE users.social_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    provider oauth_provider NOT NULL,       -- ENUM
    provider_user_id TEXT NOT NULL,
    email VARCHAR(320),                     -- RFC 5321
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_social_user
        FOREIGN KEY (user_id) REFERENCES users.accounts(id) ON DELETE CASCADE,
    CONSTRAINT uq_social_identity
        UNIQUE (provider, provider_user_id)
);

CREATE INDEX idx_social_user_id ON users.social_accounts(user_id);
    -- 이유: 사용자별 연동 계정 조회 (프로필 페이지)
CREATE INDEX idx_social_provider ON users.social_accounts(provider);
    -- 이유: OAuth 제공자별 통계, 관리자 대시보드
CREATE INDEX idx_social_provider_user ON users.social_accounts(provider, provider_user_id);
    -- 이유: OAuth 로그인 시 기존 계정 조회 (복합 키 커버링)

-- ============================================
-- users.user_characters 테이블
-- 사용자 보유 캐릭터 (스냅샷 패턴)
-- Note: character_id는 외부 도메인 참조로 FK 없음
-- ============================================
CREATE TABLE users.user_characters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    character_id UUID NOT NULL,             -- FK 없음 (도메인 분리)

    -- 캐릭터 스냅샷 (비정규화)
    character_code TEXT NOT NULL,
    character_name TEXT NOT NULL,
    character_type TEXT,
    character_dialog TEXT,
    source TEXT,

    status user_character_status NOT NULL DEFAULT 'owned',  -- ENUM
    acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_character_user
        FOREIGN KEY (user_id) REFERENCES users.accounts(id) ON DELETE CASCADE,
    CONSTRAINT uq_user_character
        UNIQUE (user_id, character_code)
);

CREATE INDEX idx_characters_user_id ON users.user_characters(user_id);
    -- 이유: "내 캐릭터 목록" 조회 (가장 빈번한 쿼리)
CREATE INDEX idx_characters_character_id ON users.user_characters(character_id);
    -- 이유: "이 캐릭터를 가진 사용자" 조회 (어드민, 통계)
CREATE INDEX idx_characters_code ON users.user_characters(character_code);
    -- 이유: 캐릭터 코드 기반 검색 (CSV 연동)
