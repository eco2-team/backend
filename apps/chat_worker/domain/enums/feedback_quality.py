"""RAG 품질 피드백 등급.

RAG 검색 결과의 품질을 평가하는 등급 정의.
"""

from enum import Enum


class FeedbackQuality(str, Enum):
    """RAG 결과 품질 등급.

    EXCELLENT: 완벽한 매칭 (0.9+)
    GOOD: 충분한 정보 (0.7-0.9)
    PARTIAL: 부분적 정보 (0.4-0.7)
    POOR: 부족한 정보 (0.2-0.4)
    NONE: 정보 없음 (0-0.2)
    """

    EXCELLENT = "excellent"
    GOOD = "good"
    PARTIAL = "partial"
    POOR = "poor"
    NONE = "none"

    @classmethod
    def from_score(cls, score: float) -> "FeedbackQuality":
        """점수에서 등급 변환.

        Args:
            score: 0.0 ~ 1.0 범위의 품질 점수

        Returns:
            해당하는 품질 등급
        """
        if score >= 0.9:
            return cls.EXCELLENT
        if score >= 0.7:
            return cls.GOOD
        if score >= 0.4:
            return cls.PARTIAL
        if score >= 0.2:
            return cls.POOR
        return cls.NONE

    def needs_fallback(self) -> bool:
        """Fallback이 필요한지 여부."""
        return self in (FeedbackQuality.POOR, FeedbackQuality.NONE)

    def needs_enhancement(self) -> bool:
        """추가 검색이 필요한지 여부."""
        return self in (FeedbackQuality.PARTIAL, FeedbackQuality.POOR, FeedbackQuality.NONE)
