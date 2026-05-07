"""tests/conftest.py

Homeassistant stubs are already in sys.modules via the stub package installed
in .venv/lib/pythonX.Y/site-packages/homeassistant/ (installed at venv setup).

The klereo package is importable because setup_test_env.sh creates a symlink
  .venv/lib/pythonX.Y/site-packages/klereo -> <project_root>
which works both locally (custom_components/klereo/) and in CI (repo root).
No sys.path manipulation is needed here.

Patch-in shim: ``homeassistant.helpers.config_validation`` is required by
``klereo/__init__.py`` (imported transitively whenever any test imports
``klereo.*``).  Older copies of the HA stub installed before this module
existed will be missing it, so we inject a minimal stand-in here at
collection time.  This is idempotent — if the real stub already provides
the module, this block is a no-op.
"""
import sys
import types

if "homeassistant.helpers.config_validation" not in sys.modules:
    _cv = types.ModuleType("homeassistant.helpers.config_validation")

    def _config_entry_only_config_schema(domain):
        def _validator(value):
            return value
        return _validator

    _cv.config_entry_only_config_schema = _config_entry_only_config_schema
    sys.modules["homeassistant.helpers.config_validation"] = _cv
    # Also attach as attribute on the parent package so `import
    # homeassistant.helpers.config_validation as cv` resolves correctly.
    try:
        import homeassistant.helpers as _ha_helpers
        _ha_helpers.config_validation = _cv
    except ImportError:
        pass
