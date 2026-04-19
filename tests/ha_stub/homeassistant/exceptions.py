"""Stub: homeassistant.exceptions"""
from homeassistant.helpers.update_coordinator import UpdateFailed  # noqa: F401


class HomeAssistantError(Exception):
    pass


class ConfigEntryAuthFailed(HomeAssistantError):
    pass


class ConfigEntryNotReady(HomeAssistantError):
    pass
    pass
