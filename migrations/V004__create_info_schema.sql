-- ============================================================================
-- V004: info 스키마 생성 (뉴스 기사 영구 저장)
--
-- 목표:
--   - news_articles 테이블 생성 (3-Tier Architecture의 Source of Truth)
--   - Cursor-based Pagination 지원 인덱스
--   - URL 기반 중복 제거 (UPSERT 지원)
--
-- 타입 규칙:
--   - TEXT: 기본 문자열 타입 (가변 길이)
--   - VARCHAR: 제한된 값 (source, category 등)
--   - TEXT[]: 키워드 배열
--   - TIMESTAMPTZ: 시간대 포함 타임스탬프 (KST)
--
-- 참조:
--   - ADR: docs/plans/info-3tier-architecture-adr.md
-- ============================================================================

-- ============================================
-- Step 1: 스키마 생성
-- ============================================
CREATE SCHEMA IF NOT EXISTS info;

-- 타임존 설정 (KST)
SET timezone = 'Asia/Seoul';

-- ============================================
-- Step 2: news_articles 테이블 생성
-- ============================================
CREATE TABLE info.news_articles (
    -- PK: URL 기반 해시 (중복 제거)
    -- 형식: {source}_{external_id} (예: naver_123456)
    id              VARCHAR(64) PRIMARY KEY,

    -- 기본 정보
    url             TEXT NOT NULL,
    title           TEXT NOT NULL,
    snippet         TEXT NOT NULL,

    -- 소스 정보
    source          VARCHAR(32) NOT NULL,       -- 'naver', 'newsdata'
    source_name     VARCHAR(128) NOT NULL,      -- 언론사 이름
    source_icon_url TEXT,                       -- 언론사 아이콘 URL

    -- 미디어
    thumbnail_url   TEXT,                       -- 썸네일 이미지 URL
    video_url       TEXT,                       -- 동영상 URL (NewsData)

    -- 분류
    category        VARCHAR(32) NOT NULL,       -- 'environment', 'energy', 'ai', 'all'
    keywords        TEXT[],                     -- 관련 키워드 배열
    ai_tag          VARCHAR(64),                -- AI 기반 세부 태그 (NewsData)

    -- 시간
    published_at    TIMESTAMPTZ NOT NULL,       -- 기사 게시 시간
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Soft Delete
    is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,

    -- Constraints
    CONSTRAINT uq_news_articles_url UNIQUE (url)
);

-- ============================================
-- Step 3: 인덱스 생성
-- ============================================

-- 3.1: Cursor-based Pagination (핵심 인덱스)
-- 쿼리: WHERE category = $1 AND (published_at, id) < ($2, $3) ORDER BY ... DESC
-- 복합 인덱스로 Seek Method 최적화
CREATE INDEX idx_news_articles_cursor
    ON info.news_articles (category, published_at DESC, id DESC)
    WHERE is_deleted = FALSE;

-- 3.2: 소스별 조회
-- 쿼리: WHERE source = $1 ORDER BY published_at DESC
CREATE INDEX idx_news_articles_source
    ON info.news_articles (source, published_at DESC)
    WHERE is_deleted = FALSE;

-- 3.3: 최근 기사 조회 (캐시 워밍용)
-- 쿼리: SELECT ... ORDER BY published_at DESC LIMIT N
CREATE INDEX idx_news_articles_recent
    ON info.news_articles (published_at DESC)
    WHERE is_deleted = FALSE;

-- 3.4: URL 유니크 체크 (UPSERT용)
-- 이미 UNIQUE constraint가 있어 별도 인덱스 불필요
-- uq_news_articles_url이 암묵적 인덱스 역할

-- ============================================
-- Step 4: 트리거 함수 (updated_at 자동 갱신)
-- ============================================
CREATE OR REPLACE FUNCTION info.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_news_articles_updated_at
    BEFORE UPDATE ON info.news_articles
    FOR EACH ROW
    EXECUTE FUNCTION info.update_updated_at_column();

-- ============================================
-- Step 5: 코멘트 (문서화)
-- ============================================
COMMENT ON TABLE info.news_articles IS '뉴스 기사 영구 저장 테이블 (3-Tier Architecture Source of Truth)';
COMMENT ON COLUMN info.news_articles.id IS 'PK: {source}_{external_id} 형식';
COMMENT ON COLUMN info.news_articles.category IS '카테고리: environment, energy, ai, all';
COMMENT ON COLUMN info.news_articles.source IS '뉴스 소스: naver, newsdata';
COMMENT ON INDEX info.idx_news_articles_cursor IS 'Cursor-based Pagination용 복합 인덱스';
