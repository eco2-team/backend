"""Users Worker.

유저 캐릭터 소유권 배치 저장을 담당하는 Celery Worker입니다.

Clean Architecture:
    - Presentation: Celery Batch Task
    - Application: SaveCharactersCommand
    - Infrastructure: SqlaCharacterStore (PostgreSQL)
"""
