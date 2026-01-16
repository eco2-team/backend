"""수거함 위치 API 클라이언트 Port.

폐전자제품, 폐건전지, 폐형광등 등의 수거함 위치 검색을 위한 추상 인터페이스.

Clean Architecture:
- Port: 이 파일 (추상 인터페이스)
- Adapter: infrastructure/integrations/keco/ (HTTP 구현)

데이터 소스:
- 한국환경공단 폐전자제품 수거함 위치정보 (data.go.kr/data/15106385)
- 향후: 지자체별 폐건전지/폐형광등 수거함 데이터

API 문서:
- https://www.data.go.kr/data/15106385/fileData.do
- Swagger: https://infuser.odcloud.kr/oas/docs?namespace=15106385/v1
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CollectionPointDTO:
    """수거함 위치 정보 DTO.

    한국환경공단 API 응답을 Application Layer용 DTO로 변환.

    Attributes:
        id: 순번 (고유 ID)
        name: 상호명 (예: "이마트 용산점")
        collection_types: 수거 가능 품목 종류 (예: ["폐휴대폰", "폐가전"])
        collection_method: 수거 방법 (예: "수거함 설치")
        address: 주소 (예: "서울특별시 용산구 한강대로 123")
        place_category: 장소 구분 (예: "대형마트")
        fee: 수거 비용 (무료/유료)
        lat: 위도 (선택, 좌표 변환 시)
        lon: 경도 (선택, 좌표 변환 시)
    """

    id: int
    name: str
    collection_types: tuple[str, ...] = ()
    collection_method: str | None = None
    address: str | None = None
    place_category: str | None = None
    fee: str | None = None
    lat: float | None = None
    lon: float | None = None

    @property
    def is_free(self) -> bool:
        """무료 여부."""
        if self.fee is None:
            return True
        return "무료" in self.fee or self.fee == ""

    @property
    def collection_types_text(self) -> str:
        """수거 가능 품목을 읽기 좋은 형태로 반환."""
        if not self.collection_types:
            return "폐전자제품"
        return ", ".join(self.collection_types)


@dataclass
class CollectionPointSearchResponse:
    """수거함 검색 응답.

    Attributes:
        results: 검색 결과 목록
        total_count: 전체 결과 수
        page: 현재 페이지
        page_size: 페이지 크기
        query: 검색 조건
    """

    results: list[CollectionPointDTO] = field(default_factory=list)
    total_count: int = 0
    page: int = 1
    page_size: int = 10
    query: dict[str, str] = field(default_factory=dict)

    @property
    def has_next(self) -> bool:
        """다음 페이지 존재 여부."""
        return self.page * self.page_size < self.total_count


class CollectionPointClientPort(ABC):
    """수거함 위치 API 클라이언트 Port.

    다양한 데이터 소스를 추상화:
    - 한국환경공단 폐전자제품 수거함
    - 지자체별 폐건전지/폐형광등 수거함 (향후)
    - 폐의약품 수거함 (향후)

    Infrastructure Layer에서 HTTP 구현체 제공.
    """

    @abstractmethod
    async def search_collection_points(
        self,
        address_keyword: str | None = None,
        name_keyword: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> CollectionPointSearchResponse:
        """수거함 위치 검색.

        Args:
            address_keyword: 주소 검색어 (예: "강남구", "용산")
            name_keyword: 상호명 검색어 (예: "이마트", "주민센터")
            page: 페이지 번호
            page_size: 한 페이지 결과 수 (최대 1000)

        Returns:
            CollectionPointSearchResponse
        """
        pass

    @abstractmethod
    async def get_nearby_collection_points(
        self,
        lat: float,
        lon: float,
        radius_km: float = 2.0,
        limit: int = 10,
    ) -> list[CollectionPointDTO]:
        """주변 수거함 검색.

        Note:
            한국환경공단 API는 좌표 검색을 지원하지 않으므로,
            주소 기반 검색 후 클라이언트에서 거리 계산 필요.
            또는 Kakao Local API와 연동하여 좌표 변환.

        Args:
            lat: 위도
            lon: 경도
            radius_km: 검색 반경 (km)
            limit: 최대 결과 수

        Returns:
            거리순 정렬된 수거함 목록
        """
        pass

    async def close(self) -> None:
        """리소스 정리 (선택적 구현)."""
        pass


__all__ = [
    "CollectionPointDTO",
    "CollectionPointSearchResponse",
    "CollectionPointClientPort",
]
