"""Pytest configuration for pipeline unit tests.

Adds container-app/ to sys.path so `from pipeline import ...` works when
running `pytest tests/` from the container-app directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CONTAINER_APP = _HERE.parent
if str(_CONTAINER_APP) not in sys.path:
    sys.path.insert(0, str(_CONTAINER_APP))
