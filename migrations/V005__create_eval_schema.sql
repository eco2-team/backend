-- ============================================================================
-- V005: Eval Pipeline 테이블 생성 (chat 스키마)
--
-- 목표:
--   - chat.eval_results: 응답 품질 평가 결과 영구 저장 (L3 Cold Storage)
--   - chat.calibration_drift_log: CUSUM Calibration Drift 탐지 로그
--
-- 타입 규칙:
--   - JSONB: axis_scores, metadata (비정규화, 축별 유연 확장)
--   - NUMERIC(5,2): 0-100 연속 점수
--   - NUMERIC(10,6): 비용 (USD, 소수점 6자리)
--   - VARCHAR(10): 등급 (S/A/B/C)
--   - VARCHAR(20): eval_mode (sync/async/shadow)
--   - TIMESTAMPTZ: 시간대 포함 타임스탬프 (KST)
--
-- 참조:
--   - docs/plans/chat-eval-pipeline-plan.md §5.1
--   - 기존: chat.conversations, chat.messages (V002)
-- ============================================================================

-- chat 스키마는 V002에서 이미 생성됨
-- CREATE SCHEMA IF NOT EXISTS chat;

SET timezone = 'Asia/Seoul';

-- ============================================
-- Step 1: chat.eval_results 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS chat.eval_results (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id          UUID NOT NULL,
    intent          VARCHAR(50) NOT NULL DEFAULT '',
    grade           VARCHAR(10) NOT NULL,
    continuous_score NUMERIC(5,2) NOT NULL,
    axis_scores     JSONB NOT NULL DEFAULT '{}',
    eval_mode       VARCHAR(20) NOT NULL DEFAULT 'async',
    model_version   VARCHAR(100) NOT NULL DEFAULT 'unknown',
    prompt_version  VARCHAR(100) NOT NULL DEFAULT 'unknown',
    eval_duration_ms INTEGER NOT NULL DEFAULT 0,
    eval_cost_usd   NUMERIC(10,6),
    calibration_status VARCHAR(20),
    code_grader_result JSONB,
    llm_grader_result  JSONB,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE chat.eval_results IS '응답 품질 평가 결과 (Swiss Cheese 3-Tier)';
COMMENT ON COLUMN chat.eval_results.job_id IS 'Chat 처리 작업 ID (ProcessChatCommand)';
COMMENT ON COLUMN chat.eval_results.grade IS '등급 (S/A/B/C)';
COMMENT ON COLUMN chat.eval_results.continuous_score IS '0-100 연속 점수 (비대칭 가중 합산)';
COMMENT ON COLUMN chat.eval_results.axis_scores IS 'BARS 5-Axis 축별 점수 (JSONB)';
COMMENT ON COLUMN chat.eval_results.eval_mode IS '실행 모드 (sync/async/shadow)';
COMMENT ON COLUMN chat.eval_results.calibration_status IS 'CUSUM Calibration 상태 (STABLE/DRIFTING/RECALIBRATING)';

-- ============================================
-- Step 2: 인덱스 (eval_results)
-- ============================================

-- Intent + 생성일 기반 조회 (Calibration coverage, 트래픽 분포 분석)
CREATE INDEX IF NOT EXISTS idx_eval_results_intent_created
    ON chat.eval_results (intent, created_at DESC);

-- 등급 기반 필터 (C등급 재생성 추적, 등급 분포 분석)
CREATE INDEX IF NOT EXISTS idx_eval_results_grade
    ON chat.eval_results (grade);

-- Job ID 기반 조회 (특정 작업의 평가 결과 확인)
CREATE INDEX IF NOT EXISTS idx_eval_results_job
    ON chat.eval_results (job_id);

-- ============================================
-- Step 3: chat.calibration_drift_log 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS chat.calibration_drift_log (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    axis            VARCHAR(50) NOT NULL,
    severity        VARCHAR(20) NOT NULL,
    cusum_positive  NUMERIC(8,4) NOT NULL DEFAULT 0.0,
    cusum_negative  NUMERIC(8,4) NOT NULL DEFAULT 0.0,
    sample_count    INTEGER NOT NULL DEFAULT 0,
    action_taken    VARCHAR(50),
    calibration_version VARCHAR(100),
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE chat.calibration_drift_log IS 'CUSUM Calibration Drift 탐지 로그';
COMMENT ON COLUMN chat.calibration_drift_log.axis IS '평가 축 (faithfulness, relevance, ...)';
COMMENT ON COLUMN chat.calibration_drift_log.severity IS '심각도 (OK/WARNING/CRITICAL)';
COMMENT ON COLUMN chat.calibration_drift_log.cusum_positive IS 'CUSUM 양방향 누적합 (상향 drift)';
COMMENT ON COLUMN chat.calibration_drift_log.cusum_negative IS 'CUSUM 음방향 누적합 (하향 drift)';
COMMENT ON COLUMN chat.calibration_drift_log.action_taken IS '취해진 조치 (예: recalibrate, notify)';

-- Axis + 생성일 기반 조회 (축별 drift 이력)
CREATE INDEX IF NOT EXISTS idx_calibration_drift_log_axis_created
    ON chat.calibration_drift_log (axis, created_at DESC);
