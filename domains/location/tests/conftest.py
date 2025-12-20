"""Pytest configuration for location tests."""

import sys
from pathlib import Path

# Add project paths for imports
PATHS_TO_ADD = (
    Path(__file__).resolve().parents[1],  # domains/location
    Path(__file__).resolve().parents[2],  # domains
    Path(__file__).resolve().parents[3],  # repo root
)
for extra_path in PATHS_TO_ADD:
    if str(extra_path) not in sys.path:
        sys.path.insert(0, str(extra_path))
