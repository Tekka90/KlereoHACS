"""Stub: homeassistant.config_entries"""


class ConfigEntry:
    entry_id: str = ""
    data: dict = {}


class _HandlersRegistry:
    """Minimal stub for config_entries.HANDLERS."""

    def register(self, domain):
        """No-op decorator — just returns the class unchanged."""
        def decorator(cls):
            return cls
        return decorator


HANDLERS = _HandlersRegistry()


class ConfigFlow:
    """Minimal stub for homeassistant.config_entries.ConfigFlow."""

    VERSION = 1

    def __init_subclass__(cls, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)

    def async_show_form(self, *, step_id, data_schema=None, errors=None, **kwargs):
        return {"type": "form", "step_id": step_id, "errors": errors or {}, **kwargs}

    def async_create_entry(self, *, title, data):
        return {"type": "create_entry", "title": title, "data": data}
