# FMI Solar Forecast

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

A Home Assistant integration for solar power forecasting using the Finnish Meteorological Institute (FMI) services.

## Features

- Solar power production forecasts based on FMI weather data
- Configurable location (latitude/longitude)
- Configurable solar panel parameters (peak power, azimuth, tilt)
- Energy dashboard integration
- Automatic updates with configurable polling interval

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Click on "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL and select "Integration" as the category
6. Click "Install"
7. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/fmi_solar_forecast` directory to your Home Assistant's `custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to Settings → Devices & Services
2. Click "+ Add Integration"
3. Search for "FMI Solar Forecast"
4. Follow the configuration steps:
   - Enter your location (latitude and longitude)
   - Configure your solar panel parameters:
     - Peak power (kW)
     - Azimuth (degrees, 0=North, 90=East, 180=South, 270=West)
     - Tilt angle (degrees, 0=horizontal, 90=vertical)
   - Set the update interval (minutes)

## Usage

After configuration, the integration will create sensor entities for:
- Current solar power forecast
- Hourly forecast data
- Daily energy production estimates

These sensors can be used in:
- Energy dashboard
- Automations
- Lovelace cards
- Scripts and templates

## Energy Dashboard Integration

The integration automatically provides energy forecast data that can be used in Home Assistant's Energy dashboard to help visualize expected solar production.

## Support

For issues, feature requests, or contributions, please visit the [GitHub repository](https://github.com/viljasenville/fmi_solar_forecast).

## Credits

This integration uses the [FMI Open PV Forecast](https://github.com/fmidev/fmi-open-pv-forecast-packaged) library and services provided by the Finnish Meteorological Institute.

The FMI logo used as the integration icon is the property of the Finnish Meteorological Institute (Ilmatieteen laitos). All rights to the logo belong to FMI.

## License

This project is licensed under the Apache 2.0 License - see the LICENSE file for details.
