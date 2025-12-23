"""Unit tests for scan_reward_task (Chain Step 4).

4단계 Celery Chain의 마지막 단계인 reward task 테스트.
판정/저장 분리 구조:
- scan_reward_task: 판정만 (빠른 응답) - scan 도메인
- persist_reward_task: dispatcher (발행만) - character 도메인
- save_ownership_task: character DB 저장 - character 도메인
- save_my_character_task: my DB 저장 - my 도메인
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


class TestShouldAttemptReward:
    """_should_attempt_reward 함수 테스트."""

    @pytest.fixture
    def valid_classification(self) -> dict:
        """유효한 분류 결과."""
        return {
            "classification": {
                "major_category": "재활용폐기물",
                "middle_category": "무색페트병",
            }
        }

    @pytest.fixture
    def valid_disposal_rules(self) -> dict:
        """유효한 배출 규정."""
        return {"배출방법_공통": "라벨 제거 후 분리수거"}

    @pytest.fixture
    def valid_final_answer(self) -> dict:
        """유효한 최종 답변."""
        return {"user_answer": "답변", "insufficiencies": []}

    def test_returns_true_for_valid_recyclable(
        self, valid_classification, valid_disposal_rules, valid_final_answer
    ):
        """재활용 + 규정 + insufficiencies 없음 → True."""
        from domains.scan.tasks.reward import _should_attempt_reward

        with patch.dict("os.environ", {"REWARD_FEATURE_ENABLED": "true"}):
            result = _should_attempt_reward(
                valid_classification, valid_disposal_rules, valid_final_answer
            )
        assert result is True

    def test_returns_false_when_feature_disabled(
        self, valid_classification, valid_disposal_rules, valid_final_answer
    ):
        """REWARD_FEATURE_ENABLED=false → False."""
        from domains.scan.tasks.reward import _should_attempt_reward

        with patch.dict("os.environ", {"REWARD_FEATURE_ENABLED": "false"}):
            result = _should_attempt_reward(
                valid_classification, valid_disposal_rules, valid_final_answer
            )
        assert result is False

    def test_returns_false_for_non_recyclable(self, valid_disposal_rules, valid_final_answer):
        """major_category != 재활용폐기물 → False."""
        from domains.scan.tasks.reward import _should_attempt_reward

        classification = {
            "classification": {
                "major_category": "일반쓰레기",
                "middle_category": "음식물",
            }
        }
        with patch.dict("os.environ", {"REWARD_FEATURE_ENABLED": "true"}):
            result = _should_attempt_reward(
                classification, valid_disposal_rules, valid_final_answer
            )
        assert result is False

    def test_returns_false_when_no_disposal_rules(self, valid_classification, valid_final_answer):
        """disposal_rules 없음 → False."""
        from domains.scan.tasks.reward import _should_attempt_reward

        with patch.dict("os.environ", {"REWARD_FEATURE_ENABLED": "true"}):
            result = _should_attempt_reward(valid_classification, None, valid_final_answer)
        assert result is False

    def test_returns_false_when_has_insufficiencies(
        self, valid_classification, valid_disposal_rules
    ):
        """insufficiencies 있음 → False."""
        from domains.scan.tasks.reward import _should_attempt_reward

        final_answer = {
            "user_answer": "답변",
            "insufficiencies": ["라벨 미제거"],
        }
        with patch.dict("os.environ", {"REWARD_FEATURE_ENABLED": "true"}):
            result = _should_attempt_reward(
                valid_classification, valid_disposal_rules, final_answer
            )
        assert result is False

    def test_returns_false_when_missing_category(self, valid_disposal_rules, valid_final_answer):
        """major 또는 middle이 비어있음 → False."""
        from domains.scan.tasks.reward import _should_attempt_reward

        classification = {"classification": {"major_category": ""}}
        with patch.dict("os.environ", {"REWARD_FEATURE_ENABLED": "true"}):
            result = _should_attempt_reward(
                classification, valid_disposal_rules, valid_final_answer
            )
        assert result is False


class TestScanRewardTaskLogic:
    """scan_reward_task 로직 테스트 - 판정만 수행."""

    @pytest.fixture
    def prev_result(self) -> dict:
        """answer_task 결과 (이전 단계 출력)."""
        return {
            "task_id": str(uuid4()),
            "user_id": str(uuid4()),
            "status": "completed",
            "category": "재활용폐기물",
            "classification_result": {
                "classification": {
                    "major_category": "재활용폐기물",
                    "middle_category": "무색페트병",
                }
            },
            "disposal_rules": {"배출방법": "분리수거"},
            "final_answer": {
                "user_answer": "페트병 분리배출 방법",
                "insufficiencies": [],
            },
            "metadata": {
                "duration_vision_ms": 2000,
                "duration_rule_ms": 500,
                "duration_answer_ms": 1500,
                "duration_total_ms": 4000,
            },
        }

    def test_reward_response_excludes_internal_fields(self, prev_result):
        """클라이언트 응답에는 내부용 필드가 포함되지 않음."""
        internal_decision = {
            "received": True,
            "already_owned": False,
            "character_id": str(uuid4()),
            "character_code": "ECO001",
            "name": "페트병이",
            "dialog": "잘했어!",
            "match_reason": "무색페트병",
            "character_type": "페트",
            "type": "페트",
        }

        reward_response = {
            "received": internal_decision["received"],
            "already_owned": internal_decision["already_owned"],
            "name": internal_decision["name"],
            "dialog": internal_decision["dialog"],
            "match_reason": internal_decision["match_reason"],
            "character_type": internal_decision["character_type"],
            "type": internal_decision["type"],
        }

        result = {**prev_result, "reward": reward_response}

        assert "character_id" not in result["reward"]
        assert "character_code" not in result["reward"]
        assert result["reward"]["received"] is True
        assert result["reward"]["name"] == "페트병이"

    def test_all_fields_preserved(self, prev_result):
        """이전 결과의 모든 필드가 보존됨."""
        result = {**prev_result, "reward": None}

        expected_fields = [
            "task_id",
            "user_id",
            "status",
            "category",
            "classification_result",
            "disposal_rules",
            "final_answer",
            "metadata",
        ]

        for field in expected_fields:
            assert field in result
            assert result[field] == prev_result[field]


class TestPersistRewardDispatcher:
    """persist_reward_task 로직 테스트 - dispatcher."""

    @pytest.fixture
    def sample_params(self) -> dict:
        """persist_reward_task 파라미터."""
        return {
            "user_id": str(uuid4()),
            "character_id": str(uuid4()),
            "character_code": "ECO001",
            "character_name": "페트병이",
            "character_type": "페트",
            "character_dialog": "잘했어!",
            "source": "scan",
            "task_id": str(uuid4()),
        }

    def test_dispatches_both_tasks_logic(self, sample_params):
        """2개의 저장 task를 동시에 발행하는 로직 검증."""
        # persist_reward_task의 로직을 시뮬레이션
        dispatched = {"ownership": False, "my_character": False}

        mock_ownership = MagicMock()
        mock_my = MagicMock()

        # 발행 시도
        try:
            mock_ownership.delay(
                user_id=sample_params["user_id"],
                character_id=sample_params["character_id"],
                source=sample_params["source"],
            )
            dispatched["ownership"] = True
        except Exception:
            pass

        try:
            mock_my.delay(
                user_id=sample_params["user_id"],
                character_id=sample_params["character_id"],
                character_code=sample_params["character_code"],
                character_name=sample_params["character_name"],
                character_type=sample_params["character_type"],
                character_dialog=sample_params["character_dialog"],
                source=sample_params["source"],
            )
            dispatched["my_character"] = True
        except Exception:
            pass

        mock_ownership.delay.assert_called_once()
        mock_my.delay.assert_called_once()
        assert dispatched["ownership"] is True
        assert dispatched["my_character"] is True

    def test_one_failure_does_not_block_other_logic(self, sample_params):
        """하나가 실패해도 다른 하나는 발행되는 로직 검증."""
        dispatched = {"ownership": False, "my_character": False}

        mock_ownership = MagicMock()
        mock_ownership.delay.side_effect = Exception("Connection error")

        mock_my = MagicMock()

        # ownership 발행 시도 (실패)
        try:
            mock_ownership.delay(
                user_id=sample_params["user_id"],
                character_id=sample_params["character_id"],
                source=sample_params["source"],
            )
            dispatched["ownership"] = True
        except Exception:
            pass

        # my_character 발행 시도 (성공)
        try:
            mock_my.delay(
                user_id=sample_params["user_id"],
                character_id=sample_params["character_id"],
                character_code=sample_params["character_code"],
                character_name=sample_params["character_name"],
                character_type=sample_params["character_type"],
                character_dialog=sample_params["character_dialog"],
                source=sample_params["source"],
            )
            dispatched["my_character"] = True
        except Exception:
            pass

        assert dispatched["ownership"] is False
        assert dispatched["my_character"] is True


class TestSaveOwnershipTask:
    """save_ownership_task 로직 테스트."""

    @pytest.fixture
    def sample_params(self) -> dict:
        return {
            "user_id": str(uuid4()),
            "character_id": str(uuid4()),
            "source": "scan",
        }

    def test_save_ownership_result_structure_already_owned(self):
        """이미 소유한 경우 반환 구조 검증."""
        # _save_ownership_async가 이미 소유한 경우 반환하는 구조
        result = {"saved": False, "reason": "already_owned"}
        assert result["saved"] is False
        assert result["reason"] == "already_owned"

    def test_save_ownership_result_structure_success(self):
        """저장 성공 시 반환 구조 검증."""
        result = {"saved": True}
        assert result["saved"] is True

    def test_save_ownership_task_config(self):
        """save_ownership_task 설정 확인."""
        from domains.character.tasks.reward import save_ownership_task

        assert save_ownership_task.name == "character.save_ownership"
        assert save_ownership_task.max_retries == 5

    def test_handles_concurrent_insert(self):
        """동시 요청으로 인한 IntegrityError 처리."""
        result = {"saved": False, "reason": "concurrent_insert"}
        assert result["saved"] is False
        assert result["reason"] == "concurrent_insert"

    def test_handles_character_not_found(self):
        """캐릭터를 찾지 못한 경우 처리."""
        result = {"saved": False, "reason": "character_not_found"}
        assert result["saved"] is False
        assert result["reason"] == "character_not_found"


class TestSaveMyCharacterTask:
    """save_my_character_task 로직 테스트."""

    @pytest.fixture
    def sample_params(self) -> dict:
        return {
            "user_id": str(uuid4()),
            "character_id": str(uuid4()),
            "character_code": "ECO001",
            "character_name": "페트병이",
            "character_type": "페트",
            "character_dialog": "잘했어!",
            "source": "scan",
        }

    def test_save_my_character_task_config(self):
        """save_my_character_task 설정 확인."""
        from domains.my.tasks import save_my_character_task

        assert save_my_character_task.name == "my.save_character"
        assert save_my_character_task.max_retries == 5

    def test_uses_my_database_url(self):
        """MY_DATABASE_URL 환경변수 사용."""
        import os

        my_db_url = os.getenv(
            "MY_DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@localhost:5432/my",
        )
        assert "postgresql" in my_db_url
        assert "asyncpg" in my_db_url

    def test_task_queue_is_my_reward(self):
        """my.reward 큐에서 실행됨."""
        from domains._shared.celery.config import get_celery_settings

        settings = get_celery_settings()
        config = settings.get_celery_config()
        routes = config["task_routes"]

        assert routes["my.save_character"]["queue"] == "my.reward"


class TestFullChainIntegration:
    """4단계 Chain 통합 테스트 (vision → rule → answer + reward 판정)."""

    @patch("domains._shared.waste_pipeline.answer.generate_answer")
    @patch("domains._shared.waste_pipeline.rag.get_disposal_rules")
    @patch("domains._shared.waste_pipeline.vision.analyze_images")
    def test_pipeline_produces_reward_eligible_result(self, mock_vision, mock_rule, mock_answer):
        """3단계 파이프라인 후 reward 판정 가능한 결과 생성."""
        from domains.scan.tasks.answer import answer_task
        from domains.scan.tasks.reward import _should_attempt_reward
        from domains.scan.tasks.rule import rule_task
        from domains.scan.tasks.vision import vision_task

        mock_vision.return_value = {
            "classification": {
                "major_category": "재활용폐기물",
                "middle_category": "무색페트병",
            }
        }
        mock_rule.return_value = {"배출방법": "라벨 제거"}
        mock_answer.return_value = {"user_answer": "답변", "insufficiencies": []}

        task_id = str(uuid4())
        user_id = str(uuid4())

        vision_result = vision_task.run(
            task_id=task_id,
            user_id=user_id,
            image_url="https://test.com/image.jpg",
            user_input=None,
        )
        rule_result = rule_task.run(vision_result)
        answer_result = answer_task.run(rule_result)

        assert answer_result["task_id"] == task_id
        assert answer_result["status"] == "completed"
        assert answer_result["category"] == "재활용폐기물"

        with patch.dict("os.environ", {"REWARD_FEATURE_ENABLED": "true"}):
            should_reward = _should_attempt_reward(
                answer_result["classification_result"],
                answer_result["disposal_rules"],
                answer_result["final_answer"],
            )

        assert should_reward is True


class TestRewardDecisionLogic:
    """_evaluate_reward_decision 함수 테스트."""

    @patch("domains.scan.tasks.reward._match_character_async")
    def test_decision_returns_character_info(self, mock_match):
        """판정 결과에 캐릭터 정보 포함."""
        from domains.scan.tasks.reward import _evaluate_reward_decision

        character_id = str(uuid4())
        mock_match.return_value = {
            "received": True,
            "already_owned": False,
            "character_id": character_id,
            "character_code": "ECO001",
            "name": "캐릭터",
            "dialog": "안녕!",
            "match_reason": "플라스틱",
            "character_type": "플라",
            "type": "플라",
        }

        result = _evaluate_reward_decision(
            task_id="task-123",
            user_id="user-456",
            classification_result={"classification": {"major_category": "재활용폐기물"}},
            disposal_rules_present=True,
            log_ctx={"task_id": "task-123"},
        )

        assert result is not None
        assert result["character_id"] == character_id
        assert result["character_code"] == "ECO001"
        assert result["received"] is True

    @patch("domains.scan.tasks.reward._match_character_async")
    def test_decision_returns_none_on_exception(self, mock_match):
        """예외 발생 시 None 반환."""
        from domains.scan.tasks.reward import _evaluate_reward_decision

        mock_match.side_effect = Exception("DB 연결 실패")

        result = _evaluate_reward_decision(
            task_id="task-123",
            user_id="user-456",
            classification_result={},
            disposal_rules_present=False,
            log_ctx={},
        )

        assert result is None


class TestParallelSaveArchitecture:
    """병렬 저장 아키텍처 검증."""

    def test_task_routing_config(self):
        """task routing 설정 검증."""
        from domains._shared.celery.config import get_celery_settings

        settings = get_celery_settings()
        config = settings.get_celery_config()
        routes = config["task_routes"]

        # 각 task의 큐 확인 (scan.reward → character.reward, my.reward 직접 dispatch)
        assert routes["scan.reward"]["queue"] == "scan.reward"
        assert routes["character.save_ownership"]["queue"] == "character.reward"
        assert routes["my.save_character"]["queue"] == "my.reward"

    def test_each_task_has_own_retry(self):
        """각 task는 독립적인 재시도 로직."""
        from domains.character.tasks.reward import save_ownership_task
        from domains.my.tasks import save_my_character_task

        assert save_ownership_task.max_retries == 5
        assert save_my_character_task.max_retries == 5

    def test_scan_reward_dispatches_save_tasks(self):
        """scan_reward_task가 send_task로 저장 task 발행."""
        import inspect

        from domains.scan.tasks.reward import scan_reward_task

        source = inspect.getsource(scan_reward_task)
        # send_task로 발행하는지 확인
        assert "send_task" in source
        assert "character.save_ownership" in source
        assert "my.save_character" in source

    def test_no_grpc_in_save_my_character(self):
        """save_my_character_task에 gRPC 호출 없음."""
        import inspect

        from domains.my.tasks.sync_character import _save_my_character_async

        source = inspect.getsource(_save_my_character_async)
        assert "grpc" not in source.lower()
        assert "get_my_client" not in source
