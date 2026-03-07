# Event Router 아키텍처 개선안 리포트

**작성일**: 2026-01-22
**대상 코드**: `apps/event_router/`, `apps/sse_gateway/`

---

## 1. Executive Summary

Event Router는 Redis Streams → Pub/Sub 기반의 실시간 이벤트 분배 시스템이다. 전반적으로 잘 설계되어 있으나, **process_event 실패 시 ACK 처리**에 치명적인 버그가 있어 데이터 유실 위험이 존재한다. 이 외에도 몇 가지 운영 관점의 개선 사항을 제안한다.

### 발견된 이슈 요약

| 우선순위 | 이슈 | 위치 | 상태 |
|---------|------|------|------|
| **P0 Critical** | process_event 실패 시 ACK → 데이터 유실 | `consumer.py:216-223` | 수정 필요 |
| P1 | Reclaimer도 동일한 ACK 버그 | `reclaimer.py:166-172` | 수정 필요 |
| P1 | Reclaimer stream_id/stream_name 미주입 | `reclaimer.py:150-154` | 수정 필요 |
| P1 | Reclaimer 단일 도메인만 지원 | `reclaimer.py:45-46` | 개선 필요 |
| P2 | SSE 엔드포인트 인증 없음 | `stream.py:140, 206` | 검토 필요 |
| P2 | xgroup_create id="0" 재배포 시 재처리 | `consumer.py:89` | 문서화 필요 |
| P3 | Multi-shard 공정성 (HOL blocking) | `consumer.py:147-153` | 모니터링 권장 |

### 이미 잘 구현된 부분

| 항목 | 위치 | 설명 |
|------|------|------|
| stream_id 주입 (Consumer) | `consumer.py:187` | ✅ Redis Stream ID를 이벤트에 주입 |
| stream_id 기반 중복 필터링 | `broadcast_manager.py:182-190` | ✅ SSE에서 단조 증가 ID로 중복 방지 |

**주의**: Reclaimer는 stream_id를 주입하지 않음 (P1 이슈 참조)
| Token/Stage seq 분리 | `broadcast_manager.py:102-107` | ✅ `last_token_seq`와 `last_stream_id` 분리 |
| Token v2 복구 | `broadcast_manager.py:995-1094` | ✅ Token Stream + State 기반 복구 |
| Lua Script 멱등성 | `processor.py:63-99` | ✅ `router:published:{job_id}:{seq}` 마킹 |
| Pub/Sub 재시도 | `processor.py:284-319` | ✅ 3회 exponential backoff |

---

## 2. Critical Issues

### 2.1 [P0] process_event 실패 시 ACK → 데이터 유실

**위치**: `consumer.py:202-233`

```python
# 현재 코드 (문제)
try:
    await self._processor.process_event(event, stream_name=stream_name)
except Exception as e:
    logger.error("process_event_error", ...)
    # 처리 실패해도 ACK (재처리는 reclaimer가 담당)  ← 잘못된 주석
    # 또는 Pending 상태로 유지하려면 continue

# ACK - 실패해도 항상 실행됨!
try:
    await self._redis.xack(stream_name, self._consumer_group, msg_id)
```

**문제점**:
- `process_event` 실패 시에도 `XACK`가 실행됨
- ACK되면 메시지가 PEL(Pending Entries List)에서 제거됨
- Reclaimer는 **PEL에 있는 메시지만** 재할당 가능
- 따라서 실패한 메시지는 **영구 유실**됨

**영향**:
- 사용자에게 중간 이벤트(vision, rule 등) 전달 누락
- done 이벤트 유실 시 클라이언트 무한 대기
- 네트워크 일시 장애 시 대량 데이터 유실 가능

**수정안**:

```python
# 개선된 코드
try:
    success = await self._processor.process_event(event, stream_name=stream_name)
    if not success:
        # Pub/Sub 발행 실패 - PEL에 유지하여 reclaimer가 재시도
        logger.warning("process_event_pubsub_failed", extra={...})
        continue  # ACK 스킵
except Exception as e:
    logger.error("process_event_error", extra={...})
    # 처리 실패 - PEL에 유지
    continue  # ACK 스킵 (reclaimer가 재할당)

# 성공한 경우만 ACK
try:
    await self._redis.xack(stream_name, self._consumer_group, msg_id)
```

---

### 2.2 [P1] Reclaimer 동일 ACK 버그

**위치**: `reclaimer.py:152-172`

```python
try:
    await self._processor.process_event(event)
    processed_count += 1
except Exception as e:
    logger.error("reclaim_process_error", ...)

# ACK - 여기도 실패 시 ACK함!
try:
    await self._redis.xack(stream_name, self._consumer_group, msg_id)
```

**문제점**: Consumer와 동일한 버그. 실패해도 ACK하여 메시지 영구 유실.

**수정안**: Consumer와 동일하게 실패 시 `continue`로 ACK 스킵.

---

### 2.3 [P1] Reclaimer 단일 도메인만 지원

**위치**: `reclaimer.py:45-46`

```python
self._stream_prefix = stream_prefix  # 기본값: "scan:events"
self._shard_count = shard_count      # 기본값: 4
```

**문제점**:
- Consumer는 `stream_configs: list[tuple[str, int]]`로 멀티 도메인 지원
- Reclaimer는 단일 `stream_prefix`만 지원
- `chat:events` Pending 메시지는 재할당되지 않음

**수정안**: Consumer와 동일하게 `stream_configs` 지원 추가

```python
def __init__(
    self,
    ...,
    stream_configs: list[tuple[str, int]] | None = None,
    ...
) -> None:
    self._stream_configs = stream_configs or [("scan:events", 4)]
```

---

### 2.4 [P1] Reclaimer stream_id/stream_name 미주입

**위치**: `reclaimer.py:150-154`

```python
# 현재 코드 (문제)
event = self._parse_event(data)

try:
    # stream_id 주입 없음!
    # stream_name 전달 없음!
    await self._processor.process_event(event)
```

**비교 - Consumer는 정상**:
```python
# consumer.py:183-203
event = self._parse_event(data)
event["stream_id"] = msg_id  # ✅ 주입
await self._processor.process_event(event, stream_name=stream_name)  # ✅ 전달
```

**문제점**:

| 경로 | stream_id | stream_name | 결과 |
|------|-----------|-------------|------|
| Consumer → Processor | ✅ | ✅ | 정상 동작 |
| Reclaimer → Processor | ❌ | ❌ | **버그** |

1. **stream_id 누락**: SSE Gateway의 `last_stream_id` 기반 중복 필터링 우회
   - 클라이언트가 동일 이벤트 중복 수신
2. **stream_name 누락**: `_get_state_prefix()` 기본값 `scan:state` 사용
   - chat 도메인 이벤트가 `scan:state:{job_id}`에 저장됨

**수정안**:

```python
# reclaimer.py:146-154 수정
for msg_id, data in messages:
    if isinstance(msg_id, bytes):
        msg_id = msg_id.decode()

    event = self._parse_event(data)
    event["stream_id"] = msg_id  # 추가: stream_id 주입

    try:
        # stream_key 전달 추가
        await self._processor.process_event(event, stream_name=stream_key)
        processed_count += 1
```

---

## 3. Security / Operational Issues

### 3.1 [P2] SSE 엔드포인트 인증 없음

**위치**: `stream.py:138-141, 204-212`

```python
@router.get("/stream")
async def stream_events(
    request: Request,
    job_id: str = Query(..., min_length=10),  # job_id만 검증
) -> EventSourceResponse:
```

**문제점**:
- `job_id`를 알면 누구나 구독 가능
- UUID v4는 추측 어려우나 URL 노출, 로그 유출 시 문제
- 다른 사용자의 채팅 내용 탈취 가능성

**권장안**:
1. **JWT 토큰 검증**: Authorization 헤더 또는 쿼리 파라미터
2. **권한 확인**: job_id 소유자 검증 (chat: user_id, scan: session ownership)
3. **Rate limiting**: IP 또는 user 기준 연결 수 제한

```python
@router.get("/{service}/{job_id}/events")
async def stream_events_restful(
    request: Request,
    service: str,
    job_id: str,
    # 추가
    user: AuthenticatedUser = Depends(get_current_user),
):
    # 권한 검증
    if not await verify_job_ownership(user.id, job_id, service):
        raise HTTPException(403, "Access denied")
```

---

### 3.2 [P2] xgroup_create id="0" 재배포 시 재처리

**위치**: `consumer.py:86-91`

```python
await self._redis.xgroup_create(
    stream_key,
    self._consumer_group,
    id="0",      # 처음부터 읽기
    mkstream=True,
)
```

**현상**:
- 새 Consumer Group 생성 시 `id="0"`은 Stream 처음부터 읽기
- 이미 처리된 이벤트도 다시 읽음
- Lua Script의 `router:published:{job_id}:{seq}` 마킹으로 멱등성 보장됨

**잠재적 문제**:
- `published_ttl=7200` (2시간) 이후 마킹 만료
- 이때 재배포하면 오래된 이벤트 재처리 가능
- State KV가 오래된 데이터로 덮어씌워질 수 있음

**권장안**:
1. **운영 문서화**: 재배포 시 기존 Consumer Group 유지 또는 최신 ID로 생성
2. **xgroup_create 시 `$` 사용 검토**: 새 메시지만 읽기 (단, 재시작 시 유실 가능)
3. **State TTL과 Published TTL 일치**: 둘 다 동일한 TTL로 설정

```python
# 권장: 재배포 시에도 안전한 방식
# XINFO GROUPS로 기존 Group 확인 후 없을 때만 생성
group_info = await self._redis.xinfo_groups(stream_key)
if not any(g["name"] == self._consumer_group for g in group_info):
    await self._redis.xgroup_create(
        stream_key,
        self._consumer_group,
        id="$",  # 새 메시지부터
        mkstream=True,
    )
```

---

### 3.3 [P3] Multi-shard HOL Blocking

**위치**: `consumer.py:147-153`

```python
events = await self._redis.xreadgroup(
    groupname=self._consumer_group,
    consumername=self._consumer_name,
    streams=self._streams,  # 모든 shard 동시 읽기
    count=self._count,      # 전체 count
    block=self._block_ms,
)
```

**현상**:
- 단일 XREADGROUP으로 모든 shard에서 읽음
- Redis는 `count`만큼 메시지 반환 (각 shard 균등 보장 안됨)
- 특정 shard에 메시지가 몰리면 다른 shard 이벤트 지연 가능

**권장안**:
1. **모니터링 우선**: `EVENT_ROUTER_XREADGROUP_BATCH_SIZE` 메트릭으로 편중 확인
2. **심각 시 개선**: shard별 별도 Consumer 또는 round-robin 읽기

---

## 4. SSE 표준 준수 관련

### 4.1 event_id와 Last-Event-ID

**현황**:
- SSE 응답에 `id:` 필드 미사용
- `last_token_seq` 쿼리 파라미터로 복구 (비표준)

**SSE 표준**:
```
id: 1737415902456-0
event: token
data: {"seq": 100, "content": "Hello"}

id: 1737415902457-0
event: done
data: {"stage": "done"}
```

**권장안**: SSE `id:` 필드에 `stream_id` 사용

```python
# stream.py - event_generator 수정
yield {
    "event": stage,
    "data": json.dumps(event),
    "id": event.get("stream_id", ""),  # SSE id 필드
}
```

클라이언트 재연결 시 `Last-Event-ID` 헤더 자동 전송되어 표준 복구 가능.

---

### 4.2 Heartbeat/Keepalive

**현황**: `timeout_seconds=15.0`마다 keepalive 전송 (양호)

**개선점**:
- 프록시(Nginx, Istio) timeout 고려하여 간격 조정 (기본 60초 미만)
- 현재 15초는 적절함

---

## 5. 구현 개선 제안

### 5.1 Token/Stage seq 네임스페이스 (이미 양호)

**검토 결과**: 이미 분리됨

```python
# broadcast_manager.py - SubscriberQueue
last_token_seq: int = field(default=-1)    # 토큰 전용
last_stream_id: str = field(default="0-0")  # Stage 이벤트용 (Redis Stream ID)
last_seq: int = field(default=-1)           # catch-up용 (레거시)
```

**결론**: 현재 설계가 올바름. Token과 Stage seq 충돌 없음.

---

### 5.2 stream_id 주입 (이미 양호)

**검토 결과**: 이미 구현됨

```python
# consumer.py:185-187
# Stream ID를 이벤트에 추가 (단조 증가 보장)
# SSE Gateway에서 중복 필터링에 사용
event["stream_id"] = msg_id
```

**결론**: Redis Stream ID가 이벤트에 주입되어 SSE Gateway에서 중복 필터링에 활용됨.

---

## 6. 개선 우선순위 및 작업 항목

### Phase 1 (Critical - 즉시)

| 작업 | 예상 영향 | 위험도 |
|------|----------|--------|
| consumer.py ACK 버그 수정 | 데이터 유실 방지 | 낮음 (로직 변경만) |
| reclaimer.py ACK 버그 수정 | 재처리 정상화 | 낮음 |
| reclaimer.py stream_id/stream_name 주입 | 중복 수신 방지, 도메인 정상화 | 낮음 |
| reclaimer.py 멀티 도메인 지원 | chat 도메인 커버리지 | 낮음 |

### Phase 2 (Important - 1~2주 내)

| 작업 | 예상 영향 | 위험도 |
|------|----------|--------|
| SSE 엔드포인트 인증 추가 | 보안 강화 | 중간 (API 변경) |
| SSE id 필드 추가 | 표준 준수 | 낮음 |
| xgroup_create 운영 문서 작성 | 운영 안정성 | 없음 |

### Phase 3 (Nice-to-have)

| 작업 | 예상 영향 | 위험도 |
|------|----------|--------|
| Multi-shard 공정성 모니터링 | 성능 가시성 | 없음 |
| shard별 Consumer 분리 (필요 시) | 지연 방지 | 중간 |

---

## 7. 결론

Event Router의 전체 아키텍처(Streams → Router → Pub/Sub + State)는 잘 설계되어 있다:
- 멱등성 보장 (Lua Script)
- Token/Stage 분리
- stream_id 기반 중복 필터링
- Token v2 복구 메커니즘

그러나 **ACK 정책 버그**는 치명적이며 즉시 수정이 필요하다. 실패한 이벤트를 PEL에 유지해야 Reclaimer가 재처리할 수 있다. 이 수정과 함께 Reclaimer의 멀티 도메인 지원을 추가하면 안정적인 이벤트 분배 시스템이 완성된다.

---

## Appendix: 코드 수정 예시

### A. consumer.py 수정

```python
# consumer.py:202-233 수정
for msg_id, data in messages:
    # ... 파싱 ...

    try:
        success = await self._processor.process_event(event, stream_name=stream_name)
        if not success:
            # Pub/Sub 발행 실패 - PEL에 유지
            logger.warning(
                "process_event_pubsub_failed",
                extra={"stream": stream_name, "msg_id": msg_id, "job_id": event.get("job_id")},
            )
            continue  # ACK 스킵
    except Exception as e:
        logger.error(
            "process_event_error",
            extra={"stream": stream_name, "msg_id": msg_id, "error": str(e)},
        )
        continue  # ACK 스킵 - reclaimer가 재할당

    # 성공한 경우만 ACK
    try:
        await self._redis.xack(stream_name, self._consumer_group, msg_id)
        EVENT_ROUTER_XACK_TOTAL.labels(result="success").inc()
    except Exception as e:
        EVENT_ROUTER_XACK_TOTAL.labels(result="error").inc()
        logger.error("xack_error", extra={"stream": stream_name, "msg_id": msg_id, "error": str(e)})
```

### B. reclaimer.py 수정

```python
# reclaimer.py:146-181 수정
async def _process_reclaimed(self, stream_key: str, messages: list[...]) -> int:
    processed_count = 0

    for msg_id, data in messages:
        if isinstance(msg_id, bytes):
            msg_id = msg_id.decode()

        event = self._parse_event(data)
        event["stream_id"] = msg_id  # 추가: stream_id 주입 (Consumer와 동일)

        try:
            # stream_key 전달 추가
            success = await self._processor.process_event(event, stream_name=stream_key)
            if not success:
                logger.warning("reclaim_pubsub_failed", extra={...})
                continue  # ACK 스킵
            processed_count += 1
        except Exception as e:
            logger.error("reclaim_process_error", extra={...})
            continue  # ACK 스킵

        # 성공한 경우만 ACK
        try:
            await self._redis.xack(stream_key, self._consumer_group, msg_id)
        except Exception as e:
            logger.error("reclaim_xack_error", extra={...})

    return processed_count
```
