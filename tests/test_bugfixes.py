"""Discovers bugfixes/test_bugfixes.py via the standard tests/ runner."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bugfixes.test_bugfixes import TestAuditBugfixes  # noqa: F401
