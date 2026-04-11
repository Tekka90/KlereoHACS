"""Unit tests for KlereoSensor entity.

All HA infrastructure is mocked via tests/conftest.py.
Tests use a MagicMock coordinator whose .data mirrors SAMPLE_POOL_DATA.
"""
import copy
import pytest
from unittest.mock import MagicMock

from KlereoHACS.sensor import KlereoSensor
from tests.fixtures import SAMPLE_POOL_DATA


# ── Shared helpers ────────────────────────────────────────────────────────────

@pytest.fixture
def coordinator():
    """A mock coordinator whose data is a deep copy of SAMPLE_POOL_DATA.

    Using a deep copy prevents one test's mutation from affecting another.
    """
    coord = MagicMock()
    coord.data = copy.deepcopy(SAMPLE_POOL_DATA)
    return coord


def _probe(pool_data, index):
    return next(p for p in pool_data["probes"] if p["index"] == index)


def make_sensor(coordinator, probe_index=2):
    probe = _probe(coordinator.data, probe_index)
    return KlereoSensor(coordinator, probe, 12345)


# ── State ─────────────────────────────────────────────────────────────────────

class TestKlereoSensorState:
    def test_returns_filtered_value_for_water_temp(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=2)
        assert sensor.state == 26.3

    def test_returns_filtered_value_for_ph(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=3)
        assert sensor.state == 7.2

    def test_returns_float(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=2)
        assert isinstance(sensor.state, float)

    def test_returns_none_when_probe_absent_from_coordinator(self, coordinator):
        """If coordinator data no longer contains the probe, state must be None."""
        probe = {"index": 99, "type": 5, "filteredValue": 0,
                 "directValue": 0, "filteredTime": 0, "directTime": 0}
        sensor = KlereoSensor(coordinator, probe, 12345)
        assert sensor.state is None

    def test_reflects_live_coordinator_data_not_init_snapshot(self, coordinator):
        """State must be read from coordinator.data on each call, not from init-time cache."""
        sensor = make_sensor(coordinator, probe_index=2)
        coordinator.data["probes"][0]["filteredValue"] = 30.0
        assert sensor.state == 30.0


# ── Identifiers ───────────────────────────────────────────────────────────────

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


# ── Extra state attributes ────────────────────────────────────────────────────

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


# ── Device class and unit of measurement (B1 fixed) ──────────────────────────

class TestKlereoSensorDeviceClassBugB1:
    """B1 — Probes use device_class and unit_of_measurement from probe['type']."""

    def test_water_temp_probe_device_class_and_unit(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=2)  # type=5, water temp
        assert sensor.device_class == "temperature"
        assert sensor.unit_of_measurement == "°C"

    def test_ph_probe_device_class(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=3)  # type=3, pH
        assert sensor.device_class == "ph"

    def test_ph_probe_has_no_unit(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=3)
        assert sensor.unit_of_measurement is None

    def test_redox_probe_device_class_and_unit(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=4)  # type=4, Redox
        assert sensor.device_class == "voltage"
        assert sensor.unit_of_measurement == "mV"

    def test_pressure_probe_device_class_and_unit(self, coordinator):
        sensor = make_sensor(coordinator, probe_index=5)  # type=6, filter pressure
        assert sensor.device_class == "pressure"
        assert sensor.unit_of_measurement == "mbar"
