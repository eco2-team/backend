"""Kakao Place Service - 순수 비즈니스 로직.

Port 의존 없이 순수 로직만 담당:
- 좌표 추출
- 컨텍스트 변환 (to_answer_context)
- 결과 포맷팅

Port 호출(API)은 Command에서 담당.

Clean Architecture:
- Service: 이 파일 (순수 로직, Port 의존 없음)
- Command: SearchKakaoPlaceCommand (Port 호출, 오케스트레이션)
- DTO: KakaoPlaceDTO
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chat_worker.application.ports.kakao_local_client import (
        KakaoPlaceDTO,
        KakaoSearchMeta,
    )

logger = logging.getLogger(__name__)


class KakaoPlaceService:
    """카카오 장소 비즈니스 로직 서비스 (순수 로직).

    Port 의존 없이 순수 비즈니스 로직만 담당:
    - 좌표 추출
    - 컨텍스트 변환
    - 결과 포맷팅

    API 호출은 Command에서 담당.
    """

    @staticmethod
    def extract_coordinates(
        user_location: dict[str, Any] | None,
    ) -> tuple[float | None, float | None]:
        """사용자 위치에서 좌표 추출.

        다양한 형식의 위치 데이터를 처리:
        - {"latitude": 37.5, "longitude": 127.0}
        - {"lat": 37.5, "lon": 127.0}
        - {"lat": 37.5, "lng": 127.0}

        Args:
            user_location: 사용자 위치 딕셔너리

        Returns:
            (latitude, longitude) 튜플, 없으면 (None, None)
        """
        if not user_location:
            return None, None

        # 다양한 키 형식 지원
        lat = (
            user_location.get("latitude")
            or user_location.get("lat")
            or user_location.get("y")
        )
        lon = (
            user_location.get("longitude")
            or user_location.get("lon")
            or user_location.get("lng")
            or user_location.get("x")
        )

        if lat is not None and lon is not None:
            try:
                return float(lat), float(lon)
            except (ValueError, TypeError):
                logger.warning(
                    "Invalid coordinates format",
                    extra={"lat": lat, "lon": lon},
                )
                return None, None

        return None, None

    @staticmethod
    def validate_coordinates(lat: float | None, lon: float | None) -> bool:
        """좌표 유효성 검증.

        Args:
            lat: 위도
            lon: 경도

        Returns:
            유효 여부
        """
        if lat is None or lon is None:
            return False

        # 한국 영역 대략적 범위 (33~43N, 124~132E)
        if not (33.0 <= lat <= 43.0 and 124.0 <= lon <= 132.0):
            logger.warning(
                "Coordinates out of Korea range",
                extra={"lat": lat, "lon": lon},
            )
            # 범위 밖이어도 일단 허용 (해외 사용자 가능)

        return lat != 0.0 and lon != 0.0

    @staticmethod
    def to_answer_context(
        places: list["KakaoPlaceDTO"],
        query: str,
        meta: "KakaoSearchMeta | None" = None,
    ) -> dict[str, Any]:
        """Answer 노드용 컨텍스트 생성.

        Args:
            places: 검색된 장소 목록
            query: 검색 쿼리
            meta: 검색 메타 정보

        Returns:
            Answer 노드용 컨텍스트 딕셔너리
        """
        context: dict[str, Any] = {
            "found": len(places) > 0,
            "query": query,
            "count": len(places),
            "total_count": meta.total_count if meta else len(places),
        }

        if places:
            context["places"] = [
                KakaoPlaceService._place_to_dict(place) for place in places
            ]

        return context

    @staticmethod
    def _place_to_dict(place: "KakaoPlaceDTO") -> dict[str, Any]:
        """KakaoPlaceDTO를 딕셔너리로 변환.

        Args:
            place: 장소 DTO

        Returns:
            딕셔너리
        """
        return {
            "name": place.place_name,
            "category": place.category_name,
            "category_group": place.category_group_name,
            "address": place.road_address_name or place.address_name,
            "phone": place.phone,
            "distance": place.distance_text,
            "url": place.place_url,
            "coordinates": {
                "lat": place.latitude,
                "lon": place.longitude,
            },
        }

    @staticmethod
    def build_no_location_context() -> dict[str, Any]:
        """위치 정보 없음 컨텍스트 생성.

        Returns:
            위치 정보 없음 컨텍스트
        """
        return {
            "found": False,
            "count": 0,
            "error": "location_required",
            "message": "주변 장소를 찾으려면 위치 정보가 필요해요. 위치를 공유해주세요! 📍",
        }

    @staticmethod
    def build_not_found_context(query: str) -> dict[str, Any]:
        """검색 결과 없음 컨텍스트 생성.

        Args:
            query: 검색 쿼리

        Returns:
            검색 결과 없음 컨텍스트
        """
        return {
            "found": False,
            "query": query,
            "count": 0,
            "message": f"'{query}'에 대한 검색 결과가 없어요. 다른 키워드로 검색해보세요.",
        }

    @staticmethod
    def build_error_context(error_message: str) -> dict[str, Any]:
        """에러 컨텍스트 생성.

        Args:
            error_message: 에러 메시지

        Returns:
            에러 컨텍스트
        """
        return {
            "found": False,
            "count": 0,
            "error": "api_error",
            "message": error_message,
        }

    @staticmethod
    def optimize_search_query(query: str, intent: str | None = None) -> str:
        """검색 쿼리 최적화.

        Args:
            query: 원본 쿼리
            intent: 의도 (waste, location 등)

        Returns:
            최적화된 쿼리
        """
        # 재활용 관련 의도면 키워드 보강
        if intent == "location":
            recycling_keywords = ["재활용", "분리수거", "센터", "수거"]
            if not any(kw in query for kw in recycling_keywords):
                return f"{query} 재활용센터"

        return query

    @staticmethod
    def filter_by_category(
        places: list["KakaoPlaceDTO"],
        allowed_categories: list[str] | None = None,
    ) -> list["KakaoPlaceDTO"]:
        """카테고리로 장소 필터링.

        Args:
            places: 장소 목록
            allowed_categories: 허용 카테고리 코드 목록

        Returns:
            필터링된 장소 목록
        """
        if not allowed_categories:
            return places

        return [
            place
            for place in places
            if place.category_group_code in allowed_categories
        ]

    @staticmethod
    def sort_by_distance(places: list["KakaoPlaceDTO"]) -> list["KakaoPlaceDTO"]:
        """거리순 정렬.

        Args:
            places: 장소 목록

        Returns:
            거리순 정렬된 목록
        """
        return sorted(
            places,
            key=lambda p: p.distance_meters if p.distance_meters else float("inf"),
        )


__all__ = ["KakaoPlaceService"]
