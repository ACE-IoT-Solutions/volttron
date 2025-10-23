# Template System Documentation

The enhanced modbus driver includes a powerful template system for configuring multiple similar devices efficiently.

## Template Structure

Templates are defined in the `device_templates` section of the configuration and contain:

```json
{
    "device_templates": {
        "template_name": {
            "description": "Optional template description",
            "transforms": {
                "transform_name": "lambda expression"
            },
            "registers": [
                {
                    "name": "register_name",
                    "address": 0,
                    "type": "data_type",
                    "units": "unit_string",
                    "transform": "direct lambda",
                    "transform_name": "reference to transforms",
                    "writable": false
                }
            ]
        }
    }
}
```

## Transform Application Methods

There are two ways to specify transforms in templates:

### 1. Direct Transform (Inline)
Specify the transform directly in the register definition:

```json
{
    "name": "temperature",
    "address": 0,
    "type": "float",
    "transform": "lambda x: x * 0.1"
}
```

### 2. Transform Reference (Named)
Reference a transform from the template's transforms dictionary:

```json
{
    "device_templates": {
        "sensor_template": {
            "transforms": {
                "scale_temp": "lambda x: x * 0.1",
                "scale_humidity": "lambda x: x * 0.01"
            },
            "registers": [
                {
                    "name": "temperature",
                    "address": 0,
                    "type": "float",
                    "transform_name": "scale_temp"
                },
                {
                    "name": "humidity",
                    "address": 2,
                    "type": "float",
                    "transform_name": "scale_humidity"
                }
            ]
        }
    }
}
```

## Benefits of Named Transforms

1. **Reusability**: Define once, use multiple times
2. **Maintainability**: Update transform logic in one place
3. **Organization**: Group related transforms together
4. **Documentation**: Named transforms are self-documenting

## Template Variables

Templates support variable substitution for dynamic configuration:

```json
{
    "units": [
        {
            "unit_id": 1,
            "name": "meter_1",
            "template": "power_meter",
            "register_offset": 100
        }
    ]
}
```

The `register_offset` will be added to all register addresses in the template.

## Complete Example

```json
{
    "driver_config": {
        "device_templates": {
            "power_meter": {
                "description": "Generic power meter with scaling",
                "transforms": {
                    "kW_scale": "lambda x: x * 0.001",
                    "V_scale": "lambda x: x * 0.1",
                    "A_scale": "lambda x: x * 0.01",
                    "pf_scale": "lambda x: x / 1000.0"
                },
                "registers": [
                    {
                        "name": "voltage",
                        "address": 0,
                        "type": "uint16",
                        "units": "V",
                        "transform_name": "V_scale"
                    },
                    {
                        "name": "current",
                        "address": 2,
                        "type": "uint16",
                        "units": "A",
                        "transform_name": "A_scale"
                    },
                    {
                        "name": "power",
                        "address": 4,
                        "type": "int32",
                        "units": "kW",
                        "transform_name": "kW_scale"
                    },
                    {
                        "name": "power_factor",
                        "address": 6,
                        "type": "int16",
                        "transform_name": "pf_scale"
                    },
                    {
                        "name": "frequency",
                        "address": 8,
                        "type": "uint16",
                        "units": "Hz",
                        "transform": "lambda x: x * 0.01"
                    }
                ]
            }
        },
        "gateway": {
            "connection_type": "tcp",
            "address": "192.168.1.100",
            "port": 502
        },
        "units": [
            {"unit_id": 1, "name": "main_meter", "template": "power_meter"},
            {"unit_id": 2, "name": "sub_meter_1", "template": "power_meter"},
            {"unit_id": 3, "name": "sub_meter_2", "template": "power_meter"}
        ]
    }
}
```

## Transform Priority

When both `transform` and `transform_name` are specified:
1. Direct `transform` takes precedence
2. `transform_name` is used as fallback

## Best Practices

1. **Use named transforms** for common scaling operations
2. **Use direct transforms** for one-off or unique conversions
3. **Group related transforms** in the template's transforms dictionary
4. **Document transform purpose** in the transform name
5. **Test transforms** with known values before deployment

## Built-in Templates

The driver includes several built-in templates:
- `schneider_pm5000`: Schneider Electric PM5000 series meters
- `temperature_sensor`: Generic temperature/humidity sensors
- `power_meter_basic`: Basic power meter template

To list available templates, use the configuration generator:
```bash
python config_generator.py --list-templates
```