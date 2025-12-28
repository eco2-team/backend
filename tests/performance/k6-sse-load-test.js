/**
 * k6 SSE Load Test - VU 50 부하테스트
 *
 * 테스트 시나리오:
 * 1. POST /api/v1/scan - 스캔 요청
 * 2. Polling으로 결과 대기 (done까지)
 * 3. 최종 결과 확인
 *
 * Usage:
 *   # VU 50으로 2분간 테스트
 *   k6 run --env TOKEN="eyJ..." tests/performance/k6-sse-load-test.js
 *
 *   # VU 수 조정
 *   k6 run --env TOKEN="eyJ..." --env VUS=100 tests/performance/k6-sse-load-test.js
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Trend, Rate, Gauge } from 'k6/metrics';

// ============================================================================
// Configuration
// ============================================================================

const BASE_URL = __ENV.BASE_URL || 'https://api.dev.growbin.app';
const TOKEN = __ENV.TOKEN;
const IMAGE_URL = __ENV.IMAGE_URL || 'https://images.dev.growbin.app/scan/e09725344fc2418a88f293b0f20db173.png';
const TARGET_VUS = parseInt(__ENV.VUS) || 50;
const TEST_DURATION = __ENV.DURATION || '2m';

// ============================================================================
// Metrics
// ============================================================================

// Counters
const scanRequests = new Counter('scan_requests_total');
const scanSuccess = new Counter('scan_success_total');
const scanFailed = new Counter('scan_failed_total');
const pollRequests = new Counter('poll_requests_total');
const completedJobs = new Counter('completed_jobs_total');
const rewardsReceived = new Counter('rewards_received_total');

// Trends (latency)
const scanLatency = new Trend('scan_latency_ms');
const pollLatency = new Trend('poll_latency_ms');
const timeToComplete = new Trend('time_to_complete_ms');
const e2eLatency = new Trend('e2e_latency_ms');

// Rates
const scanSuccessRate = new Rate('scan_success_rate');
const completionRate = new Rate('completion_rate');
const rewardRate = new Rate('reward_rate');

// Gauges
const activeJobs = new Gauge('active_jobs');

// Stage counters
const stageVision = new Counter('stage_vision_count');
const stageRule = new Counter('stage_rule_count');
const stageAnswer = new Counter('stage_answer_count');
const stageReward = new Counter('stage_reward_count');
const stageDone = new Counter('stage_done_count');

// ============================================================================
// Test Options
// ============================================================================

export const options = {
  scenarios: {
    // VU 50 부하테스트
    load_test: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: TARGET_VUS },     // 30초간 target VU까지 증가
        { duration: TEST_DURATION, target: TARGET_VUS }, // 지정 시간동안 유지
        { duration: '30s', target: 0 },              // 30초간 종료
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    'scan_success_rate': ['rate>0.90'],           // 스캔 성공률 90% 이상
    'completion_rate': ['rate>0.85'],             // 완료율 85% 이상
    'scan_latency_ms': ['p(95)<5000'],            // 95% 스캔 5초 이내
    'time_to_complete_ms': ['p(95)<60000'],       // 95% 완료 60초 이내
    'e2e_latency_ms': ['p(95)<90000'],            // 95% E2E 90초 이내
  },
  // 태그 추가
  tags: {
    test_type: 'load_test',
    target_vus: String(TARGET_VUS),
  },
};

// ============================================================================
// Helper Functions
// ============================================================================

function getHeaders() {
  return {
    'Authorization': `Bearer ${TOKEN}`,
    'Content-Type': 'application/json',
  };
}

function generateIdempotencyKey() {
  return `k6-load-${__VU}-${Date.now()}-${Math.random().toString(36).substring(2, 10)}`;
}

/**
 * 결과 polling으로 완료 대기
 */
function waitForCompletion(jobId, startTime) {
  const maxAttempts = 30; // 최대 75초 (2.5초 * 30)
  const pollInterval = 2.5;

  let result = null;
  let completed = false;

  for (let i = 0; i < maxAttempts; i++) {
    const pollStart = Date.now();
    const res = http.get(
      `${BASE_URL}/api/v1/scan/result/${jobId}`,
      { headers: getHeaders(), timeout: '10s' }
    );
    pollLatency.add(Date.now() - pollStart);
    pollRequests.add(1);

    if (res.status === 200) {
      try {
        const data = JSON.parse(res.body);
        if (data.status === 'completed') {
          completed = true;
          result = data;

          // 스테이지 카운트
          stageVision.add(1);
          stageRule.add(1);
          stageAnswer.add(1);
          if (data.reward && data.reward.name) {
            stageReward.add(1);
            rewardsReceived.add(1);
          }
          stageDone.add(1);

          break;
        } else if (data.status === 'failed') {
          console.error(`[VU ${__VU}] Job failed: ${jobId}`);
          break;
        }
      } catch (e) {
        // JSON 파싱 실패
      }
    } else if (res.status === 404) {
      // 아직 처리 시작 안됨 - 계속 대기
    }

    sleep(pollInterval);
  }

  const elapsedMs = Date.now() - startTime;
  return {
    completed,
    result,
    elapsedMs,
    hasReward: result?.reward?.name ? true : false,
  };
}

// ============================================================================
// Main Test
// ============================================================================

export default function () {
  const iterStart = Date.now();

  // -------------------------------------------------------------------------
  // Step 1: POST /api/v1/scan
  // -------------------------------------------------------------------------
  const scanStart = Date.now();
  scanRequests.add(1);

  const scanRes = http.post(
    `${BASE_URL}/api/v1/scan`,
    JSON.stringify({ image_url: IMAGE_URL }),
    {
      headers: {
        ...getHeaders(),
        'X-Idempotency-Key': generateIdempotencyKey(),
      },
      timeout: '30s',
    }
  );

  const scanElapsed = Date.now() - scanStart;
  scanLatency.add(scanElapsed);

  const scanOk = check(scanRes, {
    'scan: status 200/202': (r) => r.status === 200 || r.status === 202,
    'scan: has job_id': (r) => {
      try {
        return JSON.parse(r.body).job_id !== undefined;
      } catch (e) {
        return false;
      }
    },
  });

  scanSuccessRate.add(scanOk);

  if (!scanOk) {
    scanFailed.add(1);
    console.error(`[VU ${__VU}] Scan failed: ${scanRes.status} - ${scanRes.body?.substring(0, 200)}`);
    completionRate.add(false);
    sleep(2);
    return;
  }

  scanSuccess.add(1);
  const scanData = JSON.parse(scanRes.body);
  const jobId = scanData.job_id;

  // Active jobs 추적
  activeJobs.add(1);

  // -------------------------------------------------------------------------
  // Step 2: 완료 대기 (Polling)
  // -------------------------------------------------------------------------
  const completionStart = Date.now();
  const completionResult = waitForCompletion(jobId, completionStart);

  timeToComplete.add(completionResult.elapsedMs);
  completionRate.add(completionResult.completed);
  rewardRate.add(completionResult.hasReward);

  if (completionResult.completed) {
    completedJobs.add(1);
  }

  // Active jobs 감소
  activeJobs.add(-1);

  // -------------------------------------------------------------------------
  // E2E 완료
  // -------------------------------------------------------------------------
  const e2eElapsed = Date.now() - iterStart;
  e2eLatency.add(e2eElapsed);

  // 로그 (10번에 1번만)
  if (__ITER % 10 === 0) {
    console.log(
      `[VU ${__VU}] Job ${jobId.substring(0, 8)}... ` +
      `completed=${completionResult.completed} ` +
      `reward=${completionResult.hasReward} ` +
      `time=${completionResult.elapsedMs}ms`
    );
  }

  // 다음 iteration 전 짧은 대기
  sleep(1 + Math.random());
}

// ============================================================================
// Setup & Teardown
// ============================================================================

export function setup() {
  console.log(`
╔══════════════════════════════════════════════════════════════════════════════╗
║                      🚀 SSE LOAD TEST STARTING                               ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Target VUs: ${String(TARGET_VUS).padEnd(62)}║
║  Duration:   ${TEST_DURATION.padEnd(62)}║
║  Base URL:   ${BASE_URL.padEnd(62)}║
║  Image:      ${IMAGE_URL.substring(0, 60).padEnd(62)}║
╚══════════════════════════════════════════════════════════════════════════════╝
`);

  // 토큰 검증
  if (!TOKEN) {
    throw new Error('TOKEN environment variable is required');
  }

  // API 연결 테스트
  const healthRes = http.get(`${BASE_URL}/health`, { timeout: '10s' });
  if (healthRes.status !== 200) {
    console.warn(`⚠️  Health check failed: ${healthRes.status}`);
  } else {
    console.log('✅ Health check passed');
  }

  return { startTime: Date.now() };
}

export function teardown(data) {
  const duration = (Date.now() - data.startTime) / 1000;
  console.log(`
╔══════════════════════════════════════════════════════════════════════════════╗
║                      ✅ SSE LOAD TEST COMPLETED                              ║
║  Total Runtime: ${duration.toFixed(1).padEnd(59)}s ║
╚══════════════════════════════════════════════════════════════════════════════╝
`);
}

// ============================================================================
// Summary
// ============================================================================

// ============================================================================
// Formatting Utilities
// ============================================================================

function formatMs(value) {
  if (value === undefined || value === null) return '-';
  const num = parseFloat(value);
  if (isNaN(num)) return '-';
  if (num >= 60000) return `${(num / 60000).toFixed(1)}m`;
  if (num >= 1000) return `${(num / 1000).toFixed(2)}s`;
  return `${num.toFixed(0)}ms`;
}

function formatPercent(value) {
  if (value === undefined || value === null) return '-';
  return `${(value * 100).toFixed(1)}%`;
}

function formatNumber(value) {
  if (value === undefined || value === null) return '0';
  return String(value);
}

function getMetricValue(data, metricName, key) {
  return data.metrics?.[metricName]?.values?.[key];
}

function pad(str, len) {
  const s = String(str);
  return s + ' '.repeat(Math.max(0, len - s.length));
}

export function handleSummary(data) {
  const timestamp = new Date().toISOString();
  const testDurationSec = ((data.state?.testRunDurationMs || 0) / 1000).toFixed(1);

  // 메트릭 추출 (k6 Trend 메트릭: avg, min, max, med, p(90), p(95))
  // NOTE: p(50)은 'med', p(99)는 기본 제공 안됨 → p(90) 사용
  const scanTotal = getMetricValue(data, 'scan_requests_total', 'count') || 0;
  const scanSuccess = getMetricValue(data, 'scan_success_total', 'count') || 0;
  const scanFailed = getMetricValue(data, 'scan_failed_total', 'count') || 0;
  const scanRate = getMetricValue(data, 'scan_success_rate', 'rate');
  const scanMed = getMetricValue(data, 'scan_latency_ms', 'med');
  const scanP90 = getMetricValue(data, 'scan_latency_ms', 'p(90)');
  const scanP95 = getMetricValue(data, 'scan_latency_ms', 'p(95)');
  const scanAvg = getMetricValue(data, 'scan_latency_ms', 'avg');
  const scanMax = getMetricValue(data, 'scan_latency_ms', 'max');

  const completedTotal = getMetricValue(data, 'completed_jobs_total', 'count') || 0;
  const completionRate = getMetricValue(data, 'completion_rate', 'rate');
  const completeMed = getMetricValue(data, 'time_to_complete_ms', 'med');
  const completeP90 = getMetricValue(data, 'time_to_complete_ms', 'p(90)');
  const completeP95 = getMetricValue(data, 'time_to_complete_ms', 'p(95)');
  const completeAvg = getMetricValue(data, 'time_to_complete_ms', 'avg');
  const completeMin = getMetricValue(data, 'time_to_complete_ms', 'min');
  const completeMax = getMetricValue(data, 'time_to_complete_ms', 'max');

  const e2eMed = getMetricValue(data, 'e2e_latency_ms', 'med');
  const e2eP90 = getMetricValue(data, 'e2e_latency_ms', 'p(90)');
  const e2eP95 = getMetricValue(data, 'e2e_latency_ms', 'p(95)');
  const e2eAvg = getMetricValue(data, 'e2e_latency_ms', 'avg');

  const rewardsTotal = getMetricValue(data, 'rewards_received_total', 'count') || 0;
  const rewardRate = getMetricValue(data, 'reward_rate', 'rate');

  const pollTotal = getMetricValue(data, 'poll_requests_total', 'count') || 0;
  const pollMed = getMetricValue(data, 'poll_latency_ms', 'med');
  const pollP95 = getMetricValue(data, 'poll_latency_ms', 'p(95)');
  const pollAvg = getMetricValue(data, 'poll_latency_ms', 'avg');

  const stageVision = getMetricValue(data, 'stage_vision_count', 'count') || 0;
  const stageRule = getMetricValue(data, 'stage_rule_count', 'count') || 0;
  const stageAnswer = getMetricValue(data, 'stage_answer_count', 'count') || 0;
  const stageReward = getMetricValue(data, 'stage_reward_count', 'count') || 0;
  const stageDone = getMetricValue(data, 'stage_done_count', 'count') || 0;

  // 처리량 계산
  const throughput = scanTotal > 0 ? (scanTotal / parseFloat(testDurationSec)).toFixed(2) : '0';
  const completedThroughput = completedTotal > 0 ? (completedTotal / parseFloat(testDurationSec)).toFixed(2) : '0';

  // Threshold 상태
  const thresholdStatus = data.thresholds || {};
  const getStatus = (key) => thresholdStatus[key]?.ok === false ? 'FAIL' : 'PASS';

  // 콘솔 출력
  const output = `
================================================================================
                           SSE LOAD TEST RESULTS
================================================================================

  Test Time   : ${timestamp}
  Duration    : ${testDurationSec}s
  Target VUs  : ${TARGET_VUS}

--------------------------------------------------------------------------------
  SCAN API
--------------------------------------------------------------------------------
  Requests    : ${pad(scanTotal, 8)} total | ${pad(scanSuccess, 6)} success | ${pad(scanFailed, 4)} failed
  Success Rate: ${formatPercent(scanRate)}  [${getStatus('scan_success_rate')}]
  Throughput  : ${throughput} req/s

  Latency     : avg ${pad(formatMs(scanAvg), 8)} | med ${pad(formatMs(scanMed), 8)} | max ${formatMs(scanMax)}
                p90 ${pad(formatMs(scanP90), 8)} | p95 ${formatMs(scanP95)}

--------------------------------------------------------------------------------
  COMPLETION (done stage reached)
--------------------------------------------------------------------------------
  Completed   : ${pad(completedTotal, 6)} / ${scanSuccess} jobs
  Rate        : ${formatPercent(completionRate)}  [${getStatus('completion_rate')}]
  Throughput  : ${completedThroughput} jobs/s

  Time        : min ${pad(formatMs(completeMin), 8)} | avg ${pad(formatMs(completeAvg), 8)} | max ${formatMs(completeMax)}
                med ${pad(formatMs(completeMed), 8)} | p90 ${pad(formatMs(completeP90), 8)} | p95 ${formatMs(completeP95)}  [${getStatus('time_to_complete_ms')}]

--------------------------------------------------------------------------------
  E2E LATENCY (request to done)
--------------------------------------------------------------------------------
  Latency     : avg ${pad(formatMs(e2eAvg), 8)} | med ${pad(formatMs(e2eMed), 8)}
                p90 ${pad(formatMs(e2eP90), 8)} | p95 ${formatMs(e2eP95)}  [${getStatus('e2e_latency_ms')}]

--------------------------------------------------------------------------------
  REWARDS
--------------------------------------------------------------------------------
  Total       : ${rewardsTotal}
  Rate        : ${formatPercent(rewardRate)}

--------------------------------------------------------------------------------
  STAGE BREAKDOWN
--------------------------------------------------------------------------------
  vision      : ${stageVision}
  rule        : ${stageRule}
  answer      : ${stageAnswer}
  reward      : ${stageReward}
  done        : ${stageDone}

--------------------------------------------------------------------------------
  POLLING
--------------------------------------------------------------------------------
  Requests    : ${pollTotal}
  Latency     : avg ${pad(formatMs(pollAvg), 8)} | med ${pad(formatMs(pollMed), 8)} | p95 ${formatMs(pollP95)}

================================================================================
  THRESHOLD SUMMARY
================================================================================
  scan_success_rate    : ${formatPercent(scanRate)} (threshold: >90%)     [${getStatus('scan_success_rate')}]
  completion_rate      : ${formatPercent(completionRate)} (threshold: >85%)     [${getStatus('completion_rate')}]
  scan_latency_ms p95  : ${formatMs(scanP95)} (threshold: <5s)        [${getStatus('scan_latency_ms')}]
  time_to_complete p95 : ${formatMs(completeP95)} (threshold: <60s)      [${getStatus('time_to_complete_ms')}]
  e2e_latency_ms p95   : ${formatMs(e2eP95)} (threshold: <90s)      [${getStatus('e2e_latency_ms')}]

================================================================================
`;

  console.log(output);

  // JSON 결과 (파일 저장용)
  const jsonResult = {
    meta: {
      timestamp,
      test_duration_sec: parseFloat(testDurationSec),
      target_vus: TARGET_VUS,
      duration_config: TEST_DURATION,
      base_url: BASE_URL,
    },
    scan_api: {
      total: scanTotal,
      success: scanSuccess,
      failed: scanFailed,
      success_rate: scanRate,
      throughput_rps: parseFloat(throughput),
      latency_ms: {
        avg: scanAvg,
        med: scanMed,
        p90: scanP90,
        p95: scanP95,
        max: scanMax,
      },
    },
    completion: {
      total: completedTotal,
      rate: completionRate,
      throughput_jps: parseFloat(completedThroughput),
      time_ms: {
        min: completeMin,
        avg: completeAvg,
        med: completeMed,
        p90: completeP90,
        p95: completeP95,
        max: completeMax,
      },
    },
    e2e_latency_ms: {
      avg: e2eAvg,
      med: e2eMed,
      p90: e2eP90,
      p95: e2eP95,
    },
    rewards: {
      total: rewardsTotal,
      rate: rewardRate,
    },
    stages: {
      vision: stageVision,
      rule: stageRule,
      answer: stageAnswer,
      reward: stageReward,
      done: stageDone,
    },
    polling: {
      total: pollTotal,
      latency_ms: {
        avg: pollAvg,
        med: pollMed,
        p95: pollP95,
      },
    },
    thresholds: thresholdStatus,
  };

  return {
    'stdout': output + '\n',
    [`k6-load-test-vu${TARGET_VUS}-${timestamp.replace(/[:.]/g, '-')}.json`]: JSON.stringify(jsonResult, null, 2),
  };
}
