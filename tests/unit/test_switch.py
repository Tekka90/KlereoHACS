"""Unit tests for KlereoOut (switch) entity.

All HA infrastructure is mocked via tests/conftest.py.
async_turn_on / async_turn_off are tested synchronously via a thin wrapper
that avoids running a real event loop.
"""
import copy
import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from klereo.switch import KlereoOut, decode_plan, _plan_active_periods, _OUT_PLAN_INDEX
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

    def test_name_uses_index_default_for_lighting(self, coordinator, mock_api):
        sw = make_switch(coordinator, mock_api, out_index=0)
        assert "Lighting" in sw.name

    def test_name_uses_index_default_for_filtration(self, coordinator, mock_api):
        sw = make_switch(coordinator, mock_api, out_index=1)
        assert "Filtration" in sw.name

    def test_name_uses_iorename_when_present(self, coordinator, mock_api):
        coordinator.data["IORename"] = [
            {"ioType": 1, "ioIndex": 0, "name": "Pool light"}
        ]
        sw = make_switch(coordinator, mock_api, out_index=0)
        assert "Pool light" in sw.name

    def test_iorename_ignored_for_different_index(self, coordinator, mock_api):
        coordinator.data["IORename"] = [
            {"ioType": 1, "ioIndex": 5, "name": "Waterfall"}
        ]
        sw = make_switch(coordinator, mock_api, out_index=0)
        assert "Waterfall" not in sw.name
        assert "Lighting" in sw.name

    def test_iorename_probe_rename_not_applied_to_output(self, coordinator, mock_api):
        """ioType=2 (probe rename) must not affect output names."""
        coordinator.data["IORename"] = [
            {"ioType": 2, "ioIndex": 0, "name": "Should not appear"}
        ]
        sw = make_switch(coordinator, mock_api, out_index=0)
        assert "Should not appear" not in sw.name
        assert "Lighting" in sw.name

    def test_name_fallback_for_unknown_index(self, coordinator, mock_api):
        """Output index not in _OUT_INDEX_NAME should fall back to 'Output {index}'."""
        out = {"index": 99, "type": 1, "mode": 0, "status": 0,
               "realStatus": 0, "offDelay": None, "updateTime": 0}
        sw = KlereoOut(mock_api, coordinator, out, 12345)
        assert "Output 99" in sw.name


# ── Extra state attributes ────────────────────────────────────────────────────

class TestKlereoOutAttributes:
    def test_extra_attributes_present(self, coordinator, mock_api):
        sw = make_switch(coordinator, mock_api, out_index=0)
        attrs = sw.extra_state_attributes
        assert attrs is not None

    def test_extra_attributes_keys(self, coordinator, mock_api):
        sw = make_switch(coordinator, mock_api, out_index=0)
        attrs = sw.extra_state_attributes
        for key in ("Mode", "control_mode", "Status", "status_reason", "RealStatus", "Type", "Time", "offDelay", "schedule"):
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


# ── Plan decoding ─────────────────────────────────────────────────────────────

class TestDecodePlan:
    """Unit tests for the decode_plan() function (mirrors Jeedom plan2arr)."""

    def test_all_zeros_gives_96_false(self):
        # 12 zero bytes → all slots off
        plan64 = base64.b64encode(bytes(12)).decode()
        result = decode_plan(plan64)
        assert len(result) == 96
        assert all(s is False for s in result)

    def test_all_ones_gives_96_true(self):
        # 12 bytes of 0xFF → all slots on
        plan64 = base64.b64encode(bytes([0xFF] * 12)).decode()
        result = decode_plan(plan64)
        assert len(result) == 96
        assert all(s is True for s in result)

    def test_first_byte_0x0F_activates_slots_0_to_3(self):
        # 0x0F = 0b00001111 → bits 0-3 = True, bits 4-7 = False
        plan64 = base64.b64encode(bytes([0x0F] + [0x00] * 11)).decode()
        result = decode_plan(plan64)
        assert result[:4] == [True, True, True, True]
        assert result[4:] == [False] * 92

    def test_first_byte_0xF0_activates_slots_4_to_7(self):
        # 0xF0 = 0b11110000 → bits 4-7 = True, bits 0-3 = False
        plan64 = base64.b64encode(bytes([0xF0] + [0x00] * 11)).decode()
        result = decode_plan(plan64)
        assert result[:4] == [False, False, False, False]
        assert result[4:8] == [True, True, True, True]
        assert result[8:] == [False] * 88

    def test_second_byte_activates_slots_8_to_15(self):
        plan64 = base64.b64encode(bytes([0x00, 0xFF] + [0x00] * 10)).decode()
        result = decode_plan(plan64)
        assert result[:8] == [False] * 8
        assert result[8:16] == [True] * 8
        assert result[16:] == [False] * 80

    def test_output_length_is_always_96(self):
        for byte_val in [0x00, 0x55, 0xAA, 0xFF]:
            plan64 = base64.b64encode(bytes([byte_val] * 12)).decode()
            assert len(decode_plan(plan64)) == 96

    def test_known_fixture_plan_decodes_correctly(self):
        # Fixture: "DwAAAAAAAAAAAAAA" = 0x0F + 11 zeros → slots 0-3 active (96 slots total)
        result = decode_plan("DwAAAAAAAAAAAAAA")
        assert result[:4] == [True, True, True, True]
        assert result[4:] == [False] * 92


class TestPlanActivePeriods:
    """Unit tests for _plan_active_periods() period formatter."""

    def test_all_off_returns_empty_list(self):
        assert _plan_active_periods([False] * 96) == []

    def test_all_on_returns_full_day(self):
        assert _plan_active_periods([True] * 96) == ["00:00-24:00"]

    def test_slots_0_to_3_gives_00_00_to_01_00(self):
        slots = [True] * 4 + [False] * 92
        assert _plan_active_periods(slots) == ["00:00-01:00"]

    def test_slots_4_to_7_gives_01_00_to_02_00(self):
        slots = [False] * 4 + [True] * 4 + [False] * 88
        assert _plan_active_periods(slots) == ["01:00-02:00"]

    def test_two_separate_periods(self):
        # 00:00-01:00 and 08:00-09:00 (slots 0-3 and slots 32-35)
        slots = [False] * 96
        for i in range(4):
            slots[i] = True
        for i in range(32, 36):
            slots[i] = True
        result = _plan_active_periods(slots)
        assert result == ["00:00-01:00", "08:00-09:00"]

    def test_period_ending_at_midnight(self):
        # Last 4 slots on = 23:00-24:00
        slots = [False] * 92 + [True] * 4
        assert _plan_active_periods(slots) == ["23:00-24:00"]


class TestSwitchScheduleAttribute:
    """The 'schedule' extra attribute must decode plans from coordinator.data."""

    def test_schedule_attribute_present_in_keys(self, coordinator, mock_api):
        attrs = make_switch(coordinator, mock_api, out_index=1).extra_state_attributes
        assert "schedule" in attrs

    def test_filtration_schedule_decoded_from_fixture(self, coordinator, mock_api):
        # Fixture has plan for plan_index=1 (Filtration out=1): slots 0-3 active
        attrs = make_switch(coordinator, mock_api, out_index=1).extra_state_attributes
        assert attrs["schedule"] == ["00:00-01:00"]

    def test_schedule_none_when_no_plan_entry_for_output(self, coordinator, mock_api):
        # out_index=0 (Lighting, plan_index=0) has no entry in fixture plans
        attrs = make_switch(coordinator, mock_api, out_index=0).extra_state_attributes
        assert attrs["schedule"] is None

    def test_schedule_none_for_output_with_no_plan_index(self, coordinator, mock_api):
        # out_index=4 (Heating) maps to plan_index=None → always None
        attrs = make_switch(coordinator, mock_api, out_index=4).extra_state_attributes
        assert attrs["schedule"] is None

    def test_schedule_updates_when_coordinator_data_changes(self, coordinator, mock_api):
        sw = make_switch(coordinator, mock_api, out_index=1)
        # Replace the plan with one where all slots are off
        all_off = base64.b64encode(bytes(12)).decode()
        coordinator.data["plans"] = [{"index": 1, "plan64": all_off}]
        attrs = sw.extra_state_attributes
        assert attrs["schedule"] == []

    def test_schedule_none_when_plans_list_is_empty(self, coordinator, mock_api):
        coordinator.data["plans"] = []
        sw = make_switch(coordinator, mock_api, out_index=1)
        assert sw.extra_state_attributes["schedule"] is None

    def test_schedule_none_when_plan64_is_empty_string(self, coordinator, mock_api):
        coordinator.data["plans"] = [{"index": 1, "plan64": ""}]
        sw = make_switch(coordinator, mock_api, out_index=1)
        assert sw.extra_state_attributes["schedule"] is None


class TestOutPlanIndexMapping:
    """_OUT_PLAN_INDEX must match Jeedom getOutInfo() table."""

    def test_lighting_plan_index(self):
        assert _OUT_PLAN_INDEX[0] == 0

    def test_filtration_plan_index(self):
        assert _OUT_PLAN_INDEX[1] == 1

    def test_ph_corrector_has_no_plan(self):
        assert _OUT_PLAN_INDEX[2] is None

    def test_heating_has_no_plan(self):
        assert _OUT_PLAN_INDEX[4] is None

    def test_flocculant_plan_index_is_4_not_8(self):
        # out index 8 → plan index 4 (non-trivial mapping from Jeedom)
        assert _OUT_PLAN_INDEX[8] == 4

    def test_hybrid_disinfectant_plan_index(self):
        assert _OUT_PLAN_INDEX[15] == 2