"""Unit tests for KlereoOut (switch) entity.

All HA infrastructure is mocked via tests/conftest.py.
async_turn_on / async_turn_off are tested synchronously via a thin wrapper
that avoids running a real event loop.
"""
import copy
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from klereo.switch import KlereoOut
from tests.fixtures import SAMPLE_POOL_DATA, SAMPLE_SET_OUT_RESPONSE


# ── Shared helpers ────────────────────────────────────────────────────────────

@pytest.fixture
def coordinator():
    coord = MagicMock()
    coord.data = copy.deepcopy(SAMPLE_POOL_DATA)
    return coord


@pytest.fixture
def mock_api():
    api = MagicMock()
    api.turn_on_device = MagicMock()
    api.turn_off_device = MagicMock()
    return api


def make_switch(coordinator, api, out_index=0):
    out = next(o for o in coordinator.data["outs"] if o["index"] == out_index)
    return KlereoOut(api, coordinator, out, 12345)


# ── is_on ─────────────────────────────────────────────────────────────────────────────

class TestKlereoOutIsOn:
    def test_off_when_status_is_zero(self, coordinator, mock_api):
        # out[0].status = 0 (OFF)
        sw = make_switch(coordinator, mock_api, out_index=0)
        assert sw.is_on is False

    def test_on_when_status_is_one(self, coordinator, mock_api):
        # status=1 means manually ON
        coordinator.data["outs"][0]["status"] = 1
        sw = make_switch(coordinator, mock_api, out_index=0)
        assert sw.is_on is True

    def test_on_when_status_is_two_auto(self, coordinator, mock_api):
        # out[1].status = 2 (AUTO — running on schedule/timer) must also report as on
        sw = make_switch(coordinator, mock_api, out_index=1)
        assert sw.is_on is True

    def test_always_reads_from_coordinator_not_local_state(self, coordinator, mock_api):
        """is_on must follow coordinator.data, never a cached local field."""
        sw = make_switch(coordinator, mock_api, out_index=0)
        assert sw.is_on is False
        # Simulate coordinator receiving updated data (pump turned on by schedule)
        coordinator.data["outs"][0]["status"] = 2
        assert sw.is_on is True

    def test_returns_none_for_missing_out(self, coordinator, mock_api):
        """If coordinator data no longer contains the output, is_on must return None."""
        out = {"index": 99, "type": 1, "mode": 0, "status": 0,
               "realStatus": 0, "updateTime": 0}  # index 99 not in coordinator.data
        sw = KlereoOut(mock_api, coordinator, out, 12345)
        assert sw.is_on is None


# ── Identifiers ───────────────────────────────────────────────────────────────

class TestKlereoOutIdentifiers:
    def test_unique_id(self, coordinator, mock_api):
        sw = make_switch(coordinator, mock_api, out_index=0)
        assert sw.unique_id == "id_klereo12345out0"

    def test_name_contains_pool_id(self, coordinator, mock_api):
        sw = make_switch(coordinator, mock_api, out_index=0)
        assert "12345" in sw.name

    def test_name_contains_out_index(self, coordinator, mock_api):
        sw = make_switch(coordinator, mock_api, out_index=0)
        assert "0" in sw.name


# ── Extra state attributes ────────────────────────────────────────────────────

class TestKlereoOutAttributes:
    def test_extra_attributes_present(self, coordinator, mock_api):
        sw = make_switch(coordinator, mock_api, out_index=0)
        attrs = sw.extra_state_attributes
        assert attrs is not None

    def test_extra_attributes_keys(self, coordinator, mock_api):
        sw = make_switch(coordinator, mock_api, out_index=0)
        attrs = sw.extra_state_attributes
        for key in ("Mode", "control_mode", "Status", "status_reason", "RealStatus", "Type", "Time"):
            assert key in attrs, f"Missing attribute: {key}"

    def test_extra_attributes_mode_value(self, coordinator, mock_api):
        sw = make_switch(coordinator, mock_api, out_index=0)  # mode=2 (Timer)
        assert sw.extra_state_attributes["Mode"] == 2

    def test_control_mode_manual(self, coordinator, mock_api):
        coordinator.data["outs"][0]["mode"] = 0
        sw = make_switch(coordinator, mock_api, out_index=0)
        assert sw.extra_state_attributes["control_mode"] == "manual"

    def test_control_mode_time_slots(self, coordinator, mock_api):
        # out[1] has mode=1 (time_slots) — the filtration pump
        sw = make_switch(coordinator, mock_api, out_index=1)
        assert sw.extra_state_attributes["control_mode"] == "time_slots"

    def test_control_mode_timer(self, coordinator, mock_api):
        # out[0] has mode=2 (timer) — lighting
        sw = make_switch(coordinator, mock_api, out_index=0)
        assert sw.extra_state_attributes["control_mode"] == "timer"

    def test_status_reason_off(self, coordinator, mock_api):
        sw = make_switch(coordinator, mock_api, out_index=0)  # status=0
        assert sw.extra_state_attributes["status_reason"] == "off"

    def test_status_reason_auto_when_running_on_schedule(self, coordinator, mock_api):
        # out[1] status=2 — pump running on schedule
        sw = make_switch(coordinator, mock_api, out_index=1)
        assert sw.extra_state_attributes["status_reason"] == "auto"

    def test_status_reason_on_when_manually_forced(self, coordinator, mock_api):
        coordinator.data["outs"][0]["status"] = 1
        sw = make_switch(coordinator, mock_api, out_index=0)
        assert sw.extra_state_attributes["status_reason"] == "on"

    def test_control_mode_unknown_falls_back_gracefully(self, coordinator, mock_api):
        coordinator.data["outs"][0]["mode"] = 99
        sw = make_switch(coordinator, mock_api, out_index=0)
        assert sw.extra_state_attributes["control_mode"] == "unknown(99)"


# ── Turn on / off ─────────────────────────────────────────────────────────────

class TestKlereoOutTurnOn:
    @pytest.mark.asyncio
    async def test_calls_api_turn_on(self, coordinator, mock_api):
        sw = make_switch(coordinator, mock_api, out_index=0)
        sw.hass.async_add_executor_job = AsyncMock(return_value=None)
        sw.coordinator.async_request_refresh = AsyncMock()
        await sw.async_turn_on()
        sw.hass.async_add_executor_job.assert_called_once_with(
            mock_api.turn_on_device, 0
        )

    @pytest.mark.asyncio
    async def test_requests_coordinator_refresh_after_turn_on(self, coordinator, mock_api):
        """After sending the command, a coordinator refresh must be requested."""
        sw = make_switch(coordinator, mock_api, out_index=0)
        sw.hass.async_add_executor_job = AsyncMock(return_value=None)
        sw.coordinator.async_request_refresh = AsyncMock()
        await sw.async_turn_on()
        sw.coordinator.async_request_refresh.assert_called_once()


class TestKlereoOutTurnOff:
    @pytest.mark.asyncio
    async def test_calls_api_turn_off(self, coordinator, mock_api):
        sw = make_switch(coordinator, mock_api, out_index=0)
        sw.hass.async_add_executor_job = AsyncMock(return_value=None)
        sw.coordinator.async_request_refresh = AsyncMock()
        await sw.async_turn_off()
        sw.hass.async_add_executor_job.assert_called_once_with(
            mock_api.turn_off_device, 0
        )

    @pytest.mark.asyncio
    async def test_requests_coordinator_refresh_after_turn_off(self, coordinator, mock_api):
        sw = make_switch(coordinator, mock_api, out_index=0)
        sw.hass.async_add_executor_job = AsyncMock(return_value=None)
        sw.coordinator.async_request_refresh = AsyncMock()
        await sw.async_turn_off()
        sw.coordinator.async_request_refresh.assert_called_once()


# ── DeviceInfo ────────────────────────────────────────────────────────────────

class TestKlereoOutDeviceInfo:
    def test_device_info_identifiers(self, coordinator, mock_api):
        sw = make_switch(coordinator, mock_api, out_index=0)
        assert sw.device_info["identifiers"] == {("klereo", 12345)}

    def test_device_info_name(self, coordinator, mock_api):
        sw = make_switch(coordinator, mock_api, out_index=0)
        assert sw.device_info["name"] == "Ma piscine (test)"

    def test_device_info_serial(self, coordinator, mock_api):
        sw = make_switch(coordinator, mock_api, out_index=0)
        assert sw.device_info["serial_number"] == "POD-TEST-001"

    def test_device_info_manufacturer(self, coordinator, mock_api):
        sw = make_switch(coordinator, mock_api, out_index=0)
        assert sw.device_info["manufacturer"] == "Klereo"

    def test_fallback_name_when_nickname_absent(self, coordinator, mock_api):
        coordinator.data.pop("poolNickname", None)
        sw = make_switch(coordinator, mock_api, out_index=0)
        assert "12345" in sw.device_info["name"]
