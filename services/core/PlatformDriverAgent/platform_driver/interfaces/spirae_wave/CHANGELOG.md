# Spirae Wave Interface Driver Changelog

## [1.0.0] - 2025-01-14

### Initial Release

#### Features
- **Auto-discovery**: Automatically discovers all assets and their properties from the Spirae Wave REST API
- **Dynamic register generation**: Creates VOLTTRON registers dynamically based on discovered assets
- **Token-based authentication**: Handles authentication with automatic token refresh
- **Asset filtering**: Optional filtering to limit data collection to specific assets/properties
- **String value filtering**: `collect_string_values` flag to control collection of non-numeric data
- **Robust error handling**: Includes retry logic and graceful error recovery
- **SSL support**: Configurable SSL verification for secure connections
- **Async operations**: Uses grequests for non-blocking HTTP requests in gevent context
- **Batch scraping**: Efficiently fetches all points using parallel requests

#### Configuration Options
- `url` - Base URL of the Spirae Wave system
- `username` - Authentication username
- `password` - Authentication password  
- `verify_ssl` - SSL certificate verification (default: true)
- `timeout` - Request timeout in seconds (default: 30)
- `collect_string_values` - Collect string values (default: true)
- `asset_property_map` - Optional asset/property filtering map

#### Type Conversion
- Boolean values are converted to floats (true → 1.0, false → 0.0)
- Numeric values are returned as floats for consistency
- String values can be filtered out when `collect_string_values` is false

#### Dependencies
- `grequests>=0.6.0` - For async HTTP requests in gevent context
- `requests>=2.28.0` - HTTP library
- `gevent>=21.0.0` - Coroutine-based Python networking library

#### Compatibility
- Python 3.8 or higher
- VOLTTRON Platform Driver 4.6.2+

---

## Usage Example

```json
{
    "driver_config": {
        "url": "https://192.168.1.100:18080",
        "username": "operator",
        "password": "secure_password",
        "verify_ssl": false,
        "collect_string_values": false,
        "asset_property_map": {
            "system": ["System_frequency", "System_voltage"],
            "bess": null
        }
    },
    "driver_type": "spirae_wave",
    "interval": 60
}
```