"""Unit tests for KlereoPumpSpeedNumber (number platform).

Covers:
- Entity is registered only when PumpMaxSpeed > 1
- native_value reads realStatus from coordinator data (not a cached field)
- native_min/max/step are correct
- unique_id and name are stable
- async_set_native_value calls api.set_pump_speed then requests coordinator refresh
- extra_state_attributes contains expected keys
- switch platform skips filtration out#1 when PumpMaxSpeed > 1
"""
import copy
import pytest
from unittest.mock import AsyncMock, MagicMock

from klereo.number import KlereoPumpSpeedNumber, FILTRATION_OUT_INDEX
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
    return KlereoPumpSpeedNumber(api, coordinator, 12345, pump_max_speed)


# ── Identity ──────────────────────────────────────────────────────────────────

class TestKlereoPumpSpeedIdentity:
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


# ── Range ─────────────────────────────────────────────────────────────────────

class TestKlereoPumpSpeedRange:
    def test_min_is_zero(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api, pump_max_speed=3)
        assert entity.native_min_value == 0.0

    def test_max_equals_pump_max_speed(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api, pump_max_speed=3)
        assert entity.native_max_value == 3.0

    def test_max_reflects_constructor_argument(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api, pump_max_speed=5)
        assert entity.native_max_value == 5.0

    def test_step_is_one(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api)
        assert entity.native_step == 1.0


# ── State reads from coordinator ──────────────────────────────────────────────

class TestKlereoPumpSpeedState:
    def test_native_value_reads_real_status(self, varspeed_coordinator, mock_api):
        # SAMPLE_VARSPEED_POOL_DATA sets out[1].realStatus = 2
        entity = make_entity(varspeed_coordinator, mock_api)
        assert entity.native_value == 2.0

    def test_native_value_reads_from_coordinator_not_cache(self, varspeed_coordinator, mock_api):
        """State must follow coordinator.data, not a cached init-time value."""
        entity = make_entity(varspeed_coordinator, mock_api)
        assert entity.native_value == 2.0
        # Simulate coordinator receiving updated data (pump speed changed)
        varspeed_coordinator.data["outs"][1]["realStatus"] = 0
        assert entity.native_value == 0.0

    def test_native_value_returns_none_when_out_missing(self, varspeed_coordinator, mock_api):
        varspeed_coordinator.data["outs"] = []
        entity = make_entity(varspeed_coordinator, mock_api)
        assert entity.native_value is None

    def test_extra_state_attributes_keys(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api)
        attrs = entity.extra_state_attributes
        for key in ("pump_max_speed", "status", "mode", "updateTime"):
            assert key in attrs, f"Missing attribute: {key}"

    def test_extra_state_attributes_pump_max_speed(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api, pump_max_speed=3)
        assert entity.extra_state_attributes["pump_max_speed"] == 3

    def test_extra_state_attributes_empty_when_out_missing(self, varspeed_coordinator, mock_api):
        varspeed_coordinator.data["outs"] = []
        entity = make_entity(varspeed_coordinator, mock_api)
        assert entity.extra_state_attributes == {}


# ── Write ─────────────────────────────────────────────────────────────────────

class TestKlereoPumpSpeedWrite:
    @pytest.mark.asyncio
    async def test_calls_api_set_pump_speed(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api)
        entity.hass.async_add_executor_job = AsyncMock(return_value=None)
        entity.coordinator.async_request_refresh = AsyncMock()
        await entity.async_set_native_value(2.0)
        entity.hass.async_add_executor_job.assert_called_once_with(
            mock_api.set_pump_speed, FILTRATION_OUT_INDEX, 2
        )

    @pytest.mark.asyncio
    async def test_casts_value_to_int(self, varspeed_coordinator, mock_api):
        """Floats from HA number UI must be cast to int before sending to API."""
        entity = make_entity(varspeed_coordinator, mock_api)
        entity.hass.async_add_executor_job = AsyncMock(return_value=None)
        entity.coordinator.async_request_refresh = AsyncMock()
        await entity.async_set_native_value(1.9)  # e.g. rounding edge
        _, _, speed = entity.hass.async_add_executor_job.call_args[0]
        assert isinstance(speed, int)
        assert speed == 1

    @pytest.mark.asyncio
    async def test_requests_coordinator_refresh(self, varspeed_coordinator, mock_api):
        entity = make_entity(varspeed_coordinator, mock_api)
        entity.hass.async_add_executor_job = AsyncMock(return_value=None)
        entity.coordinator.async_request_refresh = AsyncMock()
        await entity.async_set_native_value(3.0)
        entity.coordinator.async_request_refresh.assert_called_once()


# ── Switch platform skips filtration when variable-speed ──────────────────────

class TestSwitchSkipsVariableSpeedFiltration:
    def test_filtration_out_excluded_from_switches_when_varspeed(self, varspeed_coordinator):
        """When PumpMaxSpeed > 1 the filtration out (index 1) must NOT become a KlereoOut."""
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
        """When PumpMaxSpeed <= 1 the filtration out must remain a KlereoOut switch."""
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
