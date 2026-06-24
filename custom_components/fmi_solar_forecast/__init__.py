"""FMI Solar Forecast integration for Home Assistant."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .coordinator import FmiSolarForecastCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

SERVICE_CLEAR_HISTORY = "clear_history"
SERVICE_REFRESH_FORECAST = "refresh_forecast"
_ATTR_ENTRY_ID = "config_entry_id"

_CLEAR_HISTORY_SCHEMA = vol.Schema({vol.Optional(_ATTR_ENTRY_ID): cv.string})
_REFRESH_FORECAST_SCHEMA = vol.Schema({vol.Optional(_ATTR_ENTRY_ID): cv.string})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up FMI Solar Forecast from a config entry."""
    coordinator = FmiSolarForecastCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    if not hass.services.has_service(DOMAIN, SERVICE_CLEAR_HISTORY):

        async def _handle_clear_history(call: ServiceCall) -> None:
            entry_id: str | None = call.data.get(_ATTR_ENTRY_ID)
            coordinators: dict[str, FmiSolarForecastCoordinator] = hass.data.get(DOMAIN, {})
            targets = (
                [coordinators[entry_id]]
                if entry_id and entry_id in coordinators
                else list(coordinators.values())
            )
            for coord in targets:
                await coord.async_clear_history()

        hass.services.async_register(
            DOMAIN,
            SERVICE_CLEAR_HISTORY,
            _handle_clear_history,
            schema=_CLEAR_HISTORY_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_FORECAST):

        async def _handle_refresh_forecast(call: ServiceCall) -> None:
            entry_id: str | None = call.data.get(_ATTR_ENTRY_ID)
            coordinators: dict[str, FmiSolarForecastCoordinator] = hass.data.get(DOMAIN, {})
            targets = (
                [coordinators[entry_id]]
                if entry_id and entry_id in coordinators
                else list(coordinators.values())
            )
            for coord in targets:
                await coord.async_request_refresh()

        hass.services.async_register(
            DOMAIN,
            SERVICE_REFRESH_FORECAST,
            _handle_refresh_forecast,
            schema=_REFRESH_FORECAST_SCHEMA,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data.get(DOMAIN):
            hass.services.async_remove(DOMAIN, SERVICE_CLEAR_HISTORY)
            hass.services.async_remove(DOMAIN, SERVICE_REFRESH_FORECAST)
    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle config entry option updates — merge options into data and reload."""
    if entry.options:
        updated_data = {**entry.data, **entry.options}
        hass.config_entries.async_update_entry(entry, data=updated_data, options={})
    await hass.config_entries.async_reload(entry.entry_id)
