"""waste_pipeline 유틸리티.

파일 I/O, 프롬프트 로딩 등 공통 유틸리티 제공.

Note:
    LLM 클라이언트는 domains._shared.llm 모듈로 이전됨.
    하위 호환성을 위해 get_openai_client, get_async_openai_client 유지.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

PACKAGE_ROOT = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_ROOT / "data"
ITEM_CLASS_PATH = DATA_DIR / "item_class_list.yaml"
SITUATION_TAG_PATH = DATA_DIR / "situation_tags.yaml"
PROMPTS_DIR = DATA_DIR / "prompts"
SOURCE_DIR = DATA_DIR / "source"
RESULTS_DIR = DATA_DIR / "results"
VISION_PROMPT_PATH = PROMPTS_DIR / "vision_classification_prompt.txt"
TEXT_CLASSIFICATION_PROMPT_PATH = PROMPTS_DIR / "text_classification_prompt.txt"
ANSWER_GENERATION_PROMPT_PATH = PROMPTS_DIR / "answer_generation_prompt.txt"


# ============================================================================
# Deprecated: OpenAI 클라이언트 (하위 호환성)
# 새 코드는 domains._shared.llm.get_llm_provider() 사용 권장
# ============================================================================


def get_openai_client():
    """Deprecated: Use domains._shared.llm.get_llm_provider() instead."""
    warnings.warn(
        "get_openai_client() is deprecated. Use get_llm_provider() from domains._shared.llm",
        DeprecationWarning,
        stacklevel=2,
    )
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
    return OpenAI(api_key=api_key)


def get_async_openai_client():
    """Deprecated: Use domains._shared.llm.get_llm_provider() instead."""
    warnings.warn(
        "get_async_openai_client() is deprecated. Use get_llm_provider() from domains._shared.llm",
        DeprecationWarning,
        stacklevel=2,
    )
    from openai import AsyncOpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
    return AsyncOpenAI(api_key=api_key)


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def load_prompt(path: Path) -> str:
    with path.open("r", encoding="utf-8") as file:
        content = file.read()
    digest = hashlib.sha1(content.encode("utf-8")).hexdigest()
    logger.info("Loaded prompt from %s (len=%d, sha1=%s)", path, len(content), digest)
    logger.debug("Prompt preview (%s): %s", path.name, content[:200])
    return content


def load_json_data(path: Path | str) -> Any:
    path_obj = Path(path)
    with path_obj.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json_result(data: dict, filename_prefix: str = "result") -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = RESULTS_DIR / f"{filename_prefix}_{timestamp}.json"
    with file_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    return file_path
