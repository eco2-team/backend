from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Iterable


def resolve_csv_path(
    base_dir: Path,
    filename: str,
    *,
    search_keywords: Iterable[str] | None = None,
) -> Path:
    """Locate CSV file either next to the Dockerfile or under the data/ directory."""

    search_roots = [base_dir, base_dir / "data"]
    candidates: list[Path] = []
    for root in search_roots:
        candidates.append(root / filename)
        candidates.append(root / unicodedata.normalize("NFD", filename))

    for candidate in candidates:
        if candidate.exists():
            return candidate

    normalized_keywords = tuple(search_keywords or ())
    for root in search_roots:
        if not root.exists():
            continue
        for csv_file in root.glob("*.csv"):
            normalized = unicodedata.normalize("NFC", csv_file.name)
            if normalized_keywords and not all(
                keyword in normalized for keyword in normalized_keywords
            ):
                continue
            return csv_file

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
