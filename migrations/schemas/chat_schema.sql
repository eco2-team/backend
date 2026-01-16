-- ============================================================================
-- Chat 스키마 DDL
--
-- 목적: 채팅 세션 및 메시지 영속화
--
-- 테이블:
--   - chat.conversations: 대화 세션 (사이드바 목록)
--   - chat.messages: 메시지 히스토리
--
-- API 매핑:
--   GET    /chat                    → chat.conversations 목록
--   POST   /chat                    → chat.conversations 생성
--   GET    /chat/{id}               → chat.conversations + messages JOIN
--   DELETE /chat/{id}               → is_deleted = TRUE
--   POST   /chat/{id}/messages      → chat.messages 생성
--
-- 타입 규칙:
--   - TEXT: 기본 문자열 (content, title, preview, role)
--   - CHECK: role (값 집합 고정, 확장 용이)
--   - JSONB: metadata (유연한 확장)
--
-- 참조:
--   - Open WebUI API 패턴
--   - Crunchy Data: TEXT + CHECK > ENUM (확장성)
-- ============================================================================

-- ============================================
-- 스키마 생성
-- ============================================
CREATE SCHEMA IF NOT EXISTS chat;

-- 타임존 설정 (KST)
SET timezone = 'Asia/Seoul';

-- ============================================
-- chat.conversations 테이블
-- 대화 세션 (사이드바에 표시되는 대화 목록)
-- ============================================
CREATE TABLE chat.conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,

    -- 메타데이터
    title TEXT,                                 -- 자동 생성 또는 NULL
    preview TEXT,                               -- 마지막 메시지 요약
    message_count INT NOT NULL DEFAULT 0,
    last_message_at TIMESTAMPTZ,

    -- Soft delete
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT fk_conversations_user
        FOREIGN KEY (user_id) REFERENCES users.accounts(id) ON DELETE CASCADE,
    CONSTRAINT chk_message_count CHECK (message_count >= 0)
);

-- 사이드바 목록 조회: 최근 대화순 (삭제되지 않은 것만)
CREATE INDEX idx_conversations_user_recent
    ON chat.conversations(user_id, last_message_at DESC)
    WHERE is_deleted = FALSE;

-- ============================================
-- chat.messages 테이블
-- 메시지 히스토리
-- ============================================
CREATE TABLE chat.messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID NOT NULL,

    -- 메시지 내용
    role TEXT NOT NULL,                         -- 'user' | 'assistant' (확장: 'system', 'tool')
    content TEXT NOT NULL,

    -- AI 응답 메타데이터 (assistant만)
    intent TEXT,                                -- 분류된 intent
    metadata JSONB,                             -- node_results, citations 등

    -- 비동기 작업 추적
    job_id UUID,                                -- Worker job_id (nullable)

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT fk_messages_conversation
        FOREIGN KEY (chat_id) REFERENCES chat.conversations(id) ON DELETE CASCADE,
    CONSTRAINT chk_role CHECK (role IN ('user', 'assistant'))
);

-- 메시지 히스토리 조회: 시간순
CREATE INDEX idx_messages_chat_ts
    ON chat.messages(chat_id, created_at ASC);

-- job_id로 메시지 조회 (SSE 완료 후 업데이트용)
CREATE INDEX idx_messages_job
    ON chat.messages(job_id)
    WHERE job_id IS NOT NULL;

-- ============================================
-- Comments
-- ============================================
COMMENT ON TABLE chat.conversations IS '대화 세션 - 사이드바에 표시되는 대화 목록';
COMMENT ON TABLE chat.messages IS '메시지 히스토리 - 각 대화의 메시지들';

COMMENT ON COLUMN chat.conversations.preview IS '마지막 메시지 요약 (사이드바 미리보기)';
COMMENT ON COLUMN chat.conversations.is_deleted IS 'Soft delete 플래그';
COMMENT ON COLUMN chat.messages.role IS '메시지 역할: user, assistant (향후 system, tool 확장 가능)';
COMMENT ON COLUMN chat.messages.intent IS 'AI가 분류한 intent (assistant 메시지만)';
COMMENT ON COLUMN chat.messages.metadata IS 'node_results, citations 등 확장 데이터';
COMMENT ON COLUMN chat.messages.job_id IS '비동기 Worker job_id (응답 추적용)';
