"""Constants for the FMI Solar Forecast integration."""

DOMAIN = "fmi_solar_forecast"

# Config entry keys
CONF_NAME = "name"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_TILT = "tilt"
CONF_AZIMUTH = "azimuth"
CONF_POWER_KW = "power_kw"
CONF_PANEL_GROUPS = "panel_groups"  # list of {name, tilt, azimuth, power_kw}
CONF_GROUP_NAME = "group_name"

# Option keys
CONF_DEFAULT_AIR_TEMP = "default_air_temp"
CONF_DEFAULT_ALBEDO = "default_albedo"
CONF_UPDATE_INTERVAL = "update_interval"

# Defaults
DEFAULT_TILT = 25
DEFAULT_AZIMUTH = 180
DEFAULT_POWER_KW = 5.0
DEFAULT_AIR_TEMP = 10.0
DEFAULT_ALBEDO = 0.2
DEFAULT_UPDATE_INTERVAL = 60  # minutes

# Sensor attributes
ATTR_FORECAST = "forecast"
ATTR_NEXT_HOUR_W = "next_hour_w"
ATTR_TODAY_KWH = "today_kwh"
ATTR_TOMORROW_KWH = "tomorrow_kwh"
ATTR_PEAK_TODAY_W = "peak_today_w"
ATTR_PANEL_GROUPS = "panel_groups"
ATTR_FORECAST_SOURCE = "forecast_source"
ATTR_LAST_UPDATED = "last_updated"
