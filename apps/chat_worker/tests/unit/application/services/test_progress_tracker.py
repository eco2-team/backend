"""DynamicProgressTracker 단위 테스트."""

from __future__ import annotations

import pytest

from chat_worker.application.services.progress_tracker import (
    DynamicProgressTracker,
    PHASE_PROGRESS,
    SUBAGENT_NODES,
    get_stage_for_node,
    get_node_message,
)


class TestDynamicProgressTracker:
    """DynamicProgressTracker 테스트 스위트."""

    @pytest.fixture
    def tracker(self) -> DynamicProgressTracker:
        """테스트용 Tracker."""
        return DynamicProgressTracker()

    # ==========================================================
    # Phase Constants Tests
    # ==========================================================

    def test_phase_progress_has_required_phases(self):
        """필수 Phase가 정의되어 있어야 함."""
        required = ["queued", "intent", "vision", "subagents", "aggregator", "answer", "done"]
        for phase in required:
            assert phase in PHASE_PROGRESS

    def test_subagent_nodes_has_required_nodes(self):
        """필수 서브에이전트 노드가 정의되어 있어야 함."""
        required = ["waste_rag", "character", "location", "weather", "web_search"]
        for node in required:
            assert node in SUBAGENT_NODES

    # ==========================================================
    # Subagent Tracking Tests
    # ==========================================================

    def test_on_subagent_start_tracks_node(self, tracker: DynamicProgressTracker):
        """서브에이전트 시작 추적."""
        tracker.on_subagent_start("waste_rag")

        status = tracker.get_subagent_status()
        assert status["total"] == 1
        assert "waste_rag" in status["active"]

    def test_on_subagent_start_ignores_non_subagent(self, tracker: DynamicProgressTracker):
        """비서브에이전트 노드는 추적하지 않음."""
        tracker.on_subagent_start("intent")

        status = tracker.get_subagent_status()
        assert status["total"] == 0

    def test_on_subagent_end_tracks_completion(self, tracker: DynamicProgressTracker):
        """서브에이전트 완료 추적."""
        tracker.on_subagent_start("waste_rag")
        tracker.on_subagent_end("waste_rag")

        status = tracker.get_subagent_status()
        assert status["total"] == 1
        assert status["completed"] == 1
        assert "waste_rag" not in status["active"]

    def test_multiple_subagents_tracking(self, tracker: DynamicProgressTracker):
        """여러 서브에이전트 추적."""
        # 3개 시작
        tracker.on_subagent_start("waste_rag")
        tracker.on_subagent_start("weather")
        tracker.on_subagent_start("location")

        # 1개 완료
        tracker.on_subagent_end("weather")

        status = tracker.get_subagent_status()
        assert status["total"] == 3
        assert status["completed"] == 1
        assert set(status["active"]) == {"waste_rag", "location"}

    # ==========================================================
    # Progress Calculation Tests
    # ==========================================================

    def test_calculate_progress_queued(self, tracker: DynamicProgressTracker):
        """queued Phase Progress."""
        assert tracker.calculate_progress("queued", "started") == 0
        assert tracker.calculate_progress("queued", "completed") == 0

    def test_calculate_progress_intent(self, tracker: DynamicProgressTracker):
        """intent Phase Progress."""
        assert tracker.calculate_progress("intent", "started") == 5
        assert tracker.calculate_progress("intent", "completed") == 15

    def test_calculate_progress_answer(self, tracker: DynamicProgressTracker):
        """answer Phase Progress."""
        assert tracker.calculate_progress("answer", "started") == 75
        assert tracker.calculate_progress("answer", "completed") == 95

    def test_calculate_progress_done(self, tracker: DynamicProgressTracker):
        """done Phase Progress."""
        assert tracker.calculate_progress("done", "started") == 100
        assert tracker.calculate_progress("done", "completed") == 100

    def test_calculate_progress_unknown_phase(self, tracker: DynamicProgressTracker):
        """알 수 없는 Phase는 0 반환."""
        assert tracker.calculate_progress("unknown", "started") == 0

    # ==========================================================
    # Dynamic Subagent Progress Tests
    # ==========================================================

    def test_subagent_progress_no_activation(self, tracker: DynamicProgressTracker):
        """서브에이전트 미활성화 시 시작 값."""
        progress = tracker.calculate_progress("subagents", "started")
        assert progress == 20  # subagents.start

    def test_subagent_progress_all_active(self, tracker: DynamicProgressTracker):
        """서브에이전트 활성화만 된 경우 (완료 없음)."""
        tracker.on_subagent_start("waste_rag")
        tracker.on_subagent_start("weather")

        progress = tracker.calculate_progress("subagents", "started")
        # 0/2 완료 → 20 + (0/2) * 35 = 20
        assert progress == 20

    def test_subagent_progress_partial_completion(self, tracker: DynamicProgressTracker):
        """서브에이전트 부분 완료."""
        tracker.on_subagent_start("waste_rag")
        tracker.on_subagent_start("weather")
        tracker.on_subagent_start("location")

        tracker.on_subagent_end("weather")

        progress = tracker.calculate_progress("subagents", "completed")
        # 1/3 완료 → 20 + (1/3) * 35 ≈ 31
        assert progress == 31

    def test_subagent_progress_all_completion(self, tracker: DynamicProgressTracker):
        """서브에이전트 전체 완료."""
        tracker.on_subagent_start("waste_rag")
        tracker.on_subagent_start("weather")

        tracker.on_subagent_end("waste_rag")
        tracker.on_subagent_end("weather")

        progress = tracker.calculate_progress("subagents", "completed")
        # 2/2 완료 → 20 + (2/2) * 35 = 55
        assert progress == 55

    def test_subagent_progress_single_node(self, tracker: DynamicProgressTracker):
        """단일 서브에이전트 완료."""
        tracker.on_subagent_start("waste_rag")
        tracker.on_subagent_end("waste_rag")

        progress = tracker.calculate_progress("subagents", "completed")
        # 1/1 완료 → 20 + (1/1) * 35 = 55
        assert progress == 55

    # ==========================================================
    # Node to Phase Mapping Tests
    # ==========================================================

    def test_get_phase_for_subagent_node(self, tracker: DynamicProgressTracker):
        """서브에이전트 노드 → subagents Phase."""
        for node in ["waste_rag", "weather", "character", "location"]:
            assert tracker.get_phase_for_node(node) == "subagents"

    def test_get_phase_for_non_subagent_node(self, tracker: DynamicProgressTracker):
        """비서브에이전트 노드 → 매핑된 Phase."""
        assert tracker.get_phase_for_node("intent") == "intent"
        assert tracker.get_phase_for_node("answer") == "answer"

    def test_get_phase_for_unknown_node(self, tracker: DynamicProgressTracker):
        """알 수 없는 노드 → 기본 subagents Phase."""
        assert tracker.get_phase_for_node("unknown_node") == "subagents"

    def test_is_subagent(self, tracker: DynamicProgressTracker):
        """서브에이전트 판별."""
        assert tracker.is_subagent("waste_rag") is True
        assert tracker.is_subagent("intent") is False
        assert tracker.is_subagent("answer") is False

    # ==========================================================
    # Reset Tests
    # ==========================================================

    def test_reset_clears_tracking(self, tracker: DynamicProgressTracker):
        """reset()이 추적 상태를 초기화."""
        tracker.on_subagent_start("waste_rag")
        tracker.on_subagent_end("waste_rag")

        tracker.reset()

        status = tracker.get_subagent_status()
        assert status["total"] == 0
        assert status["completed"] == 0
        assert status["active"] == []

    # ==========================================================
    # Edge Cases
    # ==========================================================

    def test_end_without_start(self, tracker: DynamicProgressTracker):
        """시작 없이 완료 호출 (엣지 케이스)."""
        tracker.on_subagent_end("waste_rag")

        status = tracker.get_subagent_status()
        # completed에는 추가되지만 total은 0
        assert status["completed"] == 1  # frozenset 체크로 추가됨

    def test_duplicate_start(self, tracker: DynamicProgressTracker):
        """중복 시작 호출."""
        tracker.on_subagent_start("waste_rag")
        tracker.on_subagent_start("waste_rag")

        status = tracker.get_subagent_status()
        assert status["total"] == 1  # set이므로 중복 무시


class TestGetStageForNode:
    """get_stage_for_node 함수 테스트.

    노드명 = Stage명 (1:1 매핑).
    """

    def test_waste_rag_same_as_stage(self):
        """waste_rag 노드는 그대로 waste_rag stage."""
        assert get_stage_for_node("waste_rag") == "waste_rag"

    def test_aggregator_same_as_stage(self):
        """aggregator 노드는 그대로 aggregator stage."""
        assert get_stage_for_node("aggregator") == "aggregator"

    def test_weather_same_as_stage(self):
        """weather 노드는 그대로 weather stage."""
        assert get_stage_for_node("weather") == "weather"

    def test_location_same_as_stage(self):
        """location 노드는 그대로 location stage."""
        assert get_stage_for_node("location") == "location"

    def test_character_same_as_stage(self):
        """character 노드는 그대로 character stage."""
        assert get_stage_for_node("character") == "character"

    def test_any_node_returns_itself(self):
        """모든 노드는 그대로 반환."""
        assert get_stage_for_node("any_node") == "any_node"


class TestGetNodeMessage:
    """get_node_message 함수 테스트."""

    def test_weather_started_message(self):
        """weather 노드 started 메시지."""
        msg = get_node_message("weather", "started")
        assert "날씨" in msg

    def test_weather_completed_message(self):
        """weather 노드 completed 메시지."""
        msg = get_node_message("weather", "completed")
        assert "완료" in msg

    def test_general_started_message(self):
        """general 노드 started 메시지."""
        msg = get_node_message("general", "started")
        assert "응답" in msg

    def test_kakao_place_started_message(self):
        """kakao_place 노드 started 메시지."""
        msg = get_node_message("kakao_place", "started")
        assert "장소" in msg

    def test_unknown_node_fallback(self):
        """알 수 없는 노드는 기본 포맷 반환."""
        msg = get_node_message("unknown_node", "started")
        assert msg == "unknown_node started"
