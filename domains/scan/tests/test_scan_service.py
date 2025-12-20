"""ScanService unit tests."""

from __future__ import annotations


import pytest

from domains.scan.schemas.scan import ClassificationRequest


class TestShouldAttemptReward:
    """_should_attempt_reward 메서드 테스트."""

    def test_returns_false_when_reward_disabled(
        self, mock_settings, mock_repository, mock_pipeline_result
    ):
        """reward_feature_enabled가 False면 False 반환."""
        from domains._shared.schemas.waste import WasteClassificationResult
        from domains.scan.services.scan import ScanService

        mock_settings.reward_feature_enabled = False
        service = ScanService.__new__(ScanService)
        service.settings = mock_settings
        service.repository = mock_repository

        result = WasteClassificationResult(**mock_pipeline_result)
        assert service._should_attempt_reward(result) is False

    def test_returns_false_when_non_recyclable(self, mock_settings, mock_repository):
        """major_category가 '재활용폐기물'이 아니면 False."""
        from domains._shared.schemas.waste import WasteClassificationResult
        from domains.scan.services.scan import ScanService

        service = ScanService.__new__(ScanService)
        service.settings = mock_settings
        service.repository = mock_repository

        result = WasteClassificationResult(
            classification_result={
                "classification": {
                    "major_category": "일반폐기물",
                    "middle_category": "음식물",
                }
            },
            disposal_rules={"배출방법_공통": "종량제 봉투"},
            final_answer={"user_answer": "답변", "insufficiencies": []},
        )
        assert service._should_attempt_reward(result) is False

    def test_returns_false_when_no_disposal_rules(self, mock_settings, mock_repository):
        """disposal_rules가 비어있으면 False."""
        from domains._shared.schemas.waste import WasteClassificationResult
        from domains.scan.services.scan import ScanService

        service = ScanService.__new__(ScanService)
        service.settings = mock_settings
        service.repository = mock_repository

        result = WasteClassificationResult(
            classification_result={
                "classification": {
                    "major_category": "재활용폐기물",
                    "middle_category": "무색페트병",
                }
            },
            disposal_rules={},  # 빈 딕셔너리 = falsy
            final_answer={"user_answer": "답변", "insufficiencies": []},
        )
        assert service._should_attempt_reward(result) is False

    def test_returns_true_for_valid_recyclable(
        self, mock_settings, mock_repository, mock_pipeline_result
    ):
        """재활용폐기물 + disposal_rules 있으면 True."""
        from domains._shared.schemas.waste import WasteClassificationResult
        from domains.scan.services.scan import ScanService

        service = ScanService.__new__(ScanService)
        service.settings = mock_settings
        service.repository = mock_repository

        result = WasteClassificationResult(**mock_pipeline_result)
        assert service._should_attempt_reward(result) is True


class TestExtractClassification:
    """_extract_classification 메서드 테스트."""

    def test_extracts_all_categories(self, mock_pipeline_result):
        """major, middle, minor 카테고리 추출."""
        from domains._shared.schemas.waste import WasteClassificationResult
        from domains.scan.services.scan import ScanService

        result = WasteClassificationResult(**mock_pipeline_result)
        major, middle, minor = ScanService._extract_classification(result)

        assert major == "재활용폐기물"
        assert middle == "무색페트병"
        assert minor == "음료수병"

    def test_handles_missing_minor(self):
        """minor_category가 없을 때 None 반환."""
        from domains._shared.schemas.waste import WasteClassificationResult
        from domains.scan.services.scan import ScanService

        result = WasteClassificationResult(
            classification_result={
                "classification": {
                    "major_category": "재활용폐기물",
                    "middle_category": "무색페트병",
                }
            },
            disposal_rules={},
            final_answer={},
        )
        major, middle, minor = ScanService._extract_classification(result)

        assert major == "재활용폐기물"
        assert middle == "무색페트병"
        assert minor is None

    def test_handles_empty_result(self):
        """classification_result가 비어있을 때."""
        from domains._shared.schemas.waste import WasteClassificationResult
        from domains.scan.services.scan import ScanService

        result = WasteClassificationResult(
            classification_result={},
            disposal_rules={},
            final_answer={},
        )
        major, middle, minor = ScanService._extract_classification(result)

        assert major == ""
        assert middle == ""
        assert minor is None


class TestHasInsufficiencies:
    """_has_insufficiencies 메서드 테스트."""

    def test_returns_true_when_insufficiencies_none(self):
        """insufficiencies가 None이면 True."""
        from domains._shared.schemas.waste import WasteClassificationResult
        from domains.scan.services.scan import ScanService

        result = WasteClassificationResult(
            classification_result={},
            disposal_rules={},
            final_answer={"user_answer": "답변"},  # insufficiencies 없음
        )
        assert ScanService._has_insufficiencies(result) is True

    def test_returns_false_when_empty_list(self):
        """insufficiencies가 빈 리스트면 False."""
        from domains._shared.schemas.waste import WasteClassificationResult
        from domains.scan.services.scan import ScanService

        result = WasteClassificationResult(
            classification_result={},
            disposal_rules={},
            final_answer={"user_answer": "답변", "insufficiencies": []},
        )
        assert ScanService._has_insufficiencies(result) is False

    def test_returns_true_when_has_items(self):
        """insufficiencies에 항목이 있으면 True."""
        from domains._shared.schemas.waste import WasteClassificationResult
        from domains.scan.services.scan import ScanService

        result = WasteClassificationResult(
            classification_result={},
            disposal_rules={},
            final_answer={
                "user_answer": "답변",
                "insufficiencies": ["라벨이 제거되지 않았습니다"],
            },
        )
        assert ScanService._has_insufficiencies(result) is True


class TestBuildRewardRequest:
    """_build_reward_request 메서드 테스트."""

    def test_builds_valid_request(
        self, mock_settings, mock_repository, mock_pipeline_result, test_user_id
    ):
        """유효한 CharacterRewardRequest 생성."""
        from domains._shared.schemas.waste import WasteClassificationResult
        from domains.character.schemas.reward import CharacterRewardSource
        from domains.scan.services.scan import ScanService

        service = ScanService.__new__(ScanService)
        service.settings = mock_settings
        service.repository = mock_repository

        result = WasteClassificationResult(**mock_pipeline_result)
        request = service._build_reward_request(test_user_id, "task-123", result)

        assert request is not None
        assert request.source == CharacterRewardSource.SCAN
        assert request.user_id == test_user_id
        assert request.task_id == "task-123"
        assert request.classification.major_category == "재활용폐기물"
        assert request.classification.middle_category == "무색페트병"
        assert request.disposal_rules_present is True

    def test_returns_none_when_missing_category(self, mock_settings, mock_repository, test_user_id):
        """major 또는 middle이 없으면 None."""
        from domains._shared.schemas.waste import WasteClassificationResult
        from domains.scan.services.scan import ScanService

        service = ScanService.__new__(ScanService)
        service.settings = mock_settings
        service.repository = mock_repository

        result = WasteClassificationResult(
            classification_result={"classification": {}},
            disposal_rules={},
            final_answer={},
        )
        request = service._build_reward_request(test_user_id, "task-123", result)

        assert request is None


class TestClassify:
    """classify 메서드 통합 테스트."""

    @pytest.mark.asyncio
    async def test_returns_failed_when_no_image_url(
        self, mock_settings, mock_repository, test_user_id
    ):
        """image_url이 없으면 실패 응답."""
        from domains.scan.core.validators import ImageUrlValidator
        from domains.scan.services.scan import ScanService

        service = ScanService.__new__(ScanService)
        service.settings = mock_settings
        service.repository = mock_repository
        service.image_validator = ImageUrlValidator(mock_settings)

        payload = ClassificationRequest(image_url=None)
        response = await service.classify(payload, test_user_id)

        assert response.status == "failed"
        assert response.error == "IMAGE_URL_REQUIRED"

    @pytest.mark.asyncio
    async def test_returns_failed_on_invalid_url(
        self, mock_settings, mock_repository, test_user_id, invalid_image_url
    ):
        """유효하지 않은 URL이면 실패."""
        from domains.scan.core.validators import ImageUrlValidator
        from domains.scan.services.scan import ScanService

        service = ScanService.__new__(ScanService)
        service.settings = mock_settings
        service.repository = mock_repository
        service.image_validator = ImageUrlValidator(mock_settings)

        payload = ClassificationRequest(image_url=invalid_image_url)
        response = await service.classify(payload, test_user_id)

        assert response.status == "failed"
        assert "HTTPS_REQUIRED" in (response.error or "")

    @pytest.mark.asyncio
    async def test_successful_classification(
        self,
        mock_settings,
        mock_repository,
        mock_pipeline_result,
        test_user_id,
        valid_image_url,
    ):
        """성공적인 분류 플로우."""
        from domains.scan.core.validators import ImageUrlValidator
        from domains.scan.services.scan import ScanService

        service = ScanService.__new__(ScanService)
        service.settings = mock_settings
        service.repository = mock_repository
        service.image_validator = ImageUrlValidator(mock_settings)

        # Mock pipeline
        async def mock_run_pipeline(*args, **kwargs):
            from domains._shared.schemas.waste import WasteClassificationResult

            return WasteClassificationResult(**mock_pipeline_result), None

        service._run_pipeline = mock_run_pipeline

        # Mock reward (disabled for simplicity)
        mock_settings.reward_feature_enabled = False

        payload = ClassificationRequest(image_url=valid_image_url)
        response = await service.classify(payload, test_user_id)

        assert response.status == "completed"
        assert response.pipeline_result is not None


class TestCategories:
    """categories 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_loads_categories_from_yaml(self, mock_settings, mock_repository):
        """YAML에서 카테고리 로드."""
        from domains.scan.services.scan import ScanService

        service = ScanService.__new__(ScanService)
        service.settings = mock_settings
        service.repository = mock_repository

        # 캐시 초기화
        ScanService._category_cache = None

        categories = await service.categories()

        assert isinstance(categories, list)
        # 캐시가 설정되었는지 확인
        assert ScanService._category_cache is not None

        # 두 번째 호출은 캐시 사용
        categories2 = await service.categories()
        assert categories2 == categories

        # 캐시 정리
        ScanService._category_cache = None


class TestMetrics:
    """metrics 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_returns_metrics_dict(self, mock_settings, mock_repository):
        """메트릭 딕셔너리 반환."""
        from domains.scan.services.scan import ScanService

        service = ScanService.__new__(ScanService)
        service.settings = mock_settings
        service.repository = mock_repository

        # 캐시 초기화
        ScanService._category_cache = None

        metrics = await service.metrics()

        assert "completed_tasks" in metrics
        assert metrics["completed_tasks"] == 10  # mock_repository 반환값
        assert "last_completed_at" in metrics
        assert "supported_categories" in metrics

        # 캐시 정리
        ScanService._category_cache = None
