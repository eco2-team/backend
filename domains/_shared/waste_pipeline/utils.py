from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data" / "waste_pipeline"
ITEM_CLASS_PATH = DATA_DIR / "item_class_list.yaml"
SITUATION_TAG_PATH = DATA_DIR / "situation_tags.yaml"
PROMPTS_DIR = DATA_DIR / "prompts"
SOURCE_DIR = DATA_DIR / "source"
RESULTS_DIR = DATA_DIR / "results"
VISION_PROMPT_PATH = PROMPTS_DIR / "vision_classification_prompt.txt"
ANSWER_GENERATION_PROMPT_PATH = PROMPTS_DIR / "answer_generation_prompt.txt"

_openai_client: OpenAI | None = None


def _build_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
    return OpenAI(api_key=api_key)


def get_openai_client() -> OpenAI:
    """Lazy-initialize OpenAI client to avoid import-time failures."""
    global _openai_client
    if _openai_client is None:
        _openai_client = _build_client()
    return _openai_client


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def load_prompt(path: Path) -> str:
    with path.open("r", encoding="utf-8") as file:
        return file.read()


def load_json_data(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json_result(data: dict, filename_prefix: str = "result") -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = RESULTS_DIR / f"{filename_prefix}_{timestamp}.json"
    with file_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    return file_path
