"""KECO (한국환경공단) Integration - 폐전자제품 수거함 위치 API.

한국환경공단 공공데이터포털 API:
- 폐전자제품 수거함 위치정보 (전국 12,830개)

참고:
- https://www.data.go.kr/data/15106385/fileData.do
"""

from chat_worker.infrastructure.integrations.keco.keco_collection_point_client import (
    KecoCollectionPointClient,
)

__all__ = ["KecoCollectionPointClient"]
