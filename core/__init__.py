# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
Core module initialization.
"""

from .config import settings
from .app_logging import setup_logging, get_logger

__all__ = ["settings", "setup_logging", "get_logger"]
