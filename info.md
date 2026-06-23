# FMI Solar Forecast

Solar power forecasting integration using the Finnish Meteorological Institute (FMI) services.

## Features

- ☀️ Solar power production forecasts based on FMI weather data
- 📍 Configurable location (latitude/longitude)
- ⚡ Configurable solar panel parameters (peak power, azimuth, tilt)
- 📊 Energy dashboard integration
- 🔄 Automatic updates with configurable polling interval

## Configuration

After installation, add the integration through:

**Settings** → **Devices & Services** → **Add Integration** → **FMI Solar Forecast**

You'll need to provide:
- **Location**: Latitude and longitude of your solar panels
- **Peak Power**: Maximum power output of your solar system (kW)
- **Azimuth**: Panel orientation (0°=North, 90°=East, 180°=South, 270°=West)
- **Tilt**: Panel angle from horizontal (0°=flat, 90°=vertical)
- **Update Interval**: How often to fetch new forecasts (minutes)

## Sensors

The integration provides:
- Current solar power forecast
- Hourly forecast data
- Daily energy production estimates

Forecast is compatible with Home Assistant's Energy dashboard.
