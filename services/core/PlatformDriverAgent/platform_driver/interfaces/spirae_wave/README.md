# Spirae Wave Interface Driver

This driver provides integration with Spirae Wave energy management systems through their REST API.

## Features

- **Auto-discovery**: Automatically discovers all assets and their properties from the Spirae Wave system
- **Dynamic register generation**: Creates VOLTTRON registers dynamically based on discovered assets
- **Token-based authentication**: Handles authentication and automatic token refresh
- **Asset filtering**: Optional filtering to limit data collection to specific assets/properties
- **Robust error handling**: Includes retry logic and graceful error recovery
- **SSL support**: Configurable SSL verification for secure connections

## Configuration

### Driver Configuration

The driver requires the following configuration parameters:

```json
{
    "driver_config": {
        "url": "https://localhost:18080",      // Base URL of the Spirae Wave system
        "username": "admin",                    // Authentication username
        "password": "admin",                    // Authentication password
        "verify_ssl": false,                    // SSL certificate verification (optional, default: true)
        "timeout": 30,                          // Request timeout in seconds (optional, default: 30)
        "asset_property_map": {                 // Optional asset/property filtering
            "system": [                         // List specific properties to collect
                "System_frequency",
                "System_voltage"
            ],
            "bess": null                        // null means collect all properties for this asset
        }
    },
    "driver_type": "spirae_wave",
    "registry_config": "config://spirae_wave.csv",  // Optional registry override
    "interval": 60,
    "timezone": "US/Pacific"
}
```

### Asset Property Map

The `asset_property_map` parameter allows you to filter which assets and properties are collected:

- **Omit the parameter**: Collect all assets and all their properties
- **Empty object `{}`**: Collect no assets
- **Asset with null value**: Collect all properties for that asset
- **Asset with property list**: Only collect specified properties for that asset

Examples:

```json
// Collect everything (default behavior)
"asset_property_map": null

// Collect only system frequency and voltage
"asset_property_map": {
    "system": ["System_frequency", "System_voltage"]
}

// Collect all system properties and specific BESS properties
"asset_property_map": {
    "system": null,
    "bess": ["ESS_breakerStatus", "ESS_totalCapacity"]
}
```

## Auto-Discovery Process

When the driver starts, it:

1. Authenticates with the Spirae Wave system
2. Fetches the list of available assets from `/assets`
3. For each asset, queries the following endpoints:
   - `/assets/{asset}/properties` - Configuration and command properties
   - `/assets/{asset}/status` - Status information
   - `/assets/{asset}/quickview` - Quick view data
4. Creates VOLTTRON registers for each discovered property
5. Properties in the "Command Info" group are marked as writable

## Register Naming Convention

Registers are automatically named using the pattern: `{asset_name}/{property_name}`

For example:
- `system/System_frequency`
- `bess/ESS_totalCapacity`
- `pv1/PV_activePowerReading`

## Registry Configuration Override

While the driver auto-discovers all registers, you can provide an optional CSV registry file to:
- Override auto-discovered settings (e.g., mark additional points as writable)
- Define custom Volttron point names
- Add additional metadata

Example registry CSV:

```csv
Point Name,Volttron Point Name,Units,Writable,Description
system/System_frequency,frequency,Hz,FALSE,System frequency
system/System_reset,reset_command,,TRUE,Reset system alarms
bess/ESS_totalCapacity,bess_capacity,kW,FALSE,Total BESS capacity
```

## Usage Examples

### Basic Configuration (Auto-discover everything)

```json
{
    "driver_config": {
        "url": "https://192.168.1.100:18080",
        "username": "operator",
        "password": "secure_password"
    },
    "driver_type": "spirae_wave",
    "interval": 30
}
```

### Filtered Configuration (Specific assets/properties)

```json
{
    "driver_config": {
        "url": "https://192.168.1.100:18080",
        "username": "operator",
        "password": "secure_password",
        "asset_property_map": {
            "system": [
                "System_frequency",
                "System_voltage",
                "System_activeLoad"
            ],
            "bess": [
                "ESS_breakerStatus",
                "ESS_totalCapacity"
            ]
        }
    },
    "driver_type": "spirae_wave",
    "interval": 60
}
```

### Development/Testing Configuration

```json
{
    "driver_config": {
        "url": "https://localhost:18080",
        "username": "admin",
        "password": "admin",
        "verify_ssl": false,
        "timeout": 10
    },
    "driver_type": "spirae_wave",
    "interval": 5
}
```

## Error Handling

The driver includes comprehensive error handling:

- **Authentication failures**: Automatic re-authentication when tokens expire
- **Network errors**: Graceful handling of timeouts and connection issues
- **Invalid responses**: Logging and partial data return when possible
- **SSL errors**: Configurable SSL verification for development environments

## Logging

The driver uses the standard Python logging module. Enable debug logging to see:
- Authentication flow
- Asset discovery process
- Register creation details
- API request/response information

To enable debug logging, set the logging level for the module:
```python
logging.getLogger('platform_driver.interfaces.spirae_wave').setLevel(logging.DEBUG)
```

## Testing

The driver can be tested using the provided sample data files:
- `endpoints.json`: Sample endpoint responses
- `assets.json`: Sample asset list
- `scratch.py`: Example authentication and data fetching code

## Troubleshooting

### Common Issues

1. **SSL Certificate Errors**
   - Set `"verify_ssl": false` for self-signed certificates
   - Ensure the system has proper CA certificates installed

2. **Authentication Failures**
   - Verify username and password
   - Check network connectivity to the Spirae Wave system
   - Ensure the user has appropriate permissions

3. **Missing Data Points**
   - Check the asset_property_map configuration
   - Verify the asset/property exists in the system
   - Review debug logs for discovery issues

4. **Timeout Errors**
   - Increase the timeout value in configuration
   - Check network latency to the Spirae Wave system
   - Verify the system is not overloaded