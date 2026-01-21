"""SubscriberQueue Timestamp-based Filtering Tests."""

import time

import pytest

from sse_gateway.core.broadcast_manager import SubscriberQueue


class TestSubscriberQueueTimestampFiltering:
    """Timestamp 기반 중복 필터링 테스트."""

    @pytest.mark.asyncio
    async def test_allows_events_with_increasing_timestamp(self):
        """증가하는 timestamp를 가진 이벤트는 모두 허용."""
        queue = SubscriberQueue(job_id="test-1")

        event1 = {"stage": "intent", "status": "started", "timestamp": 1000.0, "seq": 10}
        event2 = {"stage": "intent", "status": "completed", "timestamp": 1001.0, "seq": 11}

        assert await queue.put_event(event1) is True
        assert await queue.put_event(event2) is True
        assert queue.queue.qsize() == 2

    @pytest.mark.asyncio
    async def test_filters_duplicate_event_with_same_timestamp(self):
        """같은 timestamp를 가진 중복 이벤트는 필터링."""
        queue = SubscriberQueue(job_id="test-2")

        event1 = {"stage": "weather", "status": "started", "timestamp": 2000.0, "seq": 80}
        event2 = {"stage": "weather", "status": "started", "timestamp": 2000.0, "seq": 80}

        assert await queue.put_event(event1) is True
        assert await queue.put_event(event2) is False  # 중복
        assert queue.queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_filters_old_timestamp_for_same_event(self):
        """더 오래된 timestamp를 가진 이벤트는 필터링."""
        queue = SubscriberQueue(job_id="test-3")

        event1 = {"stage": "kakao_place", "status": "started", "timestamp": 3000.0, "seq": 60}
        event2 = {"stage": "kakao_place", "status": "started", "timestamp": 2999.0, "seq": 60}

        assert await queue.put_event(event1) is True
        assert await queue.put_event(event2) is False  # 더 오래됨
        assert queue.queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_allows_parallel_stages_with_out_of_order_seq(self):
        """병렬 실행 시 seq가 역순이어도 timestamp로 허용 (핵심 테스트)."""
        queue = SubscriberQueue(job_id="test-4")

        # 기존 seq 기반에서는 이 순서가 문제였음:
        # weather:started (seq=80) 먼저 도착
        # kakao_place:started (seq=60) 나중 도착 → DROP (60 <= 80)

        weather = {"stage": "weather", "status": "started", "timestamp": 4000.0, "seq": 80}
        kakao = {"stage": "kakao_place", "status": "started", "timestamp": 4001.0, "seq": 60}

        assert await queue.put_event(weather) is True
        assert await queue.put_event(kakao) is True  # ✅ timestamp 기반이므로 허용!
        assert queue.queue.qsize() == 2

    @pytest.mark.asyncio
    async def test_allows_done_after_needs_input(self):
        """needs_input(seq=180) 이후 done(seq=171)도 허용."""
        queue = SubscriberQueue(job_id="test-5")

        needs_input = {"stage": "needs_input", "status": "started", "timestamp": 5000.0, "seq": 180}
        done = {"stage": "done", "status": "completed", "timestamp": 5001.0, "seq": 171}

        assert await queue.put_event(needs_input) is True
        assert await queue.put_event(done) is True  # ✅ timestamp 기반이므로 허용!
        assert queue.queue.qsize() == 2

    @pytest.mark.asyncio
    async def test_different_stages_are_independent(self):
        """다른 stage는 독립적으로 중복 체크."""
        queue = SubscriberQueue(job_id="test-6")

        event1 = {"stage": "intent", "status": "started", "timestamp": 6000.0, "seq": 10}
        event2 = {"stage": "weather", "status": "started", "timestamp": 6000.0, "seq": 80}

        # 다른 stage이므로 같은 timestamp여도 허용
        assert await queue.put_event(event1) is True
        assert await queue.put_event(event2) is True
        assert queue.queue.qsize() == 2

    @pytest.mark.asyncio
    async def test_same_stage_different_status_are_independent(self):
        """같은 stage의 다른 status는 독립적."""
        queue = SubscriberQueue(job_id="test-7")

        started = {"stage": "answer", "status": "started", "timestamp": 7000.0, "seq": 160}
        completed = {"stage": "answer", "status": "completed", "timestamp": 7000.0, "seq": 161}

        # 같은 timestamp여도 status가 다르므로 허용
        assert await queue.put_event(started) is True
        assert await queue.put_event(completed) is True
        assert queue.queue.qsize() == 2

    @pytest.mark.asyncio
    async def test_last_seq_still_updated_for_catch_up(self):
        """timestamp 필터링이지만 last_seq는 catch-up을 위해 계속 업데이트."""
        queue = SubscriberQueue(job_id="test-8")

        assert queue.last_seq == -1

        event1 = {"stage": "intent", "status": "started", "timestamp": 8000.0, "seq": 10}
        event2 = {"stage": "weather", "status": "started", "timestamp": 8001.0, "seq": 80}
        event3 = {"stage": "kakao_place", "status": "started", "timestamp": 8002.0, "seq": 60}

        await queue.put_event(event1)
        assert queue.last_seq == 10

        await queue.put_event(event2)
        assert queue.last_seq == 80  # max seq 추적

        await queue.put_event(event3)
        assert queue.last_seq == 80  # 60은 80보다 작으므로 유지

    @pytest.mark.asyncio
    async def test_invalid_timestamp_treated_as_zero(self):
        """잘못된 timestamp는 0으로 처리."""
        queue = SubscriberQueue(job_id="test-9")

        event1 = {"stage": "intent", "status": "started", "timestamp": "invalid", "seq": 10}
        event2 = {"stage": "intent", "status": "started", "timestamp": 0, "seq": 10}

        assert await queue.put_event(event1) is True  # timestamp=0으로 처리
        assert await queue.put_event(event2) is False  # 0 <= 0 → 중복

    @pytest.mark.asyncio
    async def test_missing_timestamp_treated_as_zero(self):
        """timestamp 없으면 0으로 처리."""
        queue = SubscriberQueue(job_id="test-10")

        event1 = {"stage": "intent", "status": "started", "seq": 10}  # timestamp 없음
        event2 = {"stage": "intent", "status": "started", "timestamp": 1, "seq": 10}

        assert await queue.put_event(event1) is True  # timestamp=0
        assert await queue.put_event(event2) is True  # 1 > 0

    @pytest.mark.asyncio
    async def test_real_world_parallel_execution_scenario(self):
        """실제 병렬 실행 시나리오 전체 테스트."""
        queue = SubscriberQueue(job_id="test-11")
        base_ts = time.time()

        # 순차 실행
        events = [
            {"stage": "queued", "status": "started", "timestamp": base_ts, "seq": 0},
            {"stage": "queued", "status": "completed", "timestamp": base_ts + 0.1, "seq": 1},
            {"stage": "intent", "status": "started", "timestamp": base_ts + 0.2, "seq": 10},
            {"stage": "intent", "status": "completed", "timestamp": base_ts + 0.3, "seq": 11},
        ]

        # 병렬 실행 (seq 역순 도착)
        parallel_events = [
            {"stage": "weather", "status": "started", "timestamp": base_ts + 0.4, "seq": 80},
            {"stage": "character", "status": "started", "timestamp": base_ts + 0.5, "seq": 40},
            {"stage": "kakao_place", "status": "started", "timestamp": base_ts + 0.6, "seq": 60},
            {"stage": "location", "status": "started", "timestamp": base_ts + 0.7, "seq": 50},
        ]

        # 완료
        final_events = [
            {"stage": "aggregator", "status": "started", "timestamp": base_ts + 1.0, "seq": 140},
            {"stage": "answer", "status": "started", "timestamp": base_ts + 1.1, "seq": 160},
            {"stage": "done", "status": "completed", "timestamp": base_ts + 1.2, "seq": 171},
        ]

        all_events = events + parallel_events + final_events

        for event in all_events:
            result = await queue.put_event(event)
            assert result is True, f"Event {event['stage']}:{event['status']} should be accepted"

        assert queue.queue.qsize() == len(all_events)

    @pytest.mark.asyncio
    async def test_done_after_hitl_scenario(self):
        """HITL 후 done 이벤트 시나리오."""
        queue = SubscriberQueue(job_id="test-12")
        base_ts = time.time()

        events = [
            {"stage": "intent", "status": "completed", "timestamp": base_ts, "seq": 11},
            {"stage": "bulk_waste", "status": "started", "timestamp": base_ts + 0.1, "seq": 70},
            # HITL 트리거 (seq가 가장 높음)
            {"stage": "needs_input", "status": "started", "timestamp": base_ts + 0.2, "seq": 180},
            # 사용자 입력 후 재처리
            {"stage": "bulk_waste", "status": "completed", "timestamp": base_ts + 1.0, "seq": 71},
            {"stage": "aggregator", "status": "started", "timestamp": base_ts + 1.1, "seq": 140},
            {"stage": "answer", "status": "started", "timestamp": base_ts + 1.2, "seq": 160},
            # done이 needs_input보다 낮은 seq
            {"stage": "done", "status": "completed", "timestamp": base_ts + 1.3, "seq": 171},
        ]

        for event in events:
            result = await queue.put_event(event)
            assert result is True, f"Event {event['stage']} should be accepted"

        assert queue.queue.qsize() == len(events)
