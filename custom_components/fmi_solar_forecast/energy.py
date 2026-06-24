"""Energy platform for FMI Solar Forecast."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_get_solar_forecast(
    hass: HomeAssistant, config_entry_id: str
) -> dict[str, Any] | None:
    """Return solar forecast for the energy dashboard."""
    if not hass.data.get(DOMAIN):
        _LOGGER.warning("Domain %s is not yet available to provide forecast data", DOMAIN)
        return None

    entry = hass.config_entries.async_get_entry(config_entry_id)
    if entry is None or entry.runtime_data is None:
        return None

    coordinator = entry.runtime_data
    if not hasattr(coordinator, "data") or coordinator.data is None:
        return None

    # Start with persisted history (up to 30 days back)
    wh_hours: dict[str, float] = dict(await coordinator.async_get_history())

    # Overlay current (future) forecast on top
    for slot in coordinator.data.get("forecast", []):
        power = slot.get("power_w", 0.0)
        if power > 0:
            wh_hours[slot["datetime"]] = power

    if not wh_hours:
        return None

    return {"wh_hours": wh_hours}
