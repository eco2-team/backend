from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Iterable


def _build_candidates(base_dir: Path, filename: str) -> list[Path]:
    """검색할 파일 경로 후보 목록 생성."""
    search_roots = [base_dir, base_dir / "data"]
    candidates = []
    for root in search_roots:
        candidates.append(root / filename)
        candidates.append(root / unicodedata.normalize("NFD", filename))
    return candidates


def _find_by_keywords(base_dir: Path, keywords: tuple[str, ...]) -> Path | None:
    """키워드로 CSV 파일 검색."""
    for root in [base_dir, base_dir / "data"]:
        if not root.exists():
            continue
        for csv_file in root.glob("*.csv"):
            normalized = unicodedata.normalize("NFC", csv_file.name)
            if all(kw in normalized for kw in keywords):
                return csv_file
    return None


def resolve_csv_path(
    base_dir: Path,
    filename: str,
    *,
    search_keywords: Iterable[str] | None = None,
) -> Path:
    """Locate CSV file either next to the Dockerfile or under the data/ directory."""
    for candidate in _build_candidates(base_dir, filename):
        if candidate.exists():
            return candidate

    keywords = tuple(search_keywords or ())
    if keywords:
        found = _find_by_keywords(base_dir, keywords)
        if found:
            return found

    raise FileNotFoundError(
        f"CSV file '{filename}' not found under {base_dir} (or its data/ subdirectory). "
        "Ensure the dataset CSV is present alongside the Dockerfile or in the data folder."
    )


def clean_str(value: str | None) -> str:
    return (value or "").strip()


def clean_float(value: str | None) -> float | None:
    text = clean_str(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def clean_int(value: str | None) -> int | None:
    text = clean_str(value)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None
