"""SubscriberQueue Stream ID 기반 필터링 테스트.

정석 패턴:
- 토큰 이벤트: 전용 seq 기반 (last_token_seq)
- Stage 이벤트: Redis Stream ID 기반 (단조 증가 보장)

Stream ID 장점:
- 분산 환경에서도 순서 보장 (Redis가 발급)
- timestamp 기반의 clock skew 문제 없음
- 병렬 노드에서도 정상 이벤트 드랍 방지
"""

import pytest

from sse_gateway.core.broadcast_manager import SubscriberQueue


class TestSubscriberQueueStreamIdFiltering:
    """Stream ID 기반 중복 필터링 테스트."""

    @pytest.mark.asyncio
    async def test_allows_events_with_increasing_stream_id(self):
        """증가하는 stream_id를 가진 이벤트는 모두 허용."""
        queue = SubscriberQueue(job_id="test-1")

        event1 = {"stage": "intent", "status": "started", "stream_id": "1000-0", "seq": 10}
        event2 = {"stage": "intent", "status": "completed", "stream_id": "1001-0", "seq": 11}

        assert await queue.put_event(event1) is True
        assert await queue.put_event(event2) is True
        assert queue.queue.qsize() == 2

    @pytest.mark.asyncio
    async def test_filters_duplicate_event_with_same_stream_id(self):
        """같은 stream_id를 가진 중복 이벤트는 필터링."""
        queue = SubscriberQueue(job_id="test-2")

        event1 = {"stage": "weather", "status": "started", "stream_id": "2000-0", "seq": 80}
        event2 = {"stage": "weather", "status": "started", "stream_id": "2000-0", "seq": 80}

        assert await queue.put_event(event1) is True
        assert await queue.put_event(event2) is False  # 중복
        assert queue.queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_filters_old_stream_id(self):
        """더 오래된 stream_id를 가진 이벤트는 필터링."""
        queue = SubscriberQueue(job_id="test-3")

        event1 = {"stage": "kakao_place", "status": "started", "stream_id": "3000-0", "seq": 60}
        event2 = {"stage": "kakao_place", "status": "started", "stream_id": "2999-0", "seq": 60}

        assert await queue.put_event(event1) is True
        assert await queue.put_event(event2) is False  # 더 오래됨
        assert queue.queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_allows_parallel_stages_with_increasing_stream_id(self):
        """병렬 실행 시 seq 역순이어도 stream_id 증가하면 허용."""
        queue = SubscriberQueue(job_id="test-4")

        # 병렬 실행: Stream ID는 Redis가 발급하므로 단조 증가 보장
        weather = {"stage": "weather", "status": "started", "stream_id": "4000-0", "seq": 80}
        kakao = {"stage": "kakao_place", "status": "started", "stream_id": "4001-0", "seq": 60}

        assert await queue.put_event(weather) is True
        assert await queue.put_event(kakao) is True  # ✅ stream_id 증가하므로 허용!
        assert queue.queue.qsize() == 2

    @pytest.mark.asyncio
    async def test_allows_done_after_needs_input(self):
        """needs_input(seq=180) 이후 done(seq=171)도 stream_id 증가하면 허용."""
        queue = SubscriberQueue(job_id="test-5")

        needs_input = {
            "stage": "needs_input",
            "status": "started",
            "stream_id": "5000-0",
            "seq": 180,
        }
        done = {"stage": "done", "status": "completed", "stream_id": "5001-0", "seq": 171}

        assert await queue.put_event(needs_input) is True
        assert await queue.put_event(done) is True  # ✅ stream_id 증가하므로 허용!
        assert queue.queue.qsize() == 2

    @pytest.mark.asyncio
    async def test_last_seq_still_updated_for_catch_up(self):
        """stream_id 필터링이지만 last_seq는 catch-up을 위해 계속 업데이트."""
        queue = SubscriberQueue(job_id="test-6")

        assert queue.last_seq == -1

        event1 = {"stage": "intent", "status": "started", "stream_id": "6000-0", "seq": 10}
        event2 = {"stage": "weather", "status": "started", "stream_id": "6001-0", "seq": 80}
        event3 = {"stage": "kakao_place", "status": "started", "stream_id": "6002-0", "seq": 60}

        await queue.put_event(event1)
        assert queue.last_seq == 10

        await queue.put_event(event2)
        assert queue.last_seq == 80  # max seq 추적

        await queue.put_event(event3)
        assert queue.last_seq == 80  # 60은 80보다 작으므로 유지

    @pytest.mark.asyncio
    async def test_stream_id_seq_comparison(self):
        """stream_id 내 seq 부분도 비교."""
        queue = SubscriberQueue(job_id="test-7")

        # 같은 timestamp, 다른 seq
        event1 = {"stage": "intent", "status": "started", "stream_id": "7000-0", "seq": 10}
        event2 = {"stage": "intent", "status": "completed", "stream_id": "7000-1", "seq": 11}

        assert await queue.put_event(event1) is True
        assert await queue.put_event(event2) is True  # seq 부분이 더 큼
        assert queue.queue.qsize() == 2


class TestSubscriberQueueTokenFiltering:
    """토큰 이벤트 필터링 테스트 (전용 seq 기반)."""

    @pytest.mark.asyncio
    async def test_token_uses_dedicated_seq(self):
        """토큰은 전용 last_token_seq를 사용."""
        queue = SubscriberQueue(job_id="test-token-1")

        # Stage 이벤트로 last_seq 업데이트
        stage_event = {"stage": "intent", "status": "started", "stream_id": "1000-0", "seq": 100}
        await queue.put_event(stage_event)
        assert queue.last_seq == 100

        # 토큰은 자체 seq 시퀀스 (1001, 1002, ...)
        token1 = {"stage": "token", "status": "streaming", "seq": 1001}
        token2 = {"stage": "token", "status": "streaming", "seq": 1002}

        assert await queue.put_event(token1) is True
        assert await queue.put_event(token2) is True
        assert queue.last_token_seq == 1002
        assert queue.queue.qsize() == 3

    @pytest.mark.asyncio
    async def test_token_seq_independent_from_stage(self):
        """토큰 seq는 stage seq와 독립적."""
        queue = SubscriberQueue(job_id="test-token-2")

        # 높은 seq의 stage 이벤트
        stage_event = {"stage": "weather", "status": "started", "stream_id": "2000-0", "seq": 50000}
        await queue.put_event(stage_event)

        # 토큰은 1001부터 시작 (stage seq에 영향받지 않음)
        token1 = {"stage": "token", "status": "streaming", "seq": 1001}
        assert await queue.put_event(token1) is True  # ✅ 허용!

    @pytest.mark.asyncio
    async def test_token_duplicate_filtering(self):
        """토큰 중복 필터링."""
        queue = SubscriberQueue(job_id="test-token-3")

        token1 = {"stage": "token", "status": "streaming", "seq": 1001}
        token1_dup = {"stage": "token", "status": "streaming", "seq": 1001}
        token2 = {"stage": "token", "status": "streaming", "seq": 1002}

        assert await queue.put_event(token1) is True
        assert await queue.put_event(token1_dup) is False  # 중복
        assert await queue.put_event(token2) is True
        assert queue.queue.qsize() == 2

    @pytest.mark.asyncio
    async def test_token_out_of_order_filtering(self):
        """토큰 역순 필터링."""
        queue = SubscriberQueue(job_id="test-token-4")

        token1 = {"stage": "token", "status": "streaming", "seq": 1005}
        token2 = {"stage": "token", "status": "streaming", "seq": 1003}  # 역순

        assert await queue.put_event(token1) is True
        assert await queue.put_event(token2) is False  # 역순 → 필터링
        assert queue.queue.qsize() == 1


class TestSubscriberQueueStreamIdComparison:
    """Stream ID 비교 로직 테스트."""

    def test_compare_stream_id_basic(self):
        """기본 비교."""
        assert SubscriberQueue._compare_stream_id("1000-0", "999-0") == 1  # 1000 > 999
        assert SubscriberQueue._compare_stream_id("999-0", "1000-0") == -1  # 999 < 1000
        assert SubscriberQueue._compare_stream_id("1000-0", "1000-0") == 0  # equal

    def test_compare_stream_id_seq_part(self):
        """seq 부분 비교."""
        assert SubscriberQueue._compare_stream_id("1000-1", "1000-0") == 1  # seq 1 > 0
        assert SubscriberQueue._compare_stream_id("1000-0", "1000-1") == -1  # seq 0 < 1
        assert SubscriberQueue._compare_stream_id("1000-5", "1000-5") == 0  # equal

    def test_compare_stream_id_invalid(self):
        """잘못된 형식."""
        assert SubscriberQueue._compare_stream_id("invalid", "1000-0") == -1
        assert SubscriberQueue._compare_stream_id("1000-0", "invalid") == 1
        assert SubscriberQueue._compare_stream_id("", "1000-0") == -1
        assert SubscriberQueue._compare_stream_id("0-0", "0-0") == 0


class TestSubscriberQueueRealWorldScenario:
    """실제 시나리오 테스트."""

    @pytest.mark.asyncio
    async def test_full_chat_flow(self):
        """전체 채팅 플로우 시뮬레이션."""
        queue = SubscriberQueue(job_id="test-flow-1")
        base_ts = 1737415902000

        # 순차 이벤트
        events = [
            {"stage": "queued", "status": "started", "stream_id": f"{base_ts}-0", "seq": 0},
            {"stage": "queued", "status": "completed", "stream_id": f"{base_ts + 100}-0", "seq": 1},
            {"stage": "intent", "status": "started", "stream_id": f"{base_ts + 200}-0", "seq": 10},
            {
                "stage": "intent",
                "status": "completed",
                "stream_id": f"{base_ts + 300}-0",
                "seq": 11,
            },
        ]

        # 병렬 이벤트 (seq 역순이지만 stream_id는 증가)
        parallel_events = [
            {"stage": "weather", "status": "started", "stream_id": f"{base_ts + 400}-0", "seq": 80},
            {
                "stage": "character",
                "status": "started",
                "stream_id": f"{base_ts + 401}-0",
                "seq": 40,
            },
            {
                "stage": "kakao_place",
                "status": "started",
                "stream_id": f"{base_ts + 402}-0",
                "seq": 60,
            },
        ]

        # 토큰 이벤트
        token_events = [
            {"stage": "token", "status": "streaming", "seq": 1001},
            {"stage": "token", "status": "streaming", "seq": 1002},
            {"stage": "token", "status": "streaming", "seq": 1003},
        ]

        # 완료 이벤트
        final_events = [
            {
                "stage": "answer",
                "status": "completed",
                "stream_id": f"{base_ts + 1000}-0",
                "seq": 161,
            },
            {
                "stage": "done",
                "status": "completed",
                "stream_id": f"{base_ts + 1100}-0",
                "seq": 171,
            },
        ]

        all_events = events + parallel_events + token_events + final_events

        for event in all_events:
            result = await queue.put_event(event)
            assert (
                result is True
            ), f"Event {event.get('stage')}:{event.get('status')} should be accepted"

        assert queue.queue.qsize() == len(all_events)

    @pytest.mark.asyncio
    async def test_hitl_scenario(self):
        """HITL (Human-in-the-Loop) 시나리오."""
        queue = SubscriberQueue(job_id="test-hitl-1")
        base_ts = 1737415902000

        events = [
            {"stage": "intent", "status": "completed", "stream_id": f"{base_ts}-0", "seq": 11},
            {
                "stage": "bulk_waste",
                "status": "started",
                "stream_id": f"{base_ts + 100}-0",
                "seq": 70,
            },
            # HITL 트리거 (seq가 높음)
            {
                "stage": "needs_input",
                "status": "started",
                "stream_id": f"{base_ts + 200}-0",
                "seq": 180,
            },
            # 사용자 입력 후 재처리
            {
                "stage": "bulk_waste",
                "status": "completed",
                "stream_id": f"{base_ts + 1000}-0",
                "seq": 71,
            },
            {
                "stage": "aggregator",
                "status": "started",
                "stream_id": f"{base_ts + 1100}-0",
                "seq": 140,
            },
            # done이 needs_input보다 낮은 seq지만 stream_id가 더 크므로 허용
            {
                "stage": "done",
                "status": "completed",
                "stream_id": f"{base_ts + 1200}-0",
                "seq": 171,
            },
        ]

        for event in events:
            result = await queue.put_event(event)
            assert result is True, f"Event {event['stage']} should be accepted"

        assert queue.queue.qsize() == len(events)


class TestSubscriberQueueLegacyFallback:
    """Stream ID가 없는 경우 폴백 테스트."""

    @pytest.mark.asyncio
    async def test_event_without_stream_id_allowed(self):
        """stream_id가 없는 이벤트도 허용 (레거시 호환)."""
        queue = SubscriberQueue(job_id="test-legacy-1")

        # stream_id 없는 이벤트
        event1 = {"stage": "intent", "status": "started", "seq": 10}
        event2 = {"stage": "intent", "status": "completed", "seq": 11}

        assert await queue.put_event(event1) is True
        assert await queue.put_event(event2) is True
        assert queue.queue.qsize() == 2

    @pytest.mark.asyncio
    async def test_mixed_events_with_and_without_stream_id(self):
        """stream_id 있는 이벤트와 없는 이벤트 혼합."""
        queue = SubscriberQueue(job_id="test-legacy-2")

        event1 = {"stage": "intent", "status": "started", "stream_id": "1000-0", "seq": 10}
        event2 = {"stage": "weather", "status": "started", "seq": 80}  # stream_id 없음

        assert await queue.put_event(event1) is True
        assert await queue.put_event(event2) is True  # 허용 (stream_id 없으면 필터링 안함)
        assert queue.queue.qsize() == 2
