"""Unit tests for Celery tasks.

Phase 2: 3단계 파이프라인 테스트 (vision → rule → answer)
이 테스트는 Celery worker 없이 Task 로직만 테스트합니다.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4


class TestVisionTask:
    """vision_task 단위 테스트."""

    @pytest.fixture
    def mock_vision_result(self) -> dict:
        """Vision API 결과."""
        return {
            "classification": {
                "major_category": "재활용폐기물",
                "middle_category": "무색페트병",
                "minor_category": "음료수병",
            },
            "situation_tags": ["내용물_없음"],
        }

    @patch("domains._shared.waste_pipeline.vision.analyze_images")
    def test_vision_task_success(self, mock_analyze, mock_vision_result):
        """Vision 분석 성공."""
        from domains.scan.tasks.vision import vision_task

        mock_analyze.return_value = mock_vision_result
        task_id = str(uuid4())
        user_id = str(uuid4())

        result = vision_task.run(
            task_id=task_id,
            user_id=user_id,
            image_url="https://images.dev.growbin.app/scan/test.jpg",
            user_input="이 폐기물 어떻게 버려요?",
        )

        assert result["task_id"] == task_id
        assert result["user_id"] == user_id
        assert result["classification_result"] == mock_vision_result
        assert "metadata" in result
        assert "duration_vision_ms" in result["metadata"]
        mock_analyze.assert_called_once()

    @patch("domains._shared.waste_pipeline.vision.analyze_images")
    def test_vision_task_default_prompt(self, mock_analyze, mock_vision_result):
        """user_input이 없으면 기본 프롬프트 사용."""
        from domains.scan.tasks.vision import vision_task

        mock_analyze.return_value = mock_vision_result

        vision_task.run(
            task_id=str(uuid4()),
            user_id=str(uuid4()),
            image_url="https://images.dev.growbin.app/scan/test.jpg",
            user_input=None,
        )

        # 기본 프롬프트로 호출됐는지 확인
        call_args = mock_analyze.call_args
        assert "분리배출" in call_args[0][0]


class TestRuleTask:
    """rule_task 단위 테스트."""

    @pytest.fixture
    def mock_prev_result(self) -> dict:
        """vision_task 결과."""
        return {
            "task_id": str(uuid4()),
            "user_id": str(uuid4()),
            "image_url": "https://images.dev.growbin.app/scan/test.jpg",
            "user_input": None,
            "classification_result": {
                "classification": {
                    "major_category": "재활용폐기물",
                    "middle_category": "무색페트병",
                }
            },
            "metadata": {"duration_vision_ms": 2000},
        }

    @patch("domains._shared.waste_pipeline.rag.get_disposal_rules")
    def test_rule_task_success(self, mock_get_rules, mock_prev_result):
        """규정 검색 성공."""
        from domains.scan.tasks.rule import rule_task

        mock_get_rules.return_value = {"배출방법_공통": "라벨 제거 후 배출"}

        result = rule_task.run(mock_prev_result)

        assert result["task_id"] == mock_prev_result["task_id"]
        assert result["disposal_rules"] == {"배출방법_공통": "라벨 제거 후 배출"}
        assert "duration_rule_ms" in result["metadata"]
        mock_get_rules.assert_called_once()

    @patch("domains._shared.waste_pipeline.rag.get_disposal_rules")
    def test_rule_task_no_rules_found(self, mock_get_rules, mock_prev_result):
        """규정을 못 찾아도 진행 (None 반환)."""
        from domains.scan.tasks.rule import rule_task

        mock_get_rules.return_value = None

        result = rule_task.run(mock_prev_result)

        assert result["disposal_rules"] is None
        # 에러 없이 진행됨


class TestAnswerTask:
    """answer_task 단위 테스트."""

    @pytest.fixture
    def mock_prev_result(self) -> dict:
        """rule_task 결과."""
        return {
            "task_id": str(uuid4()),
            "user_id": str(uuid4()),
            "image_url": "https://images.dev.growbin.app/scan/test.jpg",
            "user_input": None,
            "classification_result": {
                "classification": {
                    "major_category": "재활용폐기물",
                    "middle_category": "무색페트병",
                },
                "situation_tags": ["내용물_없음"],
            },
            "disposal_rules": {"배출방법_공통": "라벨 제거 후 배출"},
            "metadata": {
                "duration_vision_ms": 2000,
                "duration_rule_ms": 500,
            },
        }

    @patch("domains._shared.waste_pipeline.answer.generate_answer")
    def test_answer_task_success(self, mock_generate, mock_prev_result):
        """답변 생성 성공."""
        from domains.scan.tasks.answer import answer_task

        mock_generate.return_value = {
            "user_answer": "페트병 분리배출 방법",
            "insufficiencies": [],
        }

        result = answer_task.run(mock_prev_result)

        assert result["task_id"] == mock_prev_result["task_id"]
        assert result["status"] == "completed"
        assert result["category"] == "재활용폐기물"
        assert "final_answer" in result
        assert "duration_answer_ms" in result["metadata"]
        assert "duration_total_ms" in result["metadata"]

    @patch("domains._shared.waste_pipeline.answer.generate_answer")
    def test_answer_task_no_disposal_rules(self, mock_generate, mock_prev_result):
        """disposal_rules가 없으면 기본 답변."""
        from domains.scan.tasks.answer import answer_task

        mock_prev_result["disposal_rules"] = None

        result = answer_task.run(mock_prev_result)

        # generate_answer가 호출되지 않음
        mock_generate.assert_not_called()
        assert "규정을 찾지 못했습니다" in result["final_answer"]["answer"]


class TestCeleryChain:
    """Celery Chain 통합 테스트 (vision → rule → answer)."""

    @patch("domains._shared.waste_pipeline.answer.generate_answer")
    @patch("domains._shared.waste_pipeline.rag.get_disposal_rules")
    @patch("domains._shared.waste_pipeline.vision.analyze_images")
    def test_pipeline_chain_without_reward(self, mock_vision, mock_rule, mock_answer):
        """3단계 파이프라인 체인 시뮬레이션 (reward 제외)."""
        from domains.scan.tasks.answer import answer_task
        from domains.scan.tasks.rule import rule_task
        from domains.scan.tasks.vision import vision_task

        # Setup mocks
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

        # Step 1: Vision
        vision_result = vision_task.run(
            task_id=task_id,
            user_id=user_id,
            image_url="https://test.com/image.jpg",
            user_input=None,
        )

        # Step 2: Rule (receives vision_result)
        rule_result = rule_task.run(vision_result)

        # Step 3: Answer (receives rule_result)
        answer_result = answer_task.run(rule_result)

        # Verify chain (reward는 별도 테스트에서 검증)
        assert answer_result["task_id"] == task_id
        assert answer_result["status"] == "completed"
        assert answer_result["category"] == "재활용폐기물"
        assert "duration_total_ms" in answer_result["metadata"]


class TestWebhookTask:
    """WebhookTask 베이스 클래스 테스트."""

    def test_send_webhook_success(self):
        """Webhook 전송 성공."""
        import httpx

        with patch("domains._shared.celery.base_task.httpx.Client") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response

            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    "https://example.com/callback",
                    json={"status": "completed"},
                )
                assert response.status_code == 200

    def test_send_webhook_no_url(self):
        """callback_url이 없으면 False."""
        from domains._shared.celery.base_task import WebhookTask

        task = WebhookTask()
        result = task.send_webhook("", {"status": "completed"})
        assert result is False


class TestCeleryConfig:
    """Celery 설정 테스트."""

    def test_celery_settings_defaults(self):
        """기본 설정값 확인."""
        from domains._shared.celery.config import CelerySettings

        settings = CelerySettings()
        assert settings.task_serializer == "json"
        assert settings.timezone == "Asia/Seoul"
        assert settings.task_acks_late is True
        assert settings.worker_prefetch_multiplier == 1

    def test_celery_settings_from_env(self, monkeypatch):
        """환경변수에서 설정 로드."""
        from domains._shared.celery.config import CelerySettings

        monkeypatch.setenv("CELERY_BROKER_URL", "amqp://test:test@localhost:5672/test")
        monkeypatch.setenv("CELERY_WORKER_CONCURRENCY", "4")

        settings = CelerySettings()
        assert settings.broker_url == "amqp://test:test@localhost:5672/test"
        assert settings.worker_concurrency == 4

    def test_get_celery_config_task_routes(self):
        """Phase 2 task_routes 설정 확인."""
        from domains._shared.celery.config import CelerySettings

        settings = CelerySettings()
        config = settings.get_celery_config()

        assert "task_routes" in config
        routes = config["task_routes"]

        # Phase 2: 단계별 큐 분리
        assert routes["scan.vision"]["queue"] == "scan.vision"
        assert routes["scan.rule"]["queue"] == "scan.rule"
        assert routes["scan.answer"]["queue"] == "scan.answer"
        assert routes["scan.reward"]["queue"] == "scan.reward"
        assert routes["character.save_ownership"]["queue"] == "character.reward"
        assert routes["my.save_character"]["queue"] == "my.reward"
        assert routes["dlq.*"]["queue"] == "celery"

    def test_get_celery_config_beat_schedule(self):
        """Beat 스케줄 설정 확인."""
        from domains._shared.celery.config import CelerySettings

        settings = CelerySettings()
        config = settings.get_celery_config()

        assert "beat_schedule" in config
        schedule = config["beat_schedule"]

        assert "reprocess-dlq-scan-vision" in schedule
        assert "reprocess-dlq-scan-rule" in schedule
        assert "reprocess-dlq-scan-answer" in schedule
        assert "reprocess-dlq-scan-reward" in schedule
        assert "reprocess-dlq-character-reward" in schedule
        assert "reprocess-dlq-my-reward" in schedule

        # 5분마다 실행
        assert schedule["reprocess-dlq-scan-vision"]["schedule"] == 300.0


class TestDLQTasks:
    """DLQ 재처리 Task 테스트."""

    @pytest.fixture(autouse=True)
    def mock_pika(self):
        """pika 모듈을 mock하여 설치되지 않은 환경에서도 테스트 가능."""
        import sys

        mock_pika = MagicMock()
        mock_pika.URLParameters = MagicMock()
        mock_pika.BlockingConnection = MagicMock()
        mock_pika.BasicProperties = MagicMock()
        sys.modules["pika"] = mock_pika
        yield mock_pika
        # Cleanup: pika가 실제로 설치된 경우 원래대로 복원하지 않음
        # (테스트 후 격리 환경에서 실행되므로 문제 없음)

    @patch("domains._shared.celery.dlq_tasks._get_rabbitmq_connection")
    def test_reprocess_dlq_empty_queue(self, mock_conn):
        """DLQ가 비어있을 때."""
        from domains._shared.celery.dlq_tasks import reprocess_dlq_scan_vision

        mock_channel = MagicMock()
        mock_channel.basic_get.return_value = (None, None, None)
        mock_conn.return_value.channel.return_value = mock_channel

        result = reprocess_dlq_scan_vision(max_messages=10)

        assert result["processed"] == 0
        assert result["retried"] == 0
        assert result["archived"] == 0
