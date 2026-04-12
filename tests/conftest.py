"""tests/conftest.py

Homeassistant stubs are already in sys.modules via the stub package installed
in .venv/lib/pythonX.Y/site-packages/homeassistant/ (installed at venv setup).

This conftest only ensures the klereo package is importable by adding
the custom_components directory to sys.path.
"""
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent   # .../custom_components/klereo/
sys.path.insert(0, str(_PROJECT_ROOT.parent))  # .../custom_components/  → enables 'import klereo'
