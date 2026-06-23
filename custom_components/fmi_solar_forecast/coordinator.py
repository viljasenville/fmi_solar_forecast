"""Data update coordinator for FMI Solar Forecast."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_DEFAULT_AIR_TEMP,
    CONF_DEFAULT_ALBEDO,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_PANEL_GROUPS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_AIR_TEMP,
    DEFAULT_ALBEDO,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# fmi_pv_forecaster uses module-level global state for location, angles, and
# the FMI weather cache. A process-wide lock ensures that when multiple config
# entries exist, their executor jobs never interleave and corrupt each other's
# configuration or share a wrong cached weather fetch.
_PVFC_LOCK = threading.Lock()


class FmiSolarForecastCoordinator(DataUpdateCoordinator):
    """Coordinator that fetches and caches FMI solar forecast data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        update_interval = timedelta(
            minutes=entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch fresh forecast data from FMI in a thread-safe executor job."""
        try:
            return await self.hass.async_add_executor_job(self._fetch_forecast)
        except Exception as err:
            raise UpdateFailed(f"FMI forecast update failed: {err}") from err

    def _fetch_forecast(self) -> dict[str, Any]:
        """Blocking forecast fetch — runs in executor, protected by a global lock."""
        try:
            import fmi_pv_forecaster as pvfc
        except ImportError as exc:
            raise UpdateFailed(
                "fmi_pv_forecaster not installed. "
                "See integration docs for install instructions."
            ) from exc

        cfg = self.entry.data
        lat = cfg[CONF_LATITUDE]
        lon = cfg[CONF_LONGITUDE]
        panel_groups: list[dict] = cfg.get(CONF_PANEL_GROUPS, [])
        default_temp = cfg.get(CONF_DEFAULT_AIR_TEMP, DEFAULT_AIR_TEMP)
        default_albedo = cfg.get(CONF_DEFAULT_ALBEDO, DEFAULT_ALBEDO)

        with _PVFC_LOCK:
            # Set this entry's location and defaults, then clear the shared
            # FMI weather cache so we fetch fresh data for this location.
            pvfc.set_location(lat, lon)
            pvfc.set_default_air_temp(default_temp)
            pvfc.set_default_albedo(default_albedo)
            pvfc.force_clear_fmi_cache()

            combined_output = None
            group_results = []

            for group in panel_groups:
                pvfc.set_angles(group["tilt"], group["azimuth"])
                pvfc.set_nominal_power_kw(group["power_kw"])

                df = pvfc.get_default_fmi_forecast()
                output_series = df["output"].fillna(0.0)

                group_results.append(
                    {
                        "tilt": group["tilt"],
                        "azimuth": group["azimuth"],
                        "power_kw": group["power_kw"],
                        "forecast_w": {
                            str(ts): round(float(w), 2)
                            for ts, w in output_series.items()
                        },
                    }
                )

                if combined_output is None:
                    combined_output = output_series.copy()
                else:
                    combined_output = combined_output.add(output_series, fill_value=0.0)

        if combined_output is None:
            raise UpdateFailed("No panel groups configured")

        # ── Derive aggregated values ──────────────────────────────────────
        now_utc = datetime.now(tz=timezone.utc)
        today_utc = now_utc.date()
        tomorrow_utc = today_utc + timedelta(days=1)

        current_w = 0.0
        for ts, w in zip(combined_output.index.to_pydatetime(), combined_output.values):
            ts_aware = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
            if ts_aware >= now_utc:
                current_w = float(w)
                break

        def _kwh_for_date(date) -> float:
            total = 0.0
            for ts, w in combined_output.items():
                ts_date = ts.date() if hasattr(ts, "date") else ts.to_pydatetime().date()
                if ts_date == date:
                    total += float(w) if float(w) > 0 else 0.0
            return round(total / 1000.0, 3)

        today_kwh = _kwh_for_date(today_utc)
        tomorrow_kwh = _kwh_for_date(tomorrow_utc)

        peak_today_w = 0.0
        for ts, w in combined_output.items():
            ts_date = ts.date() if hasattr(ts, "date") else ts.to_pydatetime().date()
            if ts_date == today_utc:
                peak_today_w = max(peak_today_w, float(w))

        forecast = []
        for ts, w in combined_output.items():
            ts_aware = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
            forecast.append(
                {
                    "datetime": ts_aware.isoformat(),
                    "power_w": round(float(w), 1) if float(w) > 0 else 0.0,
                    "power_kw": round(float(w) / 1000.0, 4) if float(w) > 0 else 0.0,
                }
            )

        return {
            "current_power_w": round(current_w, 1),
            "today_energy_kwh": today_kwh,
            "tomorrow_energy_kwh": tomorrow_kwh,
            "peak_today_w": round(peak_today_w, 1),
            "forecast": forecast,
            "panel_groups": group_results,
            "last_updated": now_utc.isoformat(),
            "forecast_source": "FMI open data",
        }
