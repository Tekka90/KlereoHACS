"""Unit tests for KlereoConfigFlow.

Tests cover the two-step flow:
  step 1 (user)  — username + password → GetJWT + GetIndex
  step 2 (pool)  — dropdown selection → config entry created

All async executor calls are intercepted via unittest.mock so no real HTTP is needed.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from klereo.config_flow import KlereoConfigFlow, InvalidAuth
from klereo.const import CONF_USERNAME, CONF_PASSWORD, CONF_POOLID


# ── Helpers ───────────────────────────────────────────────────────────────────

SAMPLE_POOLS = [
    {"idSystem": 12345, "poolNickname": "Ma piscine"},
    {"idSystem": 67890, "poolNickname": "La piscine du jardin"},
]


def _make_flow(pools=None, auth_fails=False):
    """Return a KlereoConfigFlow with hass stubbed out.

    If auth_fails=True, async_add_executor_job raises on the get_jwt call.
    Otherwise get_jwt returns a JWT string and get_index returns `pools`.
    """
    flow = KlereoConfigFlow()

    async def fake_executor(fn, *args, **kwargs):
        # Identify which API method is being called by its __name__
        name = getattr(fn, "__name__", "")
        if name == "get_jwt":
            if auth_fails:
                raise Exception("401 Unauthorized")
            return "fake-jwt"
        if name == "get_index":
            return pools if pools is not None else SAMPLE_POOLS
        return None

    hass = MagicMock()
    hass.async_add_executor_job = fake_executor
    flow.hass = hass

    # Stub config-flow helpers so we can inspect what they return
    flow.async_show_form = lambda **kw: {"type": "form", **kw}
    flow.async_create_entry = lambda title, data: {"type": "create_entry", "title": title, "data": data}
    return flow


# ── Step 1 (user) ─────────────────────────────────────────────────────────────

class TestAsyncStepUser:
    @pytest.mark.asyncio
    async def test_shows_form_on_first_call(self):
        flow = _make_flow()
        result = await flow.async_step_user(user_input=None)
        assert result["type"] == "form"
        assert result["step_id"] == "user"

    @pytest.mark.asyncio
    async def test_valid_credentials_advance_to_pool_step(self):
        flow = _make_flow()
        result = await flow.async_step_user(
            user_input={CONF_USERNAME: "user@example.com", CONF_PASSWORD: "s3cr3t"}
        )
        # Should move straight to step_pool (which returns a form, no user input yet)
        assert result["type"] == "form"
        assert result["step_id"] == "pool"

    @pytest.mark.asyncio
    async def test_invalid_auth_shows_error(self):
        flow = _make_flow(auth_fails=True)
        result = await flow.async_step_user(
            user_input={CONF_USERNAME: "bad", CONF_PASSWORD: "wrong"}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "user"
        assert result["errors"]["base"] == "invalid_auth"

    @pytest.mark.asyncio
    async def test_username_and_password_stored_in_flow(self):
        flow = _make_flow()
        await flow.async_step_user(
            user_input={CONF_USERNAME: "user@example.com", CONF_PASSWORD: "s3cr3t"}
        )
        assert flow._username == "user@example.com"
        assert flow._password == "s3cr3t"

    @pytest.mark.asyncio
    async def test_pool_options_populated_from_get_index(self):
        flow = _make_flow(pools=SAMPLE_POOLS)
        await flow.async_step_user(
            user_input={CONF_USERNAME: "u", CONF_PASSWORD: "p"}
        )
        assert "12345" in flow._pool_options
        assert "67890" in flow._pool_options
        assert flow._pool_options["12345"] == "Ma piscine (12345)"

    @pytest.mark.asyncio
    async def test_empty_pool_list_raises_invalid_auth(self):
        flow = _make_flow(pools=[])
        result = await flow.async_step_user(
            user_input={CONF_USERNAME: "u", CONF_PASSWORD: "p"}
        )
        assert result["errors"]["base"] == "invalid_auth"


# ── Step 2 (pool) ─────────────────────────────────────────────────────────────

class TestAsyncStepPool:
    @pytest.mark.asyncio
    async def test_shows_pool_dropdown_form(self):
        flow = _make_flow()
        # Advance to step 2 first
        await flow.async_step_user(
            user_input={CONF_USERNAME: "u", CONF_PASSWORD: "p"}
        )
        result = await flow.async_step_pool(user_input=None)
        assert result["type"] == "form"
        assert result["step_id"] == "pool"

    @pytest.mark.asyncio
    async def test_pool_selection_creates_entry(self):
        flow = _make_flow(pools=SAMPLE_POOLS)
        await flow.async_step_user(
            user_input={CONF_USERNAME: "user@example.com", CONF_PASSWORD: "s3cr3t"}
        )
        result = await flow.async_step_pool(user_input={CONF_POOLID: "12345"})
        assert result["type"] == "create_entry"
        assert result["data"][CONF_USERNAME] == "user@example.com"
        assert result["data"][CONF_PASSWORD] == "s3cr3t"
        assert result["data"][CONF_POOLID] == 12345  # stored as int

    @pytest.mark.asyncio
    async def test_entry_title_uses_pool_nickname(self):
        flow = _make_flow(pools=SAMPLE_POOLS)
        await flow.async_step_user(
            user_input={CONF_USERNAME: "u", CONF_PASSWORD: "p"}
        )
        result = await flow.async_step_pool(user_input={CONF_POOLID: "12345"})
        assert "Ma piscine" in result["title"]
        assert "12345" in result["title"]

    @pytest.mark.asyncio
    async def test_second_pool_selectable(self):
        flow = _make_flow(pools=SAMPLE_POOLS)
        await flow.async_step_user(
            user_input={CONF_USERNAME: "u", CONF_PASSWORD: "p"}
        )
        result = await flow.async_step_pool(user_input={CONF_POOLID: "67890"})
        assert result["data"][CONF_POOLID] == 67890
        assert "La piscine du jardin" in result["title"]

    @pytest.mark.asyncio
    async def test_pool_id_stored_as_int_not_string(self):
        """CONF_POOLID must be an int — downstream code does entry.data.get('poolid')."""
        flow = _make_flow(pools=SAMPLE_POOLS)
        await flow.async_step_user(
            user_input={CONF_USERNAME: "u", CONF_PASSWORD: "p"}
        )
        result = await flow.async_step_pool(user_input={CONF_POOLID: "12345"})
        assert isinstance(result["data"][CONF_POOLID], int)
