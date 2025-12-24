"""Service layer for the Character domain.

Note: CharacterService는 fastapi 의존성이 있어 worker에서 import 시 문제가 발생할 수 있습니다.
필요한 경우 직접 import하세요: from domains.character.services.character import CharacterService
"""

# Worker에서 evaluators만 import할 때 fastapi 의존성 문제 방지
# CharacterService는 필요한 곳에서 직접 import
__all__: list[str] = []
