"""Unit tests for KlereoAPI.

All HTTP calls are intercepted by the ``requests-mock`` pytest fixture.
No real network traffic is produced.
"""
import hashlib
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
import requests

from klereo.klereo_api import KlereoAPI
from tests.fixtures import (
    SAMPLE_GET_POOL_RESPONSE,
    SAMPLE_INDEX_RESPONSE,
    SAMPLE_JWT_RESPONSE,
    SAMPLE_MAINTENANCE_RESPONSE,
    SAMPLE_SET_OUT_RESPONSE,
    SAMPLE_WAIT_COMMAND_SUCCESS,
    SAMPLE_WAIT_COMMAND_POOL_NOT_CONNECTED,
)

# ── URL constants (match klereo_api.py) ──────────────────────────────────────
JWT_URL = "https://connect.klereo.fr/php/GetJWT.php"
INDEX_URL = "https://connect.klereo.fr/php/GetIndex.php"
POOL_URL = "https://connect.klereo.fr/php/GetPoolDetails.php"
SET_OUT_URL = "https://connect.klereo.fr/php/SetOut.php"
WAIT_CMD_URL = "https://connect.klereo.fr/php/WaitCommand.php"


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def api():
    """A fresh KlereoAPI instance with no JWT cached."""
    return KlereoAPI("user@example.com", "s3cr3t", 12345)


@pytest.fixture
def authed_api(api):
    """KlereoAPI with a pre-seeded JWT — skips the GetJWT call."""
    api.jwt = "test-jwt-token"
    return api


# ── hash_password ─────────────────────────────────────────────────────────────

class TestHashPassword:
    def test_returns_sha1_hex_digest(self, api):
        expected = hashlib.sha1(b"s3cr3t").hexdigest()
        assert api.hash_password() == expected

    def test_different_passwords_produce_different_hashes(self):
        api1 = KlereoAPI("u", "password1", 1)
        api2 = KlereoAPI("u", "password2", 1)
        assert api1.hash_password() != api2.hash_password()

    def test_hash_is_40_hex_chars(self, api):
        h = api.hash_password()
        assert len(h) == 40
        assert all(c in "0123456789abcdef" for c in h)


# ── get_jwt ───────────────────────────────────────────────────────────────────

class TestGetJwt:
    def test_returns_jwt_field_not_token(self, api, requests_mock):
        """Must use the 'jwt' field, not the deprecated 'token' field."""
        requests_mock.post(JWT_URL, json=SAMPLE_JWT_RESPONSE)
        result = api.get_jwt()
        assert result == SAMPLE_JWT_RESPONSE["jwt"]
        assert result != SAMPLE_JWT_RESPONSE["token"]

    def test_stores_jwt_on_instance(self, api, requests_mock):
        requests_mock.post(JWT_URL, json=SAMPLE_JWT_RESPONSE)
        api.get_jwt()
        assert api.jwt == SAMPLE_JWT_RESPONSE["jwt"]

    def test_sends_sha1_password_not_plain_text(self, api, requests_mock):
        """Security: plain-text password must never leave the process."""
        m = requests_mock.post(JWT_URL, json=SAMPLE_JWT_RESPONSE)
        api.get_jwt()
        body = m.last_request.body or ""
        plain = "s3cr3t"
        expected_hash = hashlib.sha1(plain.encode()).hexdigest()
        assert plain not in body, "Plain-text password must never be sent"
        assert expected_hash in body, "SHA-1 hash of password must be in the request"

    def test_sends_ha_version_string(self, api, requests_mock):
        m = requests_mock.post(JWT_URL, json=SAMPLE_JWT_RESPONSE)
        api.get_jwt()
        body = m.last_request.body or ""
        assert "version=100-HA" in body

    def test_raises_config_entry_auth_failed_on_http_error(self, api, requests_mock):
        from homeassistant.exceptions import ConfigEntryAuthFailed
        requests_mock.post(JWT_URL, status_code=500)
        with pytest.raises(ConfigEntryAuthFailed):
            api.get_jwt()

    def test_raises_config_entry_auth_failed_on_bad_credentials(self, api, requests_mock):
        from homeassistant.exceptions import ConfigEntryAuthFailed
        requests_mock.post(JWT_URL, json={"status": "error", "detail": "invalid credentials"})
        with pytest.raises(ConfigEntryAuthFailed):
            api.get_jwt()


# ── get_index ─────────────────────────────────────────────────────────────────

class TestGetIndex:
    def test_returns_list_of_pools(self, authed_api, requests_mock):
        requests_mock.post(INDEX_URL, json=SAMPLE_INDEX_RESPONSE)
        result = authed_api.get_index()
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["idSystem"] == 12345

    def test_authenticates_automatically_when_no_jwt(self, api, requests_mock):
        requests_mock.post(JWT_URL, json=SAMPLE_JWT_RESPONSE)
        requests_mock.post(INDEX_URL, json=SAMPLE_INDEX_RESPONSE)
        api.get_index()
        assert api.jwt == SAMPLE_JWT_RESPONSE["jwt"]

    def test_no_name_error_regression(self, authed_api, requests_mock):
        """Regression: B2 — get_index() previously referenced undefined 'sensors'."""
        requests_mock.post(INDEX_URL, json=SAMPLE_INDEX_RESPONSE)
        # Must not raise NameError
        authed_api.get_index()

    def test_sends_auth_header(self, authed_api, requests_mock):
        m = requests_mock.post(INDEX_URL, json=SAMPLE_INDEX_RESPONSE)
        authed_api.get_index()
        assert m.last_request.headers["Authorization"] == "Bearer test-jwt-token"


# ── get_pool ──────────────────────────────────────────────────────────────────

class TestGetPool:
    def test_returns_pool_dict_with_probes_and_outs(self, authed_api, requests_mock):
        requests_mock.post(POOL_URL, json=SAMPLE_GET_POOL_RESPONSE)
        pool = authed_api.get_pool()
        assert pool["idSystem"] == 12345
        assert "probes" in pool
        assert "outs" in pool

    def test_sends_pool_id_in_payload(self, authed_api, requests_mock):
        m = requests_mock.post(POOL_URL, json=SAMPLE_GET_POOL_RESPONSE)
        authed_api.get_pool()
        body = m.last_request.body or ""
        assert "poolID=12345" in body

    def test_sends_lang_fr(self, authed_api, requests_mock):
        m = requests_mock.post(POOL_URL, json=SAMPLE_GET_POOL_RESPONSE)
        authed_api.get_pool()
        body = m.last_request.body or ""
        assert "lang=fr" in body

    def test_authenticates_automatically_when_no_jwt(self, api, requests_mock):
        requests_mock.post(JWT_URL, json=SAMPLE_JWT_RESPONSE)
        requests_mock.post(POOL_URL, json=SAMPLE_GET_POOL_RESPONSE)
        api.get_pool()
        assert api.jwt == SAMPLE_JWT_RESPONSE["jwt"]

    def test_raises_update_failed_on_http_error(self, authed_api, requests_mock):
        from homeassistant.helpers.update_coordinator import UpdateFailed
        requests_mock.post(POOL_URL, status_code=503)
        with pytest.raises(UpdateFailed):
            authed_api.get_pool()

    def test_raises_config_entry_auth_failed_on_401(self, authed_api, requests_mock):
        from homeassistant.exceptions import ConfigEntryAuthFailed
        requests_mock.post(POOL_URL, status_code=401)
        with pytest.raises(ConfigEntryAuthFailed):
            authed_api.get_pool()


# ── turn_on_device ────────────────────────────────────────────────────────────

class TestTurnOnDevice:
    def test_sends_out_index_and_state_on(self, authed_api, requests_mock):
        m = requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)
        requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.turn_on_device(1)
        body = m.last_request.body or ""
        assert "outIdx=1" in body
        assert "newState=1" in body

    def test_sends_pool_id(self, authed_api, requests_mock):
        m = requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)
        requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.turn_on_device(0)
        body = m.last_request.body or ""
        assert "poolID=12345" in body

    def test_sends_auth_header(self, authed_api, requests_mock):
        m = requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)
        requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.turn_on_device(0)
        assert m.last_request.headers["Authorization"] == "Bearer test-jwt-token"

    def test_raises_update_failed_on_http_error(self, authed_api, requests_mock):
        from homeassistant.helpers.update_coordinator import UpdateFailed
        requests_mock.post(SET_OUT_URL, status_code=500)
        with pytest.raises(UpdateFailed):
            authed_api.turn_on_device(1)

    def test_raises_config_entry_auth_failed_on_401(self, authed_api, requests_mock):
        from homeassistant.exceptions import ConfigEntryAuthFailed
        requests_mock.post(SET_OUT_URL, status_code=401)
        with pytest.raises(ConfigEntryAuthFailed):
            authed_api.turn_on_device(1)


# ── turn_off_device ───────────────────────────────────────────────────────────

class TestTurnOffDevice:
    def test_sends_out_index_and_state_off(self, authed_api, requests_mock):
        m = requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)
        requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.turn_off_device(1)
        body = m.last_request.body or ""
        assert "outIdx=1" in body
        assert "newState=0" in body

    def test_sends_pool_id(self, authed_api, requests_mock):
        m = requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)
        requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.turn_off_device(0)
        body = m.last_request.body or ""
        assert "poolID=12345" in body


# ── JWT auto-refresh on expiry ────────────────────────────────────────────────────────

SAMPLE_JWT_EXPIRED_RESPONSE = {"status": "error", "detail": "jwt expired"}
SAMPLE_JWT_INVALID_RESPONSE = {"status": "error", "detail": "invalid jwt"}


class TestJwtAutoRefresh:
    """When a request returns a JWT-expiry error the API must re-auth and retry."""

    def test_get_pool_retries_after_jwt_expired(self, authed_api, requests_mock):
        """First call returns jwt-expired; second (after re-auth) returns valid data."""
        requests_mock.post(JWT_URL, json=SAMPLE_JWT_RESPONSE)
        pool_mock = requests_mock.post(POOL_URL, [
            {"json": SAMPLE_JWT_EXPIRED_RESPONSE},
            {"json": SAMPLE_GET_POOL_RESPONSE},
        ])
        result = authed_api.get_pool()
        assert result["idSystem"] == 12345
        assert pool_mock.call_count == 2

    def test_get_pool_re_authenticates_on_expiry(self, authed_api, requests_mock):
        jwt_mock = requests_mock.post(JWT_URL, json=SAMPLE_JWT_RESPONSE)
        requests_mock.post(POOL_URL, [
            {"json": SAMPLE_JWT_EXPIRED_RESPONSE},
            {"json": SAMPLE_GET_POOL_RESPONSE},
        ])
        authed_api.get_pool()
        assert jwt_mock.call_count == 1

    def test_turn_on_retries_after_jwt_expired(self, authed_api, requests_mock):
        requests_mock.post(JWT_URL, json=SAMPLE_JWT_RESPONSE)
        set_mock = requests_mock.post(SET_OUT_URL, [
            {"json": SAMPLE_JWT_EXPIRED_RESPONSE},
            {"json": SAMPLE_SET_OUT_RESPONSE},
        ])
        requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.turn_on_device(1)
        assert set_mock.call_count == 2

    def test_raises_update_failed_on_non_auth_api_error(self, authed_api, requests_mock):
        """Non-auth API errors must raise UpdateFailed, not silently swallow."""
        from homeassistant.helpers.update_coordinator import UpdateFailed
        requests_mock.post(POOL_URL, json={"status": "error", "detail": "unknown_pool"})
        with pytest.raises(UpdateFailed):
            authed_api.get_pool()


# ── SetOut payload correctness (newMode=0 Manual, comMode=1) ──────────────────

class TestSetOutPayloadCorrectness:
    """Verify that turn_on and turn_off send newMode=0 (Manual) and comMode=1."""

    def test_turn_on_uses_manual_mode(self, authed_api, requests_mock):
        m = requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)
        requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.turn_on_device(1)
        body = m.last_request.body or ""
        assert "newMode=0" in body, "turn_on must use newMode=0 (Manual), not Timer"

    def test_turn_off_uses_manual_mode(self, authed_api, requests_mock):
        m = requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)
        requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.turn_off_device(1)
        body = m.last_request.body or ""
        assert "newMode=0" in body, "turn_off must use newMode=0 (Manual), not Timer"

    def test_turn_on_sends_com_mode_1(self, authed_api, requests_mock):
        m = requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)
        requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.turn_on_device(1)
        body = m.last_request.body or ""
        assert "comMode=1" in body

    def test_turn_off_sends_com_mode_1(self, authed_api, requests_mock):
        m = requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)
        requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.turn_off_device(1)
        body = m.last_request.body or ""
        assert "comMode=1" in body


# ── Maintenance window detection ──────────────────────────────────────────────

class TestMaintenanceDetection:
    """get_pool must raise UpdateFailed when the server returns a maintenance response."""

    def test_raises_update_failed_on_maintenance(self, authed_api, requests_mock):
        from homeassistant.helpers.update_coordinator import UpdateFailed
        requests_mock.post(POOL_URL, json=SAMPLE_MAINTENANCE_RESPONSE)
        with pytest.raises(UpdateFailed):
            authed_api.get_pool()

    def test_maintenance_detection_does_not_raise_http_error(self, authed_api, requests_mock):
        """Maintenance responses have HTTP 200 — must not be treated as an HTTP error."""
        from homeassistant.helpers.update_coordinator import UpdateFailed
        requests_mock.post(POOL_URL, json=SAMPLE_MAINTENANCE_RESPONSE, status_code=200)
        with pytest.raises(UpdateFailed):
            authed_api.get_pool()


class TestMaintenanceWindowProactive:
    """_is_maintenance_window() and the proactive skip in _post()."""

    # ---- _is_maintenance_window unit tests ----

    def test_sunday_inside_window_returns_true(self):
        # Sunday 02:00 — inside 01:45–04:45
        t = datetime(2026, 4, 19, 2, 0)  # Sunday
        assert KlereoAPI._is_maintenance_window(t) is True

    def test_sunday_before_window_returns_false(self):
        # Sunday 01:44
        t = datetime(2026, 4, 19, 1, 44)
        assert KlereoAPI._is_maintenance_window(t) is False

    def test_sunday_after_window_returns_false(self):
        # Sunday 04:46
        t = datetime(2026, 4, 19, 4, 46)
        assert KlereoAPI._is_maintenance_window(t) is False

    def test_sunday_at_window_start_returns_true(self):
        t = datetime(2026, 4, 19, 1, 45)
        assert KlereoAPI._is_maintenance_window(t) is True

    def test_sunday_at_window_end_returns_true(self):
        t = datetime(2026, 4, 19, 4, 45)
        assert KlereoAPI._is_maintenance_window(t) is True

    def test_tuesday_inside_window_returns_true(self):
        # Tuesday 01:32 — inside 01:30–01:35
        t = datetime(2026, 4, 21, 1, 32)  # Tuesday
        assert KlereoAPI._is_maintenance_window(t) is True

    def test_tuesday_outside_window_returns_false(self):
        t = datetime(2026, 4, 21, 2, 0)
        assert KlereoAPI._is_maintenance_window(t) is False

    def test_monday_no_window_returns_false(self):
        # Monday has no maintenance window
        t = datetime(2026, 4, 20, 1, 32)  # Monday
        assert KlereoAPI._is_maintenance_window(t) is False

    def test_saturday_inside_window_returns_true(self):
        t = datetime(2026, 4, 18, 1, 30)  # Saturday 01:30
        assert KlereoAPI._is_maintenance_window(t) is True

    def test_saturday_outside_window_returns_false(self):
        t = datetime(2026, 4, 18, 1, 36)  # Saturday 01:36
        assert KlereoAPI._is_maintenance_window(t) is False

    # ---- proactive skip in _post() ----

    def test_post_raises_update_failed_during_maintenance_without_http_call(
        self, authed_api, requests_mock
    ):
        """During a maintenance window _post must raise UpdateFailed immediately,
        without sending any HTTP request."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        with patch.object(KlereoAPI, '_is_maintenance_window', return_value=True):
            m = requests_mock.post(POOL_URL, json=SAMPLE_GET_POOL_RESPONSE)
            with pytest.raises(UpdateFailed, match="maintenance"):
                authed_api.get_pool()
            assert m.call_count == 0, "No HTTP request must be made during maintenance"

    def test_post_proceeds_normally_outside_maintenance_window(
        self, authed_api, requests_mock
    ):
        """Outside a maintenance window _post must proceed normally."""
        with patch.object(KlereoAPI, '_is_maintenance_window', return_value=False):
            requests_mock.post(POOL_URL, json=SAMPLE_GET_POOL_RESPONSE)
            result = authed_api.get_pool()
            assert result is not None


# ── B3: Proactive JWT refresh (≥55 minutes) ───────────────────────────────────

class TestJwtProactiveRefresh:
    """B3 — The JWT must be refreshed proactively when ≥55 minutes old,
    before the next API request, not only on server-side rejection.
    """

    def _api_with_old_jwt(self, age_minutes: int) -> KlereoAPI:
        """Return an api instance whose JWT was acquired `age_minutes` ago."""
        api = KlereoAPI("user@example.com", "s3cr3t", 12345)
        api.jwt = "old-jwt-token"
        api.jwt_acquired_at = datetime.now() - timedelta(minutes=age_minutes)
        return api

    def test_no_refresh_when_token_is_fresh(self, requests_mock):
        """A token that is only 10 minutes old must NOT trigger a proactive refresh."""
        api = self._api_with_old_jwt(10)
        jwt_mock = requests_mock.post(JWT_URL, json=SAMPLE_JWT_RESPONSE)
        requests_mock.post(POOL_URL, json=SAMPLE_GET_POOL_RESPONSE)
        api.get_pool()
        assert jwt_mock.call_count == 0, "Fresh token must not be re-acquired"

    def test_no_refresh_when_token_is_54_minutes_old(self, requests_mock):
        """A token that is 54 minutes old is still within the 55-minute window."""
        api = self._api_with_old_jwt(54)
        jwt_mock = requests_mock.post(JWT_URL, json=SAMPLE_JWT_RESPONSE)
        requests_mock.post(POOL_URL, json=SAMPLE_GET_POOL_RESPONSE)
        api.get_pool()
        assert jwt_mock.call_count == 0

    def test_refresh_when_token_is_exactly_55_minutes_old(self, requests_mock):
        """A token that is exactly 55 minutes old must be refreshed proactively."""
        api = self._api_with_old_jwt(55)
        jwt_mock = requests_mock.post(JWT_URL, json=SAMPLE_JWT_RESPONSE)
        requests_mock.post(POOL_URL, json=SAMPLE_GET_POOL_RESPONSE)
        api.get_pool()
        assert jwt_mock.call_count == 1, "Token ≥55 min must trigger proactive refresh"

    def test_refresh_when_token_is_60_minutes_old(self, requests_mock):
        """A token that is 60 minutes old (expired) must be proactively refreshed."""
        api = self._api_with_old_jwt(60)
        jwt_mock = requests_mock.post(JWT_URL, json=SAMPLE_JWT_RESPONSE)
        requests_mock.post(POOL_URL, json=SAMPLE_GET_POOL_RESPONSE)
        api.get_pool()
        assert jwt_mock.call_count == 1

    def test_new_jwt_is_stored_and_used_after_proactive_refresh(self, requests_mock):
        """After proactive refresh the new JWT must be used for the actual request."""
        api = self._api_with_old_jwt(56)
        requests_mock.post(JWT_URL, json=SAMPLE_JWT_RESPONSE)
        pool_mock = requests_mock.post(POOL_URL, json=SAMPLE_GET_POOL_RESPONSE)
        api.get_pool()
        # The pool request must carry the NEW token, not the old one
        assert pool_mock.last_request.headers["Authorization"] == (
            f"Bearer {SAMPLE_JWT_RESPONSE['jwt']}"
        )

    def test_jwt_acquired_at_is_updated_after_proactive_refresh(self, requests_mock):
        """After proactive refresh, jwt_acquired_at must be reset to ~now."""
        api = self._api_with_old_jwt(56)
        requests_mock.post(JWT_URL, json=SAMPLE_JWT_RESPONSE)
        requests_mock.post(POOL_URL, json=SAMPLE_GET_POOL_RESPONSE)
        before = datetime.now()
        api.get_pool()
        after = datetime.now()
        assert api.jwt_acquired_at is not None
        assert before <= api.jwt_acquired_at <= after, (
            "jwt_acquired_at must be updated to the current time after refresh"
        )

    def test_proactive_refresh_does_not_double_refresh_on_fresh_server_response(
        self, requests_mock
    ):
        """When proactive refresh fires, the subsequent successful pool response
        must NOT trigger a second (reactive) re-auth, resulting in exactly 1 JWT call.
        """
        api = self._api_with_old_jwt(56)
        jwt_mock = requests_mock.post(JWT_URL, json=SAMPLE_JWT_RESPONSE)
        requests_mock.post(POOL_URL, json=SAMPLE_GET_POOL_RESPONSE)
        api.get_pool()
        assert jwt_mock.call_count == 1

    def test_get_jwt_sets_jwt_acquired_at(self, requests_mock):
        """Calling get_jwt() directly must record jwt_acquired_at."""
        api = KlereoAPI("user@example.com", "s3cr3t", 12345)
        requests_mock.post(JWT_URL, json=SAMPLE_JWT_RESPONSE)
        before = datetime.now()
        api.get_jwt()
        after = datetime.now()
        assert api.jwt_acquired_at is not None
        assert before <= api.jwt_acquired_at <= after


# ── wait_command ──────────────────────────────────────────────────────────────

class TestWaitCommand:
    def test_returns_success_status_on_code_9(self, authed_api, requests_mock):
        requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        result = authed_api.wait_command(42)
        assert result == 9

    def test_sends_cmd_id_in_payload(self, authed_api, requests_mock):
        m = requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.wait_command(42)
        assert "cmdID=42" in (m.last_request.body or "")

    def test_sends_auth_header(self, authed_api, requests_mock):
        m = requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.wait_command(42)
        assert m.last_request.headers["Authorization"] == "Bearer test-jwt-token"

    def test_raises_home_assistant_error_on_failure_status(self, authed_api, requests_mock):
        """Status 17 (pool not connected) must raise HomeAssistantError."""
        from homeassistant.exceptions import HomeAssistantError
        requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_POOL_NOT_CONNECTED)
        with pytest.raises(HomeAssistantError, match="Pool not connected"):
            authed_api.wait_command(42)

    def test_raises_for_each_known_failure_code(self, authed_api, requests_mock):
        """Every non-9 status code must raise HomeAssistantError."""
        from homeassistant.exceptions import HomeAssistantError
        for code in [10, 11, 12, 13, 15, 16, 17, 18, 19]:
            requests_mock.post(WAIT_CMD_URL, json={"status": "ok", "response": {"status": code, "cmdID": 1}})
            with pytest.raises(HomeAssistantError):
                authed_api.wait_command(1)

    def test_raises_on_http_error(self, authed_api, requests_mock):
        from homeassistant.exceptions import UpdateFailed
        requests_mock.post(WAIT_CMD_URL, status_code=500)
        with pytest.raises(UpdateFailed):
            authed_api.wait_command(42)


# ── turn_on_device / turn_off_device (now with WaitCommand) ──────────────────

class TestTurnOnOffWithWaitCommand:
    def _setup(self, requests_mock, set_out_response=None, wait_response=None):
        requests_mock.post(
            SET_OUT_URL,
            json=set_out_response or SAMPLE_SET_OUT_RESPONSE,
        )
        requests_mock.post(
            WAIT_CMD_URL,
            json=wait_response or SAMPLE_WAIT_COMMAND_SUCCESS,
        )

    def test_turn_on_calls_set_out_then_wait_command(self, authed_api, requests_mock):
        set_out_m = requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)
        wait_m = requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.turn_on_device(0)
        assert set_out_m.call_count == 1
        assert wait_m.call_count == 1

    def test_turn_on_sends_newstate_1(self, authed_api, requests_mock):
        self._setup(requests_mock)
        m = requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)
        requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.turn_on_device(0)
        assert "newState=1" in (m.last_request.body or "")

    def test_turn_off_sends_newstate_0(self, authed_api, requests_mock):
        self._setup(requests_mock)
        m = requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)
        requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.turn_off_device(0)
        assert "newState=0" in (m.last_request.body or "")

    def test_turn_on_sends_cmd_id_to_wait_command(self, authed_api, requests_mock):
        """The cmdID returned by SetOut must be forwarded to WaitCommand."""
        requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)  # cmdID=42
        wait_m = requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_SUCCESS)
        authed_api.turn_on_device(0)
        assert "cmdID=42" in (wait_m.last_request.body or "")

    def test_turn_on_raises_if_pool_not_connected(self, authed_api, requests_mock):
        """If WaitCommand returns code 17, HomeAssistantError must bubble up."""
        from homeassistant.exceptions import HomeAssistantError
        requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)
        requests_mock.post(WAIT_CMD_URL, json=SAMPLE_WAIT_COMMAND_POOL_NOT_CONNECTED)
        with pytest.raises(HomeAssistantError, match="Pool not connected"):
            authed_api.turn_on_device(0)

    def test_turn_off_raises_if_command_fails(self, authed_api, requests_mock):
        from homeassistant.exceptions import HomeAssistantError
        fail_resp = {"status": "ok", "response": {"status": 10, "cmdID": 42}}  # 10=failed
        requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)
        requests_mock.post(WAIT_CMD_URL, json=fail_resp)
        with pytest.raises(HomeAssistantError):
            authed_api.turn_off_device(0)
