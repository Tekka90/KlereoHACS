"""tests/conftest.py

Homeassistant stubs are already in sys.modules via
.venv/site-packages/sitecustomize.py (runs at Python startup).

This conftest only ensures the KlereoHACS package is importable by adding
the project's parent directory to sys.path.
"""
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent   # .../KlereoHACS/
sys.path.insert(0, str(_PROJECT_ROOT.parent))  # .../Projects/  → enables 'import KlereoHACS'
