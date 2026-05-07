"""Stub: homeassistant.helpers.config_validation

Minimal stand-in for the real HA module — only the symbols used by the
klereo integration are provided.
"""


def config_entry_only_config_schema(domain):
    """Stub: returns a callable that validates / passes through config dicts."""
    def _validator(value):
        return value
    return _validator
