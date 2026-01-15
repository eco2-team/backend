"""재활용자원 가격 정보 통합.

한국환경공단 재활용가능자원 가격조사 데이터 연동.
"""

from chat_worker.infrastructure.integrations.recyclable_price.local_price_client import (
    LocalRecyclablePriceClient,
)

__all__ = ["LocalRecyclablePriceClient"]
