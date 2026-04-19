"""Stub: homeassistant.components.number"""


class NumberEntity:
    _attr_native_min_value: float = 0
    _attr_native_max_value: float = 100
    _attr_native_step: float = 1
    _attr_native_unit_of_measurement: str | None = None
    _attr_device_class: str | None = None
    _attr_mode: str = "auto"

    @property
    def native_min_value(self) -> float:
        return self._attr_native_min_value

    @property
    def native_max_value(self) -> float:
        return self._attr_native_max_value

    @property
    def native_step(self) -> float:
        return self._attr_native_step

    @property
    def native_value(self) -> float | None:
        return None

    async def async_set_native_value(self, value: float) -> None:
        pass


class NumberMode:
    AUTO = "auto"
    BOX = "box"
    SLIDER = "slider"
