from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass, SensorEntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

import logging
LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Probe sensors (from pool_data['probes'])
# ---------------------------------------------------------------------------

_PROBE_TYPE_MAP: dict[int, SensorEntityDescription] = {
    0:  SensorEntityDescription(key="0",  device_class=SensorDeviceClass.TEMPERATURE, native_unit_of_measurement="°C"),    # Tech room temperature
    1:  SensorEntityDescription(key="1",  device_class=SensorDeviceClass.TEMPERATURE, native_unit_of_measurement="°C"),    # Air temperature
    2:  SensorEntityDescription(key="2",  device_class=None,                          native_unit_of_measurement="%"),      # Water level
    3:  SensorEntityDescription(key="3",  device_class=SensorDeviceClass.PH,          native_unit_of_measurement=None),    # pH
    4:  SensorEntityDescription(key="4",  device_class=SensorDeviceClass.VOLTAGE,     native_unit_of_measurement="mV"),    # Redox / ORP
    5:  SensorEntityDescription(key="5",  device_class=SensorDeviceClass.TEMPERATURE, native_unit_of_measurement="°C"),    # Water temperature
    6:  SensorEntityDescription(key="6",  device_class=SensorDeviceClass.PRESSURE,    native_unit_of_measurement="mbar"),  # Filter pressure
    10: SensorEntityDescription(key="10", device_class=None,                          native_unit_of_measurement="%"),      # Generic
    11: SensorEntityDescription(key="11", device_class=None,                          native_unit_of_measurement="m³/h"),  # Flow rate
    12: SensorEntityDescription(key="12", device_class=None,                          native_unit_of_measurement="%"),      # Tank level
    13: SensorEntityDescription(key="13", device_class=None,                          native_unit_of_measurement="%"),      # Cover / curtain position
    14: SensorEntityDescription(key="14", device_class=None,                          native_unit_of_measurement="mg/L"),  # Chlorine
}

_DEFAULT_DESCRIPTION = SensorEntityDescription(key="unknown", device_class=None, native_unit_of_measurement=None)


# ---------------------------------------------------------------------------
# Params sensors (from pool_data['params'])
# ---------------------------------------------------------------------------

@dataclass
class KlereoParamDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with a value transform function."""
    value_fn: Callable[[dict], Any] | None = None


def _hours(params: dict, key: str) -> float | None:
    """Convert seconds to hours, return None if key missing."""
    v = params.get(key)
    return round(v / 3600, 2) if v is not None else None

def _consumed_today_ml(params: dict, time_key: str, debit_key: str) -> float | None:
    t = params.get(time_key)
    d = params.get(debit_key)
    return round(t * d / 36, 2) if t is not None and d is not None else None

def _consumed_total_l(params: dict, time_key: str, debit_key: str) -> float | None:
    t = params.get(time_key)
    d = params.get(debit_key)
    return round(t * d / 36000, 2) if t is not None and d is not None else None


# Numeric params — each entry defines how to extract and display one sensor.
_PARAM_SENSORS: list[KlereoParamDescription] = [
    KlereoParamDescription(
        key="filtration_today_h",
        name="Filtration Today",
        native_unit_of_measurement="h",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda p: _hours(p, "Filtration_TodayTime"),
    ),
    KlereoParamDescription(
        key="filtration_total_h",
        name="Filtration Total",
        native_unit_of_measurement="h",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda p: _hours(p, "Filtration_TotalTime"),
    ),
    KlereoParamDescription(
        key="phminus_today_ml",
        name="pH- Consumed Today",
        native_unit_of_measurement="mL",
        device_class=None,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda p: _consumed_today_ml(p, "PHMinus_TodayTime", "PHMinus_Debit"),
    ),
    KlereoParamDescription(
        key="phminus_total_l",
        name="pH- Consumed Total",
        native_unit_of_measurement="L",
        device_class=None,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda p: _consumed_total_l(p, "PHMinus_TotalTime", "PHMinus_Debit"),
    ),
    KlereoParamDescription(
        key="elec_gram_done",
        name="Chlorine Production Today",
        native_unit_of_measurement="g",
        device_class=None,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda p: round(p["Elec_GramDone"] / 1000, 3) if p.get("Elec_GramDone") is not None else None,
    ),
    KlereoParamDescription(
        key="chlore_today_ml",
        name="Liquid Chlorine Consumed Today",
        native_unit_of_measurement="mL",
        device_class=None,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda p: _consumed_today_ml(p, "ElectroChlore_TodayTime", "Chlore_Debit"),
    ),
    KlereoParamDescription(
        key="chlore_total_l",
        name="Liquid Chlorine Consumed Total",
        native_unit_of_measurement="L",
        device_class=None,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda p: _consumed_total_l(p, "ElectroChlore_TotalTime", "Chlore_Debit"),
    ),
    KlereoParamDescription(
        key="heating_today_h",
        name="Heating Today",
        native_unit_of_measurement="h",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda p: _hours(p, "Chauff_TodayTime"),
    ),
    KlereoParamDescription(
        key="heating_total_h",
        name="Heating Total",
        native_unit_of_measurement="h",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda p: _hours(p, "Chauff_TotalTime"),
    ),
    KlereoParamDescription(
        key="setpoint_water_temp",
        name="Heating Setpoint",
        native_unit_of_measurement="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda p: float(p["ConsigneEau"]) if p.get("ConsigneEau") is not None else None,
    ),
    KlereoParamDescription(
        key="setpoint_ph",
        name="pH Setpoint",
        native_unit_of_measurement=None,
        device_class=SensorDeviceClass.PH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda p: float(p["ConsignePH"]) if p.get("ConsignePH") is not None else None,
    ),
    KlereoParamDescription(
        key="setpoint_redox",
        name="Redox Setpoint",
        native_unit_of_measurement="mV",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda p: float(p["ConsigneRedox"]) if p.get("ConsigneRedox") is not None else None,
    ),
    KlereoParamDescription(
        key="setpoint_chlore",
        name="Chlorine Setpoint",
        native_unit_of_measurement="mg/L",
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda p: float(p["ConsigneChlore"]) if p.get("ConsigneChlore") is not None else None,
    ),
]


# ---------------------------------------------------------------------------
# Enum/string params sensors (from pool_data['params'])
# ---------------------------------------------------------------------------

_POOL_MODE_MAP = {0: "Off", 1: "Eco", 2: "Comfort", 4: "Winter", 5: "Install"}
_TRAIT_MODE_MAP = {0: "None", 1: "Liquid chlorine", 2: "Electrolyser", 3: "KL1", 4: "Active oxygen", 5: "Bromine", 6: "KL2", 8: "KL3"}
_PH_MODE_MAP = {0: "None", 1: "pH-Minus", 2: "pH-Plus"}
_HEATER_MODE_MAP = {0: "None", 1: "ON/OFF heat pump", 2: "EasyTherm", 3: "ON/OFF no setpoint", 4: "Other heat pump"}

@dataclass
class KlereoEnumDescription(SensorEntityDescription):
    """Param key, value map, and options list for enum sensors."""
    param_key: str = ""
    value_map: dict[int, str] = field(default_factory=dict)


_ENUM_SENSORS: list[KlereoEnumDescription] = [
    KlereoEnumDescription(
        key="pool_mode",
        name="Pool Mode",
        device_class=SensorDeviceClass.ENUM,
        options=list(_POOL_MODE_MAP.values()),
        param_key="PoolMode",
        value_map=_POOL_MODE_MAP,
    ),
    KlereoEnumDescription(
        key="trait_mode",
        name="Disinfectant Type",
        device_class=SensorDeviceClass.ENUM,
        options=list(_TRAIT_MODE_MAP.values()),
        param_key="TraitMode",
        value_map=_TRAIT_MODE_MAP,
    ),
    KlereoEnumDescription(
        key="ph_mode",
        name="pH Corrector Type",
        device_class=SensorDeviceClass.ENUM,
        options=list(_PH_MODE_MAP.values()),
        param_key="pHMode",
        value_map=_PH_MODE_MAP,
    ),
    KlereoEnumDescription(
        key="heater_mode",
        name="Heater Type",
        device_class=SensorDeviceClass.ENUM,
        options=list(_HEATER_MODE_MAP.values()),
        param_key="HeaterMode",
        value_map=_HEATER_MODE_MAP,
    ),
]


# ---------------------------------------------------------------------------
# Setup entry
# ---------------------------------------------------------------------------

async def async_setup_entry(hass, config_entry, async_add_entities):

    LOGGER.info(f"Setting up sensors...")
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    pool_data = coordinator.data
    probes = pool_data["probes"]
    poolid = pool_data['idSystem']
    params = pool_data.get("params", {})

    entities: list = []

    # Probe sensors
    for probe in probes:
        LOGGER.info(f"Adding probe sensor for #{poolid}: {probe}")
        entities.append(KlereoSensor(coordinator, probe, poolid))

    # Numeric params sensors — only add if the required key(s) exist in params
    for desc in _PARAM_SENSORS:
        try:
            value = desc.value_fn(params)
            if value is not None:
                LOGGER.info(f"Adding param sensor '{desc.name}' for #{poolid}")
                entities.append(KlereoParamSensor(coordinator, poolid, desc))
        except Exception:
            pass  # param not available for this pool — skip silently

    # Enum params sensors — only add if the param key exists in params
    for desc in _ENUM_SENSORS:
        if desc.param_key in params:
            LOGGER.info(f"Adding enum sensor '{desc.name}' for #{poolid}")
            entities.append(KlereoEnumSensor(coordinator, poolid, desc))

    async_add_entities(entities, update_before_add=True)


class KlereoSensor(CoordinatorEntity, SensorEntity):

    def __init__(self, coordinator, probe, poolid):
        super().__init__(coordinator)
        self._probe_name = f"klereo{poolid}probe{probe['index']}"
        self._index = probe['index']
        self._probe_type = int(probe['type'])
        self._poolid = poolid
        # Assign the EntityDescription — this is what HA uses authoritatively
        # for device_class and native_unit_of_measurement, ignoring the registry cache.
        self.entity_description = _PROBE_TYPE_MAP.get(self._probe_type, _DEFAULT_DESCRIPTION)
        LOGGER.debug(f"{self._probe_name} type={self._probe_type} → device_class={self.entity_description.device_class}, unit={self.entity_description.native_unit_of_measurement}")

    @property
    def name(self):
        return self._probe_name

    @property
    def native_value(self):
        probes = self.coordinator.data['probes']
        for probe in probes:
            if probe['index'] == self._index:
                LOGGER.debug(f"{self._probe_name}={probe['filteredValue']}")
                return float(probe['filteredValue'])
        return None

    @property
    def unique_id(self):
        return f"id_{self._probe_name}"

    @property
    def extra_state_attributes(self):
        probes = self.coordinator.data['probes']
        for probe in probes:
            if probe['index'] == self._index:
                return {
                    'Time': probe['filteredTime'],
                    'Type': self._probe_type,
                }
        return None


# ---------------------------------------------------------------------------
# Numeric params sensor
# ---------------------------------------------------------------------------

class KlereoParamSensor(CoordinatorEntity, SensorEntity):
    """A sensor derived from pool_data['params'] with a transform function."""

    def __init__(self, coordinator, poolid: int, description: KlereoParamDescription):
        super().__init__(coordinator)
        self._poolid = poolid
        self.entity_description = description

    @property
    def name(self) -> str:
        return self.entity_description.name

    @property
    def unique_id(self) -> str:
        return f"klereo{self._poolid}_param_{self.entity_description.key}"

    @property
    def native_value(self):
        params = self.coordinator.data.get("params", {})
        try:
            return self.entity_description.value_fn(params)
        except Exception as err:
            LOGGER.debug(f"Param sensor '{self.entity_description.key}' error: {err}")
            return None


# ---------------------------------------------------------------------------
# Enum/string params sensor
# ---------------------------------------------------------------------------

class KlereoEnumSensor(CoordinatorEntity, SensorEntity):
    """A sensor that maps a numeric pool param to a human-readable string."""

    def __init__(self, coordinator, poolid: int, description: KlereoEnumDescription):
        super().__init__(coordinator)
        self._poolid = poolid
        self.entity_description = description

    @property
    def name(self) -> str:
        return self.entity_description.name

    @property
    def unique_id(self) -> str:
        return f"klereo{self._poolid}_enum_{self.entity_description.key}"

    @property
    def native_value(self) -> str | None:
        params = self.coordinator.data.get("params", {})
        raw = params.get(self.entity_description.param_key)
        if raw is None:
            return None
        return self.entity_description.value_map.get(int(raw), f"Unknown ({raw})")
