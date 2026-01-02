-- ============================================================================
-- V003: users 스키마 생성 및 데이터 통합
--
-- 목표:
--   - auth.users + user_profile.users → users.accounts (통합)
--   - auth.user_social_accounts → users.social_accounts (이동)
--   - user_profile.user_characters → users.user_characters (이동)
--
-- Note:
--   - username 컬럼 제거 (OAuth 전용이므로 불필요)
--
-- 실행 전 백업 필수!
-- ============================================================================

-- ============================================
-- Step 1: 새 스키마 생성
-- ============================================
CREATE SCHEMA IF NOT EXISTS users;

-- ============================================
-- Step 2: users.accounts 테이블 생성 (통합)
-- ============================================
CREATE TABLE users.accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nickname VARCHAR(120),
    name VARCHAR(120),
    email VARCHAR(320),
    phone_number VARCHAR(32),
    profile_image_url VARCHAR(512),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ,

    CONSTRAINT uq_accounts_phone UNIQUE (phone_number)
);

-- Partial indexes (NULL 제외)
CREATE INDEX idx_accounts_nickname ON users.accounts(nickname) WHERE nickname IS NOT NULL;
CREATE INDEX idx_accounts_phone ON users.accounts(phone_number) WHERE phone_number IS NOT NULL;
CREATE INDEX idx_accounts_email ON users.accounts(email) WHERE email IS NOT NULL;

-- ============================================
-- Step 3: users.social_accounts 테이블 생성
-- ============================================
CREATE TABLE users.social_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    provider VARCHAR(32) NOT NULL,
    provider_user_id VARCHAR(255) NOT NULL,
    email VARCHAR(320),
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_social_user
        FOREIGN KEY (user_id) REFERENCES users.accounts(id) ON DELETE CASCADE,
    CONSTRAINT uq_social_identity
        UNIQUE (provider, provider_user_id)
);

CREATE INDEX idx_social_user_id ON users.social_accounts(user_id);
CREATE INDEX idx_social_provider ON users.social_accounts(provider);
CREATE INDEX idx_social_provider_user ON users.social_accounts(provider, provider_user_id);

-- ============================================
-- Step 4: users.user_characters 테이블 생성
-- ============================================
CREATE TABLE users.user_characters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    character_id UUID NOT NULL,
    character_code VARCHAR(64) NOT NULL,
    character_name VARCHAR(120) NOT NULL,
    character_type VARCHAR(64),
    character_dialog VARCHAR(500),
    source VARCHAR(120),
    status VARCHAR(20) NOT NULL DEFAULT 'owned',
    acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_character_user
        FOREIGN KEY (user_id) REFERENCES users.accounts(id) ON DELETE CASCADE,
    CONSTRAINT uq_user_character
        UNIQUE (user_id, character_code),
    CONSTRAINT chk_status
        CHECK (status IN ('owned', 'burned'))
);

CREATE INDEX idx_characters_user_id ON users.user_characters(user_id);
CREATE INDEX idx_characters_character_id ON users.user_characters(character_id);
CREATE INDEX idx_characters_code ON users.user_characters(character_code);

-- ============================================
-- Step 5: 데이터 마이그레이션 (auth → users)
-- ============================================

-- 5.1: auth.users → users.accounts (기본 데이터)
-- Note: username 컬럼은 마이그레이션하지 않음 (nickname으로 대체)
INSERT INTO users.accounts (
    id,
    nickname,
    name,
    email,
    phone_number,
    profile_image_url,
    created_at,
    updated_at,
    last_login_at
)
SELECT
    au.id,
    COALESCE(au.nickname, up.nickname) AS nickname,
    COALESCE(up.name, NULL) AS name,
    COALESCE(up.email, NULL) AS email,
    au.phone_number,
    au.profile_image_url,
    au.created_at,
    au.updated_at,
    au.last_login_at
FROM auth.users au
LEFT JOIN user_profile.users up ON au.id = up.auth_user_id
ON CONFLICT (id) DO NOTHING;

-- 5.2: auth.user_social_accounts → users.social_accounts
INSERT INTO users.social_accounts (
    id,
    user_id,
    provider,
    provider_user_id,
    email,
    last_login_at,
    created_at,
    updated_at
)
SELECT
    id,
    user_id,
    provider,
    provider_user_id,
    email,
    last_login_at,
    created_at,
    updated_at
FROM auth.user_social_accounts
ON CONFLICT (provider, provider_user_id) DO NOTHING;

-- 5.3: user_profile.user_characters → users.user_characters
INSERT INTO users.user_characters (
    id,
    user_id,
    character_id,
    character_code,
    character_name,
    character_type,
    character_dialog,
    source,
    status,
    acquired_at,
    updated_at
)
SELECT
    id,
    user_id,
    character_id,
    character_code,
    character_name,
    character_type,
    character_dialog,
    source,
    status,
    acquired_at,
    updated_at
FROM user_profile.user_characters
ON CONFLICT (user_id, character_code) DO NOTHING;

-- ============================================
-- Step 6: 검증 쿼리 (실행 후 확인용)
-- ============================================
-- SELECT 'users.accounts' AS table_name, COUNT(*) FROM users.accounts
-- UNION ALL
-- SELECT 'users.social_accounts', COUNT(*) FROM users.social_accounts
-- UNION ALL
-- SELECT 'users.user_characters', COUNT(*) FROM users.user_characters
-- UNION ALL
-- SELECT 'auth.users (원본)', COUNT(*) FROM auth.users
-- UNION ALL
-- SELECT 'auth.user_social_accounts (원본)', COUNT(*) FROM auth.user_social_accounts
-- UNION ALL
-- SELECT 'user_profile.user_characters (원본)', COUNT(*) FROM user_profile.user_characters;

-- ============================================
-- Step 7: 이전 테이블 삭제 (검증 완료 후 별도 실행)
-- ============================================
-- ⚠️ 검증 완료 후 별도 마이그레이션으로 실행:
-- DROP TABLE user_profile.users;
-- DROP TABLE user_profile.user_characters;
-- DROP SCHEMA user_profile;
-- DROP TABLE auth.user_social_accounts;
-- ALTER TABLE auth.users ... (인증 관련 필드만 남기거나 삭제)
