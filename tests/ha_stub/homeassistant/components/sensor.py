"""Stub: homeassistant.components.sensor"""
from dataclasses import dataclass, field


class SensorEntity:
    entity_description = None

    @property
    def device_class(self):
        if self.entity_description is not None:
            return self.entity_description.device_class
        return None

    @property
    def unit_of_measurement(self):
        if self.entity_description is not None:
            return self.entity_description.native_unit_of_measurement
        return None

    @property
    def state_class(self):
        if self.entity_description is not None:
            return self.entity_description.state_class
        return None


class SensorDeviceClass:
    TEMPERATURE = "temperature"
    PRESSURE = "pressure"
    VOLTAGE = "voltage"
    PH = "ph"
    DURATION = "duration"
    ENUM = "enum"
    MEASUREMENT = "measurement"


class SensorStateClass:
    MEASUREMENT = "measurement"
    TOTAL = "total"
    TOTAL_INCREASING = "total_increasing"


@dataclass
class SensorEntityDescription:
    key: str = ""
    name: str | None = None
    device_class: str | None = None
    native_unit_of_measurement: str | None = None
    state_class: str | None = None
    options: list = field(default_factory=list)
    icon: str | None = None
