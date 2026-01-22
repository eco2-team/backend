"""Recyclable Price Node Function Calling 단위 테스트.

LangGraph 노드의 Function Calling 기능 테스트.

테스트 대상:
- LLM Function Calling을 통한 재활용품 파라미터 추출
- material (paper, plastic, metal, glass) 추출
- detail_type (세부 종류) 추출
- Function Calling 실패 시 fallback 처리
- material → category 매핑 검증

Note:
이 테스트는 Function Calling 메커니즘 자체를 검증합니다.
실제 Command 실행은 별도 테스트에서 다룹니다.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from chat_worker.application.commands.search_recyclable_price_command import (
    SearchRecyclablePriceInput,
    SearchRecyclablePriceOutput,
)
from chat_worker.application.ports.recyclable_price_client import (
    RecyclableCategory,
    RecyclablePriceDTO,
    RecyclablePriceSearchResponse,
)
from chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node import (
    create_recyclable_price_node,
    RECYCLABLE_PRICE_FUNCTION,
)


class MockLLMClient:
    """테스트용 Mock LLM Client.

    Function Calling 응답을 시뮬레이션합니다.
    """

    def __init__(self):
        self.function_call_response: tuple[str | None, dict[str, Any] | None] = (None, None)
        self.call_count = 0
        self.last_prompt: str = ""
        self.last_functions: list[dict[str, Any]] = []
        self.last_system_prompt: str = ""
        self.should_raise_error = False

    def set_function_call_response(
        self,
        function_name: str | None,
        arguments: dict[str, Any] | None,
    ):
        """Function call 응답 설정."""
        self.function_call_response = (function_name, arguments)

    def set_error(self, should_raise: bool = True):
        """에러 발생 설정."""
        self.should_raise_error = should_raise

    async def generate_function_call(
        self,
        prompt: str,
        functions: list[dict[str, Any]],
        system_prompt: str | None = None,
        function_call: str | dict[str, str] = "auto",
    ) -> tuple[str | None, dict[str, Any] | None]:
        """Mock generate_function_call."""
        self.call_count += 1
        self.last_prompt = prompt
        self.last_functions = functions
        self.last_system_prompt = system_prompt or ""

        if self.should_raise_error:
            raise Exception("LLM Function Calling Error")

        return self.function_call_response


class MockEventPublisher:
    """테스트용 Mock Event Publisher."""

    def __init__(self):
        self.stages: list[dict] = []

    async def notify_stage(
        self,
        task_id: str,
        stage: str,
        status: str,
        progress: int | None = None,
        result: dict[str, Any] | None = None,
        message: str | None = None,
    ):
        self.stages.append(
            {
                "task_id": task_id,
                "stage": stage,
                "status": status,
                "progress": progress,
                "result": result,
                "message": message,
            }
        )
        return "event-id"


class MockRecyclablePriceClient:
    """테스트용 Mock Price Client."""

    def __init__(self):
        self._response = RecyclablePriceSearchResponse(
            items=[
                RecyclablePriceDTO(
                    item_code="metal_aluminum_can",
                    item_name="알루미늄캔",
                    category=RecyclableCategory.METAL,
                    price_per_kg=1200,
                    survey_date="2025-01",
                ),
            ],
            query="캔",
            survey_date="2025-01",
            total_count=1,
        )

    async def search_price(self, item_name: str, region=None):
        return self._response

    async def get_category_prices(self, category, region=None):
        return self._response

    async def get_all_prices(self, region=None):
        return self._response


class MockNodeExecutor:
    """테스트용 Mock NodeExecutor.

    NodeExecutor의 policy 적용을 우회하여 노드 함수를 직접 실행합니다.
    """

    @classmethod
    def get_instance(cls):
        """싱글톤 인스턴스 반환 (Mock)."""
        return cls()

    async def execute(
        self,
        node_name: str,
        node_func,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        """노드 함수를 직접 실행 (policy 우회)."""
        return await node_func(state)


class TestRecyclablePriceFunctionCalling:
    """Recyclable Price Node Function Calling 테스트 스위트."""

    @pytest.fixture
    def mock_llm(self) -> MockLLMClient:
        """Mock LLM Client."""
        return MockLLMClient()

    @pytest.fixture
    def mock_client(self) -> MockRecyclablePriceClient:
        """Mock Price Client."""
        return MockRecyclablePriceClient()

    @pytest.fixture
    def mock_publisher(self) -> MockEventPublisher:
        """Mock Event Publisher."""
        return MockEventPublisher()

    @pytest.fixture
    def mock_command(self):
        """Mock Command."""
        mock = AsyncMock()
        mock.execute.return_value = SearchRecyclablePriceOutput(
            success=True,
            price_context={
                "type": "recyclable_prices",
                "items": [],
                "found": True,
                "count": 1,
                "context": "Test context",
            },
        )
        return mock

    # ==========================================================
    # Test Case 1: Material Extraction
    # ==========================================================

    @pytest.mark.anyio
    async def test_material_extraction_paper(
        self,
        mock_llm: MockLLMClient,
        mock_client: MockRecyclablePriceClient,
        mock_publisher: MockEventPublisher,
        mock_command,
        monkeypatch,
    ):
        """Material 추출 - paper."""
        # Mock NodeExecutor and Command
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.NodeExecutor",
            MockNodeExecutor,
        )
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.SearchRecyclablePriceCommand",
            lambda **kwargs: mock_command,
        )

        # LLM이 paper 반환
        mock_llm.set_function_call_response(
            "get_recyclable_price",
            {"material": "paper", "detail_type": "신문지"},
        )

        node = create_recyclable_price_node(mock_client, mock_publisher, mock_llm)

        state = {
            "job_id": "job-paper",
            "message": "신문지 시세 알려줘",
        }

        result = await node(state)

        # LLM Function Calling 호출 확인
        assert mock_llm.call_count == 1
        assert mock_llm.last_prompt == "신문지 시세 알려줘"
        assert mock_llm.last_functions == [RECYCLABLE_PRICE_FUNCTION]

        # Command 호출 확인
        assert mock_command.execute.called
        call_args = mock_command.execute.call_args[0][0]
        assert isinstance(call_args, SearchRecyclablePriceInput)
        assert call_args.item_name == "신문지"  # detail_type이 item_name으로
        assert call_args.category == "paper"  # material이 category로

        # 결과 확인
        assert "recyclable_price_context" in result

    @pytest.mark.anyio
    async def test_material_extraction_plastic(
        self,
        mock_llm: MockLLMClient,
        mock_client: MockRecyclablePriceClient,
        mock_publisher: MockEventPublisher,
        mock_command,
        monkeypatch,
    ):
        """Material 추출 - plastic."""
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.NodeExecutor",
            MockNodeExecutor,
        )
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.SearchRecyclablePriceCommand",
            lambda **kwargs: mock_command,
        )

        mock_llm.set_function_call_response(
            "get_recyclable_price",
            {"material": "plastic", "detail_type": "페트병"},
        )

        node = create_recyclable_price_node(mock_client, mock_publisher, mock_llm)

        state = {
            "job_id": "job-plastic",
            "message": "페트병 얼마야?",
        }

        await node(state)

        assert mock_llm.call_count == 1
        call_args = mock_command.execute.call_args[0][0]
        assert call_args.item_name == "페트병"
        assert call_args.category == "plastic"

    @pytest.mark.anyio
    async def test_material_extraction_metal(
        self,
        mock_llm: MockLLMClient,
        mock_client: MockRecyclablePriceClient,
        mock_publisher: MockEventPublisher,
        mock_command,
        monkeypatch,
    ):
        """Material 추출 - metal."""
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.NodeExecutor",
            MockNodeExecutor,
        )
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.SearchRecyclablePriceCommand",
            lambda **kwargs: mock_command,
        )

        mock_llm.set_function_call_response(
            "get_recyclable_price",
            {"material": "metal", "detail_type": "캔"},
        )

        node = create_recyclable_price_node(mock_client, mock_publisher, mock_llm)

        state = {
            "job_id": "job-metal",
            "message": "캔 가격 알려줘",
        }

        await node(state)

        assert mock_llm.call_count == 1
        call_args = mock_command.execute.call_args[0][0]
        assert call_args.item_name == "캔"
        assert call_args.category == "metal"

    @pytest.mark.anyio
    async def test_material_extraction_glass(
        self,
        mock_llm: MockLLMClient,
        mock_client: MockRecyclablePriceClient,
        mock_publisher: MockEventPublisher,
        mock_command,
        monkeypatch,
    ):
        """Material 추출 - glass."""
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.NodeExecutor",
            MockNodeExecutor,
        )
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.SearchRecyclablePriceCommand",
            lambda **kwargs: mock_command,
        )

        mock_llm.set_function_call_response(
            "get_recyclable_price",
            {"material": "glass", "detail_type": "유리병"},
        )

        node = create_recyclable_price_node(mock_client, mock_publisher, mock_llm)

        state = {
            "job_id": "job-glass",
            "message": "유리병 시세",
        }

        await node(state)

        assert mock_llm.call_count == 1
        call_args = mock_command.execute.call_args[0][0]
        assert call_args.item_name == "유리병"
        assert call_args.category == "glass"

    # ==========================================================
    # Test Case 2: Detail Type Extraction
    # ==========================================================

    @pytest.mark.anyio
    async def test_detail_type_extraction(
        self,
        mock_llm: MockLLMClient,
        mock_client: MockRecyclablePriceClient,
        mock_publisher: MockEventPublisher,
        mock_command,
        monkeypatch,
    ):
        """Detail type 추출."""
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.NodeExecutor",
            MockNodeExecutor,
        )
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.SearchRecyclablePriceCommand",
            lambda **kwargs: mock_command,
        )

        mock_llm.set_function_call_response(
            "get_recyclable_price",
            {"material": "paper", "detail_type": "골판지"},
        )

        node = create_recyclable_price_node(mock_client, mock_publisher, mock_llm)

        state = {
            "job_id": "job-detail",
            "message": "골판지 얼마야?",
        }

        await node(state)

        # detail_type이 item_name으로 사용됨
        call_args = mock_command.execute.call_args[0][0]
        assert call_args.item_name == "골판지"

    @pytest.mark.anyio
    async def test_detail_type_priority_over_material(
        self,
        mock_llm: MockLLMClient,
        mock_client: MockRecyclablePriceClient,
        mock_publisher: MockEventPublisher,
        mock_command,
        monkeypatch,
    ):
        """Detail type이 material보다 우선."""
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.NodeExecutor",
            MockNodeExecutor,
        )
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.SearchRecyclablePriceCommand",
            lambda **kwargs: mock_command,
        )

        mock_llm.set_function_call_response(
            "get_recyclable_price",
            {"material": "plastic", "detail_type": "PET"},
        )

        node = create_recyclable_price_node(mock_client, mock_publisher, mock_llm)

        state = {
            "job_id": "job-priority",
            "message": "PET 시세",
        }

        await node(state)

        # detail_type (PET)이 item_name으로 사용됨
        call_args = mock_command.execute.call_args[0][0]
        assert call_args.item_name == "PET"

    @pytest.mark.anyio
    async def test_no_detail_type_uses_material(
        self,
        mock_llm: MockLLMClient,
        mock_client: MockRecyclablePriceClient,
        mock_publisher: MockEventPublisher,
        mock_command,
        monkeypatch,
    ):
        """Detail type 없으면 material 사용."""
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.NodeExecutor",
            MockNodeExecutor,
        )
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.SearchRecyclablePriceCommand",
            lambda **kwargs: mock_command,
        )

        mock_llm.set_function_call_response(
            "get_recyclable_price",
            {"material": "metal"},  # detail_type 없음
        )

        node = create_recyclable_price_node(mock_client, mock_publisher, mock_llm)

        state = {
            "job_id": "job-no-detail",
            "message": "고철 시세",
        }

        await node(state)

        # material이 item_name으로 사용됨
        call_args = mock_command.execute.call_args[0][0]
        assert call_args.item_name == "metal"

    # ==========================================================
    # Test Case 3: Fallback on Failure
    # ==========================================================

    @pytest.mark.anyio
    async def test_fallback_on_llm_error(
        self,
        mock_llm: MockLLMClient,
        mock_client: MockRecyclablePriceClient,
        mock_publisher: MockEventPublisher,
        monkeypatch,
    ):
        """LLM 호출 실패 시 fallback (에러 반환)."""
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.NodeExecutor",
            MockNodeExecutor,
        )

        mock_llm.set_error(True)

        node = create_recyclable_price_node(mock_client, mock_publisher, mock_llm)

        state = {
            "job_id": "job-error",
            "message": "캔 시세",
        }

        result = await node(state)

        # 에러 컨텍스트 반환
        context = result["recyclable_price_context"]
        assert context.get("success") is False
        assert "error" in context
        assert "추출할 수 없습니다" in context["error"]

        # 실패 이벤트 발행
        failed_events = [e for e in mock_publisher.stages if e["status"] == "failed"]
        assert len(failed_events) >= 1

    @pytest.mark.anyio
    async def test_fallback_on_empty_function_args(
        self,
        mock_llm: MockLLMClient,
        mock_client: MockRecyclablePriceClient,
        mock_publisher: MockEventPublisher,
        mock_command,
        monkeypatch,
    ):
        """Function call 실패 (빈 args) → fallback."""
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.NodeExecutor",
            MockNodeExecutor,
        )
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.SearchRecyclablePriceCommand",
            lambda **kwargs: mock_command,
        )

        # Function call이 None 반환
        mock_llm.set_function_call_response("get_recyclable_price", None)

        node = create_recyclable_price_node(mock_client, mock_publisher, mock_llm)

        state = {
            "job_id": "job-empty-args",
            "message": "캔 시세",
        }

        await node(state)

        # fallback: message를 item_name으로 사용
        call_args = mock_command.execute.call_args[0][0]
        assert call_args.item_name == "캔 시세"  # message 그대로

    @pytest.mark.anyio
    async def test_fallback_on_no_material_and_detail(
        self,
        mock_llm: MockLLMClient,
        mock_client: MockRecyclablePriceClient,
        mock_publisher: MockEventPublisher,
        mock_command,
        monkeypatch,
    ):
        """Material과 detail_type 둘 다 없으면 message 사용."""
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.NodeExecutor",
            MockNodeExecutor,
        )
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.SearchRecyclablePriceCommand",
            lambda **kwargs: mock_command,
        )

        mock_llm.set_function_call_response(
            "get_recyclable_price",
            {},  # material, detail_type 둘 다 없음
        )

        node = create_recyclable_price_node(mock_client, mock_publisher, mock_llm)

        state = {
            "job_id": "job-no-params",
            "message": "재활용품 시세 알려줘",
        }

        await node(state)

        # message가 item_name으로 사용됨
        call_args = mock_command.execute.call_args[0][0]
        assert call_args.item_name == "재활용품 시세 알려줘"

    # ==========================================================
    # Test Case 4: Material to Category Mapping
    # ==========================================================

    @pytest.mark.anyio
    async def test_material_to_category_mapping_paper(
        self,
        mock_llm: MockLLMClient,
        mock_client: MockRecyclablePriceClient,
        mock_publisher: MockEventPublisher,
        mock_command,
        monkeypatch,
    ):
        """Material → Category 매핑 - paper."""
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.NodeExecutor",
            MockNodeExecutor,
        )
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.SearchRecyclablePriceCommand",
            lambda **kwargs: mock_command,
        )

        mock_llm.set_function_call_response(
            "get_recyclable_price",
            {"material": "paper", "detail_type": "박스"},
        )

        node = create_recyclable_price_node(mock_client, mock_publisher, mock_llm)

        state = {
            "job_id": "job-map-paper",
            "message": "박스 시세",
        }

        await node(state)

        # material="paper"가 category로 전달됨
        call_args = mock_command.execute.call_args[0][0]
        assert call_args.category == "paper"
        assert call_args.item_name == "박스"

    @pytest.mark.anyio
    async def test_material_to_category_mapping_metal(
        self,
        mock_llm: MockLLMClient,
        mock_client: MockRecyclablePriceClient,
        mock_publisher: MockEventPublisher,
        mock_command,
        monkeypatch,
    ):
        """Material → Category 매핑 - metal."""
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.NodeExecutor",
            MockNodeExecutor,
        )
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.SearchRecyclablePriceCommand",
            lambda **kwargs: mock_command,
        )

        mock_llm.set_function_call_response(
            "get_recyclable_price",
            {"material": "metal", "detail_type": "알루미늄"},
        )

        node = create_recyclable_price_node(mock_client, mock_publisher, mock_llm)

        state = {
            "job_id": "job-map-metal",
            "message": "알루미늄 시세",
        }

        await node(state)

        call_args = mock_command.execute.call_args[0][0]
        assert call_args.category == "metal"
        assert call_args.item_name == "알루미늄"

    # ==========================================================
    # Additional Tests
    # ==========================================================

    @pytest.mark.anyio
    async def test_function_definition_structure(self):
        """Function definition 구조 검증."""
        assert RECYCLABLE_PRICE_FUNCTION["name"] == "get_recyclable_price"
        assert "description" in RECYCLABLE_PRICE_FUNCTION

        params = RECYCLABLE_PRICE_FUNCTION["parameters"]
        assert params["type"] == "object"

        properties = params["properties"]
        assert "material" in properties
        assert "detail_type" in properties

        # material enum 확인
        material_prop = properties["material"]
        assert material_prop["type"] == "string"
        assert set(material_prop["enum"]) == {"paper", "plastic", "metal", "glass"}

        # required 필드
        assert params["required"] == ["material"]

    @pytest.mark.anyio
    async def test_system_prompt_includes_mapping_guide(
        self,
        mock_llm: MockLLMClient,
        mock_client: MockRecyclablePriceClient,
        mock_publisher: MockEventPublisher,
        mock_command,
        monkeypatch,
    ):
        """System prompt에 품목 매핑 가이드 포함."""
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.NodeExecutor",
            MockNodeExecutor,
        )
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.SearchRecyclablePriceCommand",
            lambda **kwargs: mock_command,
        )

        mock_llm.set_function_call_response(
            "get_recyclable_price",
            {"material": "paper"},
        )

        node = create_recyclable_price_node(mock_client, mock_publisher, mock_llm)

        state = {
            "job_id": "job-prompt",
            "message": "신문지 시세",
        }

        await node(state)

        # System prompt 확인
        system_prompt = mock_llm.last_system_prompt
        assert "품목 매핑" in system_prompt
        assert "종이류" in system_prompt
        assert "플라스틱" in system_prompt
        assert "고철" in system_prompt
        assert "유리" in system_prompt

    @pytest.mark.anyio
    async def test_llm_function_call_forced(
        self,
        mock_llm: MockLLMClient,
        mock_client: MockRecyclablePriceClient,
        mock_publisher: MockEventPublisher,
        mock_command,
        monkeypatch,
    ):
        """LLM Function call이 강제로 호출됨."""
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.NodeExecutor",
            MockNodeExecutor,
        )
        monkeypatch.setattr(
            "chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node.SearchRecyclablePriceCommand",
            lambda **kwargs: mock_command,
        )

        mock_llm.set_function_call_response(
            "get_recyclable_price",
            {"material": "paper"},
        )

        node = create_recyclable_price_node(mock_client, mock_publisher, mock_llm)

        state = {
            "job_id": "job-forced",
            "message": "신문지 시세",
        }

        await node(state)

        # Function call이 호출되었는지 확인 (실제 호출 시 강제 파라미터 확인은 LLM Client 테스트에서)
        assert mock_llm.call_count == 1
