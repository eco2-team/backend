"""OpenAI Client Function Calling 단위 테스트.

Function Calling API 호출 및 결과 파싱 테스트.

TODO: respx 라이브러리를 사용한 httpx 레벨 mocking으로 리팩터링 필요
      참고: https://laszlo.substack.com/p/mocking-openai-unit-testing-in-the
      OpenAI 클라이언트는 내부적으로 httpx를 사용하므로,
      respx로 HTTP 레벨에서 mock하는 것이 더 안정적임.
"""

from __future__ import annotations

import pytest

# Skip 이유: OpenAI AsyncOpenAI 클라이언트의 내부 구조 때문에
# MagicMock/patch 방식으로는 안정적인 테스트가 어려움.
# respx 라이브러리를 도입하여 httpx 레벨에서 mock해야 함.
pytestmark = pytest.mark.skip(
    reason="OpenAI client mocking requires respx library for httpx-level mocking. "
    "See: https://laszlo.substack.com/p/mocking-openai-unit-testing-in-the"
)


class TestOpenAIClientFunctionCalling:
    """OpenAI Client Function Calling 테스트.

    현재 skip 상태:
    - AsyncOpenAI는 내부적으로 httpx를 사용
    - MagicMock으로 _client를 교체해도 httpx 레벨에서 문제 발생
    - respx 라이브러리로 HTTP 응답을 mock해야 안정적인 테스트 가능

    향후 작업:
    1. requirements-dev.txt에 respx 추가
    2. respx.mock 데코레이터로 OpenAI API 엔드포인트 mock
    3. 실제 OpenAI API 응답 형식으로 JSON 반환하도록 설정
    """

    @pytest.mark.asyncio
    async def test_function_call_success(self):
        """Function call 성공 시나리오."""
        pass

    @pytest.mark.asyncio
    async def test_function_call_forced(self):
        """Function call 강제 호출."""
        pass

    @pytest.mark.asyncio
    async def test_no_function_call(self):
        """Function call이 없는 경우."""
        pass

    @pytest.mark.asyncio
    async def test_invalid_json_arguments(self):
        """잘못된 JSON arguments."""
        pass

    @pytest.mark.asyncio
    async def test_system_prompt_included(self):
        """System prompt 포함 확인."""
        pass
