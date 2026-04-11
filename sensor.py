from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

import logging
LOGGER = logging.getLogger(__name__)

# Maps probe['type'] → (device_class, unit_of_measurement)
# Source: copilot-instructions probe type table
_PROBE_TYPE_MAP: dict[int, tuple[str | None, str | None]] = {
    0:  ("temperature", "°C"),     # Tech room temperature
    1:  ("temperature", "°C"),     # Air temperature
    2:  (None,          "%"),      # Water level
    3:  ("ph",          None),     # pH
    4:  ("voltage",     "mV"),     # Redox / ORP
    5:  ("temperature", "°C"),     # Water temperature
    6:  ("pressure",    "mbar"),   # Filter pressure
    10: (None,          "%"),      # Generic
    11: (None,          "m³/h"),   # Flow rate
    12: (None,          "%"),      # Tank level
    13: (None,          "%"),      # Cover / curtain position
    14: (None,          "mg/L"),   # Chlorine
}

async def async_setup_entry(hass, config_entry, async_add_entities):

    LOGGER.info(f"Setting up sensors...")
    # Get infos from coordinator
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    pool_data=coordinator.data;
    probes = pool_data["probes"]
    poolid = pool_data['idSystem']
    # Add sensors
    sensors = []
    for probe in probes:
        LOGGER.info(f"Adding sensor for #{poolid}: {probe}")
        sensors.append(KlereoSensor(coordinator,probe,poolid))
    #add sensor enitities
    async_add_entities(sensors, update_before_add=True)


class KlereoSensor(CoordinatorEntity):

    def __init__(self, coordinator, probe, poolid):
        super().__init__(coordinator)
        self._name = f"klereo{poolid}probe{probe['index']}"
        self._index = probe['index']
        self._type = probe['type']
        self._poolid = poolid

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        probes = self.coordinator.data['probes']
        for probe in probes:
            if probe['index'] == self._index:
                LOGGER.debug(f"{self._name}={probe['filteredValue']}")
                return float(probe['filteredValue'])
        return None

    @property
    def unique_id(self):
        return f"id_{self._name}"

    @property
    def device_class(self):
        device_class, _ = _PROBE_TYPE_MAP.get(self._type, (None, None))
        return device_class

    @property
    def unit_of_measurement(self):
        _, unit = _PROBE_TYPE_MAP.get(self._type, (None, None))
        return unit

    @property
    def extra_state_attributes(self):
        probes = self.coordinator.data['probes']
        for probe in probes:
            if probe['index'] == self._index:
                return {
                    'Time': probe['filteredTime'],
                    'Type': int(probe['type'])
                }
        return None
