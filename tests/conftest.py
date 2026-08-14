"""
Root test configuration.

Puts this directory on sys.path so the sub-suites can `import helpers`
regardless of which pytest import mode is in effect.
"""

import sys
from pathlib import Path

TESTS_DIR = str(Path(__file__).resolve().parent)

if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)
