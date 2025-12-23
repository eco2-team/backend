"""End-to-End Chain Assembly Tests.

4단계 Celery Chain (vision → rule → answer → reward)을 거쳐
최종 응답이 올바르게 조립되는지 검증합니다.

테스트 시나리오:
1. 재활용 가능 폐기물 + 리워드 성공
2. 재활용 가능 폐기물 + 리워드 미획득 (insufficiencies)
3. 일반 폐기물 (리워드 대상 아님)
4. 규정 없음 (disposal_rules = None)
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest


class TestChainDataFlow:
    """Chain 데이터 흐름 테스트."""

    @pytest.fixture
    def task_id(self) -> str:
        return str(uuid4())

    @pytest.fixture
    def user_id(self) -> str:
        return str(uuid4())

    @pytest.fixture
    def image_url(self) -> str:
        return "https://images.dev.growbin.app/scan/a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4.jpg"

    def test_vision_output_structure(self, task_id, user_id, image_url):
        """Step 1: vision_task 출력 구조 검증."""
        from domains.scan.tasks.vision import vision_task

        with patch("domains._shared.waste_pipeline.vision.analyze_images") as mock:
            mock.return_value = {
                "classification": {
                    "major_category": "재활용폐기물",
                    "middle_category": "무색페트병",
                    "minor_category": "음료수병",
                },
                "situation_tags": ["내용물_없음", "라벨_있음"],
            }

            result = vision_task.run(
                task_id=task_id,
                user_id=user_id,
                image_url=image_url,
                user_input="이 페트병 어떻게 버려요?",
            )

        # 필수 필드 검증
        assert result["task_id"] == task_id
        assert result["user_id"] == user_id
        assert result["image_url"] == image_url
        assert result["user_input"] == "이 페트병 어떻게 버려요?"
        assert "classification_result" in result
        assert "metadata" in result
        assert "duration_vision_ms" in result["metadata"]

        # classification 구조 검증
        cls = result["classification_result"]["classification"]
        assert cls["major_category"] == "재활용폐기물"
        assert cls["middle_category"] == "무색페트병"

    def test_rule_receives_vision_output(self, task_id, user_id, image_url):
        """Step 2: rule_task가 vision 출력을 올바르게 수신."""
        from domains.scan.tasks.rule import rule_task

        # vision_task 출력 시뮬레이션
        vision_output = {
            "task_id": task_id,
            "user_id": user_id,
            "image_url": image_url,
            "user_input": None,
            "classification_result": {
                "classification": {
                    "major_category": "재활용폐기물",
                    "middle_category": "무색페트병",
                }
            },
            "metadata": {"duration_vision_ms": 2500},
        }

        with patch("domains._shared.waste_pipeline.rag.get_disposal_rules") as mock:
            mock.return_value = {
                "배출방법_공통": "내용물 비우고 라벨 제거",
                "배출방법_세부": "투명 페트병 전용 수거함",
            }

            result = rule_task.run(vision_output)

        # vision 데이터 보존 확인
        assert result["task_id"] == task_id
        assert result["user_id"] == user_id
        assert result["classification_result"] == vision_output["classification_result"]

        # rule 데이터 추가 확인
        assert "disposal_rules" in result
        assert result["disposal_rules"]["배출방법_공통"] == "내용물 비우고 라벨 제거"
        assert "duration_rule_ms" in result["metadata"]

    def test_answer_receives_rule_output(self, task_id, user_id, image_url):
        """Step 3: answer_task가 rule 출력을 올바르게 수신."""
        from domains.scan.tasks.answer import answer_task

        # rule_task 출력 시뮬레이션
        rule_output = {
            "task_id": task_id,
            "user_id": user_id,
            "image_url": image_url,
            "user_input": None,
            "classification_result": {
                "classification": {
                    "major_category": "재활용폐기물",
                    "middle_category": "무색페트병",
                },
                "situation_tags": ["라벨_있음"],
            },
            "disposal_rules": {
                "배출방법_공통": "내용물 비우고 라벨 제거",
            },
            "metadata": {
                "duration_vision_ms": 2500,
                "duration_rule_ms": 800,
            },
        }

        with patch("domains._shared.waste_pipeline.answer.generate_answer") as mock:
            mock.return_value = {
                "user_answer": "페트병은 라벨을 제거하고 투명 페트병 수거함에 배출하세요.",
                "insufficiencies": [],
            }

            result = answer_task.run(rule_output)

        # 이전 데이터 보존 확인
        assert result["task_id"] == task_id
        assert result["classification_result"] == rule_output["classification_result"]
        assert result["disposal_rules"] == rule_output["disposal_rules"]

        # answer 데이터 추가 확인
        assert result["status"] == "completed"
        assert result["category"] == "재활용폐기물"
        assert "final_answer" in result
        assert "user_answer" in result["final_answer"]
        assert "duration_answer_ms" in result["metadata"]
        assert "duration_total_ms" in result["metadata"]


class TestFullChainAssembly:
    """전체 Chain 조립 테스트."""

    @pytest.fixture
    def task_id(self) -> str:
        return str(uuid4())

    @pytest.fixture
    def user_id(self) -> str:
        return str(uuid4())

    @patch("domains._shared.waste_pipeline.answer.generate_answer")
    @patch("domains._shared.waste_pipeline.rag.get_disposal_rules")
    @patch("domains._shared.waste_pipeline.vision.analyze_images")
    def test_recyclable_with_reward(self, mock_vision, mock_rule, mock_answer, task_id, user_id):
        """시나리오 1: 재활용 폐기물 + 리워드 획득."""
        from domains.character.consumers.reward import _should_attempt_reward
        from domains.scan.tasks.answer import answer_task
        from domains.scan.tasks.rule import rule_task
        from domains.scan.tasks.vision import vision_task

        # Mock 설정
        mock_vision.return_value = {
            "classification": {
                "major_category": "재활용폐기물",
                "middle_category": "무색페트병",
                "minor_category": "음료수병",
            },
            "situation_tags": ["내용물_없음", "라벨_제거됨"],
        }
        mock_rule.return_value = {
            "배출방법_공통": "내용물 비우고 라벨 제거",
            "배출방법_세부": "투명 페트병 전용 수거함에 납작하게 눌러서 배출",
        }
        mock_answer.return_value = {
            "user_answer": "이 페트병은 내용물을 비우고 라벨을 제거한 후 투명 페트병 전용 수거함에 배출하세요.",
            "insufficiencies": [],  # 빈 리스트 = 올바르게 분리배출 준비됨
        }

        # Chain 실행
        v = vision_task.run(
            task_id=task_id,
            user_id=user_id,
            image_url="https://test.com/image.jpg",
            user_input=None,
        )
        r = rule_task.run(v)
        a = answer_task.run(r)

        # Reward 조건 검증
        with patch.dict("os.environ", {"REWARD_FEATURE_ENABLED": "true"}):
            should_reward = _should_attempt_reward(
                a["classification_result"],
                a["disposal_rules"],
                a["final_answer"],
            )
        assert should_reward is True

        # 최종 결과 조립 (reward 포함)
        reward = {
            "received": True,
            "already_owned": False,
            "name": "페트병이",
            "dialog": "투명 페트병은 라벨을 제거하고 깨끗하게 버려주세요!",
            "match_reason": "무색페트병",
            "character_type": "recyclable",
            "type": "normal",
        }
        final_result = {**a, "reward": reward}

        # ClassificationResponse 스키마 검증
        self._verify_classification_response(final_result)
        assert final_result["reward"]["received"] is True
        assert final_result["reward"]["name"] == "페트병이"

    @patch("domains._shared.waste_pipeline.answer.generate_answer")
    @patch("domains._shared.waste_pipeline.rag.get_disposal_rules")
    @patch("domains._shared.waste_pipeline.vision.analyze_images")
    def test_recyclable_with_insufficiencies(
        self, mock_vision, mock_rule, mock_answer, task_id, user_id
    ):
        """시나리오 2: 재활용 폐기물 + insufficiencies로 리워드 미획득."""
        from domains.character.consumers.reward import _should_attempt_reward
        from domains.scan.tasks.answer import answer_task
        from domains.scan.tasks.rule import rule_task
        from domains.scan.tasks.vision import vision_task

        mock_vision.return_value = {
            "classification": {
                "major_category": "재활용폐기물",
                "middle_category": "무색페트병",
            },
            "situation_tags": ["라벨_있음"],  # 라벨 미제거
        }
        mock_rule.return_value = {"배출방법": "라벨 제거 후 배출"}
        mock_answer.return_value = {
            "user_answer": "라벨을 제거해주세요.",
            "insufficiencies": ["라벨이 제거되지 않았습니다"],
        }

        v = vision_task.run(
            task_id=task_id,
            user_id=user_id,
            image_url="https://test.com/image.jpg",
            user_input=None,
        )
        r = rule_task.run(v)
        a = answer_task.run(r)

        # insufficiencies가 있으면 리워드 안 줌
        with patch.dict("os.environ", {"REWARD_FEATURE_ENABLED": "true"}):
            should_reward = _should_attempt_reward(
                a["classification_result"],
                a["disposal_rules"],
                a["final_answer"],
            )
        assert should_reward is False

        # 최종 결과 (reward = None)
        final_result = {**a, "reward": None}
        self._verify_classification_response(final_result)
        assert final_result["reward"] is None

    @patch("domains._shared.waste_pipeline.answer.generate_answer")
    @patch("domains._shared.waste_pipeline.rag.get_disposal_rules")
    @patch("domains._shared.waste_pipeline.vision.analyze_images")
    def test_non_recyclable(self, mock_vision, mock_rule, mock_answer, task_id, user_id):
        """시나리오 3: 일반 폐기물 (리워드 대상 아님)."""
        from domains.character.consumers.reward import _should_attempt_reward
        from domains.scan.tasks.answer import answer_task
        from domains.scan.tasks.rule import rule_task
        from domains.scan.tasks.vision import vision_task

        mock_vision.return_value = {
            "classification": {
                "major_category": "일반쓰레기",
                "middle_category": "음식물쓰레기",
            },
        }
        mock_rule.return_value = {"배출방법": "음식물 전용 봉투"}
        mock_answer.return_value = {
            "user_answer": "음식물 전용 봉투에 버려주세요.",
            "insufficiencies": [],
        }

        v = vision_task.run(
            task_id=task_id,
            user_id=user_id,
            image_url="https://test.com/image.jpg",
            user_input=None,
        )
        r = rule_task.run(v)
        a = answer_task.run(r)

        # 일반쓰레기는 리워드 대상 아님
        with patch.dict("os.environ", {"REWARD_FEATURE_ENABLED": "true"}):
            should_reward = _should_attempt_reward(
                a["classification_result"],
                a["disposal_rules"],
                a["final_answer"],
            )
        assert should_reward is False

        final_result = {**a, "reward": None}
        self._verify_classification_response(final_result)
        assert final_result["category"] == "일반쓰레기"

    @patch("domains._shared.waste_pipeline.vision.analyze_images")
    def test_no_disposal_rules(self, mock_vision, task_id, user_id):
        """시나리오 4: 규정 없음."""
        from domains.scan.tasks.answer import answer_task
        from domains.scan.tasks.rule import rule_task
        from domains.scan.tasks.vision import vision_task

        mock_vision.return_value = {
            "classification": {
                "major_category": "기타",
                "middle_category": "분류불가",
            },
        }

        with patch("domains._shared.waste_pipeline.rag.get_disposal_rules", return_value=None):
            v = vision_task.run(
                task_id=task_id,
                user_id=user_id,
                image_url="https://test.com/image.jpg",
                user_input=None,
            )
            r = rule_task.run(v)
            a = answer_task.run(r)

        # 규정 없음 → 기본 답변
        assert a["disposal_rules"] is None
        assert "규정을 찾지 못했습니다" in a["final_answer"]["answer"]

        final_result = {**a, "reward": None}
        self._verify_classification_response(final_result)

    def _verify_classification_response(self, result: dict):
        """ClassificationResponse 스키마 검증."""
        # 필수 필드
        assert "task_id" in result
        assert "status" in result
        assert result["status"] == "completed"

        # pipeline_result 구조
        assert "classification_result" in result
        assert "disposal_rules" in result or result.get("disposal_rules") is None
        assert "final_answer" in result

        # metadata
        assert "metadata" in result
        assert "duration_vision_ms" in result["metadata"]
        assert "duration_total_ms" in result["metadata"]

        # reward (optional)
        assert "reward" in result


class TestSSEFinalEventFormat:
    """SSE 최종 이벤트 형식 검증."""

    @pytest.fixture
    def complete_chain_result(self) -> dict:
        """Chain 완료 후 결과."""
        return {
            "task_id": str(uuid4()),
            "user_id": str(uuid4()),
            "status": "completed",
            "category": "재활용폐기물",
            "classification_result": {
                "classification": {
                    "major_category": "재활용폐기물",
                    "middle_category": "무색페트병",
                    "minor_category": "음료수병",
                },
                "situation_tags": ["내용물_없음"],
            },
            "disposal_rules": {
                "배출방법_공통": "라벨 제거 후 분리수거",
            },
            "final_answer": {
                "user_answer": "페트병을 분리수거함에 버려주세요.",
                "insufficiencies": [],
            },
            "metadata": {
                "duration_vision_ms": 2500,
                "duration_rule_ms": 800,
                "duration_answer_ms": 1500,
                "duration_total_ms": 4800,
            },
            "reward": {
                "received": True,
                "already_owned": False,
                "name": "페트병이",
                "dialog": "잘했어요!",
                "match_reason": "무색페트병",
                "character_type": "recyclable",
                "type": "normal",
            },
        }

    def test_sse_final_event_structure(self, complete_chain_result):
        """SSE 최종 이벤트 구조 검증."""
        # progress.py의 _handle_event에서 생성하는 구조
        sse_data = {
            "task_id": complete_chain_result["task_id"],
            "step": "reward",
            "status": "completed",
            "progress": 100,
            "result": {
                "task_id": complete_chain_result["task_id"],
                "status": "completed",
                "message": "classification completed",
                "pipeline_result": {
                    "classification_result": complete_chain_result["classification_result"],
                    "disposal_rules": complete_chain_result["disposal_rules"],
                    "final_answer": complete_chain_result["final_answer"],
                },
                "reward": complete_chain_result["reward"],
                "error": None,
            },
        }

        # 최상위 필드
        assert sse_data["step"] == "reward"
        assert sse_data["status"] == "completed"
        assert sse_data["progress"] == 100

        # result 필드
        result = sse_data["result"]
        assert result["status"] == "completed"
        assert result["message"] == "classification completed"
        assert result["error"] is None

        # pipeline_result
        pr = result["pipeline_result"]
        assert pr["classification_result"]["classification"]["major_category"] == "재활용폐기물"
        assert pr["disposal_rules"]["배출방법_공통"] == "라벨 제거 후 분리수거"
        assert "user_answer" in pr["final_answer"]

        # reward
        assert result["reward"]["received"] is True
        assert result["reward"]["name"] == "페트병이"

    def test_sse_event_json_serializable(self, complete_chain_result):
        """SSE 이벤트가 JSON 직렬화 가능한지 검증."""
        import json

        from domains.scan.api.v1.endpoints.completion import _format_sse

        sse_data = {
            "step": "reward",
            "status": "completed",
            "progress": 100,
            "result": {
                "task_id": complete_chain_result["task_id"],
                "status": "completed",
                "pipeline_result": {
                    "classification_result": complete_chain_result["classification_result"],
                    "disposal_rules": complete_chain_result["disposal_rules"],
                    "final_answer": complete_chain_result["final_answer"],
                },
                "reward": complete_chain_result["reward"],
            },
        }

        # JSON 직렬화 테스트
        formatted = _format_sse(sse_data)

        # SSE 형식 검증
        assert "data: " in formatted
        assert formatted.endswith("\n\n")

        # JSON 파싱 가능 확인
        data_line = formatted.split("data: ")[1].strip()
        parsed = json.loads(data_line)
        assert parsed["step"] == "reward"
        assert parsed["result"]["reward"]["name"] == "페트병이"


class TestChainMetadataAccumulation:
    """Chain을 거치며 metadata가 누적되는지 검증."""

    @patch("domains._shared.waste_pipeline.answer.generate_answer")
    @patch("domains._shared.waste_pipeline.rag.get_disposal_rules")
    @patch("domains._shared.waste_pipeline.vision.analyze_images")
    def test_metadata_accumulates_through_chain(self, mock_vision, mock_rule, mock_answer):
        """각 단계의 duration이 metadata에 누적됨."""
        from domains.scan.tasks.answer import answer_task
        from domains.scan.tasks.rule import rule_task
        from domains.scan.tasks.vision import vision_task

        mock_vision.return_value = {
            "classification": {"major_category": "재활용폐기물", "middle_category": "페트병"}
        }
        mock_rule.return_value = {"배출방법": "분리수거"}
        mock_answer.return_value = {"user_answer": "답변", "insufficiencies": []}

        task_id = str(uuid4())
        user_id = str(uuid4())

        # Step 1
        v = vision_task.run(
            task_id=task_id,
            user_id=user_id,
            image_url="https://test.com/image.jpg",
            user_input=None,
        )
        assert "duration_vision_ms" in v["metadata"]
        assert "duration_rule_ms" not in v["metadata"]

        # Step 2
        r = rule_task.run(v)
        assert "duration_vision_ms" in r["metadata"]
        assert "duration_rule_ms" in r["metadata"]
        assert "duration_answer_ms" not in r["metadata"]

        # Step 3
        a = answer_task.run(r)
        assert "duration_vision_ms" in a["metadata"]
        assert "duration_rule_ms" in a["metadata"]
        assert "duration_answer_ms" in a["metadata"]
        assert "duration_total_ms" in a["metadata"]

        # duration_total_ms = vision + rule + answer
        total = a["metadata"]["duration_total_ms"]
        sum_parts = (
            a["metadata"]["duration_vision_ms"]
            + a["metadata"]["duration_rule_ms"]
            + a["metadata"]["duration_answer_ms"]
        )
        # 약간의 오차 허용 (ms 단위)
        assert abs(total - sum_parts) < 10


class TestEdgeCases:
    """엣지 케이스 테스트."""

    @patch("domains._shared.waste_pipeline.vision.analyze_images")
    def test_empty_classification(self, mock_vision):
        """분류 결과가 비어있는 경우."""
        from domains.scan.tasks.rule import rule_task
        from domains.scan.tasks.vision import vision_task

        mock_vision.return_value = {
            "classification": {
                "major_category": "",
                "middle_category": "",
            },
        }

        task_id = str(uuid4())
        v = vision_task.run(
            task_id=task_id,
            user_id=str(uuid4()),
            image_url="https://test.com/image.jpg",
            user_input=None,
        )

        with patch("domains._shared.waste_pipeline.rag.get_disposal_rules", return_value=None):
            r = rule_task.run(v)

        # 빈 분류여도 chain은 계속 진행
        assert r["classification_result"]["classification"]["major_category"] == ""
        assert r["disposal_rules"] is None

    @patch("domains._shared.waste_pipeline.answer.generate_answer")
    @patch("domains._shared.waste_pipeline.rag.get_disposal_rules")
    @patch("domains._shared.waste_pipeline.vision.analyze_images")
    def test_unicode_in_answer(self, mock_vision, mock_rule, mock_answer):
        """답변에 유니코드(한글, 이모지)가 포함된 경우."""
        from domains.scan.tasks.answer import answer_task
        from domains.scan.tasks.rule import rule_task
        from domains.scan.tasks.vision import vision_task

        mock_vision.return_value = {
            "classification": {"major_category": "재활용폐기물", "middle_category": "무색페트병"},
        }
        mock_rule.return_value = {"배출방법": "분리수거 🌱"}
        mock_answer.return_value = {
            "user_answer": "페트병은 깨끗하게 씻어서 분리수거함에 버려주세요! 🌍♻️",
            "insufficiencies": [],
        }

        task_id = str(uuid4())
        v = vision_task.run(
            task_id=task_id,
            user_id=str(uuid4()),
            image_url="https://test.com/image.jpg",
            user_input=None,
        )
        r = rule_task.run(v)
        a = answer_task.run(r)

        # 유니코드 보존 확인
        assert "🌍♻️" in a["final_answer"]["user_answer"]
        assert "🌱" in a["disposal_rules"]["배출방법"]

        # JSON 직렬화 가능 확인
        import json

        json.dumps(a, ensure_ascii=False)  # 예외 없으면 성공
