"""Unit tests for KlereoSensor, KlereoParamSensor, and KlereoEnumSensor entities.

All HA infrastructure is mocked via tests/conftest.py.
Tests use a MagicMock coordinator whose .data mirrors SAMPLE_POOL_DATA.
"""
import copy
import pytest
from unittest.mock import MagicMock

from KlereoHACS.sensor import KlereoSensor, KlereoParamSensor, KlereoEnumSensor
from KlereoHACS.sensor import _PROBE_TYPE_MAP, _PARAM_SENSORS, _ENUM_SENSORS
from tests.fixtures import SAMPLE_POOL_DATA


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

    def test_reflects_live_coordinator_data_not_init_snapshot(self, coordinator):
        """native_value must re-read coordinator.data on each call."""
        sensor = make_sensor(coordinator, probe_index=2)
        coordinator.data["probes"][0]["filteredValue"] = 30.0
        assert sensor.native_value == 30.0


class TestKlereoSensorIdentifiers:
    def test_unique_id_contains_pool_and_probe_index(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=2)
        assert sensor.unique_id == "id_klereo12345probe2"

    def test_name_contains_pool_id(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=2)
        assert "12345" in sensor.name

    def test_name_contains_probe_index(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=2)
        assert "2" in sensor.name


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
