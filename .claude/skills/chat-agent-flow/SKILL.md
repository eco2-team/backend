---
name: chat-agent-flow
description: Eco² Chat 서비스 E2E 테스트 및 디버깅 가이드. API 엔드포인트, SSE 이벤트 스트림, Redis Streams 파이프라인, Intent 분류 시스템. Use when: (1) Chat API E2E 테스트 시, (2) SSE 이벤트 수신 문제 해결 시, (3) Intent 분류/라우팅 확인 시, (4) Redis Streams 이벤트 파이프라인 디버깅 시.
---

# Chat Agent Flow Guide

> Chat 서비스 E2E 테스트 및 이벤트 파이프라인 가이드

## Quick Reference

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Chat Agent E2E Flow                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  [1] POST /api/v1/chat              →  Create session (chat_id)             │
│  [2] POST /api/v1/chat/{id}/messages →  Send message (job_id)               │
│  [3] GET  /api/v1/chat/{job_id}/events →  Subscribe SSE (via chat-vs)       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## API Endpoints

| Step | Endpoint | Response |
|------|----------|----------|
| 1 | `POST /api/v1/chat` | `{id, title, created_at}` |
| 2 | `POST /api/v1/chat/{chat_id}/messages` | `{job_id, stream_url, status}` |
| 3 | `GET /api/v1/chat/{job_id}/events` | SSE stream |

## E2E Test Commands

```bash
TOKEN="<JWT_TOKEN>"

# 1. Create chat session
CHAT_RESPONSE=$(curl -s -X POST "https://api.dev.growbin.app/api/v1/chat" \
  -H "Content-Type: application/json" \
  -H "Cookie: s_access=$TOKEN" \
  -d '{"title": "E2E Test"}')
CHAT_ID=$(echo $CHAT_RESPONSE | jq -r '.id')

# 2. Send message
MSG_RESPONSE=$(curl -s -X POST "https://api.dev.growbin.app/api/v1/chat/${CHAT_ID}/messages" \
  -H "Content-Type: application/json" \
  -H "Cookie: s_access=$TOKEN" \
  -d '{"message": "플라스틱 분리배출 방법 알려줘"}')
JOB_ID=$(echo $MSG_RESPONSE | jq -r '.job_id')

# 3. Subscribe SSE
curl -sN --max-time 60 \
  "https://api.dev.growbin.app/api/v1/chat/${JOB_ID}/events" \
  -H "Accept: text/event-stream" \
  -H "Cookie: s_access=$TOKEN"
```

## Intent Classification (10 types)

| Intent | Node | Test Message |
|--------|------|--------------|
| `waste` | waste_rag | "플라스틱 분리배출 방법 알려줘" |
| `bulk_waste` | bulk_waste | "소파 버리려면 어떻게 해?" |
| `character` | character | "플라스틱 버리면 어떤 캐릭터 얻어?" |
| `location` | location | "근처 제로웨이스트샵 알려줘" |
| `collection_point` | collection_point | "근처 의류수거함 어디야?" |
| `recyclable_price` | recyclable_price | "고철 시세 얼마야?" |
| `web_search` | web_search | "최신 분리배출 정책 알려줘" |
| `image_generation` | image_generation | "페트병 버리는 법 이미지로 만들어줘" |
| `general` | general | "안녕하세요" |
| (enrichment) | weather | 자동 추가 (waste, bulk_waste) |

## SSE Event Types

| Event | Description |
|-------|-------------|
| `intent` | Intent 분류 완료 |
| `{node}` | 서브에이전트 시작/완료 |
| `token` | 답변 토큰 스트리밍 |
| `done` | 처리 완료 |
| `error` | 오류 발생 |

## Redis Streams Pipeline

```
chat-worker → XADD chat:events:{0-3} → event-router → PUBLISH sse:events:{job_id} → sse-gateway
```

| Instance | Purpose |
|----------|---------|
| `rfr-streams-redis` | Event Streams (XADD/XREADGROUP) |
| `rfr-pubsub-redis` | SSE Broadcast (PUBLISH/SUBSCRIBE) |

## Debug Commands

```bash
# Worker logs
kubectl logs -n chat -l app=chat-worker -f --tail=100

# Event Router logs
kubectl logs -n event-router -l app=event-router -f --tail=50

# Redis Streams check
kubectl exec -n redis rfr-streams-redis-0 -c redis -- redis-cli XLEN chat:events:0
kubectl exec -n redis rfr-streams-redis-0 -c redis -- redis-cli XINFO GROUPS chat:events:0

# Pub/Sub monitoring
kubectl exec -n redis rfr-pubsub-redis-0 -c redis -- redis-cli PSUBSCRIBE "sse:events:*"
```

## Reference Files

- **Architecture**: See [architecture.md](references/architecture.md) - 전체 시스템 아키텍처
- **E2E Test Script**: See [e2e-test-script.md](references/e2e-test-script.md) - Intent별 테스트 케이스
- **Troubleshooting**: See [troubleshooting.md](references/troubleshooting.md) - 일반적인 문제 해결
- **Persistence Issues**: Use `chat-agent-persistence` skill

## Related Documents

| Document | Path |
|----------|------|
| E2E Test Results | `docs/reports/e2e-intent-test-results-2026-01-18.md` |
| VirtualService | `workloads/routing/chat/base/virtual-service.yaml` |
| Dynamic Routing | `docs/blogs/applied/30-langgraph-dynamic-routing-send-api.md` |
