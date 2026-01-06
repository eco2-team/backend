"""Domain Entity 테스트.

Domain Entity는 비즈니스 로직의 핵심입니다.
동등성, 해시 가능성 등 Entity의 기본 계약을 검증합니다.
"""

from datetime import datetime, timezone
from uuid import uuid4

from character.domain.entities import Character, CharacterOwnership
from character.domain.enums import CharacterOwnershipStatus


class TestCharacterEntity:
    """Character 엔티티 테스트.

    검증 포인트:
    1. 엔티티 생성
    2. 동등성 (id 기반)
    3. 해시 가능성 (set, dict 키로 사용 가능)
    """

    def test_creation_with_required_fields(self) -> None:
        """필수 필드만으로 생성.

        검증:
        - id, code, name, type_label, dialog만으로 생성 가능

        이유:
        최소한의 정보로 캐릭터를 생성할 수 있어야
        테스트 작성과 초기 데이터 설정이 용이합니다.
        """
        character = Character(
            id=uuid4(),
            code="char-eco",
            name="이코",
            type_label="기본",
            dialog="안녕!",
        )

        assert character.code == "char-eco"
        assert character.name == "이코"
        assert character.description is None
        assert character.match_label is None

    def test_equality_based_on_id(self) -> None:
        """동등성은 id 기반.

        검증:
        - 같은 id면 다른 속성이 달라도 동등
        - 다른 id면 같은 속성이어도 다름

        이유:
        Entity는 Identity(id)로 구분됩니다.
        같은 캐릭터의 다른 버전을 비교할 때 중요합니다.
        """
        char_id = uuid4()

        char1 = Character(
            id=char_id,
            code="char-eco",
            name="이코",
            type_label="기본",
            dialog="안녕!",
        )

        char2 = Character(
            id=char_id,  # 같은 id
            code="char-eco-v2",  # 다른 code
            name="이코 2",  # 다른 name
            type_label="기본",
            dialog="안녕!",
        )

        char3 = Character(
            id=uuid4(),  # 다른 id
            code="char-eco",  # 같은 code
            name="이코",  # 같은 name
            type_label="기본",
            dialog="안녕!",
        )

        # 같은 id = 동등
        assert char1 == char2
        # 다른 id = 다름
        assert char1 != char3

    def test_not_equal_to_non_character(self) -> None:
        """다른 타입과 비교.

        검증:
        - Character가 아닌 객체와 비교하면 False

        이유:
        타입 안전성을 보장합니다.
        """
        character = Character(
            id=uuid4(),
            code="char-eco",
            name="이코",
            type_label="기본",
            dialog="안녕!",
        )

        assert character != "not a character"
        assert character != 123
        assert character != None  # noqa: E711

    def test_hashable_for_set_usage(self) -> None:
        """set에서 사용 가능.

        검증:
        - set에 Character를 추가/조회 가능
        - 같은 id의 Character는 중복 제거됨

        이유:
        캐릭터 목록에서 중복 제거 시 set을 사용합니다.
        """
        char_id = uuid4()

        char1 = Character(
            id=char_id,
            code="char-eco",
            name="이코",
            type_label="기본",
            dialog="안녕!",
        )

        char2 = Character(
            id=char_id,  # 같은 id
            code="char-eco",
            name="이코",
            type_label="기본",
            dialog="안녕!",
        )

        char3 = Character(
            id=uuid4(),  # 다른 id
            code="char-pet",
            name="페트",
            type_label="재활용",
            dialog="안녕!",
        )

        char_set = {char1, char2, char3}

        # 같은 id는 중복 제거
        assert len(char_set) == 2

    def test_hashable_for_dict_key(self) -> None:
        """dict 키로 사용 가능.

        검증:
        - Character를 dict 키로 사용 가능

        이유:
        캐릭터별 메타데이터를 저장할 때 dict를 사용합니다.
        """
        character = Character(
            id=uuid4(),
            code="char-eco",
            name="이코",
            type_label="기본",
            dialog="안녕!",
        )

        char_metadata = {character: {"popularity": 100}}

        assert char_metadata[character]["popularity"] == 100


class TestCharacterOwnershipEntity:
    """CharacterOwnership 엔티티 테스트.

    검증 포인트:
    1. 엔티티 생성
    2. 해시 가능성
    3. character 관계
    """

    def test_creation_with_required_fields(self) -> None:
        """필수 필드로 생성.

        검증:
        - id, user_id, character_id, character_code, status로 생성 가능

        이유:
        소유권의 최소 정보로 엔티티를 생성할 수 있어야 합니다.
        """
        ownership = CharacterOwnership(
            id=uuid4(),
            user_id=uuid4(),
            character_id=uuid4(),
            character_code="char-eco",
            status=CharacterOwnershipStatus.OWNED,
        )

        assert ownership.character_code == "char-eco"
        assert ownership.status == CharacterOwnershipStatus.OWNED
        assert ownership.source is None
        assert ownership.character is None

    def test_with_optional_fields(self) -> None:
        """모든 필드로 생성.

        검증:
        - source, acquired_at, character 등 optional 필드 포함

        이유:
        전체 소유권 정보를 조회할 때 모든 필드가 필요합니다.
        """
        character = Character(
            id=uuid4(),
            code="char-eco",
            name="이코",
            type_label="기본",
            dialog="안녕!",
        )

        ownership = CharacterOwnership(
            id=uuid4(),
            user_id=uuid4(),
            character_id=character.id,
            character_code="char-eco",
            status=CharacterOwnershipStatus.OWNED,
            source="scan-reward",
            acquired_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            character=character,
        )

        assert ownership.source == "scan-reward"
        assert ownership.acquired_at == datetime(2024, 1, 1, tzinfo=timezone.utc)
        assert ownership.character == character
        assert ownership.character.name == "이코"

    def test_hashable(self) -> None:
        """해시 가능성.

        검증:
        - set에서 사용 가능

        이유:
        사용자의 소유 캐릭터 목록을 중복 없이 관리할 때 필요합니다.
        """
        ownership = CharacterOwnership(
            id=uuid4(),
            user_id=uuid4(),
            character_id=uuid4(),
            character_code="char-eco",
            status=CharacterOwnershipStatus.OWNED,
        )

        # set에 추가 가능
        ownership_set = {ownership}
        assert ownership in ownership_set

    def test_status_enum_values(self) -> None:
        """소유 상태 enum 값.

        검증:
        - 유효한 status 값들이 존재하는지

        이유:
        status는 비즈니스 로직에서 중요한 역할을 합니다.
        현재는 OWNED만 사용하지만 확장 가능성을 검증합니다.
        """
        # OWNED 상태
        ownership_owned = CharacterOwnership(
            id=uuid4(),
            user_id=uuid4(),
            character_id=uuid4(),
            character_code="char-eco",
            status=CharacterOwnershipStatus.OWNED,
        )

        assert ownership_owned.status == CharacterOwnershipStatus.OWNED
        assert ownership_owned.status.value == "owned"


class TestCharacterRewardSourceEnum:
    """CharacterRewardSource enum 테스트."""

    def test_scan_source(self) -> None:
        """SCAN 소스 값.

        검증:
        - SCAN 소스가 올바른 값을 가지는지

        이유:
        리워드 소스에 따라 다른 처리가 필요할 수 있습니다.
        """
        from character.domain.enums import CharacterRewardSource

        assert CharacterRewardSource.SCAN.value == "scan"

    def test_string_conversion(self) -> None:
        """문자열 변환.

        검증:
        - gRPC에서 받은 문자열을 enum으로 변환 가능

        이유:
        외부 시스템에서 문자열로 전달받아 enum으로 변환합니다.
        """
        from character.domain.enums import CharacterRewardSource

        source = CharacterRewardSource("scan")
        assert source == CharacterRewardSource.SCAN
