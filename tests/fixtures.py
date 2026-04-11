"""Shared sample data that mirrors real Klereo API responses.

These are plain dicts (not pytest fixtures) so they can be imported freely
in both unit and live tests.
"""

# ── GetJWT response ──────────────────────────────────────────────────────────
SAMPLE_JWT_RESPONSE = {
    "status": "ok",
    "jwt": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.test.signature",
    "token": "deprecated-do-not-use",  # never use this field
    "access": 10,
    "id": 2,
}

# ── Pool data ─────────────────────────────────────────────────────────────────
# Minimal but realistic GetPoolDetails response[0] structure.
# probe types follow the documented table:
#   2=water level, 3=pH, 4=Redox/ORP, 5=water temp, 6=filter pressure
SAMPLE_POOL_DATA = {
    "idSystem": 12345,
    "poolNickname": "Ma piscine (test)",
    "podSerial": "POD-TEST-001",
    "access": 10,
    "device": 0,
    "pin": "1234",
    "EauCapteur": 2,
    "pHCapteur": 3,
    "TraitCapteur": 4,
    "PressionCapteur": 5,
    "PumpMaxSpeed": 0,
    "HybrideMode": 0,
    "ProductIdx": 0,
    "probes": [
        {
            "index": 2,
            "type": 5,          # water temperature
            "filteredValue": 26.3,
            "directValue": 26.5,
            "filteredTime": 45,
            "directTime": 45,
            "seuilMin": 15.0,
            "seuilMax": 35.0,
        },
        {
            "index": 3,
            "type": 3,          # pH
            "filteredValue": 7.2,
            "directValue": 7.25,
            "filteredTime": 45,
            "directTime": 45,
            "seuilMin": 6.8,
            "seuilMax": 7.6,
        },
        {
            "index": 4,
            "type": 4,          # Redox / ORP
            "filteredValue": 680.0,
            "directValue": 682.0,
            "filteredTime": 45,
            "directTime": 45,
            "seuilMin": 650.0,
            "seuilMax": 800.0,
        },
        {
            "index": 5,
            "type": 6,          # filter pressure (mbar)
            "filteredValue": 1200.0,
            "directValue": 1210.0,
            "filteredTime": 45,
            "directTime": 45,
            "seuilMin": -2000,
            "seuilMax": 2500.0,
        },
    ],
    "outs": [
        {
            "index": 0,         # Lighting
            "type": 1,
            "mode": 2,          # Timer
            "status": 0,        # off
            "realStatus": 0,
            "updateTime": 1712000000,
        },
        {
            "index": 1,         # Filtration
            "type": 1,
            "mode": 1,          # Time slots
            "status": 2,        # auto
            "realStatus": 1,
            "updateTime": 1712000000,
        },
        {
            "index": 4,         # Heating
            "type": 1,
            "mode": 0,          # Manual
            "status": 0,
            "realStatus": 0,
            "updateTime": 1712000000,
        },
    ],
    "params": {
        "Filtration_TodayTime": 14400,
        "Filtration_TotalTime": 3600000,
        "PoolMode": 2,
        "TraitMode": 1,
        "pHMode": 1,
        "HeaterMode": 1,
        "ConsigneEau": 28.0,
        "ConsignePH": 7.2,
        "ConsigneRedox": 680.0,
        "ConsigneChlore": -2000,
        "EauMin": 10.0,
        "EauMax": 40.0,
        "pHMin": 6.8,
        "pHMax": 7.8,
        "OrpMin": 600.0,
        "OrpMax": 900.0,
    },
    "IORename": [
        {"ioType": 2, "ioIndex": 2, "name": "Water Temp"},
        {"ioType": 1, "ioIndex": 1, "name": "Filtration"},
    ],
    "alerts": [],
    "plans": [],
}

# ── Wrapped response structures ───────────────────────────────────────────────
SAMPLE_INDEX_RESPONSE = {
    "status": "ok",
    "response": [SAMPLE_POOL_DATA],
}

SAMPLE_GET_POOL_RESPONSE = {
    "status": "ok",
    "response": [SAMPLE_POOL_DATA],
}

SAMPLE_SET_OUT_RESPONSE = {
    "status": "ok",
    "response": [{"cmdID": 42, "poolID": 12345}],
}

SAMPLE_MAINTENANCE_RESPONSE = {
    "status": "error",
    "detail": "maintenance",
}
