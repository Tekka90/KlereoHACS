"""Conftest for live API tests.

Credentials are read from environment variables, falling back to a local
``.env`` file in the project root (see ``.env.example``).

Required variables
------------------
KLEREO_USERNAME   Klereo Connect account login (e-mail)
KLEREO_PASSWORD   Plain-text password — hashed with SHA-1 before sending
KLEREO_POOLID     Integer pool ID (idSystem)

All live tests are **automatically skipped** when any variable is missing,
so CI stays green without credentials.

Run live tests
--------------
    # Option A — environment variables
    KLEREO_USERNAME=x KLEREO_PASSWORD=y KLEREO_POOLID=z pytest tests/live/ -v

    # Option B — .env file (copy .env.example → .env and fill in)
    pytest tests/live/ -v
"""
import os
import pytest

try:
    from dotenv import load_dotenv
    load_dotenv()  # silently no-ops if .env does not exist
except ImportError:
    pass  # python-dotenv is optional


# ---------------------------------------------------------------------------
# Credentials helper
# ---------------------------------------------------------------------------

def _credentials():
    username = os.environ.get("KLEREO_USERNAME")
    password = os.environ.get("KLEREO_PASSWORD")
    poolid_raw = os.environ.get("KLEREO_POOLID")
    if not (username and password and poolid_raw):
        return None
    return {
        "username": username,
        "password": password,
        "poolid": int(poolid_raw),
    }


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def live_credentials():
    """Return credentials dict, or skip the entire session if not configured."""
    creds = _credentials()
    if creds is None:
        pytest.skip(
            "Live credentials not set. "
            "Export KLEREO_USERNAME, KLEREO_PASSWORD, KLEREO_POOLID "
            "or create a .env file (see .env.example)."
        )
    return creds


@pytest.fixture(scope="session")
def live_api(live_credentials):
    """Authenticated KlereoAPI instance.

    Authenticates once per test session.  READ-ONLY — no write methods are
    called from this fixture or from the live tests themselves.
    """
    from KlereoHACS.klereo_api import KlereoAPI

    api = KlereoAPI(
        live_credentials["username"],
        live_credentials["password"],
        live_credentials["poolid"],
    )
    api.get_jwt()
    return api
