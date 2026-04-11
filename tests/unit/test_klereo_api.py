"""Unit tests for KlereoAPI.

All HTTP calls are intercepted by the ``requests-mock`` pytest fixture.
No real network traffic is produced.
"""
import hashlib

import pytest
import requests

from KlereoHACS.klereo_api import KlereoAPI
from tests.fixtures import (
    SAMPLE_GET_POOL_RESPONSE,
    SAMPLE_INDEX_RESPONSE,
    SAMPLE_JWT_RESPONSE,
    SAMPLE_MAINTENANCE_RESPONSE,
    SAMPLE_SET_OUT_RESPONSE,
)

# ── URL constants (match klereo_api.py) ──────────────────────────────────────
JWT_URL = "https://connect.klereo.fr/php/GetJWT.php"
INDEX_URL = "https://connect.klereo.fr/php/GetIndex.php"
POOL_URL = "https://connect.klereo.fr/php/GetPoolDetails.php"
SET_OUT_URL = "https://connect.klereo.fr/php/SetOut.php"


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

    def test_raises_on_http_error(self, api, requests_mock):
        requests_mock.post(JWT_URL, status_code=500)
        with pytest.raises(requests.HTTPError):
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

    def test_raises_on_http_error(self, authed_api, requests_mock):
        requests_mock.post(POOL_URL, status_code=503)
        with pytest.raises(requests.HTTPError):
            authed_api.get_pool()


# ── turn_on_device ────────────────────────────────────────────────────────────

class TestTurnOnDevice:
    def test_sends_out_index_and_state_on(self, authed_api, requests_mock):
        m = requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)
        authed_api.turn_on_device(1)
        body = m.last_request.body or ""
        assert "outIdx=1" in body
        assert "newState=1" in body

    def test_sends_pool_id(self, authed_api, requests_mock):
        m = requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)
        authed_api.turn_on_device(0)
        body = m.last_request.body or ""
        assert "poolID=12345" in body

    def test_sends_auth_header(self, authed_api, requests_mock):
        m = requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)
        authed_api.turn_on_device(0)
        assert m.last_request.headers["Authorization"] == "Bearer test-jwt-token"

    def test_raises_on_http_error(self, authed_api, requests_mock):
        requests_mock.post(SET_OUT_URL, status_code=500)
        with pytest.raises(requests.HTTPError):
            authed_api.turn_on_device(1)


# ── turn_off_device ───────────────────────────────────────────────────────────

class TestTurnOffDevice:
    def test_sends_out_index_and_state_off(self, authed_api, requests_mock):
        m = requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)
        authed_api.turn_off_device(1)
        body = m.last_request.body or ""
        assert "outIdx=1" in body
        assert "newState=0" in body

    def test_sends_pool_id(self, authed_api, requests_mock):
        m = requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)
        authed_api.turn_off_device(0)
        body = m.last_request.body or ""
        assert "poolID=12345" in body


# ── SetOut payload correctness (newMode=0 Manual, comMode=1) ──────────────────

class TestSetOutPayloadCorrectness:
    """Verify that turn_on and turn_off send newMode=0 (Manual) and comMode=1."""

    def test_turn_on_uses_manual_mode(self, authed_api, requests_mock):
        m = requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)
        authed_api.turn_on_device(1)
        body = m.last_request.body or ""
        assert "newMode=0" in body, "turn_on must use newMode=0 (Manual), not Timer"

    def test_turn_off_uses_manual_mode(self, authed_api, requests_mock):
        m = requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)
        authed_api.turn_off_device(1)
        body = m.last_request.body or ""
        assert "newMode=0" in body, "turn_off must use newMode=0 (Manual), not Timer"

    def test_turn_on_sends_com_mode_1(self, authed_api, requests_mock):
        m = requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)
        authed_api.turn_on_device(1)
        body = m.last_request.body or ""
        assert "comMode=1" in body

    def test_turn_off_sends_com_mode_1(self, authed_api, requests_mock):
        m = requests_mock.post(SET_OUT_URL, json=SAMPLE_SET_OUT_RESPONSE)
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

