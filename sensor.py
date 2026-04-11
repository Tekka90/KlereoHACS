from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass, SensorEntityDescription
from homeassistant.helpers.entity import DeviceInfo
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


def _chlore_consumed(pool_data: dict, today: bool) -> float | None:
    """Liquid chlorine consumption, handling HybrideMode correctly.

    Returns mL when today=True, L when today=False.
    When HybrideMode==1 (hybrid electrolysis+liquid-Cl), time data lives in
    ExtraParams, not params.  Jeedom ref: klereo.class.php lines 353-378.
    """
    params = pool_data.get("params", {})
    debit = params.get("Chlore_Debit")
    if debit is None:
        return None
    if pool_data.get("HybrideMode") == 1:
        extra = pool_data.get("ExtraParams", {})
        t = extra.get("HybChl_TodayTime" if today else "HybChl_TotalTime")
    else:
        t = params.get("ElectroChlore_TodayTime" if today else "ElectroChlore_TotalTime")
    if t is None:
        return None
    return round(t * debit / (36 if today else 36000), 2)


# Numeric params — each entry defines how to extract and display one sensor.
# value_fn receives the full pool_data dict (not just params) so it can
# access top-level fields such as HybrideMode and ExtraParams.
_PARAM_SENSORS: list[KlereoParamDescription] = [
    KlereoParamDescription(
        key="filtration_today_h",
        name="Filtration Today",
        native_unit_of_measurement="h",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL,           # resets daily
        value_fn=lambda d: _hours(d.get("params", {}), "Filtration_TodayTime"),
    ),
    KlereoParamDescription(
        key="filtration_total_h",
        name="Filtration Total",
        native_unit_of_measurement="h",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: _hours(d.get("params", {}), "Filtration_TotalTime"),
    ),
    KlereoParamDescription(
        key="phminus_today_ml",
        name="pH- Consumed Today",
        native_unit_of_measurement="mL",
        device_class=None,
        state_class=SensorStateClass.TOTAL,           # resets daily
        value_fn=lambda d: _consumed_today_ml(d.get("params", {}), "PHMinus_TodayTime", "PHMinus_Debit"),
    ),
    KlereoParamDescription(
        key="phminus_total_l",
        name="pH- Consumed Total",
        native_unit_of_measurement="L",
        device_class=None,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: _consumed_total_l(d.get("params", {}), "PHMinus_TotalTime", "PHMinus_Debit"),
    ),
    KlereoParamDescription(
        key="elec_gram_done",
        name="Chlorine Production Today",
        native_unit_of_measurement="g",
        device_class=None,
        state_class=SensorStateClass.TOTAL,           # resets daily
        value_fn=lambda d: round(d.get("params", {}).get("Elec_GramDone") / 1000, 3)
                           if d.get("params", {}).get("Elec_GramDone") is not None else None,
    ),
    KlereoParamDescription(
        key="chlore_today_ml",
        name="Liquid Chlorine Consumed Today",
        native_unit_of_measurement="mL",
        device_class=None,
        state_class=SensorStateClass.TOTAL,           # resets daily
        value_fn=lambda d: _chlore_consumed(d, today=True),
    ),
    KlereoParamDescription(
        key="chlore_total_l",
        name="Liquid Chlorine Consumed Total",
        native_unit_of_measurement="L",
        device_class=None,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: _chlore_consumed(d, today=False),
    ),
    KlereoParamDescription(
        key="heating_today_h",
        name="Heating Today",
        native_unit_of_measurement="h",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL,           # resets daily
        value_fn=lambda d: _hours(d.get("params", {}), "Chauff_TodayTime"),
    ),
    KlereoParamDescription(
        key="heating_total_h",
        name="Heating Total",
        native_unit_of_measurement="h",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: _hours(d.get("params", {}), "Chauff_TotalTime"),
    ),
    KlereoParamDescription(
        key="setpoint_water_temp",
        name="Heating Setpoint",
        native_unit_of_measurement="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: float(d.get("params", {})["ConsigneEau"])
                           if d.get("params", {}).get("ConsigneEau") not in (None, -2000, -1000) else None,
    ),
    KlereoParamDescription(
        key="setpoint_ph",
        name="pH Setpoint",
        native_unit_of_measurement=None,
        device_class=SensorDeviceClass.PH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: float(d.get("params", {})["ConsignePH"])
                           if d.get("params", {}).get("ConsignePH") not in (None, -2000, -1000) else None,
    ),
    KlereoParamDescription(
        key="setpoint_redox",
        name="Redox Setpoint",
        native_unit_of_measurement="mV",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: float(d.get("params", {})["ConsigneRedox"])
                           if d.get("params", {}).get("ConsigneRedox") not in (None, -2000, -1000) else None,
    ),
    KlereoParamDescription(
        key="setpoint_chlore",
        name="Chlorine Setpoint",
        native_unit_of_measurement="mg/L",
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: float(d.get("params", {})["ConsigneChlore"])
                           if d.get("params", {}).get("ConsigneChlore") not in (None, -2000, -1000) else None,
    ),
    # Chlorine pump runtime (hours) — separate from volume consumed
    KlereoParamDescription(
        key="chlore_today_h",
        name="Liquid Chlorine Pump Today",
        native_unit_of_measurement="h",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL,           # resets daily
        value_fn=lambda d: _hours(d.get("params", {}), "ElectroChlore_TodayTime"),
    ),
    KlereoParamDescription(
        key="chlore_total_h",
        name="Liquid Chlorine Pump Total",
        native_unit_of_measurement="h",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: _hours(d.get("params", {}), "ElectroChlore_TotalTime"),
    ),
]


# ---------------------------------------------------------------------------
# Enum/string params sensors (from pool_data['params'])
# ---------------------------------------------------------------------------

_POOL_MODE_MAP = {0: "Off", 1: "Eco", 2: "Comfort", 4: "Winter", 5: "Install"}
_TRAIT_MODE_MAP = {0: "None", 1: "Liquid chlorine", 2: "Electrolyser", 3: "KL1", 4: "Active oxygen", 5: "Bromine", 6: "KL2", 8: "KL3"}
_PH_MODE_MAP = {0: "None", 1: "pH-Minus", 2: "pH-Plus"}
_HEATER_MODE_MAP = {0: "None", 1: "ON/OFF heat pump", 2: "EasyTherm", 3: "ON/OFF no setpoint", 4: "KlereoTherm heat pump", 5: "InoPac heat pump"}
_PRODUCT_IDX_MAP = {0: "Care/Premium", 1: "Kompact M5", 2: "Undefined", 3: "Kompact Plus M5",
                    4: "Kalypso Pro Salt", 5: "Kompact M9", 6: "Kompact Plus M9", 7: "Kompact Plus M2"}
_PUMP_TYPE_MAP = {0: "Generic (contactor)", 1: "KlereoFlô (RS485)", 2: "Pentair (bus)", 7: "No pump"}
_IS_LOW_SALT_MAP = {0: "5g/h range", 1: "2g/h range"}

@dataclass
class KlereoEnumDescription(SensorEntityDescription):
    """Param key, value map, and options list for enum sensors."""
    param_key: str = ""
    value_map: dict[int, str] = field(default_factory=dict)
    # When set, the value is derived from the whole pool_data dict via this fn
    # rather than from params[param_key] directly.
    value_fn: Callable[[dict], str | None] | None = None


def _heater_mode_value(pool_data: dict) -> str | None:
    """HeaterMode==4 maps to aqPACType (KlereoTherm/InoPac), not HeaterMode_arr."""
    params = pool_data.get("params", {})
    raw = params.get("HeaterMode")
    if raw is None:
        return None
    if int(raw) == 4:
        aq = params.get("aqPACType")
        return _HEATER_MODE_MAP.get(4 + int(aq), f"Unknown PAC ({aq})") if aq is not None else "Other heat pump"
    return _HEATER_MODE_MAP.get(int(raw), f"Unknown ({raw})")


def _alert_string(pool_data: dict) -> str | None:
    """Decode the active alerts array into a human-readable string."""
    _ALERT_MAP = {
        1: "Faulty sensor", 2: "Relay config error", 3: "pH/Redox probe inversion",
        5: "Low battery (RFID)", 6: "Calibration required", 7: "Minimum threshold",
        8: "Maximum threshold", 10: "Not received", 11: "Frost protection",
        13: "Over water consumption", 14: "Water leak", 21: "Internal memory fault",
        22: "Circulation problem", 23: "Insufficient filtration slots",
        25: "High pH — disinfectant ineffective", 26: "Undersized filtration",
        28: "Regulation stopped", 29: "Filtration in MANUAL-OFF",
        30: "Installation mode", 31: "Shock treatment",
        34: "Regulation suspended or disabled", 35: "Maintenance",
        36: "Daily injection limit", 37: "Multi-sensor fault",
        38: "Electrolyser communication fault", 39: "Brominator daily limit",
        41: "Heat pump communication fault", 43: "Electrolyser secured",
        44: "Dosing pump maintenance", 45: "Learning not done",
        46: "No water analysis flow", 48: "Filtration uncontrolled",
        49: "Check clock", 53: "Filtration communication fault",
        56: "Filtration state unknown", 61: "Heat pump fault",
    }
    alerts = pool_data.get("alerts", [])
    if not alerts:
        return "No alerts"
    parts = []
    for a in alerts:
        code, param = a.get("code"), a.get("param")
        msg = _ALERT_MAP.get(code, f"Alert #{code}")
        if param is not None:
            msg = f"{msg} ({param})"
        parts.append(msg)
    return " || ".join(parts)


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
    # HeaterMode uses a custom value_fn to handle the aqPACType special case
    KlereoEnumDescription(
        key="heater_mode",
        name="Heater Type",
        device_class=SensorDeviceClass.ENUM,
        options=list(_HEATER_MODE_MAP.values()),
        param_key="HeaterMode",
        value_map=_HEATER_MODE_MAP,
        value_fn=_heater_mode_value,
    ),
    # Diagnostic / informational sensors
    KlereoEnumDescription(
        key="product_idx",
        name="Product Range",
        device_class=SensorDeviceClass.ENUM,
        options=list(_PRODUCT_IDX_MAP.values()),
        param_key="",          # sourced from top-level ProductIdx, not params
        value_map=_PRODUCT_IDX_MAP,
        value_fn=lambda d: _PRODUCT_IDX_MAP.get(int(d["ProductIdx"]), f"Unknown ({d['ProductIdx']})") if d.get("ProductIdx") is not None else None,
    ),
    KlereoEnumDescription(
        key="pump_type",
        name="Filtration Pump Type",
        device_class=SensorDeviceClass.ENUM,
        options=list(_PUMP_TYPE_MAP.values()),
        param_key="",
        value_map=_PUMP_TYPE_MAP,
        value_fn=lambda d: _PUMP_TYPE_MAP.get(int(d["PumpType"]), f"Unknown ({d['PumpType']})") if d.get("PumpType") is not None else None,
    ),
    KlereoEnumDescription(
        key="is_low_salt",
        name="Electrolyser Range",
        device_class=SensorDeviceClass.ENUM,
        options=list(_IS_LOW_SALT_MAP.values()),
        param_key="",
        value_map=_IS_LOW_SALT_MAP,
        value_fn=lambda d: _IS_LOW_SALT_MAP.get(int(d["isLowSalt"]), f"Unknown ({d['isLowSalt']})") if d.get("isLowSalt") is not None else None,
    ),
    # Alerts
    KlereoEnumDescription(
        key="alerts",
        name="Active Alerts",
        device_class=None,
        options=[],
        param_key="",
        value_map={},
        value_fn=_alert_string,
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

    # Numeric params sensors — only add if the value_fn returns a non-None value.
    # Guards: pH- sensors only when pHMode > 0; heating sensors only when HeaterMode > 0.
    _ph_mode = int(params.get("pHMode", 0))
    _heater_mode = int(params.get("HeaterMode", 0))
    _PH_MINUS_KEYS = {"phminus_today_ml", "phminus_total_l"}
    _HEATING_KEYS = {"heating_today_h", "heating_total_h", "setpoint_water_temp"}

    for desc in _PARAM_SENSORS:
        if desc.key in _PH_MINUS_KEYS and _ph_mode == 0:
            LOGGER.debug(f"Skipping '{desc.name}' — pHMode is 0 (no pH corrector)")
            continue
        if desc.key in _HEATING_KEYS and _heater_mode == 0:
            LOGGER.debug(f"Skipping '{desc.name}' — HeaterMode is 0 (no heater)")
            continue
        try:
            value = desc.value_fn(pool_data)
            if value is not None:
                LOGGER.info(f"Adding param sensor '{desc.name}' for #{poolid}")
                entities.append(KlereoParamSensor(coordinator, poolid, desc))
        except Exception:
            pass  # param not available for this pool — skip silently

    # Alert count — always present
    entities.append(KlereoAlertCountSensor(coordinator, poolid))

    # Enum params sensors — use value_fn when available, else fall back to param_key presence
    for desc in _ENUM_SENSORS:
        if desc.value_fn is not None:
            # value_fn sensors are always registered; the fn returns None when N/A
            LOGGER.info(f"Adding enum sensor '{desc.name}' for #{poolid}")
            entities.append(KlereoEnumSensor(coordinator, poolid, desc))
        elif desc.param_key in params:
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
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._poolid)},
            name=self.coordinator.data.get("poolNickname", f"Pool {self._poolid}"),
            serial_number=self.coordinator.data.get("podSerial"),
            manufacturer="Klereo",
        )

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
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._poolid)},
            name=self.coordinator.data.get("poolNickname", f"Pool {self._poolid}"),
            serial_number=self.coordinator.data.get("podSerial"),
            manufacturer="Klereo",
        )

    @property
    def name(self) -> str:
        return self.entity_description.name

    @property
    def unique_id(self) -> str:
        return f"klereo{self._poolid}_param_{self.entity_description.key}"

    @property
    def native_value(self):
        try:
            return self.entity_description.value_fn(self.coordinator.data)
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
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._poolid)},
            name=self.coordinator.data.get("poolNickname", f"Pool {self._poolid}"),
            serial_number=self.coordinator.data.get("podSerial"),
            manufacturer="Klereo",
        )

    @property
    def name(self) -> str:
        return self.entity_description.name

    @property
    def unique_id(self) -> str:
        return f"klereo{self._poolid}_enum_{self.entity_description.key}"

    @property
    def native_value(self) -> str | None:
        desc = self.entity_description
        # Sensors with a custom value_fn bypass the simple param_key lookup
        if desc.value_fn is not None:
            return desc.value_fn(self.coordinator.data)
        params = self.coordinator.data.get("params", {})
        raw = params.get(desc.param_key)
        if raw is None:
            return None
        return desc.value_map.get(int(raw), f"Unknown ({raw})")


class KlereoAlertCountSensor(CoordinatorEntity, SensorEntity):
    """Numeric sensor: how many active alerts the pool currently has."""

    def __init__(self, coordinator, poolid: int):
        super().__init__(coordinator)
        self._poolid = poolid

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._poolid)},
            name=self.coordinator.data.get("poolNickname", f"Pool {self._poolid}"),
            serial_number=self.coordinator.data.get("podSerial"),
            manufacturer="Klereo",
        )

    @property
    def name(self) -> str:
        return "Alert Count"

    @property
    def unique_id(self) -> str:
        return f"klereo{self._poolid}_alert_count"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.get("alerts", []))

    @property
    def native_unit_of_measurement(self) -> None:
        return None

    @property
    def state_class(self) -> SensorStateClass:
        return SensorStateClass.MEASUREMENT

    @property
    def icon(self) -> str:
        return "mdi:alert-circle-outline"

