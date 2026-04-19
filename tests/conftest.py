"""tests/conftest.py

Homeassistant stubs are already in sys.modules via the stub package installed
in .venv/lib/pythonX.Y/site-packages/homeassistant/ (installed at venv setup).

The klereo package is importable because setup_test_env.sh creates a symlink
  .venv/lib/pythonX.Y/site-packages/klereo -> <project_root>
which works both locally (custom_components/klereo/) and in CI (repo root).
No sys.path manipulation is needed here.
"""
