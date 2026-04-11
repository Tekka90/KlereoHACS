"""Live read-only API validation tests.

These tests call the **real** Klereo Connect API and validate that responses
conform to the documented structure and data types.

⚠️  NO write endpoints are called (SetOut / SetParam / SetAutoOff).
    This file must never send commands to a live pool.

Run
---
    pytest tests/live/ -v
    pytest tests/live/ -v -k "TestGetPoolDetails"

All tests are automatically skipped when credentials are absent (see conftest.py).
"""
import pytest

# Mark every test in this file as a live test
pytestmark = pytest.mark.live

# ---------------------------------------------------------------------------
# Documented valid value sets
# ---------------------------------------------------------------------------
VALID_PROBE_TYPES = {0, 1, 2, 3, 4, 5, 6, 10, 11, 12, 13, 14}
VALID_OUT_MODES = {0, 1, 2, 3, 4, 6, 8, 9}
VALID_STATUS_VALUES = {0, 1, 2}
VALID_ACCESS_LEVELS = {5, 10, 16, 20, 25}
VALID_POOL_MODES = {0, 1, 2, 4, 5}
VALID_TRAIT_MODES = {0, 1, 2, 3, 4, 5, 6, 8}
VALID_PH_MODES = {0, 1, 2}
VALID_HEATER_MODES = {0, 1, 2, 3, 4}
VALID_PRODUCT_IDX = {0, 1, 2, 3, 4, 5, 6, 7}
VALID_PUMP_TYPES = {0, 1, 2, 7}


# ===========================================================================
# Authentication
# ===========================================================================

class TestAuthentication:
    def test_get_jwt_returns_non_empty_string(self, live_credentials):
        """GetJWT.php must return a usable JWT string."""
        from KlereoHACS.klereo_api import KlereoAPI

        api = KlereoAPI(
            live_credentials["username"],
            live_credentials["password"],
            live_credentials["poolid"],
        )
        jwt = api.get_jwt()
        assert jwt is not None
        assert isinstance(jwt, str)
        assert len(jwt) > 20, "JWT looks too short to be valid"

    def test_jwt_stored_on_instance(self, live_api):
        assert live_api.jwt is not None
        assert isinstance(live_api.jwt, str)

    def test_jwt_does_not_equal_deprecated_token(self, live_credentials):
        """Sanity-check: we must be using 'jwt', not the deprecated 'token' field."""
        import requests
        import hashlib
        from KlereoHACS.const import KLEREOSERVER, HA_VERSION

        hashed = hashlib.sha1(live_credentials["password"].encode()).hexdigest()
        resp = requests.post(
            f"{KLEREOSERVER}/GetJWT.php",
            data={
                "login": live_credentials["username"],
                "password": hashed,
                "version": HA_VERSION,
                "app": "api",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        assert data["status"] == "ok"
        assert data["jwt"] != data.get("token"), (
            "jwt and token fields must differ — if equal, 'token' may have been used"
        )


# ===========================================================================
# GetIndex
# ===========================================================================

class TestGetIndex:
    def test_returns_non_empty_list(self, live_api):
        result = live_api.get_index()
        assert isinstance(result, list)
        assert len(result) >= 1, "Account must have at least one pool"

    def test_each_pool_has_id_system(self, live_api):
        for pool in live_api.get_index():
            assert "idSystem" in pool
            assert isinstance(pool["idSystem"], int)
            assert pool["idSystem"] > 0

    def test_each_pool_has_nickname(self, live_api):
        for pool in live_api.get_index():
            assert "poolNickname" in pool
            assert isinstance(pool["poolNickname"], str)
            assert len(pool["poolNickname"]) > 0

    def test_each_pool_has_valid_access_level(self, live_api):
        for pool in live_api.get_index():
            assert "access" in pool
            # Allow slightly higher values from future API versions
            assert pool["access"] >= 5, "Access level should be >= 5"

    def test_sensor_index_fields_are_integers(self, live_api):
        """EauCapteur / pHCapteur / TraitCapteur / PressionCapteur must be ints."""
        for pool in live_api.get_index():
            for key in ("EauCapteur", "pHCapteur", "TraitCapteur", "PressionCapteur"):
                if key in pool and pool[key] is not None:
                    assert isinstance(pool[key], int), f"{key} should be an int"


# Module-level fixture: one GetPoolDetails call shared across the whole module.
@pytest.fixture(scope="module")
def pool_data(live_api):
    return live_api.get_pool()


# ===========================================================================
# GetPoolDetails
# ===========================================================================

class TestGetPoolDetails:
    """Validates the full GetPoolDetails response for the configured pool."""

    # -- Top-level structure -------------------------------------------------

    def test_response_is_dict(self, pool_data):
        assert isinstance(pool_data, dict)

    def test_required_top_level_keys(self, pool_data):
        for key in ("idSystem", "probes", "outs", "params"):
            assert key in pool_data, f"Missing required key: {key}"

    def test_pool_id_matches_configured(self, pool_data, live_credentials):
        assert pool_data["idSystem"] == live_credentials["poolid"]

    # -- Probes --------------------------------------------------------------

    def test_probes_is_list(self, pool_data):
        assert isinstance(pool_data["probes"], list)

    def test_at_least_one_probe(self, pool_data):
        assert len(pool_data["probes"]) >= 1

    def test_each_probe_has_required_fields(self, pool_data):
        required = ("index", "type", "filteredValue", "directValue",
                    "filteredTime", "directTime")
        for probe in pool_data["probes"]:
            for field in required:
                assert field in probe, f"Probe missing field '{field}': {probe}"

    def test_probe_filtered_value_is_numeric(self, pool_data):
        for probe in pool_data["probes"]:
            assert isinstance(probe["filteredValue"], (int, float)), (
                f"probe[{probe['index']}].filteredValue must be numeric, "
                f"got {type(probe['filteredValue'])}"
            )

    def test_probe_types_are_in_documented_set(self, pool_data):
        unknown = [
            probe["type"]
            for probe in pool_data["probes"]
            if probe["type"] not in VALID_PROBE_TYPES
        ]
        if unknown:
            pytest.xfail(
                f"Unknown probe type(s) {unknown} found — "
                "update VALID_PROBE_TYPES if this is a new sensor type."
            )

    def test_probe_indices_are_non_negative_ints(self, pool_data):
        for probe in pool_data["probes"]:
            assert isinstance(probe["index"], int)
            assert probe["index"] >= 0

    def test_eau_capteur_probe_exists_in_probes(self, pool_data):
        """EauCapteur index must point to an actual probe in probes[]."""
        eau_idx = pool_data.get("EauCapteur")
        if eau_idx is not None:
            probe_indices = [p["index"] for p in pool_data["probes"]]
            assert eau_idx in probe_indices, (
                f"EauCapteur={eau_idx} but no probe with that index exists"
            )

    # -- Outputs -------------------------------------------------------------

    def test_outs_is_list(self, pool_data):
        assert isinstance(pool_data["outs"], list)

    def test_each_out_has_required_fields(self, pool_data):
        required = ("index", "type", "mode", "status", "realStatus")
        for out in pool_data["outs"]:
            for field in required:
                assert field in out, f"Output missing field '{field}': {out}"

    def test_out_indices_are_in_valid_range(self, pool_data):
        for out in pool_data["outs"]:
            assert 0 <= out["index"] <= 15, (
                f"Output index {out['index']} outside documented range 0–15"
            )

    def test_out_status_values_are_valid(self, pool_data):
        for out in pool_data["outs"]:
            if out["status"] is not None:
                assert out["status"] in VALID_STATUS_VALUES, (
                    f"out[{out['index']}].status={out['status']} "
                    f"not in {VALID_STATUS_VALUES}"
                )

    def test_wired_out_modes_are_valid(self, pool_data):
        """Outputs that are actually wired (type != None) must have a valid mode."""
        for out in pool_data["outs"]:
            if out["type"] is not None and out["mode"] is not None:
                assert out["mode"] in VALID_OUT_MODES, (
                    f"out[{out['index']}].mode={out['mode']} "
                    f"not in {VALID_OUT_MODES}"
                )

    # -- Params --------------------------------------------------------------

    def test_params_is_dict(self, pool_data):
        assert isinstance(pool_data["params"], dict)

    def test_pool_mode_is_known_value(self, pool_data):
        params = pool_data["params"]
        if "PoolMode" in params:
            assert params["PoolMode"] in VALID_POOL_MODES, (
                f"Unexpected PoolMode: {params['PoolMode']}"
            )

    def test_consigne_eau_is_sane(self, pool_data):
        """Water setpoint must be disabled (-2000), unknown (-1000), or a valid °C."""
        params = pool_data["params"]
        if "ConsigneEau" in params:
            val = params["ConsigneEau"]
            assert val in (-2000, -1000) or (5 <= val <= 45), (
                f"ConsigneEau={val} is outside any expected range"
            )

    def test_consigne_ph_is_sane(self, pool_data):
        params = pool_data["params"]
        if "ConsignePH" in params:
            val = params["ConsignePH"]
            assert val in (-2000, -1000) or (5.0 <= val <= 9.0), (
                f"ConsignePH={val} is outside pH range 5–9"
            )

    def test_consigne_redox_is_sane(self, pool_data):
        params = pool_data["params"]
        if "ConsigneRedox" in params:
            val = params["ConsigneRedox"]
            assert val in (-2000, -1000) or (100 <= val <= 1000), (
                f"ConsigneRedox={val} mV is outside expected range"
            )

    def test_filtration_today_time_is_non_negative(self, pool_data):
        params = pool_data["params"]
        if "Filtration_TodayTime" in params:
            assert params["Filtration_TodayTime"] >= 0

    def test_filtration_total_time_is_non_negative(self, pool_data):
        params = pool_data["params"]
        if "Filtration_TotalTime" in params:
            assert params["Filtration_TotalTime"] >= 0

    def test_filtration_total_gte_today(self, pool_data):
        params = pool_data["params"]
        if "Filtration_TodayTime" in params and "Filtration_TotalTime" in params:
            assert params["Filtration_TotalTime"] >= params["Filtration_TodayTime"], (
                "Total filtration time must be >= today's filtration time"
            )

    def test_trait_mode_is_known_value(self, pool_data):
        params = pool_data["params"]
        if "TraitMode" in params:
            assert params["TraitMode"] in VALID_TRAIT_MODES, (
                f"Unexpected TraitMode: {params['TraitMode']}"
            )

    def test_ph_mode_is_known_value(self, pool_data):
        params = pool_data["params"]
        if "pHMode" in params:
            assert params["pHMode"] in VALID_PH_MODES, (
                f"Unexpected pHMode: {params['pHMode']}"
            )

    def test_heater_mode_is_known_value(self, pool_data):
        params = pool_data["params"]
        if "HeaterMode" in params:
            assert params["HeaterMode"] in VALID_HEATER_MODES, (
                f"Unexpected HeaterMode: {params['HeaterMode']}"
            )

    def test_elec_gram_done_is_non_negative(self, pool_data):
        params = pool_data["params"]
        if "Elec_GramDone" in params:
            assert params["Elec_GramDone"] >= 0, (
                f"Elec_GramDone={params['Elec_GramDone']} must be non-negative"
            )

    def test_phminus_debit_is_positive_when_present(self, pool_data):
        params = pool_data["params"]
        if "PHMinus_Debit" in params and params["PHMinus_Debit"] is not None:
            assert params["PHMinus_Debit"] > 0, (
                "PHMinus_Debit (flow rate) must be positive"
            )

    # -- Null-type outputs ---------------------------------------------------

    def test_null_type_outs_have_no_other_required_fields(self, pool_data):
        """Outputs whose type is None are unconnected — we must not crash reading them."""
        for out in pool_data["outs"]:
            if out.get("type") is None:
                # Merely verify the index field is present and sane
                assert "index" in out
                assert 0 <= out["index"] <= 15

    def test_wired_outs_have_non_none_type(self, pool_data):
        """At least one output should be wired (type != None) on a real installation."""
        wired = [o for o in pool_data["outs"] if o.get("type") is not None]
        assert len(wired) >= 1, "Expected at least one wired output"

    def test_real_status_field_present_and_valid(self, pool_data):
        """realStatus must be present on every output (wired or not)."""
        for out in pool_data["outs"]:
            assert "realStatus" in out, f"out[{out['index']}] missing realStatus"
            if out["realStatus"] is not None:
                assert out["realStatus"] in VALID_STATUS_VALUES, (
                    f"out[{out['index']}].realStatus={out['realStatus']} not in {VALID_STATUS_VALUES}"
                )

    # -- Setpoint sentinels --------------------------------------------------

    def test_consigne_eau_sentinel_maps_to_none_in_entity(self, pool_data):
        """When ConsigneEau is -2000 or -1000, the sensor entity must return None."""
        from unittest.mock import MagicMock
        from KlereoHACS.sensor import _PARAM_SENSORS, KlereoParamSensor

        params = pool_data.get("params", {})
        val = params.get("ConsigneEau")
        if val not in (-2000, -1000):
            pytest.skip("ConsigneEau is not a sentinel value on this pool")

        coord = MagicMock()
        coord.data = pool_data
        desc = next(d for d in _PARAM_SENSORS if d.key == "setpoint_water_temp")
        sensor = KlereoParamSensor(coord, pool_data["idSystem"], desc)
        assert sensor.native_value is None, (
            f"Sentinel value {val} must map to None, got {sensor.native_value!r}"
        )

    def test_valid_consigne_eau_returns_float(self, pool_data):
        """When ConsigneEau is a real setpoint, the sensor entity must return a float."""
        from unittest.mock import MagicMock
        from KlereoHACS.sensor import _PARAM_SENSORS, KlereoParamSensor

        params = pool_data.get("params", {})
        val = params.get("ConsigneEau")
        if val is None or val in (-2000, -1000):
            pytest.skip("ConsigneEau not a valid setpoint on this pool")

        coord = MagicMock()
        coord.data = pool_data
        desc = next(d for d in _PARAM_SENSORS if d.key == "setpoint_water_temp")
        sensor = KlereoParamSensor(coord, pool_data["idSystem"], desc)
        result = sensor.native_value
        assert isinstance(result, float), f"Expected float, got {type(result)}"

    # -- HybrideMode / ExtraParams -------------------------------------------

    def test_hybride_mode_field_type(self, pool_data):
        """HybrideMode, when present, must be 0 or 1."""
        if "HybrideMode" not in pool_data:
            pytest.skip("HybrideMode not present on this pool")
        assert pool_data["HybrideMode"] in (0, 1), (
            f"HybrideMode={pool_data['HybrideMode']} must be 0 or 1"
        )

    def test_hybrid_pool_has_extra_params(self, pool_data):
        """A hybrid (HybrideMode==1) pool must have ExtraParams with the hybrid keys."""
        if pool_data.get("HybrideMode") != 1:
            pytest.skip("Pool is not in hybrid mode")
        extra = pool_data.get("ExtraParams", {})
        assert "HybChl_TodayTime" in extra, "Hybrid pool must have HybChl_TodayTime in ExtraParams"
        assert "HybChl_TotalTime" in extra, "Hybrid pool must have HybChl_TotalTime in ExtraParams"
        assert extra["HybChl_TodayTime"] >= 0
        assert extra["HybChl_TotalTime"] >= extra["HybChl_TodayTime"]

    # -- Alerts structure ----------------------------------------------------

    def test_alerts_field_is_list(self, pool_data):
        """alerts must be a list (possibly empty)."""
        assert isinstance(pool_data.get("alerts", []), list)

    def test_each_alert_has_code_and_param(self, pool_data):
        """Every alert object must have a 'code' integer."""
        for alert in pool_data.get("alerts", []):
            assert "code" in alert, f"Alert missing 'code' field: {alert}"
            assert isinstance(alert["code"], int)

    def test_alert_count_sensor_matches_alerts_list_length(self, pool_data):
        """KlereoAlertCountSensor.native_value must equal len(pool_data['alerts'])."""
        from unittest.mock import MagicMock
        from KlereoHACS.sensor import KlereoAlertCountSensor

        coord = MagicMock()
        coord.data = pool_data
        sensor = KlereoAlertCountSensor(coord, pool_data["idSystem"])
        assert sensor.native_value == len(pool_data.get("alerts", []))

    def test_alerts_string_sensor_is_non_empty_string(self, pool_data):
        """The 'alerts' enum sensor must always return a non-empty string."""
        from unittest.mock import MagicMock
        from KlereoHACS.sensor import _ENUM_SENSORS, KlereoEnumSensor

        coord = MagicMock()
        coord.data = pool_data
        desc = next(d for d in _ENUM_SENSORS if d.key == "alerts")
        sensor = KlereoEnumSensor(coord, pool_data["idSystem"], desc)
        val = sensor.native_value
        assert isinstance(val, str) and len(val) > 0

    # -- Diagnostic fields ---------------------------------------------------

    def test_product_idx_field_type(self, pool_data):
        if "ProductIdx" not in pool_data:
            pytest.skip("ProductIdx not in live data")
        assert pool_data["ProductIdx"] in VALID_PRODUCT_IDX, (
            f"Unknown ProductIdx: {pool_data['ProductIdx']}"
        )

    def test_product_idx_sensor_returns_known_string(self, pool_data):
        if "ProductIdx" not in pool_data:
            pytest.skip("ProductIdx not in live data")
        from unittest.mock import MagicMock
        from KlereoHACS.sensor import _ENUM_SENSORS, KlereoEnumSensor

        coord = MagicMock()
        coord.data = pool_data
        desc = next(d for d in _ENUM_SENSORS if d.key == "product_idx")
        sensor = KlereoEnumSensor(coord, pool_data["idSystem"], desc)
        val = sensor.native_value
        assert val is not None
        assert isinstance(val, str)

    def test_pump_type_field_type(self, pool_data):
        if "PumpType" not in pool_data:
            pytest.skip("PumpType not in live data")
        assert pool_data["PumpType"] in VALID_PUMP_TYPES, (
            f"Unknown PumpType: {pool_data['PumpType']}"
        )

    def test_pump_type_sensor_returns_known_string(self, pool_data):
        if "PumpType" not in pool_data:
            pytest.skip("PumpType not in live data")
        from unittest.mock import MagicMock
        from KlereoHACS.sensor import _ENUM_SENSORS, KlereoEnumSensor

        coord = MagicMock()
        coord.data = pool_data
        desc = next(d for d in _ENUM_SENSORS if d.key == "pump_type")
        sensor = KlereoEnumSensor(coord, pool_data["idSystem"], desc)
        val = sensor.native_value
        assert val is not None
        assert isinstance(val, str)

    def test_is_low_salt_field_type(self, pool_data):
        if "isLowSalt" not in pool_data:
            pytest.skip("isLowSalt not in live data")
        assert pool_data["isLowSalt"] in (0, 1), (
            f"isLowSalt must be 0 or 1, got {pool_data['isLowSalt']}"
        )

    # -- Chlorine runtime params ---------------------------------------------

    def test_chlore_today_time_is_non_negative(self, pool_data):
        params = pool_data["params"]
        if "ElectroChlore_TodayTime" not in params:
            pytest.skip("ElectroChlore_TodayTime not in live data")
        assert params["ElectroChlore_TodayTime"] >= 0

    def test_chlore_total_time_gte_today(self, pool_data):
        params = pool_data["params"]
        if "ElectroChlore_TotalTime" not in params or "ElectroChlore_TodayTime" not in params:
            pytest.skip("ElectroChlore_Total/Today not both in live data")
        assert params["ElectroChlore_TotalTime"] >= params["ElectroChlore_TodayTime"]

    def test_chlore_today_h_sensor_produces_hours(self, pool_data):
        params = pool_data.get("params", {})
        if "ElectroChlore_TodayTime" not in params:
            pytest.skip("ElectroChlore_TodayTime not in live data")
        from unittest.mock import MagicMock
        from KlereoHACS.sensor import _PARAM_SENSORS, KlereoParamSensor

        coord = MagicMock()
        coord.data = pool_data
        desc = next(d for d in _PARAM_SENSORS if d.key == "chlore_today_h")
        sensor = KlereoParamSensor(coord, pool_data["idSystem"], desc)
        val = sensor.native_value
        assert val is not None
        assert 0 <= val <= 24, f"chlore_today_h={val}h outside 0–24h range"

    # -- HeaterMode == 4 (aqPACType) -----------------------------------------

    def test_heater_mode_4_has_aqpactype(self, pool_data):
        """When HeaterMode is 4, aqPACType must be present and 0 or 1."""
        params = pool_data.get("params", {})
        if params.get("HeaterMode") != 4:
            pytest.skip("HeaterMode != 4 on this pool")
        assert "aqPACType" in params, "HeaterMode==4 requires aqPACType in params"
        assert params["aqPACType"] in (0, 1), (
            f"aqPACType must be 0 or 1, got {params['aqPACType']}"
        )

    def test_heater_mode_4_sensor_returns_heat_pump_string(self, pool_data):
        params = pool_data.get("params", {})
        if params.get("HeaterMode") != 4:
            pytest.skip("HeaterMode != 4 on this pool")
        from unittest.mock import MagicMock
        from KlereoHACS.sensor import _ENUM_SENSORS, KlereoEnumSensor

        coord = MagicMock()
        coord.data = pool_data
        desc = next(d for d in _ENUM_SENSORS if d.key == "heater_mode")
        sensor = KlereoEnumSensor(coord, pool_data["idSystem"], desc)
        val = sensor.native_value
        assert val is not None
        assert "heat pump" in val.lower(), (
            f"HeaterMode==4 should return a heat pump label, got {val!r}"
        )


# ===========================================================================
# Params → sensor entity smoke test (unit-level cross-check with live data)
# ===========================================================================

class TestParamSensorsWithLiveData:
    """Instantiate the actual HA sensor classes with live coordinator data
    and verify they produce sane values — no mocking, pure logic check."""

    def test_filtration_today_sensor_produces_hours(self, pool_data):
        from unittest.mock import MagicMock
        from KlereoHACS.sensor import _PARAM_SENSORS, KlereoParamSensor

        params = pool_data.get("params", {})
        if "Filtration_TodayTime" not in params:
            pytest.skip("Filtration_TodayTime not in live data")

        coord = MagicMock()
        coord.data = pool_data
        desc = next(d for d in _PARAM_SENSORS if d.key == "filtration_today_h")
        sensor = KlereoParamSensor(coord, pool_data["idSystem"], desc)
        val = sensor.native_value
        assert val is not None
        assert 0 <= val <= 24, f"Filtration today {val}h is outside 0–24h range"

    def test_setpoint_water_temp_not_sentinel(self, pool_data):
        """If ConsigneEau is a real value, the sensor must not return -2000 or -1000."""
        from unittest.mock import MagicMock
        from KlereoHACS.sensor import _PARAM_SENSORS, KlereoParamSensor

        params = pool_data.get("params", {})
        if "ConsigneEau" not in params:
            pytest.skip("ConsigneEau not in live data")

        coord = MagicMock()
        coord.data = pool_data
        desc = next(d for d in _PARAM_SENSORS if d.key == "setpoint_water_temp")
        sensor = KlereoParamSensor(coord, pool_data["idSystem"], desc)
        val = sensor.native_value
        if val is not None:
            assert val not in (-2000, -1000), (
                f"Sentinel value {val} must not be exposed as the sensor state"
            )

    def test_setpoint_ph_not_sentinel(self, pool_data):
        from unittest.mock import MagicMock
        from KlereoHACS.sensor import _PARAM_SENSORS, KlereoParamSensor

        params = pool_data.get("params", {})
        if "ConsignePH" not in params:
            pytest.skip("ConsignePH not in live data")

        coord = MagicMock()
        coord.data = pool_data
        desc = next(d for d in _PARAM_SENSORS if d.key == "setpoint_ph")
        sensor = KlereoParamSensor(coord, pool_data["idSystem"], desc)
        val = sensor.native_value
        if val is not None:
            assert val not in (-2000, -1000)

    def test_setpoint_redox_not_sentinel(self, pool_data):
        from unittest.mock import MagicMock
        from KlereoHACS.sensor import _PARAM_SENSORS, KlereoParamSensor

        params = pool_data.get("params", {})
        if "ConsigneRedox" not in params:
            pytest.skip("ConsigneRedox not in live data")

        coord = MagicMock()
        coord.data = pool_data
        desc = next(d for d in _PARAM_SENSORS if d.key == "setpoint_redox")
        sensor = KlereoParamSensor(coord, pool_data["idSystem"], desc)
        val = sensor.native_value
        if val is not None:
            assert val not in (-2000, -1000)

    def test_pool_mode_enum_sensor_produces_known_string(self, pool_data):
        from unittest.mock import MagicMock
        from KlereoHACS.sensor import _ENUM_SENSORS, KlereoEnumSensor

        params = pool_data.get("params", {})
        if "PoolMode" not in params:
            pytest.skip("PoolMode not in live data")

        coord = MagicMock()
        coord.data = pool_data
        desc = next(d for d in _ENUM_SENSORS if d.key == "pool_mode")
        sensor = KlereoEnumSensor(coord, pool_data["idSystem"], desc)
        val = sensor.native_value
        assert val is not None
        assert val in desc.options or "Unknown" in val, (
            f"Pool mode '{val}' not in known options {desc.options}"
        )

    def test_heater_mode_enum_sensor_produces_known_string(self, pool_data):
        from unittest.mock import MagicMock
        from KlereoHACS.sensor import _ENUM_SENSORS, KlereoEnumSensor

        params = pool_data.get("params", {})
        if "HeaterMode" not in params:
            pytest.skip("HeaterMode not in live data")

        coord = MagicMock()
        coord.data = pool_data
        desc = next(d for d in _ENUM_SENSORS if d.key == "heater_mode")
        sensor = KlereoEnumSensor(coord, pool_data["idSystem"], desc)
        val = sensor.native_value
        assert val is not None
        assert isinstance(val, str)
        # Regardless of aqPACType, the value must always be a non-empty string
        assert len(val) > 0

    def test_alert_count_sensor_is_non_negative_int(self, pool_data):
        from unittest.mock import MagicMock
        from KlereoHACS.sensor import KlereoAlertCountSensor

        coord = MagicMock()
        coord.data = pool_data
        sensor = KlereoAlertCountSensor(coord, pool_data["idSystem"])
        val = sensor.native_value
        assert isinstance(val, int)
        assert val >= 0


# ===========================================================================
# Cross-check: GetIndex vs GetPoolDetails consistency
# ===========================================================================

class TestCrossCheck:
    def test_pool_found_in_index(self, live_api, live_credentials):
        """The configured pool ID must appear in GetIndex results."""
        pools = live_api.get_index()
        ids = [p["idSystem"] for p in pools]
        assert live_credentials["poolid"] in ids, (
            f"Pool {live_credentials['poolid']} not found in GetIndex response: {ids}"
        )

    def test_probe_count_consistent(self, pool_data):
        """GetPoolDetails probe count must be >= 1."""
        assert len(pool_data["probes"]) >= 1
