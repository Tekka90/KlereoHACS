"""Number platform for Klereo — writable regulation setpoints.

Currently registered entities
------------------------------
(none yet — see TODO: Implement SetParam.php for ConsigneEau, ConsignePH, etc.)

Variable-speed filtration pump
------------------------------
The pump speed control was previously a NumberEntity but has been moved to the
``select`` platform (``select.py`` / ``KlereoPumpSpeedSelect``) so that each
discrete speed level is presented as a named option rather than a bare integer.

When ``pool_data['PumpMaxSpeed'] > 1`` the switch platform skips filtration
output index 1; the select platform registers a named-speed selector instead.
"""

from __future__ import annotations

import logging
LOGGER = logging.getLogger(__name__)

from .const import DOMAIN


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up Klereo number entities — placeholder for future setpoint entities."""
    LOGGER.debug("Klereo number platform: no entities to register yet")
