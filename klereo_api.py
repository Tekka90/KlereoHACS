import logging
import hashlib
from datetime import datetime, timedelta
from .const import KLEREOSERVER, HA_VERSION

# 'requests' is imported inside each method to avoid blocking the HA event loop
# during the import_module() call at integration load time.

LOGGER = logging.getLogger(__name__)

# JSON error details that indicate the JWT has expired / is invalid
_JWT_EXPIRED_DETAILS = {"jwt expired", "invalid jwt", "jwt invalid", "unauthorized", "not authenticated"}

# Re-authenticate when the token is this old — Jeedom uses 55 min (token valid 60 min)
_JWT_REFRESH_AFTER = timedelta(minutes=55)

# Klereo server scheduled maintenance windows (local server time).
# Format: {weekday: (from_hhmm, to_hhmm)} where weekday follows PHP date('w'):
#   0=Sunday, 1=Monday, 2=Tuesday, 3=Wednesday, 4=Thursday, 5=Friday, 6=Saturday
# Monday (1) has no maintenance window.
# Source: Jeedom plugin klereo.class.php $_MAINTENANCES
_MAINTENANCE_WINDOWS: dict[int, tuple[int, int]] = {
    0: (145, 445),   # Sunday   01:45 – 04:45
    2: (130, 135),   # Tuesday  01:30 – 01:35
    3: (130, 135),   # Wednesday 01:30 – 01:35
    4: (130, 135),   # Thursday  01:30 – 01:35
    5: (130, 135),   # Friday    01:30 – 01:35
    6: (130, 135),   # Saturday  01:30 – 01:35
}


class KlereoAPI:
    def __init__(self, username, password, poolid):
        self.username = username
        self.password = password
        self.poolid = poolid
        self.base_url = KLEREOSERVER
        self.jwt = None
        self.jwt_acquired_at: datetime | None = None

    def hash_password(self):
        return hashlib.sha1(self.password.encode()).hexdigest()

    def get_jwt(self):
        import requests  # deferred — first import happens in executor thread
        from homeassistant.exceptions import ConfigEntryAuthFailed
        url = f"{self.base_url}/GetJWT.php"
        hashed_password = self.hash_password()
        payload = {
            'login': self.username,
            'password': hashed_password,
            'version': HA_VERSION,
            'app': 'api'
        }
        try:
            response = requests.post(url, data=payload)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ConfigEntryAuthFailed(f"Klereo authentication failed: {exc}") from exc
        body = response.json()
        if body.get('status') != 'ok' or not body.get('jwt'):
            raise ConfigEntryAuthFailed(
                f"Klereo authentication failed: {body.get('detail', 'no jwt in response')}"
            )
        self.jwt = body['jwt']
        self.jwt_acquired_at = datetime.now()
        LOGGER.debug("JWT refreshed successfully")
        return self.jwt

    @staticmethod
    def _is_maintenance_window(now: datetime | None = None) -> bool:
        """Return True when the current local time falls inside a Klereo maintenance window.

        Mirrors Jeedom's maintenance_ongoing(): uses PHP date('w') convention
        (0=Sunday … 6=Saturday) and a compact HHMM integer for comparison.
        """
        t = now or datetime.now()
        # PHP date('w'): 0=Sunday, 1=Monday, …, 6=Saturday
        php_weekday = int(t.strftime('%w'))  # 0-6, same convention as PHP
        window = _MAINTENANCE_WINDOWS.get(php_weekday)
        if window is None:
            return False
        compact = t.hour * 100 + t.minute
        return window[0] <= compact <= window[1]

    def _is_auth_error(self, body: dict) -> bool:
        """Return True when the JSON response signals an expired / invalid JWT."""
        if body.get('status') != 'error':
            return False
        detail = str(body.get('detail', '')).lower()
        return any(kw in detail for kw in _JWT_EXPIRED_DETAILS)

    def _post(self, url: str, payload: dict | None = None) -> dict:
        """POST helper that automatically re-authenticates once on JWT expiry.

        Two refresh strategies are combined:
        1. **Proactive**: if the stored JWT is ≥ 55 minutes old, re-authenticate
           before sending the request (mirrors Jeedom's login_dt logic).
        2. **Reactive**: if the server returns a JWT-expiry error on any request,
           re-authenticate once and retry.
        """
        import requests  # deferred — first import happens in executor thread
        from homeassistant.exceptions import ConfigEntryAuthFailed
        from homeassistant.helpers.update_coordinator import UpdateFailed
        # --- Proactive maintenance window skip (mirrors Jeedom curl_request guard) ---
        if self._is_maintenance_window():
            LOGGER.debug("Klereo server maintenance window active — skipping request")
            raise UpdateFailed("Klereo server maintenance")
        # --- Proactive refresh (B3) ---
        if self.jwt is None or (
            self.jwt_acquired_at is not None
            and datetime.now() - self.jwt_acquired_at >= _JWT_REFRESH_AFTER
        ):
            if self.jwt_acquired_at is not None and self.jwt is not None:
                LOGGER.info("JWT is ≥55 min old — proactively refreshing before request")
            self.get_jwt()
        headers = {'Authorization': f'Bearer {self.jwt}'}
        try:
            response = requests.post(url, headers=headers, data=payload or {})
            response.raise_for_status()
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 401:
                raise ConfigEntryAuthFailed(f"Klereo auth error (HTTP 401): {exc}") from exc
            raise UpdateFailed(f"Klereo HTTP error: {exc}") from exc
        except requests.RequestException as exc:
            raise UpdateFailed(f"Klereo request failed: {exc}") from exc
        body = response.json()
        # --- Reactive refresh ---
        if self._is_auth_error(body):
            LOGGER.info("JWT expired — re-authenticating and retrying request")
            self.get_jwt()
            headers = {'Authorization': f'Bearer {self.jwt}'}
            try:
                response = requests.post(url, headers=headers, data=payload or {})
                response.raise_for_status()
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 401:
                    raise ConfigEntryAuthFailed(f"Klereo auth error (HTTP 401): {exc}") from exc
                raise UpdateFailed(f"Klereo HTTP error: {exc}") from exc
            except requests.RequestException as exc:
                raise UpdateFailed(f"Klereo request failed: {exc}") from exc
            body = response.json()
        return body

    def get_index(self):
        from homeassistant.helpers.update_coordinator import UpdateFailed
        url = f"{self.base_url}/GetIndex.php"
        body = self._post(url)
        if body.get('status') != 'ok' or 'response' not in body:
            raise UpdateFailed(f"GetIndex unexpected response: {body.get('detail', body)}")
        index = body['response']
        LOGGER.info(f"Successfully obtained GetIndex: {index}")
        return index

    def get_pool(self):
        from homeassistant.helpers.update_coordinator import UpdateFailed
        LOGGER.info(f"GetPoolDetails #{self.poolid}")
        url = f"{self.base_url}/GetPoolDetails.php"
        payload = {'poolID': self.poolid, 'lang': 'fr'}
        pooldetails = self._post(url, payload)
        if pooldetails.get('status') == 'error':
            detail = pooldetails.get('detail', '')
            if detail == 'maintenance':
                LOGGER.warning("Klereo server maintenance in progress — skipping update")
                raise UpdateFailed("Klereo server maintenance")
            raise UpdateFailed(f"Klereo API error: {detail}")
        pool = pooldetails['response'][0]
        return pool

    # ---- command status codes returned by WaitCommand.php ----
    _CMD_STATUS_SUCCESS = 9
    _CMD_STATUS_MESSAGES = {
        0:  "Pending",
        1:  "Executing",
        9:  "Success",
        10: "Command failed",
        11: "Bad parameters",
        12: "Unknown command",
        13: "Insufficient access rights",
        15: "Execution timeout",
        16: "Abandoned",
        17: "Pool not connected",
        18: "Service unavailable",
        19: "Firmware update required",
    }

    def _set_out(self, outIdx: int, newMode: int, newState: int) -> int:
        """Call SetOut.php and return the cmdID.  Raises on API error."""
        LOGGER.info(f"SetOut #{self.poolid} out{outIdx} mode={newMode} state={newState}")
        url = f"{self.base_url}/SetOut.php"
        payload = {
            'poolID': self.poolid,
            'outIdx': outIdx,
            'newMode': newMode,
            'newState': newState,
            'comMode': 1,
        }
        from homeassistant.exceptions import HomeAssistantError
        body = self._post(url, payload)
        if body.get('status') != 'ok':
            raise HomeAssistantError(f"SetOut failed: {body.get('detail', body)}")
        cmd_id = body['response'][0]['cmdID']
        LOGGER.debug(f"SetOut cmdID={cmd_id}")
        return cmd_id

    def wait_command(self, cmd_id: int) -> int:
        """Call WaitCommand.php and block until the pool controller confirms.

        Returns the status code (9 = success).  Raises HomeAssistantError on
        any failure status so the caller can surface the error in the UI.

        WaitCommand response shape (from Jeedom source):
            {"status": "ok", "response": {"status": 9, "cmdID": 42}}
        Note: response is a *dict*, not a list.
        """
        from homeassistant.exceptions import HomeAssistantError
        LOGGER.debug(f"WaitCommand cmdID={cmd_id}")
        url = f"{self.base_url}/WaitCommand.php"
        body = self._post(url, {'cmdID': cmd_id})
        if body.get('status') != 'ok':
            raise HomeAssistantError(f"WaitCommand HTTP error: {body.get('detail', body)}")
        status = body.get('response', {}).get('status')
        if status is None:
            LOGGER.warning(f"WaitCommand: unexpected response shape: {body}")
            return 0
        LOGGER.debug(f"WaitCommand status={status} ({self._CMD_STATUS_MESSAGES.get(status, '?')})")
        if status != self._CMD_STATUS_SUCCESS:
            msg = self._CMD_STATUS_MESSAGES.get(status, f"Unknown status {status}")
            raise HomeAssistantError(f"Klereo command rejected: {msg} (code {status})")
        return status

    def turn_on_device(self, outIdx):
        LOGGER.info(f"TurnOn #{self.poolid} out{outIdx}")
        cmd_id = self._set_out(outIdx, newMode=0, newState=1)
        self.wait_command(cmd_id)

    def turn_off_device(self, outIdx):
        LOGGER.info(f"TurnOff #{self.poolid} out{outIdx}")
        cmd_id = self._set_out(outIdx, newMode=0, newState=0)
        self.wait_command(cmd_id)

    def set_pump_speed(self, outIdx: int, speed: int) -> None:
        """Set the speed of a variable-speed (analogue) pump via SetOut.

        For analogue pumps PumpMaxSpeed > 1.  The speed value (0..PumpMaxSpeed)
        is passed directly as ``newState``.  ``newMode=0`` (Manual) keeps the
        output under HA control rather than reverting to a schedule.
        """
        LOGGER.info(f"SetPumpSpeed #{self.poolid} out{outIdx} speed={speed}")
        cmd_id = self._set_out(outIdx, newMode=0, newState=speed)
        self.wait_command(cmd_id)

    def set_param(self, param_id: str, value: float) -> None:
        """Write a regulation setpoint via SetParam.php.

        Valid param_id values: "ConsigneEau", "ConsignePH", "ConsigneRedox",
        "ConsigneChlore".  Returns `cmdID` from the response and verifies it
        with WaitCommand before returning.

        Access level gates (checked by the server — will raise HomeAssistantError
        on insufficient rights, code 13):
          - ConsigneEau   : access >= 10 (end-user)
          - ConsignePH, ConsigneRedox, ConsigneChlore : access >= 16 (advanced)
        """
        from homeassistant.exceptions import HomeAssistantError
        LOGGER.info(f"SetParam #{self.poolid} {param_id}={value}")
        url = f"{self.base_url}/SetParam.php"
        payload = {
            'poolID': self.poolid,
            'paramID': param_id,
            'newValue': value,
            'comMode': 1,
        }
        body = self._post(url, payload)
        if body.get('status') != 'ok':
            raise HomeAssistantError(f"SetParam failed: {body.get('detail', body)}")
        cmd_id = body['response'][0]['cmdID']
        LOGGER.debug(f"SetParam cmdID={cmd_id}")
        self.wait_command(cmd_id)

    def set_auto_off(self, out_idx: int, off_delay: int) -> None:
        """Set the timer auto-off delay (in minutes) for a timer-capable output.

        Valid for output indices: 0, 5, 6, 7, 9, 10, 11, 12, 13, 14.
        ``off_delay`` must be 1–600 (minutes).  Raises ``HomeAssistantError`` if
        the pool controller rejects the command (e.g. pool not connected, bad
        output index).

        Note: this only sets the *delay value* — it does NOT activate timer mode.
        Activating timer mode requires a separate SetOut call (newMode=2, newState=2).
        """
        from homeassistant.exceptions import HomeAssistantError
        LOGGER.info(f"SetAutoOff #{self.poolid} out{out_idx} offDelay={off_delay}min")
        url = f"{self.base_url}/SetAutoOff.php"
        payload = {
            'poolID':   self.poolid,
            'outIdx':   out_idx,
            'offDelay': int(off_delay),
            'comMode':  1,
        }
        body = self._post(url, payload)
        if body.get('status') != 'ok':
            raise HomeAssistantError(f"SetAutoOff failed: {body.get('detail', body)}")
        cmd_id = body['response'][0]['cmdID']
        LOGGER.debug(f"SetAutoOff cmdID={cmd_id}")
        self.wait_command(cmd_id)

    def set_device_mode(self, outIdx: int, mode: int, state: int = 2) -> None:
        """Set the operating mode of an output without changing its on/off state.

        ``mode`` must be one of the ``_OUT_MODE_*`` constants (0, 1, 2, 3, 4, 6, 8, 9).
        Do NOT use 5 or 7 — those are Klereo-internal values.

        ``state`` defaults to 2 (Auto) so the output follows the new mode's
        schedule/regulation logic immediately, which mirrors Jeedom behaviour.
        Use state=0 to disable the output, or state=1 to force it on.

        Not applicable for outputs 2, 3, 4, 8, 15 (Pro/heating outputs that
        have no user-selectable mode field) — for those, call turn_on/turn_off
        or set a setpoint via set_param().
        """
        LOGGER.info(f"SetDeviceMode #{self.poolid} out{outIdx} mode={mode} state={state}")
        cmd_id = self._set_out(outIdx, newMode=mode, newState=state)
        self.wait_command(cmd_id)


