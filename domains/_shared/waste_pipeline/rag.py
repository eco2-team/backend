from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Optional

from .utils import SOURCE_DIR, load_json_data


logger = logging.getLogger(__name__)


# ==========================================
# Lite RAG: 분류 결과 기반 JSON 파일 매칭
# ==========================================
def find_matching_json(classification_result: dict) -> Optional[str]:
    """
    분류 결과를 기반으로 source/ 폴더에서 매칭되는 JSON 파일 경로를 반환

    Args:
        classification_result: Vision API의 분류 결과 JSON

    Returns:
        매칭된 JSON 파일 경로 (문자열), 매칭 실패 시 None
    """
    classification = classification_result.get("classification", {})
    major_category = classification.get("major_category")
    middle_category = classification.get("middle_category")

    # 1) 재활용폐기물의 경우: {major_category}_{middle_category}.json
    if major_category == "재활용폐기물" and middle_category:
        filename = f"{major_category}_{middle_category}.json"
        file_path = SOURCE_DIR / filename

        if file_path.exists():
            return str(file_path)

    # 2) 다른 카테고리의 경우: {major_category}.json
    if major_category:
        filename = f"{major_category}.json"
        file_path = SOURCE_DIR / filename

        if file_path.exists():
            return str(file_path)

    # 3) 매칭 실패
    return None


def get_disposal_rules(classification_result: dict) -> Optional[dict]:
    """
    분류 결과를 기반으로 배출 규정을 조회

    Args:
        classification_result: Vision API의 분류 결과 JSON

    Returns:
        배출 규정 JSON (dict), 매칭 실패 시 None
    """
    started_at = datetime.now(timezone.utc)
    timer = perf_counter()
    matched_json_path: Optional[str] = None
    success = False
    classification = (
        classification_result.get("classification", {}) if classification_result else {}
    )
    logger.info(
        "Lite RAG get_disposal_rules started at %s (major=%s, middle=%s)",
        started_at.isoformat(),
        classification.get("major_category"),
        classification.get("middle_category"),
    )

    try:
        matched_json_path = find_matching_json(classification_result)

        if not matched_json_path:
            return None

        payload = load_json_data(matched_json_path)
        success = payload is not None
        return payload
    finally:
        finished_at = datetime.now(timezone.utc)
        elapsed_ms = (perf_counter() - timer) * 1000
        logger.info(
            "Lite RAG get_disposal_rules finished at %s (started_at=%s, %.1f ms, success=%s, source=%s)",
            finished_at.isoformat(),
            started_at.isoformat(),
            elapsed_ms,
            success,
            matched_json_path or "N/A",
        )
