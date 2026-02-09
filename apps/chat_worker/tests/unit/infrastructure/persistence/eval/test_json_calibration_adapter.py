"""JsonCalibrationDataAdapter Unit Tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from chat_worker.domain.value_objects.calibration_sample import CalibrationSample
from chat_worker.infrastructure.persistence.eval.json_calibration_adapter import (
    JsonCalibrationDataAdapter,
)


def _make_calibration_json(samples: list[dict], version: str = "v1.0-test") -> Path:
    """임시 calibration JSON 파일 생성."""
    data = {
        "version": version,
        "description": "test calibration set",
        "min_kappa": 0.6,
        "samples": samples,
    }
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(data, tmp, ensure_ascii=False)
    tmp.flush()
    return Path(tmp.name)


_VALID_SAMPLE = {
    "query": "페트병 분리배출",
    "intent": "waste",
    "context": "페트병은 라벨을 제거합니다.",
    "reference_answer": "라벨을 제거하세요.",
    "human_scores": {
        "faithfulness": 5,
        "relevance": 4,
        "completeness": 4,
        "safety": 5,
        "communication": 4,
    },
    "annotator_agreement": 0.85,
}


@pytest.mark.eval_unit
class TestJsonCalibrationDataAdapter:
    """JsonCalibrationDataAdapter 테스트."""

    async def test_get_calibration_set_returns_samples(self) -> None:
        """JSON에서 CalibrationSample 리스트 로드."""
        path = _make_calibration_json([_VALID_SAMPLE])
        adapter = JsonCalibrationDataAdapter(file_path=path)

        samples = await adapter.get_calibration_set()

        assert len(samples) == 1
        assert isinstance(samples[0], CalibrationSample)
        assert samples[0].query == "페트병 분리배출"
        assert samples[0].intent == "waste"
        assert samples[0].annotator_agreement == 0.85

    async def test_get_calibration_version(self) -> None:
        """버전 문자열 반환."""
        path = _make_calibration_json([], version="v2.0-2026-02-10")
        adapter = JsonCalibrationDataAdapter(file_path=path)

        version = await adapter.get_calibration_version()

        assert version == "v2.0-2026-02-10"

    async def test_get_calibration_intent_set(self) -> None:
        """Intent 집합 반환."""
        samples = [
            {**_VALID_SAMPLE, "intent": "waste"},
            {**_VALID_SAMPLE, "intent": "general", "query": "안녕"},
            {**_VALID_SAMPLE, "intent": "waste", "query": "비닐"},
        ]
        path = _make_calibration_json(samples)
        adapter = JsonCalibrationDataAdapter(file_path=path)

        intent_set = await adapter.get_calibration_intent_set()

        assert intent_set == {"waste", "general"}

    async def test_memory_cache_prevents_reload(self) -> None:
        """두 번째 호출은 캐시에서 반환."""
        path = _make_calibration_json([_VALID_SAMPLE])
        adapter = JsonCalibrationDataAdapter(file_path=path)

        samples1 = await adapter.get_calibration_set()
        samples2 = await adapter.get_calibration_set()

        assert len(samples1) == len(samples2) == 1

    async def test_file_not_found_returns_empty(self) -> None:
        """파일 없을 때 빈 리스트 반환."""
        adapter = JsonCalibrationDataAdapter(file_path="/nonexistent/calibration_set.json")

        samples = await adapter.get_calibration_set()
        version = await adapter.get_calibration_version()
        intents = await adapter.get_calibration_intent_set()

        assert samples == []
        assert version == "unknown"
        assert intents == set()

    async def test_invalid_sample_skipped(self) -> None:
        """유효하지 않은 샘플은 건너뜀."""
        invalid = {
            "query": "test",
            "intent": "waste",
            "context": "",
            "reference_answer": "",
            "human_scores": {},
            "annotator_agreement": -1.0,  # Invalid: < 0
        }
        path = _make_calibration_json([_VALID_SAMPLE, invalid])
        adapter = JsonCalibrationDataAdapter(file_path=path)

        samples = await adapter.get_calibration_set()

        # invalid sample 건너뜀, valid만 로드
        assert len(samples) == 1
        assert samples[0].query == "페트병 분리배출"

    async def test_default_path_exists(self) -> None:
        """기본 경로의 calibration_set.json이 존재."""
        adapter = JsonCalibrationDataAdapter()

        samples = await adapter.get_calibration_set()
        version = await adapter.get_calibration_version()

        # Phase 3에서 생성한 fixture 파일이 로드되어야 함
        assert len(samples) > 0
        assert version != "unknown"

    async def test_multiple_intents_coverage(self) -> None:
        """다양한 intent가 포함된 set 로드."""
        samples = [
            {**_VALID_SAMPLE, "intent": "waste", "query": "q1"},
            {**_VALID_SAMPLE, "intent": "bulk_waste", "query": "q2"},
            {**_VALID_SAMPLE, "intent": "collection_point", "query": "q3"},
            {**_VALID_SAMPLE, "intent": "general", "query": "q4"},
        ]
        path = _make_calibration_json(samples)
        adapter = JsonCalibrationDataAdapter(file_path=path)

        intent_set = await adapter.get_calibration_intent_set()

        assert len(intent_set) == 4
        assert "waste" in intent_set
        assert "bulk_waste" in intent_set
