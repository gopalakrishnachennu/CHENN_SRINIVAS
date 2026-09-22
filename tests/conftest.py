"""
pytest conftest: configure project root on sys.path and shared fixtures.
"""
import sys
from pathlib import Path

# Ensure project root is importable even when running pytest from sub-dirs
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
