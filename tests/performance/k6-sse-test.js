/**
 * k6 SSE (Server-Sent Events) 부하 테스트
 *
 * eco2 /scan/classify/completion 엔드포인트 테스트
 *
 * 설치:
 *   brew install k6
 *
 * 실행:
 *   # 기본 실행 (10 VUs, 60초)
 *   k6 run -e ACCESS_COOKIE=your_token tests/performance/k6-sse-test.js
 *
 *   # 커스텀 설정
 *   k6 run -e ACCESS_COOKIE=xxx --vus 5 --duration 30s k6-sse-test.js
 *
 *   # 스테이지별 부하 (ramp-up)
 *   k6 run -e ACCESS_COOKIE=xxx k6-sse-test.js
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Trend } from "k6/metrics";

// ========== 커스텀 메트릭 ==========
const sseCompleted = new Counter("sse_completed");
const sseFailed = new Counter("sse_failed");
const ssePartial = new Counter("sse_partial");
const sseRewardNull = new Counter("sse_reward_null"); // Reward null 추적
const ttfb = new Trend("sse_ttfb", true); // Time To First Byte
const totalDuration = new Trend("sse_total_duration", true);

// ========== 테스트 설정 ==========
export const options = {
  // 50 VU 부하 테스트
  stages: [
    { duration: "30s", target: 50 }, // 30초 동안 0 → 50 VU (ramp-up)
    { duration: "90s", target: 50 }, // 90초 동안 50 VU 유지
    { duration: "30s", target: 0 },  // 30초 동안 ramp-down
  ],

  // 또는 간단히 고정 VU
  // vus: 34,
  // duration: '3m',

  thresholds: {
    http_req_failed: ["rate<0.3"], // 실패율 30% 미만
    sse_total_duration: ["p(95)<30000"], // 95%가 30초 이내
    sse_ttfb: ["p(95)<8000"], // TTFB 95%가 8초 이내 (OpenAI 호출 포함)
  },
};

// ========== 설정 ==========
const BASE_URL =
  __ENV.BASE_URL || "https://api.dev.growbin.app";
const ACCESS_COOKIE = __ENV.ACCESS_COOKIE || "";
const IMAGE_URL =
  __ENV.IMAGE_URL ||
  "https://images.dev.growbin.app/scan/1e89074f111d4727b1f28da647bc7c8e.jpg";

// ========== 메인 테스트 ==========
export default function () {
  const url = `${BASE_URL}/api/v1/scan/classify/completion`;

  const payload = JSON.stringify({
    image_url: IMAGE_URL,
    user_input: "이 폐기물을 어떻게 분리배출해야 하나요?",
  });

  const params = {
    headers: {
      "Content-Type": "application/json",
      Cookie: `s_access=${ACCESS_COOKIE}`,
      Accept: "text/event-stream",
    },
    timeout: "120s", // SSE는 오래 걸릴 수 있음
    tags: { name: "SSE_Completion" },
  };

  const startTime = Date.now();

  // POST 요청 (SSE 스트림)
  const response = http.post(url, payload, params);

  const endTime = Date.now();
  const duration = endTime - startTime;

  // TTFB 기록 (k6가 자동으로 측정)
  ttfb.add(response.timings.waiting);
  totalDuration.add(duration);

  // 응답 검증
  const statusOk = check(response, {
    "status is 200": (r) => r.status === 200,
    "content-type is event-stream": (r) =>
      r.headers["Content-Type"] &&
      r.headers["Content-Type"].includes("text/event-stream"),
  });

  if (!statusOk) {
    sseFailed.add(1);
    console.log(`❌ Request failed: ${response.status} - ${response.body.substring(0, 200)}`);
    sleep(1);
    return;
  }

  // SSE 이벤트 파싱
  const body = response.body;
  const stages = parseSSEStages(body);

  // 스테이지 검증
  const expectedStages = ["vision", "rule", "answer", "reward"];
  const completedStages = stages.filter((s) => s.status === "completed").map((s) => s.step);

  const allCompleted = expectedStages.every((s) => completedStages.includes(s));

  if (allCompleted) {
    sseCompleted.add(1);
    console.log(`✅ [${__VU}] Completed in ${duration}ms - Stages: ${completedStages.join(" → ")}`);

    // reward 결과 확인
    const rewardStage = stages.find((s) => s.step === "reward" && s.result);
    if (rewardStage && rewardStage.result) {
      const hasReward = rewardStage.result.reward !== null;
      if (!hasReward) {
        sseRewardNull.add(1);
      }
      console.log(`   Reward: ${hasReward ? "✓" : "✗ (null)"}`);
    } else {
      sseRewardNull.add(1);
      console.log(`   Reward: ✗ (no result)`);
    }
  } else if (completedStages.length > 0) {
    ssePartial.add(1);
    const missing = expectedStages.filter((s) => !completedStages.includes(s));
    console.log(`⚠️ [${__VU}] Partial: ${completedStages.join(", ")} | Missing: ${missing.join(", ")}`);
  } else {
    sseFailed.add(1);
    console.log(`❌ [${__VU}] No stages completed`);
  }

  // 요청 간 대기
  sleep(1);
}

// ========== SSE 파싱 헬퍼 ==========
function parseSSEStages(body) {
  const stages = [];
  const seen = new Set(); // 중복 제거용
  const lines = body.split("\n");

  for (const line of lines) {
    // data: 라인만 파싱 (event: 라인은 없음)
    if (line.startsWith("data:")) {
      const dataStr = line.substring(5).trim();
      if (!dataStr) continue;

      try {
        const data = JSON.parse(dataStr);
        // step 필드가 있고 completed 상태인 이벤트만 수집 (중복 제거)
        if (data.step && data.status === "completed" && !seen.has(data.step)) {
          seen.add(data.step);
          stages.push({
            step: data.step,
            status: data.status,
            result: data.result || null,
          });
        }
      } catch (e) {
        // JSON 파싱 실패 무시 (keepalive 등)
      }
    }
  }

  return stages;
}

// ========== 테스트 시작/종료 훅 ==========
export function setup() {
  console.log("========================================");
  console.log("🚀 k6 SSE Load Test Started");
  console.log(`   Target: ${BASE_URL}`);
  console.log(`   Cookie: ${ACCESS_COOKIE ? "✓ Set" : "✗ Missing"}`);
  console.log("========================================\n");

  if (!ACCESS_COOKIE) {
    console.log("⚠️  WARNING: ACCESS_COOKIE not set. Requests may fail with 401.");
  }
}

export function teardown(data) {
  console.log("\n========================================");
  console.log("📊 k6 SSE Load Test Completed");
  console.log("========================================");
}

// ========== 커스텀 요약 출력 ==========
export function handleSummary(data) {
  const completed = data.metrics.sse_completed ? data.metrics.sse_completed.values.count : 0;
  const failed = data.metrics.sse_failed ? data.metrics.sse_failed.values.count : 0;
  const partial = data.metrics.sse_partial ? data.metrics.sse_partial.values.count : 0;
  const rewardNull = data.metrics.sse_reward_null ? data.metrics.sse_reward_null.values.count : 0;
  const total = completed + failed + partial;

  const summary = `
========================================
📊 SSE Test Summary
========================================
Total Requests:    ${total}
✅ Completed:      ${completed} (${((completed / total) * 100).toFixed(1)}%)
⚠️  Partial:       ${partial} (${((partial / total) * 100).toFixed(1)}%)
❌ Failed:         ${failed} (${((failed / total) * 100).toFixed(1)}%)
🎁 Reward Null:    ${rewardNull} (${total > 0 ? ((rewardNull / total) * 100).toFixed(1) : 0}%)

⏱️  TTFB (p95):    ${data.metrics.sse_ttfb ? data.metrics.sse_ttfb.values["p(95)"].toFixed(0) : "N/A"}ms
⏱️  Total (p95):   ${data.metrics.sse_total_duration ? data.metrics.sse_total_duration.values["p(95)"].toFixed(0) : "N/A"}ms
========================================
`;

  console.log(summary);

  return {
    stdout: summary,
    "k6-sse-summary.json": JSON.stringify(data, null, 2),
  };
}
