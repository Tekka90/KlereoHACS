"""Stub: homeassistant.helpers.entity"""
from dataclasses import dataclass, field


@dataclass
class DeviceInfo:
    identifiers: set = field(default_factory=set)
    name: str | None = None
    serial_number: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    sw_version: str | None = None

    def __getitem__(self, key: str):
        return getattr(self, key)

    def __setitem__(self, key: str, value) -> None:
        setattr(self, key, value)
