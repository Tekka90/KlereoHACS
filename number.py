"""Number platform for Klereo — writable regulation setpoints.

Entities registered
-------------------
One ``KlereoSetpointNumber`` per enabled regulation setpoint:

  * ``ConsigneEau``    — Water temperature setpoint (°C)    access >= 10
  * ``ConsignePH``     — pH setpoint                        access >= 16
  * ``ConsigneRedox``  — Redox / ORP setpoint (mV)          access >= 16
  * ``ConsigneChlore`` — Chlorine setpoint (mg/L)           access >= 16

A setpoint is considered disabled (and its entity is **not** registered) when
its current value equals ``-2000`` (disabled flag from the Klereo API).

The entity is also skipped when the pool's ``access`` level is lower than the
minimum required for that setpoint.

Variable-speed filtration pump
------------------------------
The pump speed control lives in ``select.py`` (``KlereoPumpSpeedSelect``) —
not here.  See that file for details.

Timer delay (SetAutoOff)
------------------------
One ``KlereoTimerDelayNumber`` per wired output that supports Timer mode:
indices 0, 5, 6, 7, 9, 10, 11, 12, 13, 14 (per Jeedom source).
Fixed bounds: 1–600 minutes.  Writing calls ``SetAutoOff.php`` then
``WaitCommand.php``.  Note: this only sets the *delay value* — activating
timer mode requires a separate ``SetOut`` call.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

LOGGER = logging.getLogger(__name__)

# Sentinel values from the Klereo API
_DISABLED = -2000   # setpoint is not configured / feature not present
_UNKNOWN  = -1000   # setpoint value is unknown

# Output indices that support Timer mode and therefore get an offDelay entity.
# Source: Jeedom klereo.class.php line ~935
# Excluded: 1 (Filtration), 4 (Heating), 2/3/8/15 (Pro outputs)
_TIMER_CAPABLE_OUTPUTS = frozenset([0, 5, 6, 7, 9, 10, 11, 12, 13, 14])

# Default bounds when the API does not supply them
_DEFAULT_MIN = 0.0
_DEFAULT_MAX = 100.0


@dataclass(frozen=True)
class _SetpointConfig:
    param_id:   str        # key in pool['params']
    name:       str        # human-readable entity name
    device_class: str | None
    unit:       str | None
    min_param:  str | None   # key in pool['params'] for lower bound (or None)
    max_param:  str | None   # key in pool['params'] for upper bound (or None)
    step:       float
    min_access: int          # minimum pool access level required to write


_SETPOINTS: list[_SetpointConfig] = [
    _SetpointConfig("ConsigneEau",    "Setpoint Water temperature", "temperature", "°C",  "EauMin", "EauMax",  0.5, 10),
    _SetpointConfig("ConsignePH",     "Setpoint pH",                None,          None,  "pHMin",  "pHMax",   0.1, 16),
    _SetpointConfig("ConsigneRedox",  "Setpoint Redox",             "voltage",     "mV",  "OrpMin", "OrpMax",  1,   16),
    _SetpointConfig("ConsigneChlore", "Setpoint Chlorine",          None,          "mg/L", None,    None,      0.1, 16),
]


async def async_setup_entry(hass, config_entry, async_add_entities):
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    api         = hass.data[DOMAIN][config_entry.entry_id]["api"]
    pool_data   = coordinator.data
    poolid      = pool_data["idSystem"]
    access      = int(pool_data.get("access", 10))
    params      = pool_data.get("params", {})

    entities: list = []
    for cfg in _SETPOINTS:
        raw = params.get(cfg.param_id)
        if raw is None or raw in (_DISABLED, _UNKNOWN):
            LOGGER.debug(
                f"Pool #{poolid}: {cfg.param_id}={raw} — setpoint disabled/unknown, skipping"
            )
            continue
        if access < cfg.min_access:
            LOGGER.debug(
                f"Pool #{poolid}: {cfg.param_id} requires access>={cfg.min_access}, "
                f"pool access={access} — skipping"
            )
            continue

        # --- Jeedom-matching extra guards ---
        # ConsigneEau: only register when a heat pump with a setpoint is present
        # (HeaterMode 0=none, 3=ON/OFF no setpoint — both excluded)
        if cfg.param_id == "ConsigneEau":
            heater_mode = params.get("HeaterMode")
            if heater_mode is None or int(heater_mode) in (0, 3):
                LOGGER.debug(
                    f"Pool #{poolid}: ConsigneEau skipped — HeaterMode={heater_mode} "
                    "(no heater or ON/OFF without setpoint)"
                )
                continue

        # ConsignePH: only register when a pH corrector is configured
        if cfg.param_id == "ConsignePH":
            ph_mode = params.get("pHMode")
            if ph_mode is None or int(ph_mode) == 0:
                LOGGER.debug(
                    f"Pool #{poolid}: ConsignePH skipped — pHMode={ph_mode} (no pH corrector)"
                )
                continue

        entities.append(KlereoSetpointNumber(coordinator, api, poolid, cfg))

    # ── Timer delay entities (SetAutoOff) ──────────────────────────────────
    for out in pool_data.get("outs", []):
        if out.get("type") is None:
            continue  # unconnected output
        if out["index"] not in _TIMER_CAPABLE_OUTPUTS:
            continue
        entities.append(KlereoTimerDelayNumber(coordinator, api, poolid, out["index"]))
        LOGGER.debug(f"Pool #{poolid}: registering timer delay number for out#{out['index']}")

    LOGGER.info(
        f"Pool #{poolid}: registering {len(entities)} number entities "
        f"(setpoints + timer delays)"
    )
    async_add_entities(entities)


class KlereoSetpointNumber(CoordinatorEntity, NumberEntity):
    _attr_suggested_display_precision = 2
    """A writable HA number entity for one Klereo regulation setpoint."""

    def __init__(self, coordinator, api, poolid, cfg: _SetpointConfig):
        super().__init__(coordinator)
        self._api    = api
        self._poolid = poolid
        self._cfg    = cfg

        self._attr_name            = cfg.name
        self._attr_unique_id       = f"id_klereo{poolid}_setpoint_{cfg.param_id.lower()}"
        self._unique_id            = self._attr_unique_id
        self._attr_device_class    = cfg.device_class
        self._attr_native_unit_of_measurement = cfg.unit
        self._attr_native_step     = cfg.step
        self._attr_mode            = NumberMode.BOX

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, poolid)},
            name=coordinator.data.get("poolNickname", f"Klereo pool {poolid}"),
            manufacturer="Klereo",
            serial_number=coordinator.data.get("podSerial"),
        )

    @property
    def unique_id(self) -> str:
        return self._unique_id

    # ── bounds — read from coordinator data so they update on coordinator refresh ──

    @property
    def native_min_value(self) -> float:
        params = self.coordinator.data.get("params", {})
        if self._cfg.min_param and self._cfg.min_param in params:
            return float(params[self._cfg.min_param])
        return _DEFAULT_MIN

    @property
    def native_max_value(self) -> float:
        params = self.coordinator.data.get("params", {})
        if self._cfg.max_param and self._cfg.max_param in params:
            return float(params[self._cfg.max_param])
        return _DEFAULT_MAX

    @property
    def native_value(self) -> float | None:
        """Return current setpoint from coordinator data, or None if unknown."""
        raw = self.coordinator.data.get("params", {}).get(self._cfg.param_id)
        if raw is None or raw in (_DISABLED, _UNKNOWN):
            return None
        # Round to the step precision to avoid floating-point noise from the API
        # (e.g. 7.40000009536743 → 7.4)
        step = self._cfg.step
        decimals = len(str(step).rstrip('0').split('.')[-1]) if '.' in str(step) else 0
        return round(float(raw), decimals)

    async def async_set_native_value(self, value: float) -> None:
        """Write the new setpoint to the Klereo API, then request a refresh."""
        await self.hass.async_add_executor_job(
            self._api.set_param, self._cfg.param_id, value
        )
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self) -> dict:
        params = self.coordinator.data.get("params", {})
        attrs: dict = {"param_id": self._cfg.param_id}
        if self._cfg.min_param:
            attrs["min_bound"] = params.get(self._cfg.min_param)
        if self._cfg.max_param:
            attrs["max_bound"] = params.get(self._cfg.max_param)
        return attrs


class KlereoTimerDelayNumber(CoordinatorEntity, NumberEntity):
    """Writable HA number entity for an output's auto-off timer delay.

    Supported output indices: 0, 5, 6, 7, 9, 10, 11, 12, 13, 14.
    Writing calls SetAutoOff.php (sets the delay value only — does NOT
    activate timer mode; that requires a separate SetOut call).
    """

    _attr_native_min_value: float = 1
    _attr_native_max_value: float = 600
    _attr_native_step: float = 1
    _attr_native_unit_of_measurement = "min"
    _attr_mode = NumberMode.BOX
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator, api, poolid: int, out_index: int):
        super().__init__(coordinator)
        self._api       = api
        self._poolid    = poolid
        self._out_index = out_index

        from .switch import _out_friendly_name
        friendly = _out_friendly_name(out_index, coordinator.data)
        self._attr_name = f"Timer delay {friendly} ({poolid})"
        self._unique_id = f"id_klereo{poolid}_offdelay_{out_index}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, poolid)},
            name=coordinator.data.get("poolNickname", f"Klereo pool {poolid}"),
            manufacturer="Klereo",
            serial_number=coordinator.data.get("podSerial"),
        )

    @property
    def unique_id(self) -> str:
        return self._unique_id

    @property
    def native_value(self) -> int | None:
        """Return current offDelay from coordinator data."""
        for out in self.coordinator.data.get("outs", []):
            if out["index"] == self._out_index:
                val = out.get("offDelay")
                if val is None:
                    return None
                return int(val)
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Write the new timer delay via SetAutoOff.php, then refresh."""
        await self.hass.async_add_executor_job(
            self._api.set_auto_off, self._out_index, int(value)
        )
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self) -> dict:
        return {"out_index": self._out_index}
