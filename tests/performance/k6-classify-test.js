import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Trend } from "k6/metrics";

// ========== 커스텀 메트릭 ==========
const classifySuccess = new Counter("classify_success");
const classifyFailed = new Counter("classify_failed");
const classifyLatency = new Trend("classify_latency", true);

// ========== 테스트 설정 ==========
export const options = {
  // CLI에서 --vus, --duration으로 override 가능
  vus: 30,
  duration: "90s",

  thresholds: {
    http_req_failed: ["rate<0.3"], // 실패율 30% 미만
    classify_latency: ["p(95)<30000"], // 95%가 30초 이내
  },
};

// ========== 설정 ==========
const BASE_URL = __ENV.BASE_URL || "https://api.dev.growbin.app";
const ACCESS_COOKIE = __ENV.ACCESS_COOKIE || "";
const IMAGE_URL =
  __ENV.IMAGE_URL ||
  "https://images.dev.growbin.app/scan/1e89074f111d4727b1f28da647bc7c8e.jpg";

// ========== 메인 테스트 ==========
export default function () {
  const url = `${BASE_URL}/api/v1/scan/classify`;

  const payload = JSON.stringify({
    image_url: IMAGE_URL,
    user_input: "이 폐기물을 어떻게 분리배출해야 하나요?",
  });

  const params = {
    headers: {
      "Content-Type": "application/json",
      Cookie: `s_access=${ACCESS_COOKIE}`,
    },
    timeout: "120s", // LLM 호출로 인해 오래 걸릴 수 있음
    tags: { name: "Classify_API" },
  };

  const startTime = Date.now();

  // POST 요청
  const response = http.post(url, payload, params);

  const endTime = Date.now();
  const duration = endTime - startTime;

  // Latency 기록
  classifyLatency.add(duration);

  // 응답 검증
  const statusOk = check(response, {
    "status is 200": (r) => r.status === 200,
    "has classification result": (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.classification_result || body.pipeline_result;
      } catch {
        return false;
      }
    },
  });

  if (statusOk) {
    classifySuccess.add(1);

    // 응답 파싱
    try {
      const body = JSON.parse(response.body);
      const hasReward = body.reward !== null && body.reward !== undefined;
      console.log(
        `✅ [${__VU}] Completed in ${duration}ms - Reward: ${hasReward ? "✓" : "✗"}`
      );
    } catch {
      console.log(`✅ [${__VU}] Completed in ${duration}ms`);
    }
  } else {
    classifyFailed.add(1);
    console.log(
      `❌ [${__VU}] Failed: ${response.status} - ${response.body.substring(0, 200)}`
    );
  }

  // 요청 간 대기 (OpenAI Rate Limit 고려)
  sleep(1);
}

// ========== 테스트 시작/종료 훅 ==========
export function setup() {
  console.log("========================================");
  console.log("🚀 k6 Classify API Load Test Started");
  console.log(`   Target: ${BASE_URL}/api/v1/scan/classify`);
  console.log(`   Cookie: ${ACCESS_COOKIE ? "✓ Set" : "✗ Missing"}`);
  console.log("========================================\n");

  if (!ACCESS_COOKIE) {
    console.log("⚠️  WARNING: ACCESS_COOKIE not set. Requests may fail with 401.");
  }
}

export function teardown(data) {
  console.log("\n========================================");
  console.log("📊 k6 Classify API Load Test Completed");
  console.log("========================================");
}

// ========== 커스텀 요약 출력 ==========
export function handleSummary(data) {
  const success = data.metrics.classify_success
    ? data.metrics.classify_success.values.count
    : 0;
  const failed = data.metrics.classify_failed
    ? data.metrics.classify_failed.values.count
    : 0;
  const total = success + failed || 1; // 0으로 나누기 방지

  // 안전한 값 추출
  const latencyMetrics = data.metrics.classify_latency?.values || {};
  const p50 = latencyMetrics["p(50)"];
  const p95 = latencyMetrics["p(95)"];
  const p99 = latencyMetrics["p(99)"];

  const summary = `
========================================
📊 Classify API Test Summary
========================================
Total Requests:    ${total}
✅ Success:        ${success} (${((success / total) * 100).toFixed(1)}%)
❌ Failed:         ${failed} (${((failed / total) * 100).toFixed(1)}%)

⏱️  Latency (p50):  ${p50 !== undefined ? (p50 / 1000).toFixed(2) + "s" : "N/A"}
⏱️  Latency (p95):  ${p95 !== undefined ? (p95 / 1000).toFixed(2) + "s" : "N/A"}
⏱️  Latency (p99):  ${p99 !== undefined ? (p99 / 1000).toFixed(2) + "s" : "N/A"}
========================================
`;

  console.log(summary);

  return {
    stdout: summary,
    "k6-classify-summary.json": JSON.stringify(data, null, 2),
  };
}
