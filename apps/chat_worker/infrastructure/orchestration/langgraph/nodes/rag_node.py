"""RAG Node."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.retrieval import RetrieverPort

logger = logging.getLogger(__name__)


def create_rag_node(
    retriever: "RetrieverPort",
    event_publisher: "ProgressNotifierPort",
):
    """RAG 노드 팩토리."""

    async def rag_node(state: dict[str, Any]) -> dict[str, Any]:
        job_id = state["job_id"]
        message = state.get("message", "")
        classification = state.get("classification_result")

        await event_publisher.notify_stage(
            task_id=job_id,
            stage="rag",
            status="started",
            progress=40,
            message="📚 규정 검색 중...",
        )

        try:
            disposal_rules = None

            if classification:
                category = classification.get("classification", {}).get("major_category", "")
                subcategory = classification.get("classification", {}).get("minor_category", "")
                disposal_rules = retriever.search(category, subcategory)

            if not disposal_rules:
                keywords = _extract_keywords(message)
                for keyword in keywords:
                    results = retriever.search_by_keyword(keyword, limit=1)
                    if results:
                        disposal_rules = results[0]
                        break

            logger.info("RAG: %s for job=%s", "found" if disposal_rules else "not found", job_id)

            await event_publisher.notify_stage(
                task_id=job_id,
                stage="rag",
                status="completed",
                progress=60,
                result={"found": disposal_rules is not None},
            )

            return {**state, "disposal_rules": disposal_rules}

        except Exception as e:
            logger.error("RAG failed: %s", e)
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="rag",
                status="failed",
                result={"error": str(e)},
            )
            return {**state, "disposal_rules": None}

    return rag_node


def _extract_keywords(message: str) -> list[str]:
    waste_keywords = [
        "페트병", "플라스틱", "유리병", "캔", "종이", "비닐",
        "스티로폼", "음식물", "건전지", "형광등", "가전", "의류",
    ]
    found = []
    message_lower = message.lower()
    for keyword in waste_keywords:
        if keyword in message_lower:
            found.append(keyword)
    return found
