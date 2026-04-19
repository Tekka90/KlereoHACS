import base64
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

LOGGER = logging.getLogger(__name__)

# Human-readable labels — derived from the Jeedom klereo reference implementation
_OUT_MODE_LABELS = {
    0: "manual",
    1: "time_slots",
    2: "timer",
    3: "regulation",
    4: "clone",
    5: "special",
    6: "test",
    7: "bad",
    8: "pulse",
    9: "auto",
}

_OUT_STATUS_LABELS = {
    0: "off",
    1: "on",
    2: "auto",
}

# Default human-readable names per output index — from Jeedom getOutInfo()
_OUT_INDEX_NAME = {
    0:  "Lighting",
    1:  "Filtration",
    2:  "pH corrector",
    3:  "Disinfectant",
    4:  "Heating",
    5:  "Auxiliary 1",
    6:  "Auxiliary 2",
    7:  "Auxiliary 3",
    8:  "Flocculant",
    9:  "Auxiliary 4",
    10: "Auxiliary 5",
    11: "Auxiliary 6",
    12: "Auxiliary 7",
    13: "Auxiliary 8",
    14: "Auxiliary 9",
    15: "Hybrid disinfectant",
}


# Mapping from output index to plan index — from Jeedom getOutInfo().
# The plan index is used to look up entries in details['plans'].
# None = output has no time-slot schedule (Heating, pH corrector).
_OUT_PLAN_INDEX: dict[int, int | None] = {
    0:  0,    # Lighting
    1:  1,    # Filtration
    2:  None, # pH corrector — no plan
    3:  3,    # Disinfectant
    4:  None, # Heating — no plan
    5:  5,    # Auxiliary 1
    6:  6,    # Auxiliary 2
    7:  7,    # Auxiliary 3
    8:  4,    # Flocculant (plan index 4, out index 8)
    9:  8,    # Auxiliary 4
    10: 9,    # Auxiliary 5
    11: 10,   # Auxiliary 6
    12: 11,   # Auxiliary 7
    13: 12,   # Auxiliary 8
    14: 13,   # Auxiliary 9
    15: 2,    # Hybrid disinfectant
}


def decode_plan(plan64: str) -> list[bool]:
    """Decode a Klereo plan64 schedule string to 96 booleans.

    Each boolean corresponds to a 15-minute slot over 24 hours,
    starting at 00:00. True = output is ON during that slot.

    Mirrors Jeedom plan2arr(): base64-decode the 12-byte payload,
    then extract bits LSB-first per byte (equivalent to PHP
    unpack('h*', ...) + reversed nibble iteration).
    """
    raw = base64.b64decode(plan64)
    slots: list[bool] = []
    for byte in raw:
        for bit in range(8):
            slots.append(bool((byte >> bit) & 1))
    return slots


def _plan_active_periods(slots: list[bool]) -> list[str]:
    """Convert 96 boolean time-slots to a list of 'HH:MM-HH:MM' active period strings."""
    periods: list[str] = []
    in_period = False
    start = 0
    for i, active in enumerate(slots):
        if active and not in_period:
            start = i
            in_period = True
        elif not active and in_period:
            periods.append(_format_slot_range(start, i))
            in_period = False
    if in_period:
        periods.append(_format_slot_range(start, len(slots)))
    return periods


def _format_slot_range(start_slot: int, end_slot: int) -> str:
    """Format a half-open slot range [start, end) as 'HH:MM-HH:MM'."""
    s = start_slot * 15
    e = end_slot * 15
    return f"{s // 60:02d}:{s % 60:02d}-{e // 60:02d}:{e % 60:02d}"


def _out_friendly_name(out_index: int, pool_data: dict) -> str:
    """Return a human-readable name for an output.

    Priority:
    1. User-defined rename from pool_data['IORename'] (ioType=1)
    2. Index-based default from _OUT_INDEX_NAME
    3. Fallback: 'Output {index}'
    """
    for rename in pool_data.get('IORename', []) or []:
        if rename.get('ioType') == 1 and rename.get('ioIndex') == out_index:
            return rename['name']
    return _OUT_INDEX_NAME.get(out_index, f"Output {out_index}")

async def async_setup_entry(hass, config_entry, async_add_entities):
    
    LOGGER.info(f"Setting up switches...")
    # Get infos from coordinator
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][config_entry.entry_id]["api"]
    pool_data=coordinator.data;
    outs = pool_data["outs"]
    poolid = pool_data['idSystem']
    pump_max_speed = int(pool_data.get('PumpMaxSpeed', 0))
    # Add switches
    switches = []
    for out in outs:
        if out.get('type') is None:  # unconnected/unwired output — skip
            LOGGER.debug(f"Skipping null-type out#{out['index']} for #{poolid}")
            continue
        if out['index'] == 1 and pump_max_speed > 1:
            # Variable-speed analogue pump — handled by the number platform
            LOGGER.debug(f"Skipping filtration out#1 for #{poolid}: variable-speed pump (max={pump_max_speed})")
            continue
        LOGGER.info(f"Adding out for #{poolid}: {out}")
        switches.append(KlereoOut(api,coordinator,out,poolid))
    #add switch enitities
    async_add_entities(switches, update_before_add=True)


class KlereoOut(CoordinatorEntity, SwitchEntity):

    def __init__(self, api, coordinator, out, poolid):
        super().__init__(coordinator)
        self._api = api
        self._index = out['index']
        self._type = out['type']
        self._mode = out['mode']
        self._poolid = poolid
        friendly = _out_friendly_name(out['index'], coordinator.data)
        self._name = f"{friendly} ({poolid})"

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
        return self._name

    @property
    def is_on(self):
        outs = self.coordinator.data['outs']
        for out in outs:
            if out['index'] == self._index:
                LOGGER.debug(f"{self._name} status={out['status']} realStatus={out['realStatus']}")
                # status: 0=OFF, 1=ON (manual), 2=AUTO (running on schedule/timer)
                # Any non-zero status means the output is physically active.
                return out['status'] != 0
        return None

    @property
    def mode(self):
        return self._mode


    @property
    def unique_id(self):
        return f"id_klereo{self._poolid}out{self._index}"

    @property
    def extra_state_attributes(self):
        outs = self.coordinator.data['outs']
        for out in outs:
            if out['index'] == self._index:
                mode = out['mode']
                status = out['status']
                mode_label = _OUT_MODE_LABELS.get(mode, f"unknown({mode})")
                status_label = _OUT_STATUS_LABELS.get(status, f"unknown({status})")

                # Decode time-slot schedule from plans array, if available
                schedule: list[str] | None = None
                plan_index = _OUT_PLAN_INDEX.get(self._index)
                if plan_index is not None:
                    for plan_entry in self.coordinator.data.get('plans', []) or []:
                        if plan_entry.get('index') == plan_index:
                            plan64 = plan_entry.get('plan64', '')
                            if plan64:
                                schedule = _plan_active_periods(decode_plan(plan64))
                            break

                return {
                    'Time': out['updateTime'],
                    'Type': out['type'],
                    'Mode': mode,
                    'control_mode': mode_label,
                    'Status': status,
                    'status_reason': status_label,
                    'RealStatus': out['realStatus'],
                    'offDelay': out.get('offDelay'),
                    'schedule': schedule,
                }
        return None

    async def async_turn_on(self, **kwargs):
        await self.hass.async_add_executor_job(self._api.turn_on_device, self._index)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self.hass.async_add_executor_job(self._api.turn_off_device, self._index)
        await self.coordinator.async_request_refresh()

    async def async_set_mode(self, mode):
        #if mode not in ["manual", "timer", "schedule"]:
        #    raise ValueError(f"Invalid mode: {mode}")
        LOGGER.debug(f"Change mode #{self._poolid} {mode}")
        await self.hass.async_add_executor_job(self._api.set_device_mode, self._index, mode)
        self._mode = mode
        self.async_write_ha_state()
