"""Sensor entities for FMI Solar Forecast."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_NAME, DOMAIN
from .coordinator import FmiSolarForecastCoordinator

PARALLEL_UPDATES = 0


@dataclass(frozen=True)
class FmiSolarSensorDescription(SensorEntityDescription):
    """Describes an FMI Solar Forecast sensor."""

    state: Callable[[dict[str, Any]], Any] | None = None


def _current_power(data: dict) -> float:
    return data.get("current_power_w", 0.0)

def _today_energy(data: dict) -> float:
    """Today's forecasted energy in Wh."""
    return data.get("today_energy_kwh", 0.0) * 1000.0

def _tomorrow_energy(data: dict) -> float:
    """Tomorrow's forecasted energy in Wh."""
    return data.get("tomorrow_energy_kwh", 0.0) * 1000.0

def _peak_today(data: dict) -> float:
    return data.get("peak_today_w", 0.0)

def _next_hour_energy(data: dict) -> float:
    """Energy forecasted for the next hour in Wh."""
    now = datetime.now(tz=timezone.utc)
    for slot in data.get("forecast", []):
        try:
            slot_dt = datetime.fromisoformat(slot["datetime"])
            if slot_dt.tzinfo is None:
                slot_dt = slot_dt.replace(tzinfo=timezone.utc)
        except (ValueError, KeyError):
            continue
        if slot_dt > now:
            return max(0.0, slot.get("power_w", 0.0))
    return 0.0


SENSORS: tuple[FmiSolarSensorDescription, ...] = (
    FmiSolarSensorDescription(
        key="power_production_now",
        translation_key="power_production_now",
        state=_current_power,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
    ),
    FmiSolarSensorDescription(
        key="energy_production_today",
        translation_key="energy_production_today",
        state=_today_energy,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
    ),
    FmiSolarSensorDescription(
        key="energy_production_tomorrow",
        translation_key="energy_production_tomorrow",
        state=_tomorrow_energy,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
    ),
    FmiSolarSensorDescription(
        key="energy_next_hour",
        translation_key="energy_next_hour",
        state=_next_hour_energy,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
    ),
    FmiSolarSensorDescription(
        key="peak_power_today",
        translation_key="peak_power_today",
        state=_peak_today,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up FMI Solar Forecast sensors."""
    coordinator: FmiSolarForecastCoordinator = entry.runtime_data

    async_add_entities(
        FmiSolarSensorEntity(
            entry=entry,
            coordinator=coordinator,
            entity_description=description,
        )
        for description in SENSORS
    )


class FmiSolarSensorEntity(
    CoordinatorEntity[FmiSolarForecastCoordinator], SensorEntity
):
    """An FMI Solar Forecast sensor entity."""

    _attr_has_entity_name = True
    entity_description: FmiSolarSensorDescription

    def __init__(
        self,
        *,
        entry: ConfigEntry,
        coordinator: FmiSolarForecastCoordinator,
        entity_description: FmiSolarSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        self.entity_description = entity_description
        self._attr_unique_id = f"{entry.entry_id}_{entity_description.key}"
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="Finnish Meteorological Institute",
            model="FMI Open PV Forecast",
            name=entry.data.get(CONF_NAME, entry.title),
        )

    @property
    def native_value(self) -> float | None:
        """Return the sensor state."""
        if self.coordinator.data is None:
            return None
        if self.entity_description.state is None:
            return None
        return self.entity_description.state(self.coordinator.data)
