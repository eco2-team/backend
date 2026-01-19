"""Character Name Detector.

사용자 메시지에서 캐릭터 이름/별칭을 감지합니다.
character_names.yaml의 aliases를 기반으로 매칭합니다.

사용 예시:
    detector = CharacterNameDetector()
    result = detector.detect("페티가 분리배출하는 모습 그려줘")
    # result = DetectedCharacter(code="char-petty", name="페티", cdn_code="pet")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import ClassVar

import yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DetectedCharacter:
    """감지된 캐릭터 정보."""

    code: str  # DB 코드 (char-petty)
    name: str  # 공식 이름 (페티)
    cdn_code: str  # CDN 코드 (pet)
    matched_alias: str  # 매칭된 별칭 (사용자가 입력한 것)


@dataclass(frozen=True)
class CharacterInfo:
    """캐릭터 정보 (YAML에서 로드)."""

    code: str
    name: str
    aliases: list[str]
    match_label: str
    cdn_code: str


class CharacterNameDetector:
    """캐릭터 이름 감지기.

    사용자 메시지에서 캐릭터 이름/별칭을 찾아 해당 캐릭터 정보를 반환합니다.
    """

    # 기본 캐릭터 (이코)는 감지 대상에서 제외 (항상 페르소나로 사용)
    EXCLUDED_CODES: ClassVar[set[str]] = {"char-eco"}

    def __init__(self, yaml_path: str | Path | None = None):
        """초기화.

        Args:
            yaml_path: character_names.yaml 경로 (None이면 기본 경로)
        """
        if yaml_path is None:
            yaml_path = Path(__file__).parent / "data" / "character_names.yaml"
        self._yaml_path = Path(yaml_path)
        self._characters: list[CharacterInfo] = []
        self._alias_map: dict[str, CharacterInfo] = {}  # 별칭 → 캐릭터
        self._loaded = False

    def _load_if_needed(self) -> None:
        """YAML 파일 로드 (lazy loading)."""
        if self._loaded:
            return

        try:
            with open(self._yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            characters_data = data.get("characters", [])
            for char_data in characters_data:
                code = char_data.get("code", "")

                # 이코(기본 캐릭터)는 감지 대상에서 제외
                if code in self.EXCLUDED_CODES:
                    continue

                char_info = CharacterInfo(
                    code=code,
                    name=char_data.get("name", ""),
                    aliases=char_data.get("aliases", []),
                    match_label=char_data.get("match_label", ""),
                    cdn_code=char_data.get("cdn_code", ""),
                )
                self._characters.append(char_info)

                # 별칭 맵 구축 (소문자로 정규화)
                for alias in char_info.aliases:
                    alias_lower = alias.lower()
                    self._alias_map[alias_lower] = char_info

            self._loaded = True
            logger.info(
                "Character names loaded",
                extra={
                    "character_count": len(self._characters),
                    "alias_count": len(self._alias_map),
                },
            )

        except Exception as e:
            logger.error("Failed to load character names: %s", e)
            self._loaded = True  # 에러 시에도 재시도 방지

    def detect(self, message: str) -> DetectedCharacter | None:
        """메시지에서 캐릭터 이름을 감지합니다.

        Args:
            message: 사용자 메시지

        Returns:
            DetectedCharacter 또는 None (감지 실패)

        Note:
            여러 캐릭터가 언급된 경우 첫 번째로 발견된 것을 반환합니다.
        """
        self._load_if_needed()

        if not message:
            return None

        message_lower = message.lower()

        # 별칭 길이 순으로 정렬 (긴 것 먼저 - "페트병" vs "페트" 같은 경우 방지)
        sorted_aliases = sorted(self._alias_map.keys(), key=len, reverse=True)

        for alias in sorted_aliases:
            if alias in message_lower:
                char_info = self._alias_map[alias]
                logger.debug(
                    "Character detected",
                    extra={
                        "matched_alias": alias,
                        "character_code": char_info.code,
                        "character_name": char_info.name,
                    },
                )
                return DetectedCharacter(
                    code=char_info.code,
                    name=char_info.name,
                    cdn_code=char_info.cdn_code,
                    matched_alias=alias,
                )

        return None

    def detect_all(self, message: str) -> list[DetectedCharacter]:
        """메시지에서 모든 캐릭터 이름을 감지합니다.

        Args:
            message: 사용자 메시지

        Returns:
            감지된 캐릭터 목록 (중복 제거)
        """
        self._load_if_needed()

        if not message:
            return []

        message_lower = message.lower()
        detected: dict[str, DetectedCharacter] = {}  # code → DetectedCharacter

        sorted_aliases = sorted(self._alias_map.keys(), key=len, reverse=True)

        for alias in sorted_aliases:
            if alias in message_lower:
                char_info = self._alias_map[alias]
                # 이미 감지된 캐릭터는 스킵
                if char_info.code not in detected:
                    detected[char_info.code] = DetectedCharacter(
                        code=char_info.code,
                        name=char_info.name,
                        cdn_code=char_info.cdn_code,
                        matched_alias=alias,
                    )

        return list(detected.values())

    def get_cdn_url(self, cdn_code: str) -> str:
        """CDN 코드로 이미지 URL 생성.

        Args:
            cdn_code: CDN 코드 (pet, metal, etc.)

        Returns:
            CDN 이미지 URL
        """
        return f"https://images.dev.growbin.app/character/{cdn_code}.png"


@lru_cache(maxsize=1)
def get_character_name_detector() -> CharacterNameDetector:
    """CharacterNameDetector 싱글톤."""
    return CharacterNameDetector()
