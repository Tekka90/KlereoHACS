"""Number platform for Klereo — variable-speed filtration pump.

When ``pool_data['PumpMaxSpeed'] > 1`` the filtration output (index 1) is an
analogue variable-speed pump.  In that case the switch platform skips that
output and this platform registers a ``NumberEntity`` instead, with the speed
range 0 … PumpMaxSpeed.

API mapping
-----------
* Read  : ``out['realStatus']`` from coordinator data (actual current speed)
* Write : ``SetOut.php`` with ``newMode=0`` (Manual), ``newState=<speed int>``
"""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

import logging
LOGGER = logging.getLogger(__name__)

# Filtration output is always index 1 in the Klereo API
FILTRATION_OUT_INDEX = 1


async def async_setup_entry(hass, config_entry, async_add_entities):
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][config_entry.entry_id]["api"]
    pool_data = coordinator.data
    poolid = pool_data["idSystem"]
    pump_max_speed = int(pool_data.get("PumpMaxSpeed", 0))

    if pump_max_speed <= 1:
        LOGGER.debug(f"Pool #{poolid}: PumpMaxSpeed={pump_max_speed} — no variable-speed pump, skipping number platform")
        return

    # Find the filtration output entry
    filtration_out = next(
        (o for o in pool_data.get("outs", []) if o.get("index") == FILTRATION_OUT_INDEX),
        None,
    )
    if filtration_out is None or filtration_out.get("type") is None:
        LOGGER.warning(f"Pool #{poolid}: PumpMaxSpeed={pump_max_speed} but filtration out#1 not found or null-type — skipping")
        return

    LOGGER.info(f"Pool #{poolid}: registering variable-speed pump entity (0–{pump_max_speed})")
    async_add_entities(
        [KlereoPumpSpeedNumber(api, coordinator, poolid, pump_max_speed)],
        update_before_add=True,
    )


class KlereoPumpSpeedNumber(CoordinatorEntity, NumberEntity):
    """HA Number entity representing the speed of a variable-speed filtration pump.

    Reads the current speed from ``out['realStatus']`` (actual relay/drive state).
    Writes by calling ``KlereoAPI.set_pump_speed(outIdx, speed)``.
    """

    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:pump"

    def __init__(self, api, coordinator, poolid: int, pump_max_speed: int):
        super().__init__(coordinator)
        self._api = api
        self._poolid = poolid
        self._pump_max_speed = pump_max_speed

    # ── Identity ──────────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "Filtration Speed"

    @property
    def unique_id(self) -> str:
        return f"klereo{self._poolid}_pump_speed"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._poolid)},
            name=self.coordinator.data.get("poolNickname", f"Pool {self._poolid}"),
            serial_number=self.coordinator.data.get("podSerial"),
            manufacturer="Klereo",
        )

    # ── Range ─────────────────────────────────────────────────────────────────

    @property
    def native_min_value(self) -> float:
        return 0.0

    @property
    def native_max_value(self) -> float:
        return float(self._pump_max_speed)

    @property
    def native_step(self) -> float:
        return 1.0

    @property
    def native_unit_of_measurement(self) -> str | None:
        return None  # dimensionless speed index

    # ── State ─────────────────────────────────────────────────────────────────

    @property
    def native_value(self) -> float | None:
        """Current speed from coordinator data (realStatus = actual drive output)."""
        out = self._get_out()
        if out is None:
            return None
        return float(out.get("realStatus", 0))

    @property
    def extra_state_attributes(self) -> dict:
        out = self._get_out()
        if out is None:
            return {}
        return {
            "pump_max_speed": self._pump_max_speed,
            "status": out.get("status"),
            "mode": out.get("mode"),
            "updateTime": out.get("updateTime"),
        }

    # ── Write ─────────────────────────────────────────────────────────────────

    async def async_set_native_value(self, value: float) -> None:
        speed = int(value)
        LOGGER.info(f"Setting filtration pump speed to {speed} (pool #{self._poolid})")
        await self.hass.async_add_executor_job(
            self._api.set_pump_speed, FILTRATION_OUT_INDEX, speed
        )
        await self.coordinator.async_request_refresh()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_out(self) -> dict | None:
        for out in self.coordinator.data.get("outs", []):
            if out.get("index") == FILTRATION_OUT_INDEX:
                return out
        return None
