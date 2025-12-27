/**
 * Scan Pipeline CCU 성능 테스트
 *
 * 시나리오: POST → SSE(done까지 대기) → GET result
 * 목표: CCU 50 기준 응답 시간 및 처리량 측정
 *
 * 사용법:
 *   k6 run --env BASE_URL=https://api.dev.growbin.app \
 *          --env TOKEN=<jwt_token> \
 *          --env IMAGE_URL=<image_url> \
 *          tests/performance/k6-scan-pipeline-test.js
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Trend, Gauge } from "k6/metrics";

// ─────────────────────────────────────────────────────────────────
// 환경 변수
// ─────────────────────────────────────────────────────────────────
const BASE_URL = __ENV.BASE_URL || "https://api.dev.growbin.app";
const TOKEN = __ENV.TOKEN || "";
const IMAGE_URL =
  __ENV.IMAGE_URL ||
  "https://images.dev.growbin.app/scan/0835c5ac2a6242d7b7db8310adefd899.png";

// ─────────────────────────────────────────────────────────────────
// 커스텀 메트릭
// ─────────────────────────────────────────────────────────────────

// 카운터
const scanSubmitted = new Counter("scan_submitted"); // POST 요청 수
const scanCompleted = new Counter("scan_completed"); // 완료된 파이프라인 수
const sseConnected = new Counter("sse_connected"); // SSE 연결 수
const sseEventsReceived = new Counter("sse_events_received"); // 수신된 SSE 이벤트 수
const resultFetched = new Counter("result_fetched"); // 결과 조회 수

// 에러
const scanErrors = new Counter("scan_errors");
const sseErrors = new Counter("sse_errors");
const resultErrors = new Counter("result_errors");

// 지연 시간 (Trend)
const submitDuration = new Trend("submit_duration", true); // POST 응답 시간
const pipelineDuration = new Trend("pipeline_duration", true); // 전체 파이프라인 시간 (POST~done)
const resultDuration = new Trend("result_duration", true); // GET result 응답 시간
const totalCycleDuration = new Trend("total_cycle_duration", true); // 전체 사이클 시간

// SSE 단계별 시간
const visionDuration = new Trend("vision_stage_duration", true);
const ruleDuration = new Trend("rule_stage_duration", true);
const answerDuration = new Trend("answer_stage_duration", true);
const rewardDuration = new Trend("reward_stage_duration", true);

// 현재 활성 SSE 연결 수 (CCU 추정용)
const activeSseConnections = new Gauge("active_sse_connections");

// ─────────────────────────────────────────────────────────────────
// 테스트 옵션 (시나리오 정의)
// ─────────────────────────────────────────────────────────────────
export const options = {
  scenarios: {
    // 시나리오 1: CCU 50 테스트 (Ramp-up → Steady → Ramp-down)
    ccu_test: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 10 }, // Warm-up: 10 VU로 증가
        { duration: "30s", target: 25 }, // 25 VU로 증가
        { duration: "1m", target: 50 }, // 목표: 50 CCU
        { duration: "2m", target: 50 }, // 50 CCU 유지 (Steady)
        { duration: "30s", target: 25 }, // Ramp-down
        { duration: "30s", target: 0 }, // 종료
      ],
      gracefulRampDown: "30s",
    },
  },
  thresholds: {
    // 성능 기준
    submit_duration: ["p(95)<2000"], // POST 95% < 2초
    pipeline_duration: ["p(95)<15000"], // 파이프라인 95% < 15초
    result_duration: ["p(95)<500"], // GET result 95% < 0.5초
    total_cycle_duration: ["p(95)<20000"], // 전체 사이클 95% < 20초

    // 에러율
    scan_errors: ["count<10"], // 에러 10개 미만
    sse_errors: ["count<20"], // SSE 에러 20개 미만

    // 성공률
    http_req_failed: ["rate<0.05"], // HTTP 실패율 5% 미만
  },
};

// ─────────────────────────────────────────────────────────────────
// 공통 헤더
// ─────────────────────────────────────────────────────────────────
function getHeaders(jobId = null) {
  const headers = {
    Authorization: `Bearer ${TOKEN}`,
    "Content-Type": "application/json",
  };
  if (jobId) {
    headers["X-Job-Id"] = jobId;
  }
  return headers;
}

// ─────────────────────────────────────────────────────────────────
// Step 1: POST /api/v1/scan
// ─────────────────────────────────────────────────────────────────
function submitScan() {
  const url = `${BASE_URL}/api/v1/scan`;
  const payload = JSON.stringify({ image_url: IMAGE_URL });

  const startTime = Date.now();
  const res = http.post(url, payload, { headers: getHeaders() });
  const duration = Date.now() - startTime;

  submitDuration.add(duration);
  scanSubmitted.add(1);

  const success = check(res, {
    "POST /scan status 200": (r) => r.status === 200,
    "POST /scan has job_id": (r) => {
      try {
        return JSON.parse(r.body).job_id !== undefined;
      } catch {
        return false;
      }
    },
  });

  if (!success) {
    scanErrors.add(1);
    console.error(`POST /scan failed: ${res.status} - ${res.body}`);
    return null;
  }

  const data = JSON.parse(res.body);
  return {
    jobId: data.job_id,
    streamUrl: data.stream_url,
    resultUrl: data.result_url,
  };
}

// ─────────────────────────────────────────────────────────────────
// Step 2: GET /api/v1/stream?job_id=... (SSE 구독)
// ─────────────────────────────────────────────────────────────────
function subscribeSSE(jobId, pipelineStart) {
  const url = `${BASE_URL}/api/v1/stream?job_id=${jobId}`;

  // SSE 연결 (HTTP/1.1 강제, 긴 타임아웃)
  const res = http.get(url, {
    headers: {
      ...getHeaders(jobId),
      Accept: "text/event-stream",
      Connection: "keep-alive",
    },
    timeout: "60s",
  });

  sseConnected.add(1);

  // SSE 응답 파싱
  const events = parseSSEEvents(res.body);
  sseEventsReceived.add(events.length);

  // 단계별 시간 측정
  const stageTimes = extractStageTimes(events);
  if (stageTimes.vision) visionDuration.add(stageTimes.vision);
  if (stageTimes.rule) ruleDuration.add(stageTimes.rule);
  if (stageTimes.answer) answerDuration.add(stageTimes.answer);
  if (stageTimes.reward) rewardDuration.add(stageTimes.reward);

  // done 이벤트 확인
  const hasDone = events.some((e) => e.stage === "done");
  if (hasDone) {
    const pipelineTime = Date.now() - pipelineStart;
    pipelineDuration.add(pipelineTime);
    scanCompleted.add(1);
  } else {
    sseErrors.add(1);
    console.warn(`SSE stream ended without 'done' for job ${jobId}`);
  }

  return hasDone;
}

// ─────────────────────────────────────────────────────────────────
// Step 3: GET /api/v1/scan/result/{job_id}
// ─────────────────────────────────────────────────────────────────
function fetchResult(jobId) {
  const url = `${BASE_URL}/api/v1/scan/result/${jobId}`;

  const startTime = Date.now();
  const res = http.get(url, { headers: getHeaders() });
  const duration = Date.now() - startTime;

  resultDuration.add(duration);
  resultFetched.add(1);

  const success = check(res, {
    "GET /result status 200": (r) => r.status === 200,
    "GET /result has pipeline_result": (r) => {
      try {
        const data = JSON.parse(r.body);
        return data.pipeline_result !== null;
      } catch {
        return false;
      }
    },
  });

  if (!success) {
    resultErrors.add(1);
    console.error(`GET /result failed: ${res.status} - ${res.body}`);
  }

  return success;
}

// ─────────────────────────────────────────────────────────────────
// SSE 이벤트 파싱 유틸리티
// ─────────────────────────────────────────────────────────────────
function parseSSEEvents(body) {
  if (!body) return [];

  const events = [];
  const lines = body.split("\n");

  let currentEvent = null;
  for (const line of lines) {
    if (line.startsWith("event:")) {
      currentEvent = { type: line.substring(6).trim() };
    } else if (line.startsWith("data:") && currentEvent) {
      try {
        const data = JSON.parse(line.substring(5).trim());
        currentEvent.stage = data.stage;
        currentEvent.status = data.status;
        currentEvent.ts = data.ts;
        currentEvent.seq = data.seq;
        events.push(currentEvent);
      } catch {
        // keepalive 등 JSON이 아닌 데이터 무시
      }
      currentEvent = null;
    }
  }

  return events;
}

function extractStageTimes(events) {
  const times = {};
  const stageStart = {};

  for (const event of events) {
    if (event.status === "started") {
      stageStart[event.stage] = event.ts;
    } else if (event.status === "completed" && stageStart[event.stage]) {
      times[event.stage] = (event.ts - stageStart[event.stage]) * 1000; // ms
    }
  }

  return times;
}

// ─────────────────────────────────────────────────────────────────
// 메인 테스트 함수
// ─────────────────────────────────────────────────────────────────
export default function () {
  const cycleStart = Date.now();

  // Step 1: 작업 제출
  const scanResult = submitScan();
  if (!scanResult) {
    sleep(2); // 에러 시 재시도 전 대기
    return;
  }

  // Step 2: SSE 구독 (파이프라인 완료까지 대기)
  const pipelineStart = Date.now();
  const sseSuccess = subscribeSSE(scanResult.jobId, pipelineStart);

  // Step 3: 결과 조회
  if (sseSuccess) {
    sleep(0.5); // 결과 저장 안정화 대기
    fetchResult(scanResult.jobId);
  }

  // 전체 사이클 시간 기록
  const cycleTime = Date.now() - cycleStart;
  totalCycleDuration.add(cycleTime);

  // 다음 사이클 전 짧은 대기 (Think Time 시뮬레이션)
  sleep(Math.random() * 2 + 1); // 1~3초 랜덤 대기
}

// ─────────────────────────────────────────────────────────────────
// 테스트 설정 및 요약
// ─────────────────────────────────────────────────────────────────
export function setup() {
  console.log("=".repeat(60));
  console.log("  Scan Pipeline CCU Performance Test");
  console.log("=".repeat(60));
  console.log(`  Base URL: ${BASE_URL}`);
  console.log(`  Image URL: ${IMAGE_URL}`);
  console.log(`  Token: ${TOKEN ? "Provided" : "NOT PROVIDED!"}`);
  console.log("=".repeat(60));

  if (!TOKEN) {
    console.error("ERROR: TOKEN environment variable is required!");
  }

  return { startTime: Date.now() };
}

export function teardown(data) {
  const duration = (Date.now() - data.startTime) / 1000;
  console.log("=".repeat(60));
  console.log(`  Test completed in ${duration.toFixed(1)}s`);
  console.log("=".repeat(60));
}
