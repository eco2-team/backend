/**
 * ext-authz Performance Test
 *
 * 목적: 로컬 캐시 적용 전/후 성능 비교
 * 참고: https://rooftopsnow.tistory.com/24
 *
 * 사용법:
 *   k6 run -e TOKEN="<jwt>" -e BASE_URL="https://api.dev.growbin.app" \
 *          -e VUS=100 -e DURATION="60s" k6-ext-authz-test.js
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

// ─────────────────────────────────────────────────────────────────────────────
// Configuration
// ─────────────────────────────────────────────────────────────────────────────
const BASE_URL = __ENV.BASE_URL || 'https://api.dev.growbin.app';
const TOKEN = __ENV.TOKEN;
const VUS = parseInt(__ENV.VUS) || 100;
const DURATION = __ENV.DURATION || '60s';
const RAMP_UP = __ENV.RAMP_UP || '10s';
const RAMP_DOWN = __ENV.RAMP_DOWN || '5s';

if (!TOKEN) {
    throw new Error('TOKEN environment variable is required');
}

// ─────────────────────────────────────────────────────────────────────────────
// Metrics
// ─────────────────────────────────────────────────────────────────────────────
const authLatency = new Trend('auth_latency', true);
const authSuccess = new Rate('auth_success');
const authRequests = new Counter('auth_requests');
const auth401 = new Counter('auth_401_responses');
const auth403 = new Counter('auth_403_responses');

// ─────────────────────────────────────────────────────────────────────────────
// Test Configuration
// ─────────────────────────────────────────────────────────────────────────────
export const options = {
    scenarios: {
        auth_load: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                { duration: RAMP_UP, target: VUS },      // Ramp-up
                { duration: DURATION, target: VUS },     // Steady state
                { duration: RAMP_DOWN, target: 0 },      // Ramp-down
            ],
            gracefulRampDown: '5s',
        },
    },
    thresholds: {
        'auth_latency': ['p(95)<100'],      // p95 < 100ms
        'auth_success': ['rate>0.99'],       // 99% success rate
        'http_req_failed': ['rate<0.01'],    // <1% failure
    },
};

// ─────────────────────────────────────────────────────────────────────────────
// Test Endpoint (lightweight authenticated endpoint - no DB)
// ─────────────────────────────────────────────────────────────────────────────
const TEST_ENDPOINT = `${BASE_URL}/api/v1/user/ping`;

// ─────────────────────────────────────────────────────────────────────────────
// Main Test
// ─────────────────────────────────────────────────────────────────────────────
export default function() {
    const headers = {
        'Authorization': `Bearer ${TOKEN}`,
        'Content-Type': 'application/json',
    };

    const res = http.get(TEST_ENDPOINT, { headers });

    authRequests.add(1);
    authLatency.add(res.timings.duration);

    // Check response
    const success = check(res, {
        'status is 200': (r) => r.status === 200,
        'latency < 100ms': (r) => r.timings.duration < 100,
    });

    authSuccess.add(success);

    if (res.status === 401) {
        auth401.add(1);
    } else if (res.status === 403) {
        auth403.add(1);
    }

    // Small sleep to avoid overwhelming
    sleep(0.01);
}

// ─────────────────────────────────────────────────────────────────────────────
// Summary
// ─────────────────────────────────────────────────────────────────────────────
export function handleSummary(data) {
    const now = new Date().toISOString();

    console.log('\n================================================================================');
    console.log('                    ext-authz PERFORMANCE TEST RESULTS');
    console.log('================================================================================');
    console.log(`Test Time     : ${now}`);
    console.log(`Target VUs    : ${VUS}`);
    console.log(`Duration      : ${DURATION}`);
    console.log('--------------------------------------------------------------------------------');

    // Request metrics
    const reqs = data.metrics.http_reqs;
    const latency = data.metrics.auth_latency;
    const successRate = data.metrics.auth_success;

    console.log('\nREQUEST METRICS');
    console.log('--------------------------------------------------------------------------------');
    console.log(`Total Requests: ${reqs ? reqs.values.count : 0}`);
    console.log(`RPS           : ${reqs ? (reqs.values.rate).toFixed(2) : 0}`);
    console.log(`Success Rate  : ${successRate ? (successRate.values.rate * 100).toFixed(2) : 0}%`);

    console.log('\nLATENCY (ext-authz included)');
    console.log('--------------------------------------------------------------------------------');
    if (latency) {
        console.log(`Min           : ${latency.values.min.toFixed(2)} ms`);
        console.log(`Avg           : ${latency.values.avg.toFixed(2)} ms`);
        console.log(`Med           : ${latency.values.med.toFixed(2)} ms`);
        console.log(`p90           : ${latency.values['p(90)'].toFixed(2)} ms`);
        console.log(`p95           : ${latency.values['p(95)'].toFixed(2)} ms`);
        console.log(`p99           : ${latency.values['p(99)'].toFixed(2)} ms`);
        console.log(`Max           : ${latency.values.max.toFixed(2)} ms`);
    }

    // Error breakdown
    const auth401Count = data.metrics.auth_401_responses ? data.metrics.auth_401_responses.values.count : 0;
    const auth403Count = data.metrics.auth_403_responses ? data.metrics.auth_403_responses.values.count : 0;

    if (auth401Count > 0 || auth403Count > 0) {
        console.log('\nERROR BREAKDOWN');
        console.log('--------------------------------------------------------------------------------');
        console.log(`401 Unauthorized: ${auth401Count}`);
        console.log(`403 Forbidden   : ${auth403Count}`);
    }

    console.log('\n================================================================================');
    console.log('                              TEST COMPLETE');
    console.log('================================================================================\n');

    return {
        stdout: '',
    };
}
