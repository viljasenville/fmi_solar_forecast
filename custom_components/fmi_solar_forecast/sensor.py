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
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_AZIMUTH,
    CONF_GROUP_NAME,
    CONF_NAME,
    CONF_PANEL_GROUPS,
    CONF_POWER_KW,
    CONF_TILT,
    DOMAIN,
)
from .coordinator import FmiSolarForecastCoordinator

PARALLEL_UPDATES = 0


@dataclass(frozen=True)
class FmiSolarSensorDescription(SensorEntityDescription):
    """Describes an aggregate FMI Solar Forecast sensor."""

    state: Callable[[dict[str, Any]], Any] | None = None


@dataclass(frozen=True)
class FmiSolarGroupSensorDescription(SensorEntityDescription):
    """Describes a per-panel-group FMI Solar Forecast sensor."""

    state: Callable[[dict[str, Any], int], Any] | None = None


# ── Aggregate state extractors ────────────────────────────────────────────────

def _current_power(data: dict) -> float:
    return data.get("current_power_w", 0.0)

def _today_energy(data: dict) -> float:
    return data.get("today_energy_kwh", 0.0) * 1000.0

def _tomorrow_energy(data: dict) -> float:
    return data.get("tomorrow_energy_kwh", 0.0) * 1000.0

def _peak_today(data: dict) -> float:
    return data.get("peak_today_w", 0.0)

def _next_hour_energy(data: dict) -> float:
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


# ── Per-group state extractors ────────────────────────────────────────────────

def _group_current_power(data: dict, group_idx: int) -> float:
    groups = data.get("panel_groups", [])
    if group_idx >= len(groups):
        return 0.0
    forecast_w: dict[str, float] = groups[group_idx].get("forecast_w", {})
    now = datetime.now(tz=timezone.utc)
    for ts_str in sorted(forecast_w):
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if ts >= now:
            return max(0.0, float(forecast_w[ts_str]))
    return 0.0


def _group_today_energy(data: dict, group_idx: int) -> float:
    groups = data.get("panel_groups", [])
    if group_idx >= len(groups):
        return 0.0
    forecast_w: dict[str, float] = groups[group_idx].get("forecast_w", {})
    today = datetime.now(tz=timezone.utc).date()
    total = 0.0
    for ts_str, w in forecast_w.items():
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if ts.date() == today and float(w) > 0:
            total += float(w)
    return round(total, 1)


# ── Sensor descriptors ────────────────────────────────────────────────────────

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

GROUP_SENSORS: tuple[FmiSolarGroupSensorDescription, ...] = (
    FmiSolarGroupSensorDescription(
        key="group_power_now",
        translation_key="group_power_now",
        state=_group_current_power,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
    ),
    FmiSolarGroupSensorDescription(
        key="group_energy_today",
        translation_key="group_energy_today",
        state=_group_today_energy,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
    ),
)


# ── Platform setup ─────────────────────────────────────────────────────────────

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up FMI Solar Forecast sensors."""
    coordinator: FmiSolarForecastCoordinator = entry.runtime_data
    panel_groups = entry.data.get(CONF_PANEL_GROUPS, [])

    # Remove devices for panel groups that have been deleted via the options flow.
    device_reg = dr.async_get(hass)
    group_id_prefix = f"{entry.entry_id}_g"
    for device_entry in dr.async_entries_for_config_entry(device_reg, entry.entry_id):
        for ident_domain, ident_value in device_entry.identifiers:
            if ident_domain != DOMAIN or not ident_value.startswith(group_id_prefix):
                continue
            suffix = ident_value[len(group_id_prefix):]
            if suffix.isdigit() and int(suffix) >= len(panel_groups):
                device_reg.async_remove_device(device_entry.id)

    entities: list = [
        FmiSolarSensorEntity(
            entry=entry,
            coordinator=coordinator,
            entity_description=description,
        )
        for description in SENSORS
    ]

    for i, group in enumerate(panel_groups):
        for description in GROUP_SENSORS:
            entities.append(
                FmiSolarGroupSensorEntity(
                    entry=entry,
                    coordinator=coordinator,
                    entity_description=description,
                    group_index=i,
                    group=group,
                )
            )

    async_add_entities(entities)


# ── Entity classes ─────────────────────────────────────────────────────────────

class FmiSolarSensorEntity(
    CoordinatorEntity[FmiSolarForecastCoordinator], SensorEntity
):
    """Aggregate FMI Solar Forecast sensor (all groups combined)."""

    _attr_has_entity_name = True
    entity_description: FmiSolarSensorDescription

    def __init__(
        self,
        *,
        entry: ConfigEntry,
        coordinator: FmiSolarForecastCoordinator,
        entity_description: FmiSolarSensorDescription,
    ) -> None:
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
        if self.coordinator.data is None:
            return None
        if self.entity_description.state is None:
            return None
        return self.entity_description.state(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"attribution": "Solar forecast powered by FMI"}


class FmiSolarGroupSensorEntity(
    CoordinatorEntity[FmiSolarForecastCoordinator], SensorEntity
):
    """Per-panel-group FMI Solar Forecast sensor."""

    _attr_has_entity_name = True
    entity_description: FmiSolarGroupSensorDescription

    def __init__(
        self,
        *,
        entry: ConfigEntry,
        coordinator: FmiSolarForecastCoordinator,
        entity_description: FmiSolarGroupSensorDescription,
        group_index: int,
        group: dict,
    ) -> None:
        super().__init__(coordinator=coordinator)
        self.entity_description = entity_description
        self._group_index = group_index
        self._attr_unique_id = f"{entry.entry_id}_g{group_index}_{entity_description.key}"
        tilt = group[CONF_TILT]
        azimuth = group[CONF_AZIMUTH]
        power_kw = group[CONF_POWER_KW]
        group_name = group.get(CONF_GROUP_NAME) or f"Group {group_index + 1}"
        installation_name = entry.data.get(CONF_NAME, entry.title)
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, f"{entry.entry_id}_g{group_index}")},
            manufacturer="Finnish Meteorological Institute",
            model=f"Tilt {tilt}° · Azimuth {azimuth}° · {power_kw} kW",
            name=f"{installation_name} {group_name}",
            via_device=(DOMAIN, entry.entry_id),
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        if self.entity_description.state is None:
            return None
        return self.entity_description.state(self.coordinator.data, self._group_index)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"attribution": "Solar forecast powered by FMI"}
