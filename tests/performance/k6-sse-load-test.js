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

function formatMs(value) {
  if (value === undefined || value === null) return '-';
  const num = parseFloat(value);
  if (isNaN(num)) return '-';
  if (num >= 1000) return `${(num / 1000).toFixed(2)}s`;
  return `${num.toFixed(0)}ms`;
}

function formatPercent(value) {
  if (value === undefined || value === null) return '-';
  return `${(value * 100).toFixed(2)}%`;
}

function formatNumber(value) {
  if (value === undefined || value === null) return '0';
  return value.toLocaleString();
}

function getMetricValue(data, metricName, key) {
  return data.metrics?.[metricName]?.values?.[key];
}

export function handleSummary(data) {
  const timestamp = new Date().toISOString();
  const testDurationSec = ((data.state?.testRunDurationMs || 0) / 1000).toFixed(1);

  // 메트릭 추출
  const scanTotal = getMetricValue(data, 'scan_requests_total', 'count') || 0;
  const scanSuccess = getMetricValue(data, 'scan_success_total', 'count') || 0;
  const scanFailed = getMetricValue(data, 'scan_failed_total', 'count') || 0;
  const scanRate = getMetricValue(data, 'scan_success_rate', 'rate');
  const scanP50 = getMetricValue(data, 'scan_latency_ms', 'p(50)');
  const scanP95 = getMetricValue(data, 'scan_latency_ms', 'p(95)');
  const scanP99 = getMetricValue(data, 'scan_latency_ms', 'p(99)');
  const scanAvg = getMetricValue(data, 'scan_latency_ms', 'avg');
  const scanMax = getMetricValue(data, 'scan_latency_ms', 'max');

  const completedTotal = getMetricValue(data, 'completed_jobs_total', 'count') || 0;
  const completionRate = getMetricValue(data, 'completion_rate', 'rate');
  const completeP50 = getMetricValue(data, 'time_to_complete_ms', 'p(50)');
  const completeP95 = getMetricValue(data, 'time_to_complete_ms', 'p(95)');
  const completeP99 = getMetricValue(data, 'time_to_complete_ms', 'p(99)');
  const completeAvg = getMetricValue(data, 'time_to_complete_ms', 'avg');
  const completeMin = getMetricValue(data, 'time_to_complete_ms', 'min');
  const completeMax = getMetricValue(data, 'time_to_complete_ms', 'max');

  const e2eP50 = getMetricValue(data, 'e2e_latency_ms', 'p(50)');
  const e2eP95 = getMetricValue(data, 'e2e_latency_ms', 'p(95)');
  const e2eP99 = getMetricValue(data, 'e2e_latency_ms', 'p(99)');
  const e2eAvg = getMetricValue(data, 'e2e_latency_ms', 'avg');

  const rewardsTotal = getMetricValue(data, 'rewards_received_total', 'count') || 0;
  const rewardRate = getMetricValue(data, 'reward_rate', 'rate');

  const pollTotal = getMetricValue(data, 'poll_requests_total', 'count') || 0;
  const pollP50 = getMetricValue(data, 'poll_latency_ms', 'p(50)');
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

  // 콘솔 출력 (가독성 좋은 형태)
  const output = `
╔══════════════════════════════════════════════════════════════════════════════╗
║                         🚀 SSE LOAD TEST RESULTS                             ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Test Time: ${timestamp.padEnd(45)}║
║  Duration: ${testDurationSec.padEnd(46)}s ║
║  Target VUs: ${String(TARGET_VUS).padEnd(44)}║
╠══════════════════════════════════════════════════════════════════════════════╣
║                              📊 SCAN API                                     ║
╠─────────────────────────────────────────────────────────────────────────────╣
║  Total Requests:  ${formatNumber(scanTotal).padEnd(15)} Success Rate: ${formatPercent(scanRate).padEnd(18)}║
║  ✓ Success: ${formatNumber(scanSuccess).padEnd(20)} ✗ Failed: ${formatNumber(scanFailed).padEnd(21)}║
║  Latency:  avg=${formatMs(scanAvg).padEnd(10)} p50=${formatMs(scanP50).padEnd(10)} p95=${formatMs(scanP95).padEnd(8)}║
║           p99=${formatMs(scanP99).padEnd(10)} max=${formatMs(scanMax).padEnd(30)}║
║  Throughput: ${throughput.padEnd(10)} req/s                                      ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                            ⏱️  COMPLETION                                    ║
╠─────────────────────────────────────────────────────────────────────────────╣
║  Completed Jobs: ${formatNumber(completedTotal).padEnd(15)} Rate: ${formatPercent(completionRate).padEnd(25)}║
║  Time to Complete:                                                           ║
║    min=${formatMs(completeMin).padEnd(10)} avg=${formatMs(completeAvg).padEnd(10)} max=${formatMs(completeMax).padEnd(18)}║
║    p50=${formatMs(completeP50).padEnd(10)} p95=${formatMs(completeP95).padEnd(10)} p99=${formatMs(completeP99).padEnd(18)}║
║  Throughput: ${completedThroughput.padEnd(10)} jobs/s                                    ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                             🎯 E2E LATENCY                                   ║
╠─────────────────────────────────────────────────────────────────────────────╣
║  avg=${formatMs(e2eAvg).padEnd(12)} p50=${formatMs(e2eP50).padEnd(12)} p95=${formatMs(e2eP95).padEnd(12)} p99=${formatMs(e2eP99).padEnd(8)}║
╠══════════════════════════════════════════════════════════════════════════════╣
║                             🎁 REWARDS                                       ║
╠─────────────────────────────────────────────────────────────────────────────╣
║  Total: ${formatNumber(rewardsTotal).padEnd(20)} Rate: ${formatPercent(rewardRate).padEnd(28)}║
╠══════════════════════════════════════════════════════════════════════════════╣
║                           📈 STAGE BREAKDOWN                                 ║
╠─────────────────────────────────────────────────────────────────────────────╣
║  vision: ${formatNumber(stageVision).padEnd(8)} → rule: ${formatNumber(stageRule).padEnd(8)} → answer: ${formatNumber(stageAnswer).padEnd(8)} → reward: ${formatNumber(stageReward).padEnd(5)}║
║  done: ${formatNumber(stageDone).padEnd(68)}║
╠══════════════════════════════════════════════════════════════════════════════╣
║                            🔄 POLLING                                        ║
╠─────────────────────────────────────────────────────────────────────────────╣
║  Total Requests: ${formatNumber(pollTotal).padEnd(56)}║
║  Latency: avg=${formatMs(pollAvg).padEnd(12)} p50=${formatMs(pollP50).padEnd(12)} p95=${formatMs(pollP95).padEnd(14)}║
╚══════════════════════════════════════════════════════════════════════════════╝
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
        p50: scanP50,
        p95: scanP95,
        p99: scanP99,
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
        p50: completeP50,
        p95: completeP95,
        p99: completeP99,
        max: completeMax,
      },
    },
    e2e_latency_ms: {
      avg: e2eAvg,
      p50: e2eP50,
      p95: e2eP95,
      p99: e2eP99,
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
        p50: pollP50,
        p95: pollP95,
      },
    },
    thresholds: data.thresholds,
  };

  return {
    'stdout': output + '\n',
    [`k6-load-test-vu${TARGET_VUS}-${timestamp.replace(/[:.]/g, '-')}.json`]: JSON.stringify(jsonResult, null, 2),
  };
}
