"""Suggest Entry DTO."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SuggestEntryDTO:
    """자동완성 제안 DTO."""

    place_name: str
    address: str | None
    latitude: float
    longitude: float
    place_url: str | None = None
