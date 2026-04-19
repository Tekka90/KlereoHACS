"""Stub: homeassistant.components.number"""


class NumberEntity:
    _attr_native_min_value: float = 0
    _attr_native_max_value: float = 100
    _attr_native_step: float = 1

    @property
    def native_min_value(self) -> float:
        return self._attr_native_min_value

    @property
    def native_max_value(self) -> float:
        return self._attr_native_max_value

    @property
    def native_step(self) -> float:
        return self._attr_native_step


class NumberMode:
    AUTO = "auto"
    BOX = "box"
    SLIDER = "slider"
