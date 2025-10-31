"""
Simple test runner for comparison module that avoids Unicode/emoji issues on Windows
"""
import os
import sys

# Set UTF-8 encoding for stdout
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Now import and run the tests
from test_comparison_module import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
