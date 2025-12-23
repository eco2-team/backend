from __future__ import annotations

import json
import os
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAI

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

_openai_client: OpenAI | None = None
_async_openai_client: AsyncOpenAI | None = None


def _build_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
    return OpenAI(api_key=api_key)


def _build_async_client() -> AsyncOpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
    return AsyncOpenAI(api_key=api_key)


def get_openai_client() -> OpenAI:
    """Lazy-initialize OpenAI client to avoid import-time failures."""
    global _openai_client
    if _openai_client is None:
        _openai_client = _build_client()
    return _openai_client


def get_async_openai_client() -> AsyncOpenAI:
    """Lazy-initialize AsyncOpenAI client for async contexts."""
    global _async_openai_client
    if _async_openai_client is None:
        _async_openai_client = _build_async_client()
    return _async_openai_client


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
