"""Pytest configuration for Character domain tests."""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).resolve().parents[3]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Add extra path for shared modules
extra_path = project_root / "domains"
if str(extra_path) not in sys.path:
    sys.path.insert(0, str(extra_path))
