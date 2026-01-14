"""Integrations - 외부 서비스 연동.

외부 도메인 API 호출을 캡슐화.
LLM Tool Calling 또는 그래프 노드에서 사용.

vs Subagent:
- Integration: 외부 시스템 호출 (입출력 스키마 고정)
- Subagent: 그래프 노드로 캡슐화된 기능 단위 (내부 구현은 Integration)

즉 "Subagent = Integration을 감싼 그래프 노드(모듈)"
"""

from .character import CharacterClientPort, CharacterDTO, CharacterService
from .location import LocationClientPort, LocationDTO, LocationService

__all__ = [
    # Character
    "CharacterClientPort",
    "CharacterDTO",
    "CharacterService",
    # Location
    "LocationClientPort",
    "LocationDTO",
    "LocationService",
]
