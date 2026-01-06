"""File Prompt Repository - PromptRepositoryPort 구현체.

domains/_shared/waste_pipeline/utils.py 로직 이전.
파일 시스템 기반 프롬프트/YAML 로딩.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import yaml

from scan_worker.application.classify.ports.prompt_repository import (
    PromptRepositoryPort,
)

logger = logging.getLogger(__name__)


class FilePromptRepository(PromptRepositoryPort):
    """파일 시스템 기반 프롬프트 리포지토리.

    프롬프트 템플릿, 분류체계, 상황 태그 로딩.
    """

    def __init__(self, assets_path: str | Path):
        """초기화.

        Args:
            assets_path: 정적 에셋 경로 (prompts/, data/ 포함)
        """
        self._assets_path = Path(assets_path)
        self._prompts_dir = self._assets_path / "prompts"
        self._data_dir = self._assets_path / "data"
        self._cache: dict[str, Any] = {}
        logger.info(
            "FilePromptRepository initialized (path=%s)",
            self._assets_path,
        )

    def get_prompt(self, name: str) -> str:
        """프롬프트 템플릿 로딩.

        Args:
            name: 프롬프트 이름 (확장자 제외)

        Returns:
            프롬프트 템플릿 문자열
        """
        cache_key = f"prompt:{name}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        filepath = self._prompts_dir / f"{name}.txt"
        if not filepath.exists():
            raise FileNotFoundError(f"Prompt not found: {filepath}")

        with filepath.open("r", encoding="utf-8") as f:
            content = f.read()

        # SHA1 해시로 로딩 검증
        digest = hashlib.sha1(content.encode("utf-8")).hexdigest()
        logger.info(
            "Prompt loaded (path=%s, len=%d, sha1=%s)",
            filepath,
            len(content),
            digest,
        )

        self._cache[cache_key] = content
        return content

    def get_classification_schema(self) -> dict[str, Any]:
        """분류체계 YAML 로딩.

        Returns:
            item_class_list.yaml 내용 (dict)
        """
        cache_key = "schema:classification"
        if cache_key in self._cache:
            return self._cache[cache_key]

        filepath = self._data_dir / "item_class_list.yaml"
        if not filepath.exists():
            raise FileNotFoundError(f"Classification schema not found: {filepath}")

        with filepath.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        logger.info("Classification schema loaded (path=%s)", filepath)
        self._cache[cache_key] = data
        return data

    def get_situation_tags(self) -> dict[str, Any]:
        """상황 태그 YAML 로딩.

        Returns:
            situation_tags.yaml 내용 (dict)
        """
        cache_key = "schema:situation_tags"
        if cache_key in self._cache:
            return self._cache[cache_key]

        filepath = self._data_dir / "situation_tags.yaml"
        if not filepath.exists():
            raise FileNotFoundError(f"Situation tags not found: {filepath}")

        with filepath.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        logger.info("Situation tags loaded (path=%s)", filepath)
        self._cache[cache_key] = data
        return data
