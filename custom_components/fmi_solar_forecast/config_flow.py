"""Config flow for FMI Solar Forecast integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_AZIMUTH,
    CONF_DEFAULT_AIR_TEMP,
    CONF_DEFAULT_ALBEDO,
    CONF_GROUP_NAME,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_PANEL_GROUPS,
    CONF_POWER_KW,
    CONF_TILT,
    CONF_UPDATE_INTERVAL,
    DEFAULT_AIR_TEMP,
    DEFAULT_ALBEDO,
    DEFAULT_AZIMUTH,
    DEFAULT_POWER_KW,
    DEFAULT_TILT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _format_groups_summary(groups: list[dict]) -> str:
    if not groups:
        return "No panel groups configured."
    lines = []
    for i, g in enumerate(groups, 1):
        name = g.get(CONF_GROUP_NAME) or f"Group {i}"
        lines.append(
            f"{name}: {g[CONF_TILT]}° tilt, {g[CONF_AZIMUTH]}° azimuth, {g[CONF_POWER_KW]} kW"
        )
    return "\n".join(lines)


class FmiSolarForecastConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for FMI Solar Forecast."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}
        self._panel_groups: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step: name and location."""
        errors: dict[str, str] = {}

        default_lat = self.hass.config.latitude
        default_lon = self.hass.config.longitude

        if user_input is not None:
            lat = user_input[CONF_LATITUDE]
            lon = user_input[CONF_LONGITUDE]
            if not (54.0 <= lat <= 72.0 and 4.0 <= lon <= 32.0):
                errors["base"] = "outside_coverage"
            else:
                self._data.update(user_input)
                return await self.async_step_panel_group()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="Home Solar"): str,
                vol.Required(CONF_LATITUDE, default=round(default_lat, 6)): vol.All(
                    vol.Coerce(float), vol.Range(min=54.0, max=72.0)
                ),
                vol.Required(CONF_LONGITUDE, default=round(default_lon, 6)): vol.All(
                    vol.Coerce(float), vol.Range(min=4.0, max=32.0)
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "coverage": "Finland, Scandinavia, and Baltic countries (lat 54–72°N, lon 4–32°E)"
            },
        )

    async def async_step_panel_group(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure a panel group (tilt, azimuth, power)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._panel_groups.append(
                {
                    CONF_GROUP_NAME: user_input[CONF_GROUP_NAME],
                    CONF_TILT: user_input[CONF_TILT],
                    CONF_AZIMUTH: user_input[CONF_AZIMUTH],
                    CONF_POWER_KW: user_input[CONF_POWER_KW],
                }
            )
            if user_input.get("add_another", False):
                return await self.async_step_panel_group()

            self._data[CONF_PANEL_GROUPS] = self._panel_groups
            return await self.async_step_options()

        group_num = len(self._panel_groups) + 1
        schema = vol.Schema(
            {
                vol.Required(CONF_GROUP_NAME, default=f"Group {group_num}"): str,
                vol.Required(CONF_TILT, default=DEFAULT_TILT): vol.All(
                    vol.Coerce(float), vol.Range(min=0, max=90)
                ),
                vol.Required(CONF_AZIMUTH, default=DEFAULT_AZIMUTH): vol.All(
                    vol.Coerce(float), vol.Range(min=0, max=360)
                ),
                vol.Required(CONF_POWER_KW, default=DEFAULT_POWER_KW): vol.All(
                    vol.Coerce(float), vol.Range(min=0.1, max=1000)
                ),
                vol.Optional("add_another", default=False): bool,
            }
        )

        return self.async_show_form(
            step_id="panel_group",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "group_num": str(group_num),
                "azimuth_hint": "0=N, 90=E, 180=S (default), 270=W",
                "tilt_hint": "0=flat, 90=vertical. Typical roof: 15–35°",
            },
        )

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure optional parameters."""
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(
                title=self._data[CONF_NAME], data=self._data
            )

        schema = vol.Schema(
            {
                vol.Optional(CONF_DEFAULT_AIR_TEMP, default=DEFAULT_AIR_TEMP): vol.All(
                    vol.Coerce(float), vol.Range(min=-40, max=50)
                ),
                vol.Optional(CONF_DEFAULT_ALBEDO, default=DEFAULT_ALBEDO): vol.All(
                    vol.Coerce(float), vol.Range(min=0.0, max=1.0)
                ),
                vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.All(
                    vol.Coerce(int), vol.Range(min=30, max=360)
                ),
            }
        )

        return self.async_show_form(
            step_id="options",
            data_schema=schema,
            description_placeholders={
                "air_temp_hint": "Default air temperature for clear-sky fallback (°C)",
                "albedo_hint": "Ground reflectivity 0–1 (snow=0.7, grass=0.2)",
                "update_hint": "How often to refresh the forecast (minutes, min 30)",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> FmiSolarOptionsFlow:
        """Return the options flow."""
        return FmiSolarOptionsFlow()


class FmiSolarOptionsFlow(config_entries.OptionsFlow):
    """Options flow for reconfiguring FMI Solar Forecast."""

    def __init__(self) -> None:
        """Initialize the options flow."""
        self._settings: dict[str, Any] = {}
        self._panel_groups: list[dict] = []
        self._original_groups: list[dict] = []
        self._group_index: int = 0

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options — name, location, and advanced settings."""
        data = self.config_entry.data
        errors: dict[str, str] = {}

        if user_input is not None:
            lat = user_input[CONF_LATITUDE]
            lon = user_input[CONF_LONGITUDE]
            if not (54.0 <= lat <= 72.0 and 4.0 <= lon <= 32.0):
                errors["base"] = "outside_coverage"
            else:
                self._settings = dict(user_input)
                self._original_groups = list(data.get(CONF_PANEL_GROUPS, []))
                self._panel_groups = []
                self._group_index = 0
                return await self.async_step_panel_group()

        existing_groups = data.get(CONF_PANEL_GROUPS, [])
        groups_summary = _format_groups_summary(existing_groups)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME,
                    default=data.get(CONF_NAME, "Home Solar"),
                ): str,
                vol.Required(
                    CONF_LATITUDE,
                    default=data.get(CONF_LATITUDE, round(self.hass.config.latitude, 6)),
                ): vol.All(vol.Coerce(float), vol.Range(min=54.0, max=72.0)),
                vol.Required(
                    CONF_LONGITUDE,
                    default=data.get(CONF_LONGITUDE, round(self.hass.config.longitude, 6)),
                ): vol.All(vol.Coerce(float), vol.Range(min=4.0, max=32.0)),
                vol.Optional(
                    CONF_DEFAULT_AIR_TEMP,
                    default=data.get(CONF_DEFAULT_AIR_TEMP, DEFAULT_AIR_TEMP),
                ): vol.All(vol.Coerce(float), vol.Range(min=-40, max=50)),
                vol.Optional(
                    CONF_DEFAULT_ALBEDO,
                    default=data.get(CONF_DEFAULT_ALBEDO, DEFAULT_ALBEDO),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=1.0)),
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=30, max=360)),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
            description_placeholders={"panel_groups": groups_summary},
        )

    async def async_step_panel_group(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit or add a panel group."""
        errors: dict[str, str] = {}
        is_editing = self._group_index < len(self._original_groups)

        if user_input is not None:
            if is_editing:
                if not user_input.get("delete_group", False):
                    self._panel_groups.append(
                        {
                            CONF_GROUP_NAME: user_input[CONF_GROUP_NAME],
                            CONF_TILT: user_input[CONF_TILT],
                            CONF_AZIMUTH: user_input[CONF_AZIMUTH],
                            CONF_POWER_KW: user_input[CONF_POWER_KW],
                        }
                    )
                self._group_index += 1
                if self._group_index < len(self._original_groups):
                    return await self.async_step_panel_group()
                if user_input.get("add_another", False):
                    return await self.async_step_panel_group()
                if not self._panel_groups:
                    errors["base"] = "at_least_one_group"
                    # Fall through to show the new-group form with error
                else:
                    return self._finish()
            else:
                self._panel_groups.append(
                    {
                        CONF_GROUP_NAME: user_input[CONF_GROUP_NAME],
                        CONF_TILT: user_input[CONF_TILT],
                        CONF_AZIMUTH: user_input[CONF_AZIMUTH],
                        CONF_POWER_KW: user_input[CONF_POWER_KW],
                    }
                )
                if user_input.get("add_another", False):
                    return await self.async_step_panel_group()
                return self._finish()

        # Re-evaluate after potential index increment
        is_editing = self._group_index < len(self._original_groups)

        if is_editing:
            src = self._original_groups[self._group_index]
            name_d = src.get(CONF_GROUP_NAME, f"Group {self._group_index + 1}")
            tilt_d = src[CONF_TILT]
            azimuth_d = src[CONF_AZIMUTH]
            power_d = src[CONF_POWER_KW]
            group_context = f"Editing group {self._group_index + 1} of {len(self._original_groups)}"
        else:
            new_num = len(self._panel_groups) + 1
            name_d = f"Group {new_num}"
            tilt_d = DEFAULT_TILT
            azimuth_d = DEFAULT_AZIMUTH
            power_d = DEFAULT_POWER_KW
            group_context = f"Adding new group {new_num}"

        schema_fields: dict = {
            vol.Required(CONF_GROUP_NAME, default=name_d): str,
            vol.Required(CONF_TILT, default=tilt_d): vol.All(
                vol.Coerce(float), vol.Range(min=0, max=90)
            ),
            vol.Required(CONF_AZIMUTH, default=azimuth_d): vol.All(
                vol.Coerce(float), vol.Range(min=0, max=360)
            ),
            vol.Required(CONF_POWER_KW, default=power_d): vol.All(
                vol.Coerce(float), vol.Range(min=0.1, max=1000)
            ),
        }
        if is_editing:
            schema_fields[vol.Optional("delete_group", default=False)] = bool
        schema_fields[vol.Optional("add_another", default=False)] = bool

        return self.async_show_form(
            step_id="panel_group",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
            description_placeholders={
                "group_context": group_context,
                "azimuth_hint": "0=N, 90=E, 180=S (default), 270=W",
                "tilt_hint": "0=flat, 90=vertical. Typical roof: 15–35°",
            },
        )

    def _finish(self) -> FlowResult:
        return self.async_create_entry(
            title="",
            data={**self._settings, CONF_PANEL_GROUPS: self._panel_groups},
        )
