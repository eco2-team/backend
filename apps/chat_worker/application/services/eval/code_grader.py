"""Code Grader Service - L1 결정적 코드 기반 평가.

Swiss Cheese Layer 1: 정량적 임계치 기반의 빠르고 재현 가능한 평가.
목표 지연: < 50ms. 외부 의존성 없음 (순수 비즈니스 로직).

6개 직교 슬라이스:
1. format_compliance: 응답 형식 준수 (Regex + 구조 검증)
2. length_check: 응답 길이 적정성 (Token count)
3. language_consistency: 한국어 자연어 문장 비율 (Unicode range)
4. hallucination_keywords: 금지 표현 탐지 (Keyword blocklist)
5. citation_presence: 출처 정보 포함 (Pattern matching)
6. intent_answer_alignment: 의도-응답 정합성 (Intent별 구조 템플릿)

Clean Architecture:
- Service: 이 파일 (순수 비즈니스 로직, Port 의존 없음)
- Node: eval subgraph의 code_grader 노드에서 호출
- Command: EvaluateResponseCommand에서 오케스트레이션

참조: docs/plans/chat-eval-pipeline-plan.md Section 3.1
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# ── 상수 정의 ────────────────────────────────────────────────────────────────

# 슬라이스별 가중치 (합계 1.0)
SLICE_WEIGHTS: dict[str, float] = {
    "format_compliance": 0.15,
    "length_check": 0.15,
    "language_consistency": 0.15,
    "hallucination_keywords": 0.25,
    "citation_presence": 0.15,
    "intent_answer_alignment": 0.15,
}

# 길이 검증 임계치 (근사 토큰 수: 한국어 기준 ~1.5 char/token)
MIN_TOKEN_COUNT: int = 50
MAX_TOKEN_COUNT: int = 2000

# 한국어 문장 비율 임계치
LANGUAGE_CONSISTENCY_THRESHOLD: float = 0.80

# 금지 표현 블록리스트 (주기적 갱신 대상)
HALLUCINATION_BLOCKLIST: list[str] = [
    "확실히 보장",
    "100% 안전",
    "절대로 문제없",
    "무조건 괜찮",
    "아무렇게나 버려도",
    "법적 책임 없",
    "벌금 없",
    "환경부에서 허가한 방법은 아니지만",
    "비공식적이지만",
    "인터넷에서 본 건데",
    "정확하진 않지만",
    "제 생각에는",  # 주관적 판단 지양
]

# 출처 패턴 (환경부, 지자체, 공식 가이드 등)
CITATION_PATTERNS: list[str] = [
    r"환경부",
    r"지자체",
    r"공식\s*가이드",
    r"분리배출\s*가이드",
    r"출처\s*[:：]",
    r"참고\s*[:：]",
    r"근거\s*[:：]",
    r"※",
    r"자세한\s*(내용|정보|사항)은?\s*.*(문의|확인|참고)",
    r"홈페이지",
    r"고객\s*센터",
    r"전화\s*번호",
    r"1[38]\d{2}[-\s]?\d{4}",  # 공공기관 전화번호 패턴
]

# Intent별 필수 섹션 매핑
INTENT_REQUIRED_SECTIONS: dict[str, list[str]] = {
    "waste": ["분리배출", "방법", "주의"],
    "bulk_waste": ["대형폐기물", "신청", "수수료"],
    "location": ["위치", "주소"],
    "collection_point": ["수거함", "위치"],
    "recyclable_price": ["시세", "가격"],
    "weather": ["날씨", "기온"],
    "character": ["캐릭터"],
    "web_search": [],  # 동적 컨텐츠이므로 구조 제약 없음
    "image_generation": [],  # 이미지 생성이므로 텍스트 구조 제약 없음
    "general": [],  # 일반 대화이므로 구조 제약 없음
}

# ── URL / 이모지 / 기술 용어 필터 패턴 ────────────────────────────────────────
_URL_PATTERN = re.compile(r"https?://\S+|www\.\S+")
_EMOJI_PATTERN = re.compile(
    r"[\U0001F600-\U0001F64F"
    r"\U0001F300-\U0001F5FF"
    r"\U0001F680-\U0001F6FF"
    r"\U0001F1E0-\U0001F1FF"
    r"\U00002702-\U000027B0"
    r"\U000024C2-\U0001F251]+",
    flags=re.UNICODE,
)
_TECHNICAL_TERM_PATTERN = re.compile(
    r"[A-Za-z]{2,}[-_][A-Za-z]{2,}"  # kebab-case, snake_case 기술 용어
    r"|[A-Z]{2,}"  # 대문자 약어 (API, URL, JSON 등)
)

# 한국어 유니코드 범위 (자모 + 음절)
_KOREAN_RANGES: list[tuple[int, int]] = [
    (0xAC00, 0xD7A3),  # 한글 음절
    (0x1100, 0x11FF),  # 한글 자모
    (0x3130, 0x318F),  # 한글 호환 자모
    (0xA960, 0xA97F),  # 한글 자모 확장-A
    (0xD7B0, 0xD7FF),  # 한글 자모 확장-B
]

# 제외 Unicode 카테고리 (공백, 구두점, 기호, 제어, 숫자)
_SKIP_CATEGORIES = ("Z", "P", "S", "C", "N")


def _is_korean_codepoint(cp: int) -> bool:
    """코드포인트가 한국어 범위에 포함되는지 확인."""
    return any(lo <= cp <= hi for lo, hi in _KOREAN_RANGES)


# ── Result DTO ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CodeGraderResult:
    """L1 Code Grader 평가 결과.

    Attributes:
        scores: 슬라이스별 점수 (0.0~1.0)
        passed: 슬라이스별 통과 여부
        details: 슬라이스별 상세 사유
        overall_score: 가중 합산 점수 (0.0~1.0)
    """

    scores: dict[str, float]
    passed: dict[str, bool]
    details: dict[str, str]
    overall_score: float

    def to_dict(self) -> dict[str, Any]:
        """직렬화용 딕셔너리 변환."""
        return {
            "scores": self.scores,
            "passed": dict(self.passed),
            "details": dict(self.details),
            "overall_score": self.overall_score,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodeGraderResult":
        """딕셔너리에서 CodeGraderResult 생성.

        Args:
            data: 직렬화된 결과

        Returns:
            CodeGraderResult 인스턴스
        """
        return cls(
            scores=data["scores"],
            passed=data["passed"],
            details=data["details"],
            overall_score=data["overall_score"],
        )


# ── Service ───────────────────────────────────────────────────────────────────


class CodeGraderService:
    """L1 Code-Based Grader (결정적).

    정량적 임계치 기반의 빠르고 재현 가능한 평가.
    6개 직교 슬라이스를 독립적으로 평가하여 가중 합산.

    순수 비즈니스 로직만 포함. 외부 의존성(Port) 없음.
    """

    def evaluate(
        self,
        answer: str,
        intent: str,
        query: str = "",
    ) -> CodeGraderResult:
        """6개 슬라이스 평가 실행.

        Args:
            answer: 생성된 답변 텍스트
            intent: 분류된 Intent (waste, general 등)
            query: 사용자 질문 (intent_answer_alignment에 사용)

        Returns:
            CodeGraderResult: 슬라이스별 점수, 통과 여부, 상세 사유
        """
        scores: dict[str, float] = {}
        passed: dict[str, bool] = {}
        details: dict[str, str] = {}

        # 1. format_compliance
        s, p, d = self._check_format_compliance(answer)
        scores["format_compliance"] = s
        passed["format_compliance"] = p
        details["format_compliance"] = d

        # 2. length_check
        s, p, d = self._check_length(answer)
        scores["length_check"] = s
        passed["length_check"] = p
        details["length_check"] = d

        # 3. language_consistency
        s, p, d = self._check_language_consistency(answer)
        scores["language_consistency"] = s
        passed["language_consistency"] = p
        details["language_consistency"] = d

        # 4. hallucination_keywords
        s, p, d = self._check_hallucination_keywords(answer)
        scores["hallucination_keywords"] = s
        passed["hallucination_keywords"] = p
        details["hallucination_keywords"] = d

        # 5. citation_presence
        s, p, d = self._check_citation_presence(answer, intent)
        scores["citation_presence"] = s
        passed["citation_presence"] = p
        details["citation_presence"] = d

        # 6. intent_answer_alignment
        s, p, d = self._check_intent_answer_alignment(answer, intent)
        scores["intent_answer_alignment"] = s
        passed["intent_answer_alignment"] = p
        details["intent_answer_alignment"] = d

        # 가중 합산
        overall_score = sum(scores[name] * SLICE_WEIGHTS[name] for name in SLICE_WEIGHTS)

        result = CodeGraderResult(
            scores=scores,
            passed=passed,
            details=details,
            overall_score=round(overall_score, 4),
        )

        logger.debug(
            "Code grader evaluation completed",
            extra={
                "intent": intent,
                "overall_score": result.overall_score,
                "passed_count": sum(1 for v in passed.values() if v),
                "total_slices": len(passed),
            },
        )

        return result

    # ── 개별 슬라이스 구현 ──────────────────────────────────────────────────

    def _check_format_compliance(
        self,
        answer: str,
    ) -> tuple[float, bool, str]:
        """응답 형식 준수 검증.

        Regex + 구조 검증으로 필수 필드 존재 여부 확인.
        빈 응답, 깨진 마크다운, 미완성 문장 감지.

        Returns:
            (score, passed, detail)
        """
        if not answer or not answer.strip():
            return 0.0, False, "빈 응답"

        score = 1.0
        issues: list[str] = []

        # 미완성 문장 체크 (마지막 문장이 마침표/물음표/느낌표로 끝나지 않음)
        stripped = answer.strip()
        if stripped and stripped[-1] not in (".", "!", "?", "~", ")", "」", "»"):
            # 마크다운 코드 블록이나 리스트 항목은 예외
            last_line = stripped.split("\n")[-1].strip()
            if not last_line.startswith(("-", "*", "|", "```", "#")):
                score -= 0.3
                issues.append("미완성 문장")

        # 깨진 마크다운 체크 (열린 코드 블록)
        code_block_count = answer.count("```")
        if code_block_count % 2 != 0:
            score -= 0.3
            issues.append("깨진 코드 블록")

        # 깨진 괄호 체크
        for open_c, close_c in [("(", ")"), ("[", "]"), ("{", "}")]:
            if answer.count(open_c) != answer.count(close_c):
                score -= 0.1
                issues.append(f"괄호 불일치: {open_c}{close_c}")

        score = max(0.0, score)
        passed = score >= 0.7
        detail = ", ".join(issues) if issues else "형식 준수"

        return round(score, 4), passed, detail

    def _check_length(
        self,
        answer: str,
    ) -> tuple[float, bool, str]:
        """응답 길이 적정성 검증.

        한국어 기준 근사 토큰 수 산출.
        임계치: 50 < tokens < 2000.

        Returns:
            (score, passed, detail)
        """
        # 한국어 근사 토큰 수: 공백 기준 단어 수 + 한글 음절 수 보정
        # 간이 방법: 문자 수 / 1.5 (한국어 평균)
        char_count = len(answer.strip())
        approx_tokens = max(1, int(char_count / 1.5))

        if approx_tokens < MIN_TOKEN_COUNT:
            # 너무 짧은 응답: 비례 점수
            score = approx_tokens / MIN_TOKEN_COUNT
            return round(score, 4), False, f"토큰 부족: ~{approx_tokens} (최소 {MIN_TOKEN_COUNT})"

        if approx_tokens > MAX_TOKEN_COUNT:
            # 너무 긴 응답: 초과분 비례 감점
            excess_ratio = (approx_tokens - MAX_TOKEN_COUNT) / MAX_TOKEN_COUNT
            score = max(0.0, 1.0 - excess_ratio)
            return round(score, 4), False, f"토큰 초과: ~{approx_tokens} (최대 {MAX_TOKEN_COUNT})"

        return 1.0, True, f"적정 길이: ~{approx_tokens} tokens"

    def _check_language_consistency(
        self,
        answer: str,
    ) -> tuple[float, bool, str]:
        """한국어 자연어 문장 비율 검증.

        Unicode range 기반. 기술 용어/URL/이모지 제외 후 측정.
        임계치: >= 80%.

        Returns:
            (score, passed, detail)
        """
        # 기술 용어, URL, 이모지 제거
        cleaned = _URL_PATTERN.sub("", answer)
        cleaned = _EMOJI_PATTERN.sub("", cleaned)
        cleaned = _TECHNICAL_TERM_PATTERN.sub("", cleaned)

        if not cleaned.strip():
            return 1.0, True, "내용 없음 (필터링 후)"

        # 한국어 문자 비율 계산 (공백/구두점/숫자 제외)
        total_chars = 0
        korean_chars = 0

        for ch in cleaned:
            if unicodedata.category(ch).startswith(_SKIP_CATEGORIES):
                continue
            total_chars += 1
            if _is_korean_codepoint(ord(ch)):
                korean_chars += 1

        if total_chars == 0:
            return 1.0, True, "문자 없음 (숫자/기호만)"

        ratio = korean_chars / total_chars
        passed = ratio >= LANGUAGE_CONSISTENCY_THRESHOLD
        score = min(1.0, ratio / LANGUAGE_CONSISTENCY_THRESHOLD) if not passed else 1.0

        detail = f"한국어 비율: {ratio:.1%} (임계치: {LANGUAGE_CONSISTENCY_THRESHOLD:.0%})"

        return round(score, 4), passed, detail

    def _check_hallucination_keywords(
        self,
        answer: str,
    ) -> tuple[float, bool, str]:
        """금지 표현 탐지.

        Keyword blocklist 기반. 매칭 수 0이면 통과.

        Returns:
            (score, passed, detail)
        """
        answer_lower = answer.lower()
        matched: list[str] = []

        for keyword in HALLUCINATION_BLOCKLIST:
            if keyword.lower() in answer_lower:
                matched.append(keyword)

        if not matched:
            return 1.0, True, "금지 표현 없음"

        # 매칭 수에 비례하여 감점 (1개당 0.3 감점)
        score = max(0.0, 1.0 - len(matched) * 0.3)
        detail = f"금지 표현 {len(matched)}건: {', '.join(matched[:3])}"
        if len(matched) > 3:
            detail += f" 외 {len(matched) - 3}건"

        return round(score, 4), False, detail

    def _check_citation_presence(
        self,
        answer: str,
        intent: str,
    ) -> tuple[float, bool, str]:
        """출처 정보 포함 검증.

        waste intent 시 필수. 기타 intent는 있으면 가점.

        Returns:
            (score, passed, detail)
        """
        matched_citations: list[str] = []

        for pattern in CITATION_PATTERNS:
            if re.search(pattern, answer):
                matched_citations.append(pattern)

        has_citation = len(matched_citations) > 0

        # waste intent: 출처 필수
        if intent == "waste":
            if has_citation:
                return 1.0, True, f"출처 포함 ({len(matched_citations)}개 패턴 매칭)"
            return 0.0, False, "waste intent인데 출처 정보 없음"

        # bulk_waste, collection_point: 출처 권장
        if intent in ("bulk_waste", "collection_point", "recyclable_price"):
            if has_citation:
                return 1.0, True, f"출처 포함 ({len(matched_citations)}개 패턴 매칭)"
            return 0.5, True, "출처 권장 intent이나 미포함 (감점)"

        # 기타 intent: 출처 있으면 만점, 없어도 통과
        if has_citation:
            return 1.0, True, f"출처 포함 ({len(matched_citations)}개 패턴 매칭)"
        return 0.8, True, "출처 선택적 intent (미포함이나 허용)"

    def _check_intent_answer_alignment(
        self,
        answer: str,
        intent: str,
    ) -> tuple[float, bool, str]:
        """의도-응답 정합성 검증.

        Intent별 구조 템플릿 매칭. 필수 섹션 존재 여부 확인.

        Returns:
            (score, passed, detail)
        """
        required_sections = INTENT_REQUIRED_SECTIONS.get(intent, [])

        # 필수 섹션이 없는 intent (general, web_search, image_generation)
        if not required_sections:
            return 1.0, True, f"{intent} intent: 구조 제약 없음"

        answer_lower = answer.lower()
        found: list[str] = []
        missing: list[str] = []

        for section in required_sections:
            if section.lower() in answer_lower:
                found.append(section)
            else:
                missing.append(section)

        if not missing:
            return 1.0, True, f"필수 섹션 모두 포함: {', '.join(found)}"

        # 비례 점수
        total = len(required_sections)
        found_count = len(found)
        score = found_count / total if total > 0 else 1.0

        detail = f"필수 섹션 {found_count}/{total} 포함"
        if missing:
            detail += f" (누락: {', '.join(missing)})"

        passed = score >= 0.7

        return round(score, 4), passed, detail


__all__ = ["CodeGraderService", "CodeGraderResult"]
