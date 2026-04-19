"""Unit tests for the number platform — regulation setpoint entities.

Coverage
--------
* ``KlereoAPI.set_param`` — correct payload, auth header, error handling
* ``KlereoSetpointNumber`` — state reads, min/max bounds, unique_id, write,
  disabled setpoint filtering, access-level filtering, extra_state_attributes
"""

from __future__ import annotations

import copy
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock

from klereo.klereo_api import KlereoAPI
from tests.fixtures import (
    SAMPLE_POOL_DATA,
    SAMPLE_SET_PARAM_RESPONSE,
    SAMPLE_SET_AUTO_OFF_RESPONSE,
    SAMPLE_WAIT_COMMAND_SUCCESS,
)

DOMAIN = "klereo"

# ---------------------------------------------------------------------------
# Constants shared with the real code
# ---------------------------------------------------------------------------
BASE_URL   = "https://connect.klereo.fr/php"
SET_PARAM_URL  = f"{BASE_URL}/SetParam.php"
SET_AUTO_OFF_URL = f"{BASE_URL}/SetAutoOff.php"
WAIT_CMD_URL   = f"{BASE_URL}/WaitCommand.php"

POOL_ID = SAMPLE_POOL_DATA["idSystem"]   # 12345


# ===========================================================================
# Helpers
# ===========================================================================

def _make_authed_api():
    """Return a KlereoAPI instance that already has a JWT."""
    from datetime import datetime
    api = KlereoAPI("user@example.com", "password", POOL_ID)
    api.jwt = "test-jwt-token"
    api.jwt_acquired_at = datetime.now()
    return api


def _make_coordinator(pool_data=None):
    """Return a minimal coordinator mock whose .data mirrors pool_data."""
    data = copy.deepcopy(pool_data or SAMPLE_POOL_DATA)
    coord = MagicMock()
    coord.data = data
    coord.async_request_refresh = AsyncMock()
    return coord


# ===========================================================================
# TestSetParam — KlereoAPI.set_param()
# ===========================================================================

class TestSetParam:
    """Tests for the KlereoAPI.set_param() method."""

    @pytest.fixture
    def authed_api(self):
        return _make_authed_api()

    def test_sends_correct_param_id(self, authed_api, requests_mock):
        requests_mock.post(SET_PARAM_URL, json=SAMPLE_SET_PARAM_RESPONSE)
        requests_mock.post(WAIT_CMD_URL,  json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.set_param("ConsigneEau", 28.0)
        body = requests_mock.last_request.body or ""
        # last request is WaitCommand — check SetParam instead
        history = requests_mock.request_history
        set_param_req = next(r for r in history if "SetParam" in r.url)
        assert "paramID=ConsigneEau" in set_param_req.body

    def test_sends_correct_value(self, authed_api, requests_mock):
        requests_mock.post(SET_PARAM_URL, json=SAMPLE_SET_PARAM_RESPONSE)
        requests_mock.post(WAIT_CMD_URL,  json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.set_param("ConsignePH", 7.4)
        history = requests_mock.request_history
        set_param_req = next(r for r in history if "SetParam" in r.url)
        assert "newValue=7.4" in set_param_req.body

    def test_sends_pool_id(self, authed_api, requests_mock):
        requests_mock.post(SET_PARAM_URL, json=SAMPLE_SET_PARAM_RESPONSE)
        requests_mock.post(WAIT_CMD_URL,  json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.set_param("ConsigneEau", 28.0)
        history = requests_mock.request_history
        set_param_req = next(r for r in history if "SetParam" in r.url)
        assert f"poolID={POOL_ID}" in set_param_req.body

    def test_sends_com_mode_1(self, authed_api, requests_mock):
        requests_mock.post(SET_PARAM_URL, json=SAMPLE_SET_PARAM_RESPONSE)
        requests_mock.post(WAIT_CMD_URL,  json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.set_param("ConsigneEau", 28.0)
        history = requests_mock.request_history
        set_param_req = next(r for r in history if "SetParam" in r.url)
        assert "comMode=1" in set_param_req.body

    def test_sends_auth_header(self, authed_api, requests_mock):
        requests_mock.post(SET_PARAM_URL, json=SAMPLE_SET_PARAM_RESPONSE)
        requests_mock.post(WAIT_CMD_URL,  json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.set_param("ConsigneEau", 28.0)
        history = requests_mock.request_history
        set_param_req = next(r for r in history if "SetParam" in r.url)
        assert set_param_req.headers["Authorization"] == "Bearer test-jwt-token"

    def test_calls_wait_command_with_cmd_id(self, authed_api, requests_mock):
        requests_mock.post(SET_PARAM_URL, json=SAMPLE_SET_PARAM_RESPONSE)
        m = requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.set_param("ConsigneEau", 28.0)
        assert m.called
        assert "cmdID=77" in m.last_request.body

    def test_raises_home_assistant_error_on_api_error(self, authed_api, requests_mock):
        from homeassistant.exceptions import HomeAssistantError
        requests_mock.post(SET_PARAM_URL, json={"status": "error", "detail": "bad param"})
        with pytest.raises(HomeAssistantError, match="SetParam failed"):
            authed_api.set_param("ConsigneEau", 28.0)

    def test_raises_on_http_error(self, authed_api, requests_mock):
        import requests
        requests_mock.post(SET_PARAM_URL, status_code=500)
        from homeassistant.helpers.update_coordinator import UpdateFailed
        with pytest.raises(UpdateFailed):
            authed_api.set_param("ConsigneEau", 28.0)


# ===========================================================================
# TestKlereoSetpointNumber — entity behaviour
# ===========================================================================

class TestKlereoSetpointNumber:
    """Tests for the KlereoSetpointNumber entity class."""

    def _make_entity(self, pool_data=None, param_id="ConsigneEau"):
        from klereo.number import KlereoSetpointNumber, _SETPOINTS
        coord = _make_coordinator(pool_data)
        api   = MagicMock()
        cfg   = next(c for c in _SETPOINTS if c.param_id == param_id)
        return KlereoSetpointNumber(coord, api, POOL_ID, cfg), coord, api

    # -- native_value --

    def test_native_value_returns_param_value(self):
        entity, _, _ = self._make_entity()
        assert entity.native_value == 28.0  # ConsigneEau in SAMPLE_POOL_DATA

    def test_native_value_reads_from_coordinator_not_cache(self):
        entity, coord, _ = self._make_entity()
        coord.data["params"]["ConsigneEau"] = 30.0
        assert entity.native_value == 30.0

    def test_native_value_returns_none_for_disabled(self):
        data = copy.deepcopy(SAMPLE_POOL_DATA)
        data["params"]["ConsignePH"] = -2000
        entity, _, _ = self._make_entity(data, "ConsignePH")
        assert entity.native_value is None

    def test_native_value_returns_none_for_unknown(self):
        data = copy.deepcopy(SAMPLE_POOL_DATA)
        data["params"]["ConsignePH"] = -1000
        entity, _, _ = self._make_entity(data, "ConsignePH")
        assert entity.native_value is None

    # -- bounds --

    def test_native_min_value_from_params(self):
        entity, _, _ = self._make_entity()   # ConsigneEau, EauMin=10.0
        assert entity.native_min_value == 10.0

    def test_native_max_value_from_params(self):
        entity, _, _ = self._make_entity()   # ConsigneEau, EauMax=40.0
        assert entity.native_max_value == 40.0

    def test_bounds_update_when_coordinator_data_changes(self):
        entity, coord, _ = self._make_entity()
        coord.data["params"]["EauMin"] = 15.0
        coord.data["params"]["EauMax"] = 35.0
        assert entity.native_min_value == 15.0
        assert entity.native_max_value == 35.0

    def test_ph_bounds(self):
        entity, _, _ = self._make_entity(param_id="ConsignePH")
        assert entity.native_min_value == 6.8   # pHMin
        assert entity.native_max_value == 7.8   # pHMax

    def test_redox_bounds(self):
        entity, _, _ = self._make_entity(param_id="ConsigneRedox")
        assert entity.native_min_value == 600.0  # OrpMin
        assert entity.native_max_value == 900.0  # OrpMax

    def test_chlorine_uses_default_bounds_when_params_absent(self):
        entity, coord, _ = self._make_entity(param_id="ConsigneChlore")
        # ConsigneChlore has no min/max params — should use defaults (0, 100)
        assert entity.native_min_value == 0.0
        assert entity.native_max_value == 100.0

    # -- unique_id --

    def test_unique_id_eau(self):
        entity, _, _ = self._make_entity(param_id="ConsigneEau")
        assert entity.unique_id == f"id_klereo{POOL_ID}_setpoint_consigneeau"

    def test_unique_id_ph(self):
        entity, _, _ = self._make_entity(param_id="ConsignePH")
        assert entity.unique_id == f"id_klereo{POOL_ID}_setpoint_consigneph"

    def test_unique_id_redox(self):
        entity, _, _ = self._make_entity(param_id="ConsigneRedox")
        assert entity.unique_id == f"id_klereo{POOL_ID}_setpoint_consigneredox"

    def test_unique_id_chlorine(self):
        entity, _, _ = self._make_entity(param_id="ConsigneChlore")
        assert entity.unique_id == f"id_klereo{POOL_ID}_setpoint_consignechlore"

    # -- device_class and unit --

    def test_eau_device_class_and_unit(self):
        entity, _, _ = self._make_entity(param_id="ConsigneEau")
        assert entity._attr_device_class == "temperature"
        assert entity._attr_native_unit_of_measurement == "°C"

    def test_ph_device_class_and_unit(self):
        entity, _, _ = self._make_entity(param_id="ConsignePH")
        assert entity._attr_device_class is None
        assert entity._attr_native_unit_of_measurement is None

    def test_redox_device_class_and_unit(self):
        entity, _, _ = self._make_entity(param_id="ConsigneRedox")
        assert entity._attr_device_class == "voltage"
        assert entity._attr_native_unit_of_measurement == "mV"

    def test_chlorine_unit(self):
        entity, _, _ = self._make_entity(param_id="ConsigneChlore")
        assert entity._attr_native_unit_of_measurement == "mg/L"

    # -- step --

    def test_eau_step(self):
        entity, _, _ = self._make_entity(param_id="ConsigneEau")
        assert entity._attr_native_step == 0.5

    def test_ph_step(self):
        entity, _, _ = self._make_entity(param_id="ConsignePH")
        assert entity._attr_native_step == pytest.approx(0.1)

    def test_redox_step(self):
        entity, _, _ = self._make_entity(param_id="ConsigneRedox")
        assert entity._attr_native_step == 1

    # -- write (async_set_native_value) --

    def test_async_set_native_value_calls_set_param(self):
        entity, coord, api = self._make_entity(param_id="ConsigneEau")
        api.set_param = MagicMock()
        entity.hass = MagicMock()
        entity.hass.async_add_executor_job = AsyncMock(return_value=None)
        asyncio.get_event_loop().run_until_complete(entity.async_set_native_value(30.0))
        entity.hass.async_add_executor_job.assert_called_once_with(
            api.set_param, "ConsigneEau", 30.0
        )

    def test_async_set_native_value_requests_coordinator_refresh(self):
        entity, coord, api = self._make_entity(param_id="ConsignePH")
        entity.hass = MagicMock()
        entity.hass.async_add_executor_job = AsyncMock(return_value=None)
        asyncio.get_event_loop().run_until_complete(entity.async_set_native_value(7.4))
        coord.async_request_refresh.assert_called_once()

    # -- extra_state_attributes --

    def test_extra_state_attributes_contains_param_id(self):
        entity, _, _ = self._make_entity(param_id="ConsigneEau")
        attrs = entity.extra_state_attributes
        assert attrs["param_id"] == "ConsigneEau"

    def test_extra_state_attributes_contains_bounds_for_eau(self):
        entity, _, _ = self._make_entity(param_id="ConsigneEau")
        attrs = entity.extra_state_attributes
        assert attrs["min_bound"] == 10.0
        assert attrs["max_bound"] == 40.0

    def test_extra_state_attributes_no_bounds_for_chlorine(self):
        entity, _, _ = self._make_entity(param_id="ConsigneChlore")
        attrs = entity.extra_state_attributes
        assert "min_bound" not in attrs
        assert "max_bound" not in attrs


# ===========================================================================
# TestSetpointFiltering — async_setup_entry skips disabled / access-restricted
# ===========================================================================

class TestSetpointFiltering:

    def _run_setup(self, pool_data):
        """Run async_setup_entry synchronously and return the registered entities."""
        from klereo.number import async_setup_entry

        api = _make_authed_api()
        coord = _make_coordinator(pool_data)

        hass = MagicMock()
        hass.data = {DOMAIN: {"entry_id": {"coordinator": coord, "api": api}}}

        config_entry = MagicMock()
        config_entry.entry_id = "entry_id"

        registered: list = []

        def add_entities(entities):
            registered.extend(entities)

        asyncio.get_event_loop().run_until_complete(
            async_setup_entry(hass, config_entry, add_entities)
        )
        from klereo.number import KlereoSetpointNumber
        return [e for e in registered if isinstance(e, KlereoSetpointNumber)]

    def test_disabled_setpoint_is_not_registered(self):
        data = copy.deepcopy(SAMPLE_POOL_DATA)
        data["params"]["ConsigneEau"] = -2000   # disabled
        entities = self._run_setup(data)
        names = [e._cfg.param_id for e in entities]
        assert "ConsigneEau" not in names

    def test_enabled_setpoints_are_registered(self):
        # SAMPLE_POOL_DATA has access=10, HeaterMode=1, pHMode=1
        # → ConsigneEau registered (access>=10, HeaterMode=1 OK)
        # → ConsignePH/Redox/Chlore NOT registered (access<16 or disabled)
        entities = self._run_setup(SAMPLE_POOL_DATA)
        names = [e._cfg.param_id for e in entities]
        assert "ConsigneEau"    in names
        assert "ConsignePH"     not in names   # access=10 < 16
        assert "ConsigneRedox"  not in names   # access=10 < 16
        assert "ConsigneChlore" not in names   # -2000 → disabled

    def test_access_restricted_setpoints_are_skipped(self):
        data = copy.deepcopy(SAMPLE_POOL_DATA)
        data["access"] = 10   # end-user: only ConsigneEau is allowed (min_access=10)
        entities = self._run_setup(data)
        names = [e._cfg.param_id for e in entities]
        assert "ConsigneEau" in names
        assert "ConsignePH"    not in names   # requires access >= 16
        assert "ConsigneRedox" not in names   # requires access >= 16
        assert "ConsigneChlore" not in names  # requires access >= 16

    def test_advanced_access_unlocks_ph_redox(self):
        data = copy.deepcopy(SAMPLE_POOL_DATA)
        data["access"] = 16
        entities = self._run_setup(data)
        names = [e._cfg.param_id for e in entities]
        assert "ConsignePH"    in names
        assert "ConsigneRedox" in names

    def test_consigne_eau_skipped_when_no_heater(self):
        """HeaterMode=0 (no heater) — ConsigneEau must not be registered."""
        data = copy.deepcopy(SAMPLE_POOL_DATA)
        data["params"]["HeaterMode"] = 0
        entities = self._run_setup(data)
        names = [e._cfg.param_id for e in entities]
        assert "ConsigneEau" not in names

    def test_consigne_eau_skipped_for_heater_mode_3(self):
        """HeaterMode=3 (ON/OFF no setpoint) — ConsigneEau must not be registered."""
        data = copy.deepcopy(SAMPLE_POOL_DATA)
        data["params"]["HeaterMode"] = 3
        entities = self._run_setup(data)
        names = [e._cfg.param_id for e in entities]
        assert "ConsigneEau" not in names

    def test_consigne_eau_registered_for_heat_pump(self):
        """HeaterMode=1 (ON/OFF heat pump) — ConsigneEau should be registered."""
        data = copy.deepcopy(SAMPLE_POOL_DATA)
        data["access"] = 10
        data["params"]["HeaterMode"] = 1
        entities = self._run_setup(data)
        names = [e._cfg.param_id for e in entities]
        assert "ConsigneEau" in names

    def test_consigne_ph_skipped_when_no_ph_corrector(self):
        """pHMode=0 (no pH corrector) — ConsignePH must not be registered."""
        data = copy.deepcopy(SAMPLE_POOL_DATA)
        data["access"] = 16
        data["params"]["pHMode"] = 0
        entities = self._run_setup(data)
        names = [e._cfg.param_id for e in entities]
        assert "ConsignePH" not in names

    def test_consigne_ph_registered_when_ph_corrector_present(self):
        """pHMode=1 (pH-Minus) — ConsignePH should be registered at access>=16."""
        data = copy.deepcopy(SAMPLE_POOL_DATA)
        data["access"] = 16
        data["params"]["pHMode"] = 1
        entities = self._run_setup(data)
        names = [e._cfg.param_id for e in entities]
        assert "ConsignePH" in names


# ===========================================================================
# TestSetAutoOff — KlereoAPI.set_auto_off()
# ===========================================================================

class TestSetAutoOff:
    """Tests for the KlereoAPI.set_auto_off() method."""

    @pytest.fixture
    def authed_api(self):
        return _make_authed_api()

    def test_sends_out_idx(self, authed_api, requests_mock):
        requests_mock.post(SET_AUTO_OFF_URL, json=SAMPLE_SET_AUTO_OFF_RESPONSE)
        requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.set_auto_off(5, 60)
        history = requests_mock.request_history
        req = next(r for r in history if "SetAutoOff" in r.url)
        assert "outIdx=5" in req.body

    def test_sends_off_delay(self, authed_api, requests_mock):
        requests_mock.post(SET_AUTO_OFF_URL, json=SAMPLE_SET_AUTO_OFF_RESPONSE)
        requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.set_auto_off(0, 30)
        history = requests_mock.request_history
        req = next(r for r in history if "SetAutoOff" in r.url)
        assert "offDelay=30" in req.body

    def test_sends_pool_id(self, authed_api, requests_mock):
        requests_mock.post(SET_AUTO_OFF_URL, json=SAMPLE_SET_AUTO_OFF_RESPONSE)
        requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.set_auto_off(5, 60)
        history = requests_mock.request_history
        req = next(r for r in history if "SetAutoOff" in r.url)
        assert f"poolID={POOL_ID}" in req.body

    def test_sends_com_mode_1(self, authed_api, requests_mock):
        requests_mock.post(SET_AUTO_OFF_URL, json=SAMPLE_SET_AUTO_OFF_RESPONSE)
        requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.set_auto_off(5, 60)
        history = requests_mock.request_history
        req = next(r for r in history if "SetAutoOff" in r.url)
        assert "comMode=1" in req.body

    def test_sends_auth_header(self, authed_api, requests_mock):
        requests_mock.post(SET_AUTO_OFF_URL, json=SAMPLE_SET_AUTO_OFF_RESPONSE)
        requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.set_auto_off(5, 60)
        history = requests_mock.request_history
        req = next(r for r in history if "SetAutoOff" in r.url)
        assert req.headers["Authorization"] == "Bearer test-jwt-token"

    def test_calls_wait_command_with_cmd_id(self, authed_api, requests_mock):
        requests_mock.post(SET_AUTO_OFF_URL, json=SAMPLE_SET_AUTO_OFF_RESPONSE)
        m = requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.set_auto_off(5, 60)
        # cmdID in SAMPLE_SET_AUTO_OFF_RESPONSE is 88
        assert "cmdID=88" in m.last_request.body

    def test_raises_home_assistant_error_on_api_error(self, authed_api, requests_mock):
        from homeassistant.exceptions import HomeAssistantError
        requests_mock.post(SET_AUTO_OFF_URL, json={"status": "error", "detail": "bad outIdx"})
        requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        with pytest.raises(HomeAssistantError):
            authed_api.set_auto_off(99, 60)

    def test_raises_on_http_error(self, authed_api, requests_mock):
        from homeassistant.helpers.update_coordinator import UpdateFailed
        requests_mock.post(SET_AUTO_OFF_URL, status_code=500)
        with pytest.raises(UpdateFailed):
            authed_api.set_auto_off(5, 60)


# ===========================================================================
# TestKlereoTimerDelayNumber — entity behaviour
# ===========================================================================

def _make_timer_entity(pool_data=None, out_index=0):
    """Return a KlereoTimerDelayNumber for the given out_index."""
    from klereo.number import KlereoTimerDelayNumber
    coord = _make_coordinator(pool_data or SAMPLE_POOL_DATA)
    api = _make_authed_api()
    return KlereoTimerDelayNumber(coord, api, POOL_ID, out_index)


class TestKlereoTimerDelayNumber:

    def test_native_value_from_out(self):
        entity = _make_timer_entity(out_index=0)
        # SAMPLE_POOL_DATA out index 0 has offDelay=30
        assert entity.native_value == 30

    def test_native_value_reads_from_coordinator_not_cache(self):
        entity = _make_timer_entity(out_index=0)
        entity.coordinator.data["outs"][0]["offDelay"] = 120
        assert entity.native_value == 120

    def test_native_value_returns_none_when_offdelay_is_none(self):
        entity = _make_timer_entity(out_index=1)
        # out index 1 (Filtration) has offDelay=None in fixture
        assert entity.native_value is None

    def test_native_value_returns_none_when_out_missing(self):
        entity = _make_timer_entity(out_index=9)
        # out index 9 not in fixture
        assert entity.native_value is None

    def test_native_min_value(self):
        entity = _make_timer_entity(out_index=0)
        assert entity.native_min_value == 1

    def test_native_max_value(self):
        entity = _make_timer_entity(out_index=0)
        assert entity.native_max_value == 600

    def test_native_step(self):
        entity = _make_timer_entity(out_index=0)
        assert entity.native_step == 1

    def test_unit_of_measurement(self):
        entity = _make_timer_entity(out_index=0)
        assert entity._attr_native_unit_of_measurement == "min"

    def test_unique_id_format(self):
        entity = _make_timer_entity(out_index=5)
        assert entity.unique_id == f"id_klereo{POOL_ID}_offdelay_5"

    def test_unique_ids_different_per_out(self):
        e0 = _make_timer_entity(out_index=0)
        e5 = _make_timer_entity(out_index=5)
        assert e0.unique_id != e5.unique_id

    def test_device_info_identifiers(self):
        entity = _make_timer_entity(out_index=0)
        assert (DOMAIN, POOL_ID) in entity._attr_device_info.identifiers

    def test_extra_state_attributes_contains_out_index(self):
        entity = _make_timer_entity(out_index=5)
        assert entity.extra_state_attributes["out_index"] == 5

    def test_async_set_native_value_calls_set_auto_off(self):
        entity = _make_timer_entity(out_index=5)
        called_with = {}

        def fake_set_auto_off(idx, delay):
            called_with["idx"] = idx
            called_with["delay"] = delay

        entity._api.set_auto_off = fake_set_auto_off
        entity.hass = MagicMock()
        entity.hass.async_add_executor_job = AsyncMock(return_value=None)
        asyncio.get_event_loop().run_until_complete(
            entity.async_set_native_value(45.0)
        )
        entity.hass.async_add_executor_job.assert_called_once_with(
            entity._api.set_auto_off, 5, 45
        )

    def test_async_set_native_value_requests_coordinator_refresh(self):
        entity = _make_timer_entity(out_index=5)
        entity.hass = MagicMock()
        entity.hass.async_add_executor_job = AsyncMock(return_value=None)
        asyncio.get_event_loop().run_until_complete(
            entity.async_set_native_value(45.0)
        )
        entity.coordinator.async_request_refresh.assert_awaited_once()


# ===========================================================================
# TestTimerDelayFiltering — async_setup_entry filtering
# ===========================================================================

class TestTimerDelayFiltering:

    def _run_setup(self, pool_data):
        """Run async_setup_entry and return only KlereoTimerDelayNumber instances."""
        from klereo.number import async_setup_entry, KlereoTimerDelayNumber

        api = _make_authed_api()
        coord = _make_coordinator(pool_data)

        hass = MagicMock()
        hass.data = {DOMAIN: {"entry_id": {"coordinator": coord, "api": api}}}
        config_entry = MagicMock()
        config_entry.entry_id = "entry_id"

        registered: list = []
        asyncio.get_event_loop().run_until_complete(
            async_setup_entry(hass, config_entry, lambda e: registered.extend(e))
        )
        return [e for e in registered if isinstance(e, KlereoTimerDelayNumber)]

    def test_lighting_out_gets_timer_delay_entity(self):
        entities = self._run_setup(SAMPLE_POOL_DATA)
        indices = [e._out_index for e in entities]
        assert 0 in indices   # Lighting (index 0) is timer-capable

    def test_aux1_out_gets_timer_delay_entity(self):
        entities = self._run_setup(SAMPLE_POOL_DATA)
        indices = [e._out_index for e in entities]
        assert 5 in indices   # Auxiliary 1 (index 5) is timer-capable

    def test_filtration_out_does_not_get_timer_delay(self):
        entities = self._run_setup(SAMPLE_POOL_DATA)
        indices = [e._out_index for e in entities]
        assert 1 not in indices   # Filtration is excluded

    def test_heating_out_does_not_get_timer_delay(self):
        entities = self._run_setup(SAMPLE_POOL_DATA)
        indices = [e._out_index for e in entities]
        assert 4 not in indices   # Heating is excluded

    def test_null_type_out_does_not_get_timer_delay(self):
        data = copy.deepcopy(SAMPLE_POOL_DATA)
        # Add an unwired output at index 6
        data["outs"].append({"index": 6, "type": None, "mode": 0, "status": 0,
                              "realStatus": 0, "offDelay": None, "updateTime": 0})
        entities = self._run_setup(data)
        indices = [e._out_index for e in entities]
        assert 6 not in indices   # type=None means unconnected

    def test_wired_timer_capable_outs_count(self):
        entities = self._run_setup(SAMPLE_POOL_DATA)
        # fixture has out 0 (Lighting) and out 5 (Aux1) — both timer-capable
        assert len(entities) == 2
