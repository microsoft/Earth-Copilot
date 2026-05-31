"""pytest config for the MCP server tests.

Adds the project root to sys.path so `import server` works.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
