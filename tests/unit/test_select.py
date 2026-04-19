"""Unit tests for KlereoPumpSpeedSelect (select platform).

Covers:
- _build_speed_options generates correct labels for various PumpMaxSpeed values
- _speed_to_option / _option_to_speed round-trip correctly
- Entity is registered only when PumpMaxSpeed > 1
- current_option reads realStatus from coordinator data (not a cached field)
- options list is correct length
- unique_id and name are stable
- async_select_option maps option string to int speed and calls api.set_pump_speed
- extra_state_attributes contains expected keys including speed_index
- switch platform still skips filtration out#1 when PumpMaxSpeed > 1
"""

import copy
import pytest
from unittest.mock import AsyncMock, MagicMock

from klereo.select import (
    KlereoPumpSpeedSelect,
    FILTRATION_OUT_INDEX,
    _build_speed_options,
    _speed_to_option,
    _option_to_speed,
)
from klereo.switch import KlereoOut
from tests.fixtures import SAMPLE_POOL_DATA, SAMPLE_VARSPEED_POOL_DATA


# ── Shared helpers ────────────────────────────────────────────────────────────

@pytest.fixture
def varspeed_coordinator():
    coord = MagicMock()
    coord.data = copy.deepcopy(SAMPLE_VARSPEED_POOL_DATA)
    return coord


@pytest.fixture
def normal_coordinator():
    coord = MagicMock()
    coord.data = copy.deepcopy(SAMPLE_POOL_DATA)
    return coord


@pytest.fixture
def mock_api():
    api = MagicMock()
    api.set_pump_speed = MagicMock()
    return api


def make_entity(coordinator, api, pump_max_speed=3):
    return KlereoPumpSpeedSelect(api, coordinator, 12345, pump_max_speed)


# ── Helper functions ──────────────────────────────────────────────────────────

class TestBuildSpeedOptions:
    def test_zero_is_always_off(self):
        for max_speed in [2, 3, 5, 8]:
            opts = _build_speed_options(max_speed)
            assert opts[0] == "Off"

    def test_last_is_full_speed(self):
        for max_speed in [2, 3, 5]:
            opts = _build_speed_options(max_speed)
            assert opts[-1] == "Full speed"

    def test_length_is_max_plus_one(self):
        for max_speed in [2, 3, 5, 8]:
            opts = _build_speed_options(max_speed)
            assert len(opts) == max_speed + 1

    def test_max3_labels(self):
        opts = _build_speed_options(3)
        assert opts == ["Off", "Speed 1", "Speed 2", "Full speed"]

    def test_max2_labels(self):
        opts = _build_speed_options(2)
        assert opts == ["Off", "Speed 1", "Full speed"]

    def test_max1_labels(self):
        # Edge case: only Off and Full speed
        opts = _build_speed_options(1)
        assert opts == ["Off", "Full speed"]


class TestSpeedOptionRoundTrip:
    def test_zero_maps_to_off(self):
        assert _speed_to_option(0, 3) == "Off"

    def test_max_maps_to_full_speed(self):
        assert _speed_to_option(3, 3) == "Full speed"

    def test_off_maps_to_zero(self):
        assert _option_to_speed("Off", 3) == 0

    def test_full_speed_maps_to_max(self):
        assert _option_to_speed("Full speed", 3) == 3

    def test_mid_speed_round_trip(self):
        opts = _build_speed_options(3)
        for i, opt in enumerate(opts):
            assert _option_to_speed(opt, 3) == i

    def test_unknown_option_returns_zero(self):
        assert _option_to_speed("bogus", 3) == 0

    def test_out_of_range_speed_clamps_to_max(self):
        # speed 99 on a max=3 pump → clamp to Full speed
        assert _speed_to_option(99, 3) == "Full speed"


# ── Identity ──────────────────────────────────────────────────────────────────

class TestKlereoPumpSpeedSelectIdentity:
    def test_unique_id(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api)
        assert entity.unique_id == "klereo12345_pump_speed"

    def test_name(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api)
        assert entity.name == "Filtration Speed"

    def test_device_info_identifiers(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api)
        assert entity.device_info["identifiers"] == {("klereo", 12345)}

    def test_device_info_manufacturer(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api)
        assert entity.device_info["manufacturer"] == "Klereo"

    def test_device_info_name_from_coordinator(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api)
        assert entity.device_info["name"] == "Ma piscine (test)"

    def test_device_info_fallback_name(self, varspeed_coordinator, mock_api):
        varspeed_coordinator.data.pop("poolNickname", None)
        entity = make_entity(varspeed_coordinator, mock_api)
        assert "12345" in entity.device_info["name"]


# ── Options ───────────────────────────────────────────────────────────────────

class TestKlereoPumpSpeedSelectOptions:
    def test_options_length(self, varspeed_coordinator, mock_api):
        pump_max_speed = int(varspeed_coordinator.data.get("PumpMaxSpeed", 3))
        entity = make_entity(varspeed_coordinator, mock_api, pump_max_speed)
        assert len(entity.options) == pump_max_speed + 1

    def test_options_first_is_off(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api)
        assert entity.options[0] == "Off"

    def test_options_last_is_full_speed(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api)
        assert entity.options[-1] == "Full speed"

    def test_options_max3(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api, pump_max_speed=3)
        assert entity.options == ["Off", "Speed 1", "Speed 2", "Full speed"]


# ── State reads from coordinator ──────────────────────────────────────────────

class TestKlereoPumpSpeedSelectState:
    def test_current_option_reads_real_status(self, varspeed_coordinator, mock_api):
        # SAMPLE_VARSPEED_POOL_DATA sets out[1].realStatus = 2  →  "Speed 2"
        entity = make_entity(varspeed_coordinator, mock_api, pump_max_speed=3)
        assert entity.current_option == "Speed 2"

    def test_current_option_zero_is_off(self, varspeed_coordinator, mock_api):
        varspeed_coordinator.data["outs"][1]["realStatus"] = 0
        entity = make_entity(varspeed_coordinator, mock_api, pump_max_speed=3)
        assert entity.current_option == "Off"

    def test_current_option_reads_from_coordinator_not_cache(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api, pump_max_speed=3)
        assert entity.current_option == "Speed 2"
        varspeed_coordinator.data["outs"][1]["realStatus"] = 0
        assert entity.current_option == "Off"

    def test_current_option_returns_none_when_out_missing(self, varspeed_coordinator, mock_api):
        varspeed_coordinator.data["outs"] = []
        entity = make_entity(varspeed_coordinator, mock_api)
        assert entity.current_option is None

    def test_extra_state_attributes_keys(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api)
        attrs = entity.extra_state_attributes
        for key in ("pump_max_speed", "speed_index", "status", "mode", "updateTime"):
            assert key in attrs, f"Missing attribute: {key}"

    def test_extra_state_attributes_speed_index(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api, pump_max_speed=3)
        assert entity.extra_state_attributes["speed_index"] == 2

    def test_extra_state_attributes_pump_max_speed(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api, pump_max_speed=3)
        assert entity.extra_state_attributes["pump_max_speed"] == 3

    def test_extra_state_attributes_empty_when_out_missing(self, varspeed_coordinator, mock_api):
        varspeed_coordinator.data["outs"] = []
        entity = make_entity(varspeed_coordinator, mock_api)
        assert entity.extra_state_attributes == {}


# ── Write ─────────────────────────────────────────────────────────────────────

class TestKlereoPumpSpeedSelectWrite:
    @pytest.mark.asyncio
    async def test_calls_api_set_pump_speed_with_int(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api, pump_max_speed=3)
        entity.hass.async_add_executor_job = AsyncMock(return_value=None)
        entity.coordinator.async_request_refresh = AsyncMock()
        await entity.async_select_option("Speed 2")
        entity.hass.async_add_executor_job.assert_called_once_with(
            mock_api.set_pump_speed, FILTRATION_OUT_INDEX, 2
        )

    @pytest.mark.asyncio
    async def test_off_option_sends_speed_zero(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api, pump_max_speed=3)
        entity.hass.async_add_executor_job = AsyncMock(return_value=None)
        entity.coordinator.async_request_refresh = AsyncMock()
        await entity.async_select_option("Off")
        _, _, speed = entity.hass.async_add_executor_job.call_args[0]
        assert speed == 0

    @pytest.mark.asyncio
    async def test_full_speed_option_sends_max_speed(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api, pump_max_speed=3)
        entity.hass.async_add_executor_job = AsyncMock(return_value=None)
        entity.coordinator.async_request_refresh = AsyncMock()
        await entity.async_select_option("Full speed")
        _, _, speed = entity.hass.async_add_executor_job.call_args[0]
        assert speed == 3

    @pytest.mark.asyncio
    async def test_requests_coordinator_refresh(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api, pump_max_speed=3)
        entity.hass.async_add_executor_job = AsyncMock(return_value=None)
        entity.coordinator.async_request_refresh = AsyncMock()
        await entity.async_select_option("Off")
        entity.coordinator.async_request_refresh.assert_called_once()


# ── Switch platform skips filtration when variable-speed ──────────────────────

class TestSwitchSkipsVariableSpeedFiltration:
    def test_filtration_out_excluded_from_switches_when_varspeed(self, varspeed_coordinator):
        pool_data = varspeed_coordinator.data
        pump_max_speed = int(pool_data.get("PumpMaxSpeed", 0))
        api = MagicMock()

        switches = []
        for out in pool_data["outs"]:
            if out.get("type") is None:
                continue
            if out["index"] == FILTRATION_OUT_INDEX and pump_max_speed > 1:
                continue
            switches.append(KlereoOut(api, varspeed_coordinator, out, pool_data["idSystem"]))

        out_indices = [s._index for s in switches]
        assert FILTRATION_OUT_INDEX not in out_indices

    def test_filtration_out_included_in_switches_when_normal(self, normal_coordinator):
        pool_data = normal_coordinator.data
        pump_max_speed = int(pool_data.get("PumpMaxSpeed", 0))
        api = MagicMock()

        switches = []
        for out in pool_data["outs"]:
            if out.get("type") is None:
                continue
            if out["index"] == FILTRATION_OUT_INDEX and pump_max_speed > 1:
                continue
            switches.append(KlereoOut(api, normal_coordinator, out, pool_data["idSystem"]))

        out_indices = [s._index for s in switches]
        assert FILTRATION_OUT_INDEX in out_indices
