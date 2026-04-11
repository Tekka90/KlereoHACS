"""Unit tests for KlereoSensor, KlereoParamSensor, and KlereoEnumSensor entities.

All HA infrastructure is mocked via tests/conftest.py.
Tests use a MagicMock coordinator whose .data mirrors SAMPLE_POOL_DATA.
"""
import copy
import pytest
from unittest.mock import MagicMock

from KlereoHACS.sensor import KlereoSensor, KlereoParamSensor, KlereoEnumSensor
from KlereoHACS.sensor import _PROBE_TYPE_MAP, _PARAM_SENSORS, _ENUM_SENSORS
from tests.fixtures import SAMPLE_POOL_DATA, SAMPLE_HYBRID_POOL_DATA


# ── Shared helpers ────────────────────────────────────────────────────────────

@pytest.fixture
def coordinator():
    """A mock coordinator whose data is a deep copy of SAMPLE_POOL_DATA."""
    coord = MagicMock()
    coord.data = copy.deepcopy(SAMPLE_POOL_DATA)
    return coord


def _probe(pool_data, index):
    return next(p for p in pool_data["probes"] if p["index"] == index)


def make_sensor(coordinator, probe_index=2):
    probe = _probe(coordinator.data, probe_index)
    return KlereoSensor(coordinator, probe, 12345)


def make_param_sensor(coordinator, key):
    desc = next(d for d in _PARAM_SENSORS if d.key == key)
    return KlereoParamSensor(coordinator, 12345, desc)


def make_enum_sensor(coordinator, key):
    desc = next(d for d in _ENUM_SENSORS if d.key == key)
    return KlereoEnumSensor(coordinator, 12345, desc)


# ═══════════════════════════════════════════════════════════════════════════════
# KlereoSensor (probe-based)
# ═══════════════════════════════════════════════════════════════════════════════

class TestKlereoSensorNativeValue:
    def test_returns_filtered_value_for_water_temp(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=2)
        assert sensor.native_value == 26.3

    def test_returns_filtered_value_for_ph(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=3)
        assert sensor.native_value == 7.2

    def test_returns_float(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=2)
        assert isinstance(sensor.native_value, float)

    def test_returns_none_when_probe_absent_from_coordinator(self, coordinator):
        probe = {"index": 99, "type": 5, "filteredValue": 0,
                 "directValue": 0, "filteredTime": 0, "directTime": 0}
        sensor = KlereoSensor(coordinator, probe, 12345)
        assert sensor.native_value is None

    def test_falls_back_to_direct_value_when_filtered_is_null(self, coordinator):
        """filteredValue null → use directValue (e.g. air temperature probe)."""
        coordinator.data["probes"][0]["filteredValue"] = None
        coordinator.data["probes"][0]["directValue"] = 22.1
        sensor = make_sensor(coordinator, probe_index=2)
        assert sensor.native_value == pytest.approx(22.1)

    def test_returns_none_when_both_values_are_null(self, coordinator):
        coordinator.data["probes"][0]["filteredValue"] = None
        coordinator.data["probes"][0]["directValue"] = None
        sensor = make_sensor(coordinator, probe_index=2)
        assert sensor.native_value is None

    def test_returns_none_safely_when_probes_is_null(self, coordinator):
        """API can return probes=null at boot — must not raise, must return None."""
        sensor = make_sensor(coordinator, probe_index=2)  # create while data is valid
        coordinator.data["probes"] = None  # then simulate null probes
        assert sensor.native_value is None

    def test_returns_none_safely_when_probe_not_found(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=2)
        coordinator.data["probes"] = []  # probe disappeared from list
        assert sensor.native_value is None

    def test_returns_none_for_non_numeric_value(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=2)
        coordinator.data["probes"][0]["filteredValue"] = "error"
        assert sensor.native_value is None

    def test_reflects_live_coordinator_data_not_init_snapshot(self, coordinator):
        """native_value must re-read coordinator.data on each call."""
        sensor = make_sensor(coordinator, probe_index=2)
        coordinator.data["probes"][0]["filteredValue"] = 30.0
        assert sensor.native_value == 30.0


class TestKlereoSensorIdentifiers:
    def test_unique_id_contains_pool_and_probe_index(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=2)
        assert sensor.unique_id == "id_klereo12345probe2"

    def test_name_is_human_readable_type_name(self, coordinator):
        # probe_index=4 has type=4 (Redox) — no IORename in fixture
        sensor = make_sensor(coordinator, probe_index=4)
        assert sensor.name == "Redox"

    def test_name_uses_probe_type_for_ph(self, coordinator):
        # probe_index=3 has type=3 → "pH" — no IORename in fixture
        sensor = make_sensor(coordinator, probe_index=3)
        assert sensor.name == "pH"

    def test_name_uses_probe_type_for_pressure(self, coordinator):
        # probe_index=5 has type=6 → "Filter Pressure" — no IORename in fixture
        sensor = make_sensor(coordinator, probe_index=5)
        assert sensor.name == "Filter Pressure"

    def test_name_iorename_already_present_in_fixture(self, coordinator):
        # SAMPLE_POOL_DATA has IORename for probe index=2 → "Water Temp"
        sensor = make_sensor(coordinator, probe_index=2)
        assert sensor.name == "Water Temp"

    def test_name_uses_iorename_override_when_present(self, coordinator):
        coordinator.data["IORename"] = [
            {"ioType": 2, "ioIndex": 4, "name": "My Custom Redox Sensor"}
        ]
        sensor = make_sensor(coordinator, probe_index=4)
        assert sensor.name == "My Custom Redox Sensor"

    def test_iorename_override_ignored_for_different_index(self, coordinator):
        coordinator.data["IORename"] = [
            {"ioType": 2, "ioIndex": 99, "name": "Not This One"}
        ]
        sensor = make_sensor(coordinator, probe_index=4)
        assert sensor.name == "Redox"

    def test_iorename_output_rename_not_applied_to_probe(self, coordinator):
        # ioType=1 is output rename — must not affect probe name
        coordinator.data["IORename"] = [
            {"ioType": 1, "ioIndex": 4, "name": "Output Wrong"}
        ]
        sensor = make_sensor(coordinator, probe_index=4)
        assert sensor.name == "Redox"

    def test_name_disambiguates_duplicate_types(self, coordinator):
        # Clear IORename so type-name fallback is exercised, then add duplicate type
        coordinator.data["IORename"] = []
        coordinator.data["probes"].append({
            "index": 12, "type": 4,  # second Redox probe
            "filteredValue": 650.0, "directValue": 650.0,
            "filteredTime": 10, "directTime": 10,
        })
        sensor = make_sensor(coordinator, probe_index=4)
        assert sensor.name == "Redox (4)"

    def test_name_fallback_for_unknown_type(self, coordinator):
        coordinator.data["probes"].append({
            "index": 99, "type": 99,
            "filteredValue": 0.0, "directValue": 0.0,
            "filteredTime": 0, "directTime": 0,
        })
        probe = {"index": 99, "type": 99}
        sensor = KlereoSensor(coordinator, probe, 12345)
        assert sensor.name == "Probe 99"

    def test_unique_id_unchanged_by_naming_fix(self, coordinator):
        # unique_id must stay stable regardless of name changes
        sensor = make_sensor(coordinator, probe_index=2)
        assert sensor.unique_id == "id_klereo12345probe2"


class TestKlereoSensorAttributes:
    def test_extra_attributes_contain_type(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=2)
        attrs = sensor.extra_state_attributes
        assert attrs is not None
        assert "Type" in attrs
        assert attrs["Type"] == 5  # water temperature

    def test_extra_attributes_contain_time(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=2)
        attrs = sensor.extra_state_attributes
        assert "Time" in attrs
        assert attrs["Time"] == 45

    def test_extra_attributes_expose_raw_values(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=2)
        attrs = sensor.extra_state_attributes
        assert "filteredValue" in attrs
        assert "directValue" in attrs
        assert attrs["filteredValue"] == 26.3
        assert attrs["directValue"] == 26.5

    def test_extra_attributes_source_filtered_when_filtered_value_present(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=2)
        assert sensor.extra_state_attributes["Source"] == "filtered"

    def test_extra_attributes_source_direct_when_filtered_is_null(self, coordinator):
        coordinator.data["probes"][0]["filteredValue"] = None
        coordinator.data["probes"][0]["directValue"] = 22.1
        coordinator.data["probes"][0]["directTime"] = 10
        sensor = make_sensor(coordinator, probe_index=2)
        attrs = sensor.extra_state_attributes
        assert attrs["Source"] == "direct"
        assert attrs["Time"] == 10

    def test_extra_attributes_returns_none_for_missing_probe(self, coordinator):
        probe = {"index": 99, "type": 5, "filteredValue": 0,
                 "directValue": 0, "filteredTime": 0, "directTime": 0}
        sensor = KlereoSensor(coordinator, probe, 12345)
        assert sensor.extra_state_attributes is None


class TestKlereoSensorDeviceClass:
    """B1 fixed — device_class and unit come from entity_description (probe type map)."""

    def test_water_temp_probe_device_class_and_unit(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=2)  # type=5
        assert sensor.device_class == "temperature"
        assert sensor.unit_of_measurement == "°C"

    def test_ph_probe_device_class(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=3)  # type=3
        assert sensor.device_class == "ph"

    def test_ph_probe_has_no_unit(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=3)
        assert sensor.unit_of_measurement is None

    def test_redox_probe_device_class_and_unit(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=4)  # type=4
        assert sensor.device_class == "voltage"
        assert sensor.unit_of_measurement == "mV"

    def test_pressure_probe_device_class_and_unit(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=5)  # type=6
        assert sensor.device_class == "pressure"
        assert sensor.unit_of_measurement == "mbar"

    def test_all_probe_type_map_entries_have_valid_keys(self):
        """Smoke test: every entry in _PROBE_TYPE_MAP must have a non-empty key."""
        for k, desc in _PROBE_TYPE_MAP.items():
            assert desc.key, f"_PROBE_TYPE_MAP[{k}] has empty key"

    def test_entity_description_set_on_init(self, coordinator):
        """entity_description must be set so HA uses it authoritatively."""
        sensor = make_sensor(coordinator, probe_index=3)
        assert sensor.entity_description is not None
        assert sensor.entity_description.device_class is not None


# ═══════════════════════════════════════════════════════════════════════════════
# KlereoParamSensor (numeric params)
# ═══════════════════════════════════════════════════════════════════════════════

class TestKlereoParamSensorNativeValue:
    def test_filtration_today_converts_seconds_to_hours(self, coordinator):
        # 14400 s → 4.0 h
        sensor = make_param_sensor(coordinator, "filtration_today_h")
        assert sensor.native_value == pytest.approx(4.0)

    def test_filtration_total_converts_seconds_to_hours(self, coordinator):
        # 3600000 s → 1000.0 h
        sensor = make_param_sensor(coordinator, "filtration_total_h")
        assert sensor.native_value == pytest.approx(1000.0)

    def test_phminus_today_ml_formula(self, coordinator):
        # 120 * 180 / 36 = 600.0 mL
        sensor = make_param_sensor(coordinator, "phminus_today_ml")
        assert sensor.native_value == pytest.approx(600.0)

    def test_phminus_total_l_formula(self, coordinator):
        # 7200 * 180 / 36000 = 36.0 L
        sensor = make_param_sensor(coordinator, "phminus_total_l")
        assert sensor.native_value == pytest.approx(36.0)

    def test_elec_gram_done_divides_by_1000(self, coordinator):
        # 5000 / 1000 = 5.0 g
        sensor = make_param_sensor(coordinator, "elec_gram_done")
        assert sensor.native_value == pytest.approx(5.0)

    def test_heating_today_h(self, coordinator):
        # 3600 s → 1.0 h
        sensor = make_param_sensor(coordinator, "heating_today_h")
        assert sensor.native_value == pytest.approx(1.0)

    def test_setpoint_ph(self, coordinator):
        sensor = make_param_sensor(coordinator, "setpoint_ph")
        assert sensor.native_value == pytest.approx(7.2)

    def test_setpoint_water_temp(self, coordinator):
        sensor = make_param_sensor(coordinator, "setpoint_water_temp")
        assert sensor.native_value == pytest.approx(28.0)

    def test_setpoint_redox(self, coordinator):
        sensor = make_param_sensor(coordinator, "setpoint_redox")
        assert sensor.native_value == pytest.approx(680.0)

    def test_returns_none_when_param_key_absent(self, coordinator):
        """If a required param key is missing, native_value must be None."""
        coordinator.data["params"].pop("Filtration_TodayTime", None)
        sensor = make_param_sensor(coordinator, "filtration_today_h")
        assert sensor.native_value is None

    def test_returns_none_when_params_dict_absent(self, coordinator):
        coordinator.data.pop("params", None)
        sensor = make_param_sensor(coordinator, "filtration_today_h")
        assert sensor.native_value is None


class TestKlereoParamSensorIdentifiers:
    def test_unique_id_format(self, coordinator):
        sensor = make_param_sensor(coordinator, "filtration_today_h")
        assert sensor.unique_id == "klereo12345_param_filtration_today_h"

    def test_name_is_human_readable(self, coordinator):
        sensor = make_param_sensor(coordinator, "filtration_today_h")
        assert sensor.name == "Filtration Today"


class TestKlereoParamSensorDescription:
    def test_filtration_has_duration_device_class(self, coordinator):
        sensor = make_param_sensor(coordinator, "filtration_today_h")
        assert sensor.device_class == "duration"
        assert sensor.unit_of_measurement == "h"

    def test_ph_setpoint_has_ph_device_class(self, coordinator):
        sensor = make_param_sensor(coordinator, "setpoint_ph")
        assert sensor.device_class == "ph"

    def test_all_param_sensors_have_unique_keys(self):
        keys = [d.key for d in _PARAM_SENSORS]
        assert len(keys) == len(set(keys)), "Duplicate keys in _PARAM_SENSORS"


# ═══════════════════════════════════════════════════════════════════════════════
# KlereoEnumSensor (string/enum params)
# ═══════════════════════════════════════════════════════════════════════════════

class TestKlereoEnumSensorNativeValue:
    def test_pool_mode_2_maps_to_comfort(self, coordinator):
        # SAMPLE_POOL_DATA params.PoolMode = 2
        sensor = make_enum_sensor(coordinator, "pool_mode")
        assert sensor.native_value == "Comfort"

    def test_trait_mode_1_maps_to_liquid_chlorine(self, coordinator):
        sensor = make_enum_sensor(coordinator, "trait_mode")
        assert sensor.native_value == "Liquid chlorine"

    def test_ph_mode_1_maps_to_ph_minus(self, coordinator):
        sensor = make_enum_sensor(coordinator, "ph_mode")
        assert sensor.native_value == "pH-Minus"

    def test_heater_mode_1_maps_to_on_off_heat_pump(self, coordinator):
        sensor = make_enum_sensor(coordinator, "heater_mode")
        assert sensor.native_value == "ON/OFF heat pump"

    def test_unknown_value_returns_fallback_string(self, coordinator):
        coordinator.data["params"]["PoolMode"] = 99
        sensor = make_enum_sensor(coordinator, "pool_mode")
        assert "99" in sensor.native_value  # e.g. "Unknown (99)"

    def test_returns_none_when_param_key_absent(self, coordinator):
        coordinator.data["params"].pop("PoolMode")
        sensor = make_enum_sensor(coordinator, "pool_mode")
        assert sensor.native_value is None

    def test_returns_none_when_params_absent(self, coordinator):
        coordinator.data.pop("params", None)
        sensor = make_enum_sensor(coordinator, "pool_mode")
        assert sensor.native_value is None


class TestKlereoEnumSensorIdentifiers:
    def test_unique_id_format(self, coordinator):
        sensor = make_enum_sensor(coordinator, "pool_mode")
        assert sensor.unique_id == "klereo12345_enum_pool_mode"

    def test_name_is_human_readable(self, coordinator):
        sensor = make_enum_sensor(coordinator, "pool_mode")
        assert sensor.name == "Pool Mode"


class TestKlereoEnumSensorDescription:
    def test_device_class_is_enum(self, coordinator):
        sensor = make_enum_sensor(coordinator, "pool_mode")
        assert sensor.device_class == "enum"

    def test_options_list_is_populated(self):
        desc = next(d for d in _ENUM_SENSORS if d.key == "pool_mode")
        assert "Comfort" in desc.options
        assert "Off" in desc.options

    def test_all_enum_sensors_have_unique_keys(self):
        keys = [d.key for d in _ENUM_SENSORS]
        assert len(keys) == len(set(keys)), "Duplicate keys in _ENUM_SENSORS"


# ═══════════════════════════════════════════════════════════════════════════════
# DeviceInfo — all entity classes must share the same device
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeviceInfo:
    def test_probe_sensor_device_info_identifiers(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=2)
        assert (sensor.device_info["identifiers"]) == {("klereo", 12345)}

    def test_probe_sensor_device_info_name(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=2)
        assert sensor.device_info["name"] == "Ma piscine (test)"

    def test_probe_sensor_device_info_serial(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=2)
        assert sensor.device_info["serial_number"] == "POD-TEST-001"

    def test_probe_sensor_device_info_manufacturer(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=2)
        assert sensor.device_info["manufacturer"] == "Klereo"

    def test_param_sensor_device_info_identifiers(self, coordinator):
        sensor = make_param_sensor(coordinator, "filtration_today_h")
        assert sensor.device_info["identifiers"] == {("klereo", 12345)}

    def test_enum_sensor_device_info_identifiers(self, coordinator):
        sensor = make_enum_sensor(coordinator, "pool_mode")
        assert sensor.device_info["identifiers"] == {("klereo", 12345)}

    def test_all_entity_types_share_same_identifier(self, coordinator):
        """All entity classes must return the same device identifier so HA groups them."""
        probe = make_sensor(coordinator, probe_index=2)
        param = make_param_sensor(coordinator, "filtration_today_h")
        enum_ = make_enum_sensor(coordinator, "pool_mode")
        ids = {
            frozenset(probe.device_info["identifiers"]),
            frozenset(param.device_info["identifiers"]),
            frozenset(enum_.device_info["identifiers"]),
        }
        assert len(ids) == 1, "Sensor entity classes report different device identifiers"

    def test_fallback_name_when_nickname_absent(self, coordinator):
        coordinator.data.pop("poolNickname", None)
        sensor = make_sensor(coordinator, probe_index=2)
        assert "12345" in sensor.device_info["name"]


# ═══════════════════════════════════════════════════════════════════════════════
# Liquid chlorine sensors — HybrideMode handling
# ═══════════════════════════════════════════════════════════════════════════════

class TestChloreConsumedNormal:
    def test_chlore_today_normal_mode(self, coordinator):
        # ElectroChlore_TodayTime=60, Chlore_Debit=120 → 60*120/36 = 200 mL
        sensor = make_param_sensor(coordinator, "chlore_today_ml")
        assert sensor.native_value == pytest.approx(200.0)

    def test_chlore_total_normal_mode(self, coordinator):
        # ElectroChlore_TotalTime=3600, Chlore_Debit=120 → 3600*120/36000 = 12.0 L
        sensor = make_param_sensor(coordinator, "chlore_total_l")
        assert sensor.native_value == pytest.approx(12.0)

    def test_chlore_today_returns_none_when_debit_absent(self, coordinator):
        coordinator.data["params"].pop("Chlore_Debit", None)
        sensor = make_param_sensor(coordinator, "chlore_today_ml")
        assert sensor.native_value is None

    def test_chlore_total_returns_none_when_time_absent(self, coordinator):
        coordinator.data["params"].pop("ElectroChlore_TotalTime", None)
        sensor = make_param_sensor(coordinator, "chlore_total_l")
        assert sensor.native_value is None


@pytest.fixture
def hybrid_coordinator():
    coord = MagicMock()
    coord.data = copy.deepcopy(SAMPLE_HYBRID_POOL_DATA)
    return coord


class TestChloreConsumedHybridMode:
    def test_chlore_today_uses_extra_params_in_hybrid_mode(self, hybrid_coordinator):
        # HybChl_TodayTime=120, Chlore_Debit=120 → 120*120/36 = 400 mL
        sensor = make_param_sensor(hybrid_coordinator, "chlore_today_ml")
        assert sensor.native_value == pytest.approx(400.0)

    def test_chlore_total_uses_extra_params_in_hybrid_mode(self, hybrid_coordinator):
        # HybChl_TotalTime=7200, Chlore_Debit=120 → 7200*120/36000 = 24.0 L
        sensor = make_param_sensor(hybrid_coordinator, "chlore_total_l")
        assert sensor.native_value == pytest.approx(24.0)

    def test_chlore_today_returns_none_when_extra_params_absent(self, hybrid_coordinator):
        del hybrid_coordinator.data["ExtraParams"]["HybChl_TodayTime"]
        sensor = make_param_sensor(hybrid_coordinator, "chlore_today_ml")
        assert sensor.native_value is None

    def test_chlore_total_returns_none_when_extra_params_absent(self, hybrid_coordinator):
        del hybrid_coordinator.data["ExtraParams"]["HybChl_TotalTime"]
        sensor = make_param_sensor(hybrid_coordinator, "chlore_total_l")
        assert sensor.native_value is None


# ═══════════════════════════════════════════════════════════════════════════════
# state_class correctness — today vs total sensors
# ═══════════════════════════════════════════════════════════════════════════════

class TestStateClass:
    _today_keys = ["filtration_today_h", "phminus_today_ml", "elec_gram_done",
                   "chlore_today_ml", "heating_today_h"]
    _total_keys = ["filtration_total_h", "phminus_total_l", "chlore_total_l", "heating_total_h"]

    def test_today_sensors_use_total_state_class(self, coordinator):
        for key in self._today_keys:
            desc = next(d for d in _PARAM_SENSORS if d.key == key)
            assert desc.state_class == "total", (
                f"'{key}' resets daily and must use state_class=TOTAL, not {desc.state_class!r}"
            )

    def test_cumulative_total_sensors_use_total_increasing(self, coordinator):
        for key in self._total_keys:
            desc = next(d for d in _PARAM_SENSORS if d.key == key)
            assert desc.state_class == "total_increasing", (
                f"'{key}' should use TOTAL_INCREASING, got {desc.state_class!r}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Setpoint sentinel values (-2000 = disabled, -1000 = unknown)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSetpointSentinelGuard:
    """Setpoints must return None for sentinel values, not expose -2000/-1000."""

    @pytest.mark.parametrize("key,param", [
        ("setpoint_water_temp", "ConsigneEau"),
        ("setpoint_ph",         "ConsignePH"),
        ("setpoint_redox",      "ConsigneRedox"),
        ("setpoint_chlore",     "ConsigneChlore"),
    ])
    def test_returns_none_when_disabled(self, coordinator, key, param):
        coordinator.data["params"][param] = -2000
        sensor = make_param_sensor(coordinator, key)
        assert sensor.native_value is None, f"{key}: -2000 should map to None"

    @pytest.mark.parametrize("key,param", [
        ("setpoint_water_temp", "ConsigneEau"),
        ("setpoint_ph",         "ConsignePH"),
        ("setpoint_redox",      "ConsigneRedox"),
        ("setpoint_chlore",     "ConsigneChlore"),
    ])
    def test_returns_none_when_unknown(self, coordinator, key, param):
        coordinator.data["params"][param] = -1000
        sensor = make_param_sensor(coordinator, key)
        assert sensor.native_value is None, f"{key}: -1000 should map to None"

    @pytest.mark.parametrize("key,param,value", [
        ("setpoint_water_temp", "ConsigneEau",   28.0),
        ("setpoint_ph",         "ConsignePH",    7.4),
        ("setpoint_redox",      "ConsigneRedox", 650.0),
        ("setpoint_chlore",     "ConsigneChlore", 1.5),
    ])
    def test_returns_float_for_valid_value(self, coordinator, key, param, value):
        coordinator.data["params"][param] = value
        sensor = make_param_sensor(coordinator, key)
        assert sensor.native_value == value


# ═══════════════════════════════════════════════════════════════════════════════
# pH-mode and heating mode guards (sensors omitted when mode == 0)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPHModeGuard:
    """pH- sensors must not be created when pHMode == 0."""
    from KlereoHACS.sensor import async_setup_entry as _raw_setup

    def _run_setup(self, pool_data):
        """Helper: run async_setup_entry synchronously, return entity list."""
        import asyncio, copy
        from KlereoHACS.sensor import async_setup_entry
        from unittest.mock import MagicMock

        coord = MagicMock()
        coord.data = copy.deepcopy(pool_data)
        hass = MagicMock()
        hass.data = {"klereo": {"entry_id": {"coordinator": coord}}}
        config_entry = MagicMock()
        config_entry.entry_id = "entry_id"

        captured: list = []
        # async_setup_entry calls async_add_entities without await — use a sync mock
        def fake_async_add_entities(entities, **kwargs):
            captured.extend(entities)

        asyncio.run(async_setup_entry(hass, config_entry, fake_async_add_entities))
        return captured

    def _entity_keys(self, entities):
        return [e.entity_description.key for e in entities
                if getattr(e, "entity_description", None) is not None]

    def test_ph_minus_sensors_absent_when_ph_mode_zero(self):
        data = copy.deepcopy(SAMPLE_POOL_DATA)
        data["params"]["pHMode"] = 0
        entities = self._run_setup(data)
        keys = self._entity_keys(entities)
        assert "phminus_today_ml" not in keys
        assert "phminus_total_l" not in keys

    def test_ph_minus_sensors_present_when_ph_mode_nonzero(self):
        data = copy.deepcopy(SAMPLE_POOL_DATA)
        data["params"]["pHMode"] = 1
        entities = self._run_setup(data)
        keys = self._entity_keys(entities)
        assert "phminus_today_ml" in keys
        assert "phminus_total_l" in keys

    def test_heating_sensors_absent_when_heater_mode_zero(self):
        data = copy.deepcopy(SAMPLE_POOL_DATA)
        data["params"]["HeaterMode"] = 0
        entities = self._run_setup(data)
        keys = self._entity_keys(entities)
        assert "heating_today_h" not in keys
        assert "heating_total_h" not in keys
        assert "setpoint_water_temp" not in keys

    def test_heating_sensors_present_when_heater_mode_nonzero(self):
        data = copy.deepcopy(SAMPLE_POOL_DATA)
        data["params"]["HeaterMode"] = 1
        data["params"]["ConsigneEau"] = 28.0
        entities = self._run_setup(data)
        keys = self._entity_keys(entities)
        assert "heating_today_h" in keys
        assert "heating_total_h" in keys


# ═══════════════════════════════════════════════════════════════════════════════
# HeaterMode == 4 → aqPACType lookup
# ═══════════════════════════════════════════════════════════════════════════════

class TestHeaterModeAqPACType:
    """When HeaterMode is 4, the displayed string comes from aqPACType, not HeaterMode map."""

    def test_heater_mode_4_aqpac_0_returns_klereotherm(self, coordinator):
        coordinator.data["params"]["HeaterMode"] = 4
        coordinator.data["params"]["aqPACType"] = 0
        sensor = make_enum_sensor(coordinator, "heater_mode")
        assert sensor.native_value == "KlereoTherm heat pump"

    def test_heater_mode_4_aqpac_1_returns_inopac(self, coordinator):
        coordinator.data["params"]["HeaterMode"] = 4
        coordinator.data["params"]["aqPACType"] = 1
        sensor = make_enum_sensor(coordinator, "heater_mode")
        assert sensor.native_value == "InoPac heat pump"

    def test_heater_mode_4_no_aqpac_returns_fallback(self, coordinator):
        coordinator.data["params"]["HeaterMode"] = 4
        coordinator.data["params"].pop("aqPACType", None)
        sensor = make_enum_sensor(coordinator, "heater_mode")
        assert sensor.native_value == "Other heat pump"

    def test_heater_mode_2_returns_easytherm(self, coordinator):
        coordinator.data["params"]["HeaterMode"] = 2
        sensor = make_enum_sensor(coordinator, "heater_mode")
        assert sensor.native_value == "EasyTherm"

    def test_heater_mode_0_returns_none_string(self, coordinator):
        coordinator.data["params"]["HeaterMode"] = 0
        sensor = make_enum_sensor(coordinator, "heater_mode")
        assert sensor.native_value == "None"


# ═══════════════════════════════════════════════════════════════════════════════
# Chlorine pump runtime sensors (hours)
# ═══════════════════════════════════════════════════════════════════════════════

class TestChloreRuntimeSensors:
    def test_chlore_today_h_value(self, coordinator):
        # SAMPLE_POOL_DATA: ElectroChlore_TodayTime=60s → round(60/3600, 2) = 0.02 h
        sensor = make_param_sensor(coordinator, "chlore_today_h")
        assert sensor.native_value == 0.02

    def test_chlore_total_h_value(self, coordinator):
        # SAMPLE_POOL_DATA: ElectroChlore_TotalTime=3600s → 1.0 h
        sensor = make_param_sensor(coordinator, "chlore_total_h")
        assert sensor.native_value == 1.0

    def test_chlore_today_h_state_class_total(self):
        desc = next(d for d in _PARAM_SENSORS if d.key == "chlore_today_h")
        assert desc.state_class == "total"

    def test_chlore_total_h_state_class_total_increasing(self):
        desc = next(d for d in _PARAM_SENSORS if d.key == "chlore_total_h")
        assert desc.state_class == "total_increasing"

    def test_chlore_today_h_returns_none_when_key_missing(self, coordinator):
        coordinator.data["params"].pop("ElectroChlore_TodayTime", None)
        sensor = make_param_sensor(coordinator, "chlore_today_h")
        assert sensor.native_value is None


# ═══════════════════════════════════════════════════════════════════════════════
# Alert count sensor
# ═══════════════════════════════════════════════════════════════════════════════

class TestAlertCountSensor:
    from KlereoHACS.sensor import KlereoAlertCountSensor as _cls

    def _make(self, coordinator):
        from KlereoHACS.sensor import KlereoAlertCountSensor
        return KlereoAlertCountSensor(coordinator, 12345)

    def test_zero_when_no_alerts(self, coordinator):
        coordinator.data["alerts"] = []
        assert self._make(coordinator).native_value == 0

    def test_count_matches_alerts_array_length(self, coordinator):
        coordinator.data["alerts"] = [{"code": 7, "param": 0}, {"code": 22, "param": None}]
        assert self._make(coordinator).native_value == 2

    def test_unique_id_format(self, coordinator):
        sensor = self._make(coordinator)
        assert sensor.unique_id == "klereo12345_alert_count"

    def test_reflects_live_coordinator_data(self, coordinator):
        coordinator.data["alerts"] = []
        sensor = self._make(coordinator)
        coordinator.data["alerts"] = [{"code": 1, "param": 0}]
        assert sensor.native_value == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Alerts string sensor (KlereoEnumSensor with value_fn=_alert_string)
# ═══════════════════════════════════════════════════════════════════════════════

class TestAlertsSensor:
    def test_no_alerts_returns_no_alerts_string(self, coordinator):
        coordinator.data["alerts"] = []
        sensor = make_enum_sensor(coordinator, "alerts")
        assert sensor.native_value == "No alerts"

    def test_single_alert_with_known_code(self, coordinator):
        coordinator.data["alerts"] = [{"code": 22, "param": None}]
        sensor = make_enum_sensor(coordinator, "alerts")
        assert "Circulation problem" in sensor.native_value

    def test_multiple_alerts_joined_with_double_pipe(self, coordinator):
        coordinator.data["alerts"] = [
            {"code": 8, "param": 2},   # code 8 = Maximum threshold
            {"code": 22, "param": None},
        ]
        sensor = make_enum_sensor(coordinator, "alerts")
        val = sensor.native_value
        assert " || " in val
        assert "Maximum threshold" in val
        assert "Circulation problem" in val

    def test_unknown_code_shows_alert_number(self, coordinator):
        coordinator.data["alerts"] = [{"code": 99, "param": None}]
        sensor = make_enum_sensor(coordinator, "alerts")
        assert "99" in sensor.native_value


# ═══════════════════════════════════════════════════════════════════════════════
# Diagnostic enum sensors (ProductIdx, PumpType, isLowSalt)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiagnosticEnumSensors:
    def test_product_idx_maps_correctly(self, coordinator):
        coordinator.data["ProductIdx"] = 1
        sensor = make_enum_sensor(coordinator, "product_idx")
        assert sensor.native_value == "Kompact M5"

    def test_product_idx_returns_none_when_absent(self, coordinator):
        coordinator.data.pop("ProductIdx", None)
        sensor = make_enum_sensor(coordinator, "product_idx")
        assert sensor.native_value is None

    def test_pump_type_maps_correctly(self, coordinator):
        coordinator.data["PumpType"] = 1
        sensor = make_enum_sensor(coordinator, "pump_type")
        assert sensor.native_value == "KlereoFlô (RS485)"

    def test_pump_type_returns_none_when_absent(self, coordinator):
        coordinator.data.pop("PumpType", None)
        sensor = make_enum_sensor(coordinator, "pump_type")
        assert sensor.native_value is None

    def test_is_low_salt_maps_correctly(self, coordinator):
        coordinator.data["isLowSalt"] = 0
        sensor = make_enum_sensor(coordinator, "is_low_salt")
        assert sensor.native_value == "5g/h range"

    def test_is_low_salt_maps_low_range(self, coordinator):
        coordinator.data["isLowSalt"] = 1
        sensor = make_enum_sensor(coordinator, "is_low_salt")
        assert sensor.native_value == "2g/h range"

    def test_is_low_salt_returns_none_when_absent(self, coordinator):
        coordinator.data.pop("isLowSalt", None)
        sensor = make_enum_sensor(coordinator, "is_low_salt")
        assert sensor.native_value is None

