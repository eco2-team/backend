"""JSON Calibration Data Adapter.

JSON 파일 기반 CalibrationDataGateway 구현.
초기 Calibration Set은 수동 큐레이션, PG 불필요.

파일 경로: infrastructure/assets/data/calibration_set.json
CalibrationSample.from_dict() 호환 구조.

See: docs/plans/chat-eval-pipeline-plan.md §3.3.1
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from chat_worker.domain.value_objects.calibration_sample import CalibrationSample

logger = logging.getLogger(__name__)

_DEFAULT_PATH = (
    Path(__file__).resolve().parent.parent.parent / "assets" / "data" / "calibration_set.json"
)


class JsonCalibrationDataAdapter:
    """JSON 파일 기반 CalibrationDataGateway 구현.

    CalibrationDataGateway Protocol 구현.
    파일 로드 → CalibrationSample VO 변환 → 메모리 캐시.
    """

    def __init__(self, file_path: str | Path | None = None) -> None:
        """초기화.

        Args:
            file_path: calibration_set.json 경로 (None이면 기본 경로)
        """
        self._file_path = Path(file_path) if file_path else _DEFAULT_PATH
        self._cache: list[CalibrationSample] | None = None
        self._version: str | None = None
        self._intent_set: set[str] | None = None

    def _load(self) -> None:
        """JSON 파일 로드 + 메모리 캐시."""
        if self._cache is not None:
            return

        try:
            with open(self._file_path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            logger.warning(
                "Calibration set file not found: %s",
                self._file_path,
            )
            self._cache = []
            self._version = "unknown"
            self._intent_set = set()
            return

        self._version = data.get("version", "unknown")
        samples_raw = data.get("samples", [])

        self._cache = []
        intents: set[str] = set()
        for sample_data in samples_raw:
            try:
                sample = CalibrationSample.from_dict(sample_data)
                self._cache.append(sample)
                intents.add(sample.intent)
            except Exception as e:
                logger.warning(
                    "Skipping invalid calibration sample: %s",
                    e,
                )

        self._intent_set = intents
        logger.info(
            "Calibration set loaded: %d samples, version=%s, intents=%s",
            len(self._cache),
            self._version,
            sorted(intents),
        )

    async def get_calibration_set(self) -> list[CalibrationSample]:
        """전체 Calibration Set 조회.

        Returns:
            CalibrationSample 리스트
        """
        self._load()
        return list(self._cache)  # type: ignore[arg-type]

    async def get_calibration_version(self) -> str:
        """현재 Calibration Set 버전 조회.

        Returns:
            버전 문자열
        """
        self._load()
        return self._version or "unknown"

    async def get_calibration_intent_set(self) -> set[str]:
        """Calibration Set에 포함된 Intent 집합.

        Returns:
            intent 문자열 집합
        """
        self._load()
        return set(self._intent_set or set())


__all__ = ["JsonCalibrationDataAdapter"]
