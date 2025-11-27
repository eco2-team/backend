"""
Scan application package bootstrap.

Pytest in CI sets ``PYTHONPATH=domains/scan`` which breaks relative imports
such as ``domains._shared``.  This module ensures the repository root is
available on ``sys.path`` whenever ``app.main`` (or similar) is imported.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

__all__ = ["REPO_ROOT"]
