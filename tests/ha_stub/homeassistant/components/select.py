"""Stub: homeassistant.components.select"""


class SelectEntity:
    _attr_current_option: str | None = None
    _attr_options: list[str] = []

    @property
    def options(self) -> list[str]:
        return self._attr_options

    @property
    def current_option(self) -> str | None:
        return self._attr_current_option
