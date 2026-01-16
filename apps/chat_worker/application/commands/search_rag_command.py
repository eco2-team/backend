"""Search RAG Command.

분리수거 규정 검색 UseCase.

Clean Architecture:
- Command(UseCase): 이 파일 - 정책/흐름, Port 조립
- Service: RAGSearcherService - 순수 비즈니스 로직
- Port: RetrieverPort - 검색 추상화
- Node(Adapter): rag_node.py - LangGraph glue

검색 전략 (우선순위):
1. 분류 기반 검색 (Vision 결과가 있는 경우)
2. 태그 기반 컨텍스트 검색 (item_class + situation_tags)
3. 키워드 기반 Fallback 검색
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from chat_worker.application.services.rag_searcher import RAGSearcherService

if TYPE_CHECKING:
    from chat_worker.application.ports.retrieval import RetrieverPort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchRAGInput:
    """Command 입력 DTO."""

    job_id: str
    message: str
    classification: dict[str, Any] | None = None
    enable_contextual_search: bool = True  # 태그 기반 컨텍스트 검색 활성화


@dataclass
class SearchRAGOutput:
    """Command 출력 DTO."""

    found: bool
    disposal_rules: dict[str, Any] | None = None
    search_method: str = "none"  # "classification" | "contextual" | "keyword" | "none"
    matched_keyword: str | None = None
    events: list[str] = field(default_factory=list)
    # Phase 1-4: Evidence 정보 (FeedbackResult와 연동)
    evidence: list[dict[str, Any]] = field(default_factory=list)


class SearchRAGCommand:
    """분리수거 규정 검색 Command (UseCase).

    정책/흐름:
    1. 검색 전략 결정 (분류 → 컨텍스트 → 키워드)
    2. 검색 실행
    3. Evidence 형식으로 반환 (Phase 1-4 연동)

    Port 주입:
    - retriever: 검색 Port (TagBasedRetriever 권장)
    """

    def __init__(self, retriever: "RetrieverPort") -> None:
        """Command 초기화.

        Args:
            retriever: 검색 Port
        """
        self._retriever = retriever
        self._search_service = RAGSearcherService()

    async def execute(self, input_dto: SearchRAGInput) -> SearchRAGOutput:
        """Command 실행.

        Args:
            input_dto: 입력 DTO

        Returns:
            출력 DTO (Evidence 포함)
        """
        events: list[str] = []
        evidence: list[dict[str, Any]] = []

        # 1. 검색 전략 결정 (Service)
        strategy, params = self._search_service.determine_search_strategy(
            classification=input_dto.classification,
            message=input_dto.message,
        )
        events.append(f"strategy_determined:{strategy}")

        logger.info(
            "RAG search strategy determined",
            extra={
                "job_id": input_dto.job_id,
                "strategy": strategy,
                "params": params,
            },
        )

        # 2. 검색 실행
        disposal_rules = None
        matched_keyword = None

        if strategy == "classification":
            # 분류 기반 검색
            disposal_rules = self._retriever.search(
                params["category"],
                params["subcategory"],
            )
            if disposal_rules:
                events.append("classification_search_success")
                evidence.append({
                    "chunk_id": disposal_rules.get("key", ""),
                    "relevance": "high",
                    "quoted_text": "",
                    "method": "classification",
                })
            else:
                events.append("classification_search_no_result")
                # Fallback: 컨텍스트 검색으로
                if input_dto.enable_contextual_search:
                    strategy = "contextual"
                else:
                    strategy = "keyword"
                    keywords = self._search_service.extract_keywords(input_dto.message)
                    params = {"keywords": keywords}

        # 2.1 태그 기반 컨텍스트 검색 (Anthropic Contextual Retrieval)
        if strategy == "contextual" or (
            strategy == "none" and input_dto.enable_contextual_search
        ):
            contextual_results = self._retriever.search_with_context(input_dto.message)

            if contextual_results:
                # 가장 관련성 높은 결과 사용
                best_result = contextual_results[0]
                disposal_rules = {
                    "key": best_result.chunk_id,
                    "category": best_result.category,
                    "data": best_result.data,
                }
                strategy = "contextual"
                events.append("contextual_search_success")

                # Evidence 생성
                for result in contextual_results[:3]:  # 상위 3개
                    evidence.append({
                        "chunk_id": result.chunk_id,
                        "relevance": result.relevance,
                        "quoted_text": result.quoted_text,
                        "matched_tags": result.matched_tags,
                        "method": "contextual",
                    })
            else:
                events.append("contextual_search_no_result")
                # Fallback: 키워드 검색으로
                strategy = "keyword"
                keywords = self._search_service.extract_keywords(input_dto.message)
                params = {"keywords": keywords}

        if strategy == "keyword" and params.get("keywords"):
            # 키워드 기반 검색
            for keyword in params["keywords"]:
                results = self._retriever.search_by_keyword(keyword, limit=1)
                if results:
                    disposal_rules = results[0]
                    matched_keyword = keyword
                    events.append(f"keyword_search_success:{keyword}")
                    evidence.append({
                        "chunk_id": results[0].get("key", ""),
                        "relevance": "medium",
                        "quoted_text": "",
                        "method": "keyword",
                    })
                    break

            if not disposal_rules:
                events.append("keyword_search_no_result")

        if strategy == "none":
            events.append("no_search_strategy")

        # 3. 결과 반환
        found = disposal_rules is not None

        logger.info(
            "RAG search completed",
            extra={
                "job_id": input_dto.job_id,
                "found": found,
                "method": strategy if found else "none",
                "evidence_count": len(evidence),
            },
        )

        return SearchRAGOutput(
            found=found,
            disposal_rules=disposal_rules,
            search_method=strategy if found else "none",
            matched_keyword=matched_keyword,
            events=events,
            evidence=evidence,
        )
