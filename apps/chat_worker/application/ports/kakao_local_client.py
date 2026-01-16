"""카카오 로컬 API 클라이언트 Port.

카카오 로컬 API의 추상 인터페이스 및 DTO 정의.

Clean Architecture:
- Port: 이 파일 (추상 인터페이스)
- Adapter: infrastructure/integrations/kakao/kakao_local_http_client.py

API 문서: https://developers.kakao.com/docs/latest/ko/local/dev-guide
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class KakaoCategoryGroup(str, Enum):
    """카카오 카테고리 그룹 코드.

    https://developers.kakao.com/docs/latest/ko/local/dev-guide#search-by-category
    """

    MART = "MT1"  # 대형마트
    CONVENIENCE = "CS2"  # 편의점
    KINDERGARTEN = "PS3"  # 어린이집, 유치원
    SCHOOL = "SC4"  # 학교
    ACADEMY = "AC5"  # 학원
    PARKING = "PK6"  # 주차장
    GAS_STATION = "OL7"  # 주유소, 충전소
    SUBWAY = "SW8"  # 지하철역
    BANK = "BK9"  # 은행
    CULTURE = "CT1"  # 문화시설
    AGENCY = "AG2"  # 중개업소
    PUBLIC = "PO3"  # 공공기관
    TOURISM = "AT4"  # 관광명소
    ACCOMMODATION = "AD5"  # 숙박
    RESTAURANT = "FD6"  # 음식점
    CAFE = "CE7"  # 카페
    HOSPITAL = "HP8"  # 병원
    PHARMACY = "PM9"  # 약국


@dataclass(frozen=True)
class KakaoPlaceDTO:
    """카카오 로컬 장소 DTO.

    Application Layer에서 사용하는 불변 데이터 객체.
    카카오 API 응답의 documents 항목을 매핑.

    Attributes:
        id: 장소 ID
        place_name: 장소명
        category_name: 카테고리 전체 경로 (예: "가정,생활 > 재활용센터")
        category_group_code: 카테고리 그룹 코드 (예: "PO3")
        category_group_name: 카테고리 그룹명 (예: "공공기관")
        phone: 전화번호
        address_name: 지번 주소
        road_address_name: 도로명 주소
        x: 경도 (longitude) - 문자열
        y: 위도 (latitude) - 문자열
        place_url: 장소 상세 URL
        distance: 거리 (미터 단위, 문자열)
    """

    id: str
    place_name: str
    category_name: str
    category_group_code: str
    category_group_name: str
    phone: str | None
    address_name: str
    road_address_name: str | None
    x: str  # longitude
    y: str  # latitude
    place_url: str
    distance: str | None = None

    @property
    def latitude(self) -> float:
        """위도를 float으로 반환."""
        return float(self.y) if self.y else 0.0

    @property
    def longitude(self) -> float:
        """경도를 float으로 반환."""
        return float(self.x) if self.x else 0.0

    @property
    def distance_meters(self) -> int | None:
        """거리를 정수 미터로 반환."""
        return int(self.distance) if self.distance else None

    @property
    def distance_text(self) -> str | None:
        """거리를 읽기 좋은 형태로 반환."""
        if not self.distance:
            return None
        meters = int(self.distance)
        if meters >= 1000:
            return f"{meters / 1000:.1f}km"
        return f"{meters}m"


@dataclass(frozen=True)
class KakaoSearchMeta:
    """카카오 검색 메타 정보.

    Attributes:
        total_count: 검색된 총 문서 수
        pageable_count: 노출 가능 문서 수 (최대 45)
        is_end: 마지막 페이지 여부
        same_name: 지역 및 키워드 분석 정보
    """

    total_count: int
    pageable_count: int
    is_end: bool
    same_name: dict[str, Any] | None = None


@dataclass
class KakaoSearchResponse:
    """카카오 검색 응답.

    Attributes:
        places: 검색된 장소 목록
        meta: 검색 메타 정보
        query: 원본 검색어
    """

    places: list[KakaoPlaceDTO] = field(default_factory=list)
    meta: KakaoSearchMeta | None = None
    query: str = ""


class KakaoLocalClientPort(ABC):
    """카카오 로컬 API 클라이언트 Port.

    기존 LocationClientPort와 별도로 운영:
    - LocationClientPort: 이코에코 gRPC (재활용센터 전용)
    - KakaoLocalClientPort: 카카오 REST (범용 장소 검색)

    Infrastructure Layer에서 HTTP 구현체 제공.
    """

    @abstractmethod
    async def search_keyword(
        self,
        query: str,
        x: float | None = None,
        y: float | None = None,
        radius: int = 5000,
        page: int = 1,
        size: int = 15,
        sort: str = "accuracy",
    ) -> KakaoSearchResponse:
        """키워드로 장소 검색.

        Args:
            query: 검색 키워드 (예: "강남역 카페", "재활용센터")
            x: 중심 좌표 경도 (sort=distance일 때 필수)
            y: 중심 좌표 위도
            radius: 검색 반경 (미터, 최대 20000)
            page: 페이지 번호 (1~45)
            size: 한 페이지 결과 수 (1~15)
            sort: 정렬 기준 (accuracy | distance)

        Returns:
            KakaoSearchResponse
        """
        pass

    @abstractmethod
    async def search_category(
        self,
        category_group_code: str,
        x: float,
        y: float,
        radius: int = 5000,
        page: int = 1,
        size: int = 15,
        sort: str = "distance",
    ) -> KakaoSearchResponse:
        """카테고리로 장소 검색.

        Args:
            category_group_code: 카테고리 그룹 코드 (MT1, CS2, CE7 등)
            x: 중심 좌표 경도 (필수)
            y: 중심 좌표 위도 (필수)
            radius: 검색 반경 (미터, 최대 20000)
            page: 페이지 번호 (1~45)
            size: 한 페이지 결과 수 (1~15)
            sort: 정렬 기준 (accuracy | distance)

        Returns:
            KakaoSearchResponse
        """
        pass

    async def close(self) -> None:
        """리소스 정리 (선택적 구현)."""
        pass


__all__ = [
    "KakaoCategoryGroup",
    "KakaoPlaceDTO",
    "KakaoSearchMeta",
    "KakaoSearchResponse",
    "KakaoLocalClientPort",
]
