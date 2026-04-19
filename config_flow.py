import voluptuous as vol
from homeassistant import config_entries
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN, CONF_USERNAME, CONF_PASSWORD, CONF_POOLID
from .klereo_api import KlereoAPI

import logging
LOGGER = logging.getLogger(__name__)

class InvalidAuth(HomeAssistantError):
    """Raised when credentials are invalid."""

@config_entries.HANDLERS.register(DOMAIN)
class KlereoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._username: str = ""
        self._password: str = ""
        # {str(idSystem): "poolNickname (idSystem)"} — populated after step_user
        self._pool_options: dict[str, str] = {}

    # ── Step 1: collect username + password ──────────────────────────────────

    async def async_step_user(self, user_input=None):
        errors = {}
        LOGGER.info(f"Configuration {DOMAIN} — step: credentials")
        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            try:
                pools = await self._fetch_pools(username, password)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                LOGGER.exception("Unexpected error fetching pool list")
                errors["base"] = "cannot_connect"
            else:
                self._username = username
                self._password = password
                self._pool_options = {
                    str(p["idSystem"]): f"{p['poolNickname']} ({p['idSystem']})"
                    for p in pools
                }
                return await self.async_step_pool()

        data_schema = vol.Schema({
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
        })
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    # ── Step 2: choose pool from discovered list ──────────────────────────────

    async def async_step_pool(self, user_input=None):
        errors = {}
        LOGGER.info(f"Configuration {DOMAIN} — step: pool selection")
        if user_input is not None:
            pool_id = int(user_input[CONF_POOLID])
            label = self._pool_options.get(str(pool_id), str(pool_id))
            return self.async_create_entry(
                title=label,
                data={
                    CONF_USERNAME: self._username,
                    CONF_PASSWORD: self._password,
                    CONF_POOLID: pool_id,
                },
            )

        data_schema = vol.Schema({
            vol.Required(CONF_POOLID): vol.In(self._pool_options),
        })
        return self.async_show_form(
            step_id="pool",
            data_schema=data_schema,
            errors=errors,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _fetch_pools(self, username: str, password: str) -> list:
        """Authenticate and return the list of pools from GetIndex.php.

        Raises InvalidAuth on bad credentials, propagates other exceptions.
        """
        LOGGER.info(f"Fetching pool list for user '{username}'")
        # poolid is irrelevant here — pass 0; get_index() does not use it
        api = KlereoAPI(username, password, 0)
        try:
            await self.hass.async_add_executor_job(api.get_jwt)
        except Exception as err:
            LOGGER.warning(f"Authentication failed: {err}")
            raise InvalidAuth from err
        pools = await self.hass.async_add_executor_job(api.get_index)
        if not pools:
            raise InvalidAuth
        return pools
