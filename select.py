"""Select platform for Klereo — variable-speed filtration pump.

When ``pool_data['PumpMaxSpeed'] > 1`` the filtration output (index 1) is an
analogue variable-speed pump.  In that case the switch platform skips that
output and this platform registers a ``SelectEntity`` instead, with one named
option per discrete speed level:

    0   → "Off"
    1   → "Speed 1 (33%)"      (percentage is rounded to nearest integer)
    …
    N   → "Full speed (100%)"

API mapping
-----------
* Read  : ``out['realStatus']`` from coordinator data (actual current speed)
* Write : ``SetOut.php`` with ``newMode=0`` (Manual), ``newState=<speed int>``
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

import logging
LOGGER = logging.getLogger(__name__)

# Filtration output is always index 1 in the Klereo API
FILTRATION_OUT_INDEX = 1


def _build_speed_options(pump_max_speed: int) -> list[str]:
    """Return the list of named speed options for a pump with *pump_max_speed* discrete levels.

    Speed indices come directly from the Klereo API (PumpMaxSpeed field).
    No percentages are shown — the mapping from index to actual flow rate
    is pump-model-specific and not exposed by the API.

    Examples (pump_max_speed=3):
        ["Off", "Speed 1", "Speed 2", "Full speed"]
    """
    options = ["Off"]
    for speed in range(1, pump_max_speed + 1):
        if speed == pump_max_speed:
            options.append("Full speed")
        else:
            options.append(f"Speed {speed}")
    return options


def _speed_to_option(speed: int, pump_max_speed: int) -> str:
    """Convert a raw integer speed (0–PumpMaxSpeed) to its human-readable option string."""
    options = _build_speed_options(pump_max_speed)
    if 0 <= speed < len(options):
        return options[speed]
    return options[-1]  # clamp to max if out of range


def _option_to_speed(option: str, pump_max_speed: int) -> int:
    """Convert a human-readable option string back to its integer speed index."""
    options = _build_speed_options(pump_max_speed)
    if option in options:
        return options.index(option)
    return 0  # default to Off if unknown


async def async_setup_entry(hass, config_entry, async_add_entities):
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][config_entry.entry_id]["api"]
    pool_data = coordinator.data
    poolid = pool_data["idSystem"]
    pump_max_speed = int(pool_data.get("PumpMaxSpeed", 0))

    if pump_max_speed <= 1:
        LOGGER.debug(
            f"Pool #{poolid}: PumpMaxSpeed={pump_max_speed} — no variable-speed pump, skipping select platform"
        )
        return

    # Find the filtration output entry
    filtration_out = next(
        (o for o in pool_data.get("outs", []) if o.get("index") == FILTRATION_OUT_INDEX),
        None,
    )
    if filtration_out is None or filtration_out.get("type") is None:
        LOGGER.warning(
            f"Pool #{poolid}: PumpMaxSpeed={pump_max_speed} but filtration out#1 not found or null-type — skipping"
        )
        return

    LOGGER.info(f"Pool #{poolid}: registering variable-speed pump select entity (0–{pump_max_speed})")
    async_add_entities(
        [KlereoPumpSpeedSelect(api, coordinator, poolid, pump_max_speed)],
        update_before_add=True,
    )


class KlereoPumpSpeedSelect(CoordinatorEntity, SelectEntity):
    """HA Select entity representing the speed of a variable-speed filtration pump.

    Presents one labelled option per discrete speed level (0 = "Off",
    1..N = "Speed N (X%)", last = "Full speed (100%)").

    Reads the current speed from ``out['realStatus']`` (actual relay/drive state).
    Writes by calling ``KlereoAPI.set_pump_speed(outIdx, speed)``.
    """

    _attr_icon = "mdi:pump"

    def __init__(self, api, coordinator, poolid: int, pump_max_speed: int):
        super().__init__(coordinator)
        self._api = api
        self._poolid = poolid
        self._pump_max_speed = pump_max_speed
        self._options = _build_speed_options(pump_max_speed)

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

    # ── Options ───────────────────────────────────────────────────────────────

    @property
    def options(self) -> list[str]:
        return self._options

    # ── State ─────────────────────────────────────────────────────────────────

    @property
    def current_option(self) -> str | None:
        """Current speed as a human-readable option string."""
        out = self._get_out()
        if out is None:
            return None
        speed = int(out.get("realStatus", 0))
        return _speed_to_option(speed, self._pump_max_speed)

    @property
    def extra_state_attributes(self) -> dict:
        out = self._get_out()
        if out is None:
            return {}
        return {
            "pump_max_speed": self._pump_max_speed,
            "speed_index": int(out.get("realStatus", 0)),
            "status": out.get("status"),
            "mode": out.get("mode"),
            "updateTime": out.get("updateTime"),
        }

    # ── Write ─────────────────────────────────────────────────────────────────

    async def async_select_option(self, option: str) -> None:
        speed = _option_to_speed(option, self._pump_max_speed)
        LOGGER.info(
            f"Setting filtration pump to '{option}' (speed={speed}) for pool #{self._poolid}"
        )
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
