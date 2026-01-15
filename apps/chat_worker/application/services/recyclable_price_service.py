"""Recyclable Price Service.

재활용자원 가격 관련 순수 비즈니스 로직 (Port 의존 없음).

Clean Architecture:
- Service: 이 파일 - 순수 비즈니스 로직, Port 의존 없음
- Command: search_recyclable_price_command.py - Port 호출 + 오케스트레이션
- Port: RecyclablePriceClientPort - 파일/캐시 기반
- Node: recyclable_price_node.py - LangGraph glue
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chat_worker.application.ports.recyclable_price_client import (
        RecyclablePriceDTO,
        RecyclablePriceSearchResponse,
    )


class RecyclablePriceService:
    """재활용자원 가격 관련 순수 비즈니스 로직.

    모든 메서드는 static/class method로 Port 의존 없이 구현.
    Command에서 호출하여 사용.
    """

    @staticmethod
    def format_price_result(price: "RecyclablePriceDTO") -> dict[str, Any]:
        """가격 정보를 응답 컨텍스트로 변환.

        Args:
            price: 가격 DTO

        Returns:
            LLM 응답 생성용 컨텍스트 딕셔너리
        """
        return {
            "item_name": price.display_name,
            "category": price.category.value,
            "price": price.price_text,
            "price_raw": price.price_per_kg,
            "unit": price.unit,
            "form": price.form,
            "survey_date": price.survey_date,
        }

    @staticmethod
    def format_search_results(
        response: "RecyclablePriceSearchResponse",
    ) -> dict[str, Any]:
        """검색 결과를 응답 컨텍스트로 변환.

        Args:
            response: 검색 응답

        Returns:
            LLM 응답 생성용 컨텍스트 딕셔너리
        """
        items = [
            RecyclablePriceService.format_price_result(item)
            for item in response.items
        ]

        # context 문자열 생성 (LLM 프롬프트용)
        context_str = RecyclablePriceService.build_context_string(response)

        return {
            "type": "recyclable_prices",
            "query": response.query,
            "items": items,
            "count": len(items),
            "survey_date": response.survey_date,
            "region": response.region.value if response.region else "national",
            "found": response.has_results,
            "context": context_str,  # LLM 프롬프트에 주입할 문자열
        }

    @staticmethod
    def build_context_string(
        response: "RecyclablePriceSearchResponse",
    ) -> str:
        """검색 결과를 LLM context 문자열로 변환.

        Args:
            response: 검색 응답

        Returns:
            context 문자열 (프롬프트에 주입)
        """
        from chat_worker.application.ports.recyclable_price_client import REGION_NAMES

        if not response.items:
            return ""

        lines = [
            f"## 재활용자원 시세 정보 (조사일: {response.survey_date or '미상'})",
            f"검색어: {response.query}",
            f"기준 권역: {REGION_NAMES.get(response.region, '전국')}",
            "",
        ]

        for item in response.items:
            form_str = f" ({item.form})" if item.form else ""
            lines.append(f"- **{item.item_name}{form_str}**: {item.price_per_kg:,}원/kg")

        lines.append("")
        lines.append("※ 출처: 한국환경공단 재활용가능자원 가격조사")
        lines.append("※ 가격은 업체별로 상이할 수 있습니다.")

        return "\n".join(lines)

    @staticmethod
    def build_not_found_context(query: str) -> dict[str, Any]:
        """검색 결과 없을 때의 컨텍스트.

        Args:
            query: 검색어

        Returns:
            컨텍스트 딕셔너리
        """
        return {
            "type": "not_found",
            "query": query,
            "message": (
                f"'{query}'에 대한 재활용자원 시세 정보를 찾을 수 없어요. "
                "품목명을 다르게 입력해보세요. (예: 캔, 페트병, 신문지)"
            ),
        }

    @staticmethod
    def build_error_context(error_message: str) -> dict[str, Any]:
        """에러 발생 시의 컨텍스트.

        Args:
            error_message: 에러 메시지

        Returns:
            에러 컨텍스트 딕셔너리
        """
        return {
            "type": "error",
            "message": error_message,
        }

    @staticmethod
    def extract_item_name_from_query(message: str) -> str | None:
        """사용자 메시지에서 품목명 추출.

        Args:
            message: 사용자 메시지 (예: "캔 한 개 얼마예요?")

        Returns:
            추출된 품목명 또는 None
        """
        # 간단한 키워드 매칭
        keywords = [
            "캔", "페트", "페트병", "신문지", "박스", "골판지",
            "유리", "플라스틱", "비닐", "스티로폼", "알루미늄",
            "철", "종이", "타이어", "고무",
        ]

        message_lower = message.lower()
        for keyword in keywords:
            if keyword in message_lower:
                return keyword

        return None

    @staticmethod
    def format_price_summary(items: list["RecyclablePriceDTO"]) -> str:
        """가격 요약 문자열 생성.

        Args:
            items: 가격 DTO 목록

        Returns:
            요약 문자열
        """
        if not items:
            return "가격 정보가 없습니다."

        lines = []
        for item in items[:5]:  # 최대 5개
            lines.append(f"- {item.display_name}: {item.price_text}")

        if len(items) > 5:
            lines.append(f"  외 {len(items) - 5}개 품목...")

        return "\n".join(lines)


__all__ = ["RecyclablePriceService"]
