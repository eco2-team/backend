/**
 * k6 SSE 부하 테스트 (CCU 50)
 *
 * 새 아키텍처:
 * ① POST /api/v1/scan → job_id, stream_url, result_url 반환
 * ② GET /api/v1/stream?job_id=xxx → SSE 스트리밍 (sse-gateway)
 * ③ GET /api/v1/scan/result/{job_id} → 최종 결과 조회 (scan-api)
 *
 * 설치:
 *   brew install k6
 *
 * 실행:
 *   # 기본 실행 (50 VUs, ramp-up/steady/ramp-down)
 *   k6 run -e ACCESS_TOKEN=your_jwt_token tests/performance/k6-sse-gateway-test.js
 *
 *   # 커스텀 설정
 *   k6 run -e ACCESS_TOKEN=xxx -e BASE_URL=https://api.dev.growbin.app tests/performance/k6-sse-gateway-test.js
 *
 *   # 짧은 테스트
 *   k6 run -e ACCESS_TOKEN=xxx --vus 10 --duration 30s tests/performance/k6-sse-gateway-test.js
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Trend, Gauge } from "k6/metrics";

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 커스텀 메트릭
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

// 카운터
const classifySuccess = new Counter("classify_success");
const classifyFailed = new Counter("classify_failed");
const sseCompleted = new Counter("sse_completed");
const sseFailed = new Counter("sse_failed");
const ssePartial = new Counter("sse_partial");
const sseTimeout = new Counter("sse_timeout");
const sseRewardNull = new Counter("sse_reward_null");

// 타이밍
const classifyLatency = new Trend("classify_latency", true);
const sseTTFB = new Trend("sse_ttfb", true);
const sseTotalDuration = new Trend("sse_total_duration", true);
const stageVisionDuration = new Trend("stage_vision_duration", true);
const stageRuleDuration = new Trend("stage_rule_duration", true);
const stageAnswerDuration = new Trend("stage_answer_duration", true);
const stageRewardDuration = new Trend("stage_reward_duration", true);

// 현재 상태
const activeConnections = new Gauge("active_sse_connections");

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 테스트 설정 (CCU 50)
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export const options = {
  scenarios: {
    sse_gateway_load: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 50 },  // Ramp-up: 0 → 50 VUs
        { duration: "90s", target: 50 },  // Steady: 50 VUs 유지
        { duration: "30s", target: 0 },   // Ramp-down: 50 → 0 VUs
      ],
      gracefulRampDown: "10s",
    },
  },

  thresholds: {
    // API 응답
    classify_latency: ["p(95)<1000"],        // POST /classify p95 < 1초
    http_req_failed: ["rate<0.10"],          // HTTP 실패율 10% 미만

    // SSE 파이프라인
    sse_ttfb: ["p(95)<10000"],               // 첫 이벤트 p95 < 10초
    sse_total_duration: ["p(95)<60000"],     // 전체 완료 p95 < 60초
    sse_completed: ["count>0"],              // 최소 1개 완료

    // 스테이지별 (참고용)
    stage_vision_duration: ["p(95)<15000"],  // Vision p95 < 15초
    stage_answer_duration: ["p(95)<20000"],  // Answer p95 < 20초
  },
};

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 환경 변수
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

const BASE_URL = __ENV.BASE_URL || "https://api.dev.growbin.app";
const ACCESS_TOKEN = __ENV.ACCESS_TOKEN || "";
const IMAGE_URL = __ENV.IMAGE_URL || "https://images.dev.growbin.app/scan/0835c5ac2a6242d7b7db8310adefd899.png";
const SSE_TIMEOUT_MS = parseInt(__ENV.SSE_TIMEOUT_MS || "120000"); // 2분

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 메인 테스트 함수
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export default function () {
  const vuId = __VU;
  const iterId = __ITER;

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // Step 1: POST /api/v1/scan → job_id, stream_url 획득
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  const submitUrl = `${BASE_URL}/api/v1/scan`;
  const submitPayload = JSON.stringify({
    image_url: IMAGE_URL,
    user_input: "이 폐기물을 어떻게 분리배출해야 하나요?",
  });

  const submitParams = {
    headers: {
      "Content-Type": "application/json",
      Cookie: `s_access=${ACCESS_TOKEN}`,
    },
    timeout: "30s",
    tags: { name: "submit" },
  };

  const submitStart = Date.now();
  const submitRes = http.post(submitUrl, submitPayload, submitParams);
  const submitEnd = Date.now();

  classifyLatency.add(submitEnd - submitStart);

  // Submit 응답 검증
  const submitOk = check(submitRes, {
    "submit: status 200": (r) => r.status === 200,
    "submit: has job_id": (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.job_id;
      } catch {
        return false;
      }
    },
    "submit: has stream_url": (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.stream_url;
      } catch {
        return false;
      }
    },
  });

  if (!submitOk) {
    classifyFailed.add(1);
    console.log(`❌ [VU${vuId}] Submit failed: ${submitRes.status} - ${submitRes.body.substring(0, 200)}`);
    sleep(2);
    return;
  }

  classifySuccess.add(1);

  // job_id 추출
  let jobId, streamUrl;
  try {
    const body = JSON.parse(submitRes.body);
    jobId = body.job_id;
    streamUrl = body.stream_url;
  } catch (e) {
    console.log(`❌ [VU${vuId}] Failed to parse submit response`);
    sseFailed.add(1);
    sleep(1);
    return;
  }

  console.log(`📤 [VU${vuId}] Submit OK → job_id: ${jobId.substring(0, 8)}...`);

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // Step 2: GET /api/v1/stream?job_id=xxx → SSE 구독 (sse-gateway)
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  const sseUrl = `${BASE_URL}/api/v1/stream?job_id=${jobId}`;
  const sseParams = {
    headers: {
      Accept: "text/event-stream",
      Cookie: `s_access=${ACCESS_TOKEN}`,
      "X-Job-Id": jobId,  // Istio Consistent Hash용
    },
    timeout: `${SSE_TIMEOUT_MS}ms`,
    tags: { name: "sse_stream" },
  };

  activeConnections.add(1);
  const sseStart = Date.now();
  let firstEventTime = null;

  // SSE 응답 (k6는 전체 응답을 기다림)
  const sseRes = http.get(sseUrl, sseParams);

  activeConnections.add(-1);
  const sseEnd = Date.now();
  const sseDuration = sseEnd - sseStart;

  // SSE 응답 검증
  const sseStatusOk = check(sseRes, {
    "sse: status 200": (r) => r.status === 200,
    "sse: content-type event-stream": (r) =>
      r.headers["Content-Type"] &&
      r.headers["Content-Type"].includes("text/event-stream"),
  });

  if (!sseStatusOk) {
    sseFailed.add(1);
    console.log(`❌ [VU${vuId}] SSE failed: ${sseRes.status}`);
    sleep(1);
    return;
  }

  // SSE 이벤트 파싱
  const { stages, firstEventOffset, stageTimings } = parseSSEEvents(sseRes.body, sseStart);

  // TTFB 기록
  if (firstEventOffset > 0) {
    sseTTFB.add(firstEventOffset);
  }

  // 스테이지별 타이밍 기록
  if (stageTimings.vision) stageVisionDuration.add(stageTimings.vision);
  if (stageTimings.rule) stageRuleDuration.add(stageTimings.rule);
  if (stageTimings.answer) stageAnswerDuration.add(stageTimings.answer);
  if (stageTimings.reward) stageRewardDuration.add(stageTimings.reward);

  // 결과 판정
  const expectedStages = ["vision", "rule", "answer", "reward"];
  const completedStages = stages.filter((s) => s.status === "completed").map((s) => s.stage);
  const allCompleted = expectedStages.every((s) => completedStages.includes(s));

  sseTotalDuration.add(sseDuration);

  if (allCompleted) {
    sseCompleted.add(1);

    // Reward 확인
    const rewardStage = stages.find((s) => s.stage === "reward");
    const hasReward = rewardStage && rewardStage.result && rewardStage.result.reward !== null;
    if (!hasReward) {
      sseRewardNull.add(1);
    }

    console.log(
      `✅ [VU${vuId}] Done in ${(sseDuration / 1000).toFixed(1)}s | ` +
        `TTFB: ${firstEventOffset}ms | Reward: ${hasReward ? "✓" : "✗"}`
    );
  } else if (completedStages.length > 0) {
    ssePartial.add(1);
    const missing = expectedStages.filter((s) => !completedStages.includes(s));
    console.log(`⚠️ [VU${vuId}] Partial (${completedStages.length}/4) | Missing: ${missing.join(", ")}`);
  } else if (sseDuration >= SSE_TIMEOUT_MS - 1000) {
    sseTimeout.add(1);
    console.log(`⏰ [VU${vuId}] Timeout after ${(sseDuration / 1000).toFixed(1)}s`);
  } else {
    sseFailed.add(1);
    console.log(`❌ [VU${vuId}] No stages completed`);
  }

  // 다음 요청 전 대기 (서버 부하 분산)
  sleep(Math.random() * 2 + 1); // 1~3초 랜덤
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// SSE 이벤트 파싱
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function parseSSEEvents(body, startTime) {
  const stages = [];
  const seen = new Set();
  const stageTimings = {};
  let firstEventOffset = 0;
  let lastTimestamp = startTime;

  const lines = body.split("\n");

  for (const line of lines) {
    if (!line.startsWith("data:")) continue;

    const dataStr = line.substring(5).trim();
    if (!dataStr) continue;

    try {
      const data = JSON.parse(dataStr);

      // 첫 이벤트 시간 기록
      if (firstEventOffset === 0 && data.stage) {
        firstEventOffset = Date.now() - startTime;
      }

      // stage/step 이벤트 처리
      const stageName = data.stage || data.step;
      if (stageName && data.status === "completed" && !seen.has(stageName)) {
        seen.add(stageName);

        // 타이밍 계산 (이전 스테이지와의 차이)
        const now = Date.now();
        stageTimings[stageName] = now - lastTimestamp;
        lastTimestamp = now;

        stages.push({
          stage: stageName,
          status: data.status,
          result: data.result || null,
        });
      }
    } catch {
      // keepalive 등 무시
    }
  }

  return { stages, firstEventOffset, stageTimings };
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 테스트 시작/종료 훅
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export function setup() {
  console.log("═══════════════════════════════════════════════════════════");
  console.log("🚀 SSE Gateway Load Test (CCU 50)");
  console.log("═══════════════════════════════════════════════════════════");
  console.log(`   Base URL:    ${BASE_URL}`);
  console.log(`   Image URL:   ${IMAGE_URL.substring(0, 50)}...`);
  console.log(`   Token:       ${ACCESS_TOKEN ? "✓ Set" : "✗ Missing"}`);
  console.log(`   SSE Timeout: ${SSE_TIMEOUT_MS / 1000}s`);
  console.log("═══════════════════════════════════════════════════════════\n");

  if (!ACCESS_TOKEN) {
    console.log("⚠️  WARNING: ACCESS_TOKEN not set. Requests will fail with 401.\n");
  }

  // Warm-up request
  console.log("🔥 Warm-up request...");
  const warmupRes = http.get(`${BASE_URL}/api/health`, {
    headers: { Cookie: `s_access=${ACCESS_TOKEN}` },
    timeout: "10s",
  });
  console.log(`   Health check: ${warmupRes.status}\n`);
}

export function teardown() {
  console.log("\n═══════════════════════════════════════════════════════════");
  console.log("📊 SSE Gateway Load Test Completed");
  console.log("═══════════════════════════════════════════════════════════");
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 결과 요약
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export function handleSummary(data) {
  const metrics = data.metrics;

  const classifyOk = metrics.classify_success?.values?.count || 0;
  const classifyFail = metrics.classify_failed?.values?.count || 0;
  const sseOk = metrics.sse_completed?.values?.count || 0;
  const ssePart = metrics.sse_partial?.values?.count || 0;
  const sseFail = metrics.sse_failed?.values?.count || 0;
  const sseTime = metrics.sse_timeout?.values?.count || 0;
  const rewardNull = metrics.sse_reward_null?.values?.count || 0;

  const totalClassify = classifyOk + classifyFail;
  const totalSSE = sseOk + ssePart + sseFail + sseTime;
  const successRate = totalSSE > 0 ? ((sseOk / totalSSE) * 100).toFixed(1) : 0;

  const summary = `
═══════════════════════════════════════════════════════════════════════
📊 SSE Gateway Load Test Results
═══════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────┐
│ Phase 1: POST /api/v1/scan                                          │
├─────────────────────────────────────────────────────────────────────┤
│   ✅ Success:      ${classifyOk.toString().padStart(6)}                                         │
│   ❌ Failed:       ${classifyFail.toString().padStart(6)}                                         │
│   ⏱️  Latency p95: ${metrics.classify_latency?.values?.["p(95)"]?.toFixed(0) || "N/A"}ms                                       │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ Phase 2: GET /stream?job_id=xxx (SSE Gateway)                       │
├─────────────────────────────────────────────────────────────────────┤
│   ✅ Completed:    ${sseOk.toString().padStart(6)} (${successRate}%)                               │
│   ⚠️  Partial:     ${ssePart.toString().padStart(6)}                                         │
│   ❌ Failed:       ${sseFail.toString().padStart(6)}                                         │
│   ⏰ Timeout:      ${sseTime.toString().padStart(6)}                                         │
│   🎁 Reward Null:  ${rewardNull.toString().padStart(6)}                                         │
├─────────────────────────────────────────────────────────────────────┤
│   ⏱️  TTFB p95:        ${(metrics.sse_ttfb?.values?.["p(95)"] / 1000)?.toFixed(2) || "N/A"}s                                  │
│   ⏱️  Total p95:       ${(metrics.sse_total_duration?.values?.["p(95)"] / 1000)?.toFixed(2) || "N/A"}s                                  │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ Stage Breakdown (p95)                                               │
├─────────────────────────────────────────────────────────────────────┤
│   👁️  Vision:  ${(metrics.stage_vision_duration?.values?.["p(95)"] / 1000)?.toFixed(2) || "N/A"}s                                        │
│   📋 Rule:    ${(metrics.stage_rule_duration?.values?.["p(95)"] / 1000)?.toFixed(2) || "N/A"}s                                        │
│   💬 Answer:  ${(metrics.stage_answer_duration?.values?.["p(95)"] / 1000)?.toFixed(2) || "N/A"}s                                        │
│   🎁 Reward:  ${(metrics.stage_reward_duration?.values?.["p(95)"] / 1000)?.toFixed(2) || "N/A"}s                                        │
└─────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════
`;

  console.log(summary);

  return {
    stdout: summary,
    "sse-gateway-summary.json": JSON.stringify(data, null, 2),
  };
}
