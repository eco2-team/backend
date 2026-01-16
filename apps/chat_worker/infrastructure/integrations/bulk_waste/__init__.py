"""대형폐기물 수거 API 통합.

행정안전부 생활쓰레기배출정보 API 및 지자체별 API 연동.
"""

from chat_worker.infrastructure.integrations.bulk_waste.mois_http_client import (
    MoisWasteInfoHttpClient,
)

__all__ = ["MoisWasteInfoHttpClient"]
