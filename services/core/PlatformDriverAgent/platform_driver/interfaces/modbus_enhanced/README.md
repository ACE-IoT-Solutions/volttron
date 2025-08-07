# Enhanced Modbus Driver for VOLTTRON

## Overview

The Enhanced Modbus Driver is a comprehensive redesign of the VOLTTRON modbus interface that addresses the limitations of both the legacy `modbus` and `modbus_tk` drivers. This driver provides industrial-grade support for complex modbus deployments with multiple unit devices, gateway management, and advanced configuration templating.

## Key Features

### 1. Multi-Unit Gateway Support
- **Single TCP socket per gateway**: Critical for constrained TCP-to-RTU bridges
- **Multiple units per bus**: Support all units (0-255) on a single RTU/ASCII bus
- **Serialized access**: Prevent concurrent operations that could confuse the gateway

### 2. Connection Types
- **TCP/IP**: Full support for Modbus TCP with connection pooling
- **Serial RTU**: Complete serial RTU support with configurable parameters
- **Mixed deployments**: Support both TCP and serial connections simultaneously

### 3. Advanced Configuration
- **Template system**: Define device templates for easy deployment of similar devices
- **Bulk configuration**: Generate configurations for hundreds of devices with simple commands
- **Backward compatibility**: Seamlessly works with existing modbus configurations

### 4. Gateway Architecture
- **TCP-to-RTU bridges**: Each gateway is a bridge device managing one RTU bus
- **Unit addressing**: Unit IDs (0-255) are unique only within each bus
- **Constrained gateway support**: Single TCP socket for gateways with limited resources
- **Register batching**: Automatically merge adjacent registers for efficient reading
- **Intelligent retry logic**: Exponential backoff and configurable retry attempts

### 5. Health Monitoring
- **Device health tracking**: Monitor online/offline status of each unit
- **Gateway health**: Track gateway connection status and errors
- **Connection statistics**: Monitor pool usage and performance metrics

## Architecture Comparison

### Legacy Drivers Limitations

| Feature | modbus.py | modbus_tk | Enhanced |
|---------|-----------|-----------|----------|
| Serial Support | ❌ | ✅ | ✅ |
| TCP Support | ✅ | ✅ | ✅ |
| Multi-unit per gateway | ❌ | ❌ | ✅ |
| Single socket per gateway | ❌ | ❌ | ✅ |
| Serialized bus access | ❌ | ❌ | ✅ |
| Template system | ❌ | ❌ | ✅ |
| Gateway abstraction | ❌ | ❌ | ✅ |
| Health monitoring | ❌ | ❌ | ✅ |
| Bulk configuration | ❌ | ❌ | ✅ |

## VOLTTRON Integration Approaches

The driver supports two deployment patterns in VOLTTRON:

### 1. Gateway as Device (Recommended for constrained gateways)

Configure the gateway as a VOLTTRON device with multiple units, each having its own set of points:

```json
{
    "driver_type": "modbus_enhanced",
    "driver_config": {
        "gateway": {
            "connection_type": "tcp",
            "address": "192.168.1.100",
            "port": 502
        },
        "units": [
            {"unit_id": 1, "name": "power_meter_1"},
            {"unit_id": 2, "name": "power_meter_2"},
            {"unit_id": 3, "name": "temperature_sensor"}
        ]
    },
    "registry_config": {
        "1": "config://gateway1_unit1_registers.csv",
        "2": "config://gateway1_unit2_registers.csv",
        "3": "config://gateway1_unit3_registers.csv"
    }
}
```

Points will be named: `power_meter_1.voltage`, `power_meter_2.current`, etc.

### 2. Unit as Device (More granular control)

Configure each unit as a separate VOLTTRON device. The driver uses a singleton to share the TCP connection:

```json
{
    "driver_type": "modbus_enhanced",
    "driver_config": {
        "gateway": {
            "connection_type": "tcp",
            "address": "192.168.1.100",
            "port": 502
        },
        "unit_id": 1
    },
    "registry_config": "config://unit1_registers.csv"
}
```

Multiple devices on the same gateway will automatically share the TCP socket through the singleton pattern.

## Installation

The enhanced modbus driver is located in:
```
services/core/PlatformDriverAgent/platform_driver/interfaces/modbus_enhanced/
```

No additional dependencies are required beyond the standard VOLTTRON modbus dependencies (pymodbus).

## Configuration Format

### Enhanced Format (Multi-Unit Gateway)

```json
{
    "driver_type": "modbus_enhanced",
    "driver_config": {
        "gateway": {
            "connection_type": "tcp",
            "address": "192.168.1.100",
            "port": 502,
            "retry_attempts": 3,
            "retry_backoff": "exponential"
        },
        "units": [
            {
                "unit_id": 1,
                "name": "power_meter_1",
                "template": "power_meter_basic",
                "register_offset": 0
            },
            {
                "unit_id": 2,
                "name": "power_meter_2",
                "template": "power_meter_basic",
                "register_offset": 0
            }
        ]
    },
    "device_templates": {
        "power_meter_basic": {
            "registers": [
                {"name": "voltage", "address": 100, "type": "float", "units": "V"},
                {"name": "current", "address": 102, "type": "float", "units": "A"},
                {"name": "power", "address": 104, "type": "float", "units": "kW"}
            ]
        }
    }
}
```

### Legacy Format (Backward Compatible)

The enhanced driver automatically detects and supports legacy configuration formats. It accepts both 'slave_id'/'slaves' and 'unit_id'/'units' keys for seamless migration:

```json
{
    "driver_type": "modbus_enhanced",
    "driver_config": {
        "device_address": "192.168.1.100",
        "port": 502,
        "unit_id": 1
    },
    "registry_config": "config://modbus_registers.csv"
}
```

## Migration Guide

### From modbus.py Driver

1. Change `driver_type` from `"modbus"` to `"modbus_enhanced"`
2. No other changes required - the driver is fully backward compatible
3. Optionally convert to enhanced format for multi-unit support

### From modbus_tk Driver

1. Change import from `modbus_tk` to `modbus_enhanced` in the interface path
2. Existing configurations work without modification
3. Serial configurations are fully supported

### Migration Example

**Before (modbus.py):**
```json
{
    "driver_type": "modbus",
    "driver_config": {
        "device_address": "192.168.1.100",
        "port": 502,
        "unit_id": 1
    }
}
```

**After (enhanced with multi-unit):**
```json
{
    "driver_type": "modbus_enhanced",
    "driver_config": {
        "gateway": {
            "connection_type": "tcp",
            "address": "192.168.1.100",
            "port": 502
        },
        "units": [
            {"unit_id": 1, "name": "device_1", "template": "my_template"},
            {"unit_id": 2, "name": "device_2", "template": "my_template"},
            {"unit_id": 3, "name": "device_3", "template": "my_template"}
        ]
    }
}
```

## Configuration Generator Tool

The driver includes a powerful configuration generator tool for bulk deployments:

### Generate Multiple Devices

```bash
python config_generator.py generate \
    --gateway-type tcp \
    --address 192.168.1.100 \
    --port 502 \
    --template power_meter_basic \
    --units 1-10 \
    --name-prefix meter \
    --output config.json
```

### Generate from CSV

Create a CSV file with device specifications:
```csv
unit_id,name,template,register_offset,gateway_address,gateway_port
1,building_a_meter,power_meter_basic,0,192.168.1.10,502
2,building_b_meter,power_meter_basic,0,192.168.1.10,502
10,chiller_vfd,vfd_drive,0,192.168.1.20,502
```

Generate configuration:
```bash
python config_generator.py from-csv devices.csv --output config.json
```

### List Available Templates

```bash
python config_generator.py list-templates
```

### Create Example Configurations

```bash
python config_generator.py examples --output-dir ./examples
```

## Built-in Templates

The driver includes several built-in templates for common device types:

- **power_meter_basic**: Three-phase power meter with voltage, current, power
- **temperature_sensor**: Temperature and humidity sensor with setpoints
- **digital_io**: Digital input/output module
- **vfd_drive**: Variable frequency drive with speed control

## Architecture Details

### Greenlet-Safe Concurrency

VOLTTRON runs each device driver in its own greenlet (lightweight cooperative thread). The enhanced modbus driver uses gevent's synchronization primitives to ensure safe concurrent access:

- **gevent.lock.RLock**: Used for all synchronization instead of threading locks
- **Monkey patching**: Socket operations are monkey-patched for gevent compatibility
- **Cooperative yielding**: Long operations yield to allow other greenlets to run

### Gateway Connection Management

Each gateway maintains a single TCP connection that is shared by all units on that bus:

```python
# In your agent code
connection_status = driver.connection_pool.get_connection_status()
print(connection_status)
# Output: {'tcp_192.168.1.100:502': {'connected': True, 'health': {...}}}
```

### Unit Addressing

Unit IDs are only unique within a single bus (0-255). The same unit ID can exist on different gateways:

```json
{
    "units": [
        {"unit_id": 1, "name": "gateway1_unit1"},  // Unit 1 on gateway 1
        {"unit_id": 1, "name": "gateway2_unit1"}   // Unit 1 on gateway 2 (different bus)
    ]
}
```

### Health Monitoring

Get health status of all devices:
```python
health = driver.get_health_status()
for unit_id, status in health.items():
    print(f"Unit {unit_id}: {'Online' if status['online'] else 'Offline'}")
```

### Register Optimization

The driver automatically optimizes register reading by:
1. Merging adjacent registers into single requests
2. Batching requests up to 100 registers
3. Grouping registers by type and access mode

## Serial RTU Configuration

For serial RTU connections:

```json
{
    "driver_config": {
        "gateway": {
            "connection_type": "serial",
            "address": "/dev/ttyUSB0",
            "baudrate": 19200,
            "bytesize": 8,
            "parity": "E",
            "stopbits": 1
        },
        "units": [...]
    }
}
```

## Performance Considerations

1. **Single Socket per Gateway**: Only one TCP connection per gateway (critical for constrained devices)
2. **Serialized Access**: Operations are queued to prevent concurrent access on the same bus
3. **Register Batching**: Automatic, up to 100 registers per request
4. **Retry Logic**: Configurable exponential backoff prevents overwhelming devices
5. **Health Checks**: Periodic health checks maintain connection quality

## Troubleshooting

### Common Issues

1. **Multiple units not responding**
   - Check gateway configuration
   - Verify unit IDs are correct
   - Ensure connection pool size is adequate

2. **Serial connection failures**
   - Verify device path (e.g., /dev/ttyUSB0)
   - Check baudrate, parity, and stopbits match device settings
   - Ensure user has permission to access serial device

3. **Template not found**
   - List available templates with config_generator.py
   - Verify template name in configuration
   - Check custom template definition

### Debug Logging

Enable debug logging for detailed diagnostics:
```python
import logging
logging.getLogger('modbus_enhanced').setLevel(logging.DEBUG)
```

## API Compatibility

The enhanced driver maintains full API compatibility with the VOLTTRON BaseInterface:

- `get_point(point_name)`: Read single point
- `set_point(point_name, value)`: Write single point  
- `scrape_all()`: Read all configured points
- `get_health_status()`: Get device health (new method)

## Contributing

To add new device templates:

1. Create template definition in `config_template.py`
2. Validate with `template_engine.validate_template()`
3. Test with example devices
4. Submit pull request with template and example

## License

Licensed under the Apache License, Version 2.0. See LICENSE file for details.

## Support

For issues or questions:
1. Check this README and examples
2. Review test files for usage patterns
3. Open an issue on the VOLTTRON GitHub repository

## Changelog

### Version 1.0.0 (2025)
- Initial release with full multi-unit gateway support
- Connection pooling implementation
- Template system for bulk configuration
- Backward compatibility with legacy drivers
- Serial RTU and TCP support
- Health monitoring and reporting
- Configuration generation tools