# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
Logging configuration for Earth Copilot.
"""
import logging
import sys
from typing import Dict, Any


def setup_logging(level: str = "INFO") -> None:
    """Set up application logging."""
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        handlers=[console_handler],
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Set specific logger levels
    loggers = {
        'uvicorn': logging.INFO,
        'uvicorn.access': logging.INFO,
        'fastapi': logging.INFO,
        'earth_copilot': logging.DEBUG if level.upper() == "DEBUG" else logging.INFO,
    }
    
    for logger_name, logger_level in loggers.items():
        logging.getLogger(logger_name).setLevel(logger_level)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)
