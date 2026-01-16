/**
 * Chat API E2E Test
 *
 * 전체 플로우 테스트:
 * 1. POST /chat - 채팅 제출
 * 2. GET /chat/{job_id}/events - SSE 스트리밍
 *
 * Usage:
 *   k6 run k6-chat-e2e.js --env BASE_URL=http://localhost:8000
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom Metrics
const chatSubmitSuccess = new Rate('chat_submit_success');
const chatSubmitDuration = new Trend('chat_submit_duration_ms');
const sseConnectionSuccess = new Rate('sse_connection_success');
const sseFirstEventLatency = new Trend('sse_first_event_latency_ms');
const totalEvents = new Counter('total_events_received');

// Configuration
const BASE_URL = __ENV.BASE_URL || 'http://chat-api.chat.svc.cluster.local:8000';
const AUTH_TOKEN = __ENV.AUTH_TOKEN || 'test-token';

export const options = {
  scenarios: {
    chat_flow: {
      executor: 'constant-vus',
      vus: 5,
      duration: '30s',
    },
  },
  thresholds: {
    'chat_submit_success': ['rate>0.95'],
    'chat_submit_duration_ms': ['p(95)<5000'],
    'sse_connection_success': ['rate>0.90'],
  },
};

// Test Data
const testMessages = [
  '페트병은 어떻게 버리나요?',
  '음식물쓰레기 분리배출 방법 알려줘',
  '건전지 어디에 버려요?',
  '플라스틱 용기 재활용 가능한가요?',
  '종이컵은 재활용 되나요?',
];

export default function () {
  const sessionId = `test-session-${__VU}-${Date.now()}`;
  const message = testMessages[Math.floor(Math.random() * testMessages.length)];

  group('Chat Submit', () => {
    const payload = JSON.stringify({
      session_id: sessionId,
      message: message,
    });

    const headers = {
      'Content-Type': 'application/json',
      'X-User-ID': `test-user-${__VU}`,
      'X-User-Role': 'user',
    };

    const startTime = Date.now();
    const res = http.post(`${BASE_URL}/api/v1/chat`, payload, { headers });
    const duration = Date.now() - startTime;

    chatSubmitDuration.add(duration);

    const success = check(res, {
      'submit returns 200': (r) => r.status === 200,
      'has job_id': (r) => {
        const body = JSON.parse(r.body);
        return body.job_id !== undefined;
      },
      'has stream_url': (r) => {
        const body = JSON.parse(r.body);
        return body.stream_url !== undefined;
      },
    });

    chatSubmitSuccess.add(success);

    if (success) {
      const body = JSON.parse(res.body);
      const jobId = body.job_id;

      // SSE 연결 테스트
      group('SSE Streaming', () => {
        testSSEConnection(jobId, headers);
      });
    }
  });

  sleep(1);
}

function testSSEConnection(jobId, headers) {
  // SSE Gateway URL
  const sseUrl = `${BASE_URL}/api/v1/chat/${jobId}/events`;

  const startTime = Date.now();
  let firstEventReceived = false;
  let eventsCount = 0;

  // k6는 native SSE를 지원하지 않으므로 HTTP GET으로 테스트
  // 실제 SSE 테스트는 별도 스크립트 필요
  const res = http.get(sseUrl, {
    headers: {
      ...headers,
      Accept: 'text/event-stream',
    },
    timeout: '30s',
  });

  const latency = Date.now() - startTime;

  const success = check(res, {
    'SSE returns 200 or 307': (r) => r.status === 200 || r.status === 307,
  });

  sseConnectionSuccess.add(success);

  if (success && !firstEventReceived) {
    sseFirstEventLatency.add(latency);
    firstEventReceived = true;
  }

  // 이벤트 수 카운트 (간단한 파싱)
  if (res.body) {
    const lines = res.body.split('\n');
    for (const line of lines) {
      if (line.startsWith('data:')) {
        eventsCount++;
        totalEvents.add(1);
      }
    }
  }
}

// Chat with Image Test
export function chatWithImage() {
  const sessionId = `img-session-${__VU}-${Date.now()}`;

  const payload = JSON.stringify({
    session_id: sessionId,
    message: '이 쓰레기 어떻게 버려요?',
    image_url: 'https://example.com/test-image.jpg',
  });

  const headers = {
    'Content-Type': 'application/json',
    'X-User-ID': `test-user-${__VU}`,
    'X-User-Role': 'user',
  };

  const res = http.post(`${BASE_URL}/api/v1/chat`, payload, { headers });

  check(res, {
    'image chat returns 200': (r) => r.status === 200,
    'has job_id': (r) => JSON.parse(r.body).job_id !== undefined,
  });
}

// Chat with Location Test
export function chatWithLocation() {
  const sessionId = `loc-session-${__VU}-${Date.now()}`;

  const payload = JSON.stringify({
    session_id: sessionId,
    message: '근처 재활용센터 알려줘',
    user_location: {
      latitude: 37.5665,
      longitude: 126.978,
    },
  });

  const headers = {
    'Content-Type': 'application/json',
    'X-User-ID': `test-user-${__VU}`,
    'X-User-Role': 'user',
  };

  const res = http.post(`${BASE_URL}/api/v1/chat`, payload, { headers });

  check(res, {
    'location chat returns 200': (r) => r.status === 200,
  });
}
