-- ============================================================================
-- Auth 스키마 DDL (Legacy)
--
-- 상태: DEPRECATED - users 스키마로 통합 진행 중
--
-- 마이그레이션 전략 (Parallel Running):
--   Phase 1 (현재): auth + users 스키마 공존
--   Phase 2: users 스키마로 전환, auth는 읽기 전용
--   Phase 3: auth 스키마 DROP
--
-- 이 파일의 용도:
--   - 롤백 시 참조용
--   - 기존 스키마 문서화
--   - 마이그레이션 검증용
--
-- 타입 규칙 (Unbounded String 기본 전략):
--   - TEXT: 기본 문자열 타입
--   - VARCHAR: 표준 규격이 명확한 경우만 사용
--       - phone_number: VARCHAR(20) - E.164 표준
-- ============================================================================

-- ============================================
-- 스키마 생성
-- ============================================
CREATE SCHEMA IF NOT EXISTS auth;

-- 타임존 설정 (KST)
SET timezone = 'Asia/Seoul';

-- ============================================
-- auth.users 테이블
-- Note: users 스키마 통합 후 deprecated 예정
-- ============================================
CREATE TABLE auth.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT,
    nickname TEXT,
    profile_image_url TEXT,
    phone_number VARCHAR(20),               -- E.164
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ,

    CONSTRAINT uq_auth_users_name_phone UNIQUE (username, phone_number)
);

CREATE INDEX idx_auth_users_phone ON auth.users(phone_number)
    WHERE phone_number IS NOT NULL;  -- 전화번호 검색 (Partial Index)

-- ============================================
-- auth.user_social_accounts 테이블
-- Note: users 스키마 통합 후 deprecated 예정
-- ============================================
CREATE TABLE auth.user_social_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    provider TEXT NOT NULL,
    provider_user_id TEXT NOT NULL,
    email VARCHAR(320),                     -- RFC 5321
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_auth_social_user
        FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE,
    CONSTRAINT uq_user_social_accounts_identity
        UNIQUE (provider, provider_user_id)
);

CREATE INDEX idx_auth_social_user_id ON auth.user_social_accounts(user_id);
    -- 이유: 사용자별 연동 계정 조회
CREATE INDEX idx_auth_social_provider ON auth.user_social_accounts(provider);
    -- 이유: OAuth 제공자별 통계
CREATE INDEX idx_auth_social_provider_user ON auth.user_social_accounts(provider_user_id);
    -- 이유: OAuth 로그인 시 기존 계정 조회

-- ============================================
-- auth.login_audits 테이블
-- 로그인 이력 기록 (감사 목적)
-- ============================================
CREATE TABLE auth.login_audits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    provider TEXT NOT NULL,
    jti TEXT NOT NULL,                      -- JWT ID
    login_ip TEXT,
    user_agent TEXT,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_audit_user
        FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE
);

CREATE INDEX idx_login_audits_user_id ON auth.login_audits(user_id);
    -- 이유: 사용자별 로그인 이력 조회
CREATE INDEX idx_login_audits_jti ON auth.login_audits(jti);
    -- 이유: JWT ID로 토큰 추적 (블랙리스트 확인)
CREATE INDEX idx_login_audits_issued_at ON auth.login_audits(issued_at);
    -- 이유: 시간순 로그인 이력 조회 (감사)
