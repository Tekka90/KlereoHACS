import logging
import hashlib
from .const import KLEREOSERVER, HA_VERSION

# 'requests' is imported inside each method to avoid blocking the HA event loop
# during the import_module() call at integration load time.

LOGGER = logging.getLogger(__name__)

# JSON error details that indicate the JWT has expired / is invalid
_JWT_EXPIRED_DETAILS = {"jwt expired", "invalid jwt", "jwt invalid", "unauthorized", "not authenticated"}


class KlereoAPI:
    def __init__(self, username, password, poolid):
        self.username = username
        self.password = password
        self.poolid = poolid
        self.base_url = KLEREOSERVER
        self.jwt = None

    def hash_password(self):
        return hashlib.sha1(self.password.encode()).hexdigest()

    def get_jwt(self):
        import requests  # deferred — first import happens in executor thread
        url = f"{self.base_url}/GetJWT.php"
        hashed_password = self.hash_password()
        payload = {
            'login': self.username,
            'password': hashed_password,
            'version': HA_VERSION,
            'app': 'api'
        }
        response = requests.post(url, data=payload)
        response.raise_for_status()
        self.jwt = response.json().get('jwt')
        LOGGER.debug("JWT refreshed successfully")
        return self.jwt

    def _is_auth_error(self, body: dict) -> bool:
        """Return True when the JSON response signals an expired / invalid JWT."""
        if body.get('status') != 'error':
            return False
        detail = str(body.get('detail', '')).lower()
        return any(kw in detail for kw in _JWT_EXPIRED_DETAILS)

    def _post(self, url: str, payload: dict | None = None) -> dict:
        """POST helper that automatically re-authenticates once on JWT expiry."""
        import requests  # deferred — first import happens in executor thread
        if not self.jwt:
            self.get_jwt()
        headers = {'Authorization': f'Bearer {self.jwt}'}
        response = requests.post(url, headers=headers, data=payload or {})
        response.raise_for_status()
        body = response.json()
        if self._is_auth_error(body):
            LOGGER.info("JWT expired — re-authenticating and retrying request")
            self.get_jwt()
            headers = {'Authorization': f'Bearer {self.jwt}'}
            response = requests.post(url, headers=headers, data=payload or {})
            response.raise_for_status()
            body = response.json()
        return body

    def get_index(self):
        url = f"{self.base_url}/GetIndex.php"
        body = self._post(url)
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

    def turn_on_device(self, outIdx):
        LOGGER.info(f"TurnOn #{self.poolid} out{outIdx}")
        url = f"{self.base_url}/SetOut.php"
        payload = {
            'poolID': self.poolid,
            'outIdx': outIdx,
            'newMode': 0,
            'newState': 1,
            'comMode': 1
        }
        rep = self._post(url, payload)
        LOGGER.info(f"rep={rep}")

    def turn_off_device(self, outIdx):
        LOGGER.info(f"TurnOff #{self.poolid} out{outIdx}")
        url = f"{self.base_url}/SetOut.php"
        payload = {
            'poolID': self.poolid,
            'outIdx': outIdx,
            'newMode': 0,
            'newState': 0,
            'comMode': 1
        }
        rep = self._post(url, payload)
        LOGGER.info(f"rep={rep}")

    def set_device_mode(self, outIdx, mode):
        LOGGER.info(f"Changemode #{outIdx} mode={mode}")
        

