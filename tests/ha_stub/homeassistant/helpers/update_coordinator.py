"""Stub: homeassistant.helpers.update_coordinator"""
from unittest.mock import MagicMock


class UpdateFailed(Exception):
    pass


class CoordinatorEntity:
    """Minimal stub that stores coordinator and sets up hass."""

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.hass = MagicMock()
        self.hass.async_add_executor_job = MagicMock()

    def async_write_ha_state(self):
        pass


class DataUpdateCoordinator:
    def __init__(self, hass, logger, *, name, update_interval, update_method=None):
        self.hass = hass
        self.name = name
        self.data = None
        self._update_method = update_method

    async def async_config_entry_first_refresh(self):
        if self._update_method:
            self.data = await self.hass.async_add_executor_job(self._update_method)

    async def async_request_refresh(self):
        pass
