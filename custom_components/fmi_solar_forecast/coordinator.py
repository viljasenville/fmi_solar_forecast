"""Data update coordinator for FMI Solar Forecast."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
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


def _parse_dt(dt_str: str) -> datetime:
    """Parse an ISO datetime string and ensure it is UTC-aware."""
    dt = datetime.fromisoformat(dt_str)
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


class FmiSolarForecastCoordinator(DataUpdateCoordinator):
    """Coordinator that fetches and caches FMI solar forecast data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self._store: Store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.history")
        update_interval = timedelta(
            minutes=entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )

    async def async_get_history(self) -> dict[str, float]:
        """Return persisted history as {iso_datetime: power_w}."""
        stored = await self._store.async_load() or {}
        return stored.get("wh_hours", {})

    async def async_clear_history(self) -> None:
        """Wipe the persisted history store."""
        await self._store.async_save({"wh_hours": {}, "group_wh_hours": {}})
        _LOGGER.info("Solar forecast history cleared for entry %s", self.entry.entry_id)

    async def _async_archive_past_slots(self) -> None:
        """Persist forecast slots that have now passed into the history store."""
        if not self.data:
            return

        now_utc = datetime.now(tz=timezone.utc)
        cutoff = now_utc - timedelta(days=30)

        stored = await self._store.async_load() or {}
        history: dict[str, float] = stored.get("wh_hours", {})
        group_history: dict[str, dict[str, float]] = stored.get("group_wh_hours", {})

        for slot in self.data.get("forecast", []):
            dt_str: str = slot["datetime"]
            power_w = slot["power_w"]
            try:
                dt = datetime.fromisoformat(dt_str)
            except ValueError:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            # Only write non-zero values: the FMI API returns 0.0 for past
            # hours it no longer forecasts, which would overwrite valid history.
            if cutoff <= dt < now_utc and power_w > 0:
                history[dt_str] = power_w

        for gi, group_data in enumerate(self.data.get("panel_groups", [])):
            gh = group_history.setdefault(str(gi), {})
            for dt_str, w in group_data.get("forecast_w", {}).items():
                try:
                    dt = _parse_dt(dt_str)
                except ValueError:
                    continue
                if cutoff <= dt < now_utc and w > 0:
                    gh[dt.isoformat()] = w

        # Prune entries older than 30 days
        history = {k: v for k, v in history.items() if _parse_dt(k) >= cutoff}
        group_history = {
            gi: {k: v for k, v in gh.items() if _parse_dt(k) >= cutoff}
            for gi, gh in group_history.items()
        }

        await self._store.async_save({"wh_hours": history, "group_wh_hours": group_history})

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch fresh forecast data from FMI in a thread-safe executor job."""
        await self._async_archive_past_slots()
        try:
            result = await self.hass.async_add_executor_job(self._fetch_forecast)
        except Exception as err:
            raise UpdateFailed(f"FMI forecast update failed: {err}") from err

        # The FMI forecast only contains future slots, so today_energy_kwh,
        # peak_today_w, and per-group forecast_w shrink as the day progresses.
        # Re-inject past-of-today slots from the history store.
        stored = await self._store.async_load() or {}
        history: dict[str, float] = stored.get("wh_hours", {})
        group_history: dict[str, dict[str, float]] = stored.get("group_wh_hours", {})
        now_utc = datetime.now(tz=timezone.utc)
        today_utc = now_utc.date()

        # Only claim slots where the API returned real data (power_w > 0).
        # The API time series can include past hours with 0W (outside its 3-6h
        # retrospective window); those must not block genuine history values.
        forecast_dts = {
            slot["datetime"]
            for slot in result.get("forecast", [])
            if slot["power_w"] > 0
        }
        extra_w_sum = 0.0
        extra_peak_w = 0.0
        for dt_str, power_w in history.items():
            if dt_str in forecast_dts:
                continue
            try:
                dt = _parse_dt(dt_str)
            except ValueError:
                continue
            if dt.date() == today_utc:
                extra_w_sum += power_w
                extra_peak_w = max(extra_peak_w, power_w)

        result["today_energy_kwh"] = round(
            result["today_energy_kwh"] + extra_w_sum / 1000.0, 3
        )
        result["peak_today_w"] = round(
            max(result["peak_today_w"], extra_peak_w), 1
        )

        for gi, group_data in enumerate(result.get("panel_groups", [])):
            gh = group_history.get(str(gi), {})
            if not gh:
                continue
            existing_dts = set(group_data["forecast_w"])
            for dt_str, w in gh.items():
                if dt_str in existing_dts:
                    continue
                try:
                    dt = _parse_dt(dt_str)
                except ValueError:
                    continue
                if dt.date() == today_utc:
                    group_data["forecast_w"][dt_str] = w

        return result

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
                            (ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)).isoformat(): round(float(w), 2)
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
