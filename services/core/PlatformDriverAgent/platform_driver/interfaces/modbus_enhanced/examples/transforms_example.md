# Enhanced Modbus Driver Transform Examples

## Overview

Transforms allow you to modify raw modbus register values before they are published to the VOLTTRON message bus. This is useful for:
- Scaling values (e.g., converting from counts to engineering units)
- Applying offsets or calibration factors
- Converting between unit systems
- Applying complex mathematical transformations

## Transform Configuration

Transforms can be defined in two ways:

### 1. Inline Lambda Transforms (JSON Config)

For simple transformations, you can define lambda functions directly in the configuration:

```json
{
    "driver_config": {
        "gateway": {
            "connection_type": "tcp",
            "address": "192.168.1.100",
            "port": 502
        },
        "units": [
            {
                "unit_id": 1,
                "name": "power_meter",
                "registers": [
                    {
                        "name": "voltage",
                        "address": 0,
                        "type": "uint16",
                        "units": "V",
                        "transform": "lambda x: x * 0.1",  // Scale by 0.1
                        "writable": false
                    },
                    {
                        "name": "current",
                        "address": 2,
                        "type": "uint16",
                        "units": "A",
                        "transform": "lambda x: x / 1000.0",  // Convert mA to A
                        "writable": false
                    },
                    {
                        "name": "power",
                        "address": 4,
                        "type": "int16",
                        "units": "kW",
                        "transform": "lambda x: x * 0.001 if x >= 0 else 0",  // W to kW, min 0
                        "writable": false
                    },
                    {
                        "name": "temperature_raw",
                        "address": 6,
                        "type": "int16",
                        "units": "°C",
                        "transform": "lambda x: (x - 32768) * 0.01",  // Offset and scale
                        "writable": false
                    }
                ]
            }
        ]
    }
}
```

### 2. Named Transform Functions (Template Config)

For reusable or complex transforms, define named functions in templates:

```json
{
    "driver_config": {
        "device_templates": {
            "power_meter_template": {
                "transforms": {
                    "scale_voltage": "lambda x: x * 0.1",
                    "mA_to_A": "lambda x: x / 1000.0",
                    "W_to_kW": "lambda x: x * 0.001",
                    "celsius_to_fahrenheit": "lambda x: x * 9/5 + 32",
                    "percent_to_ratio": "lambda x: x / 100.0",
                    "signed_to_unsigned": "lambda x: x + 32768 if x < 0 else x"
                },
                "registers": [
                    {
                        "name": "voltage_l1",
                        "address": 0,
                        "type": "uint16",
                        "transform": "scale_voltage"
                    },
                    {
                        "name": "current_l1",
                        "address": 2,
                        "type": "uint16",
                        "transform": "mA_to_A"
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
            {
                "unit_id": 1,
                "name": "meter_1",
                "template": "power_meter_template"
            }
        ]
    }
}
```

## Common Transform Examples

### Scaling Transforms

```json
// Simple multiplication
"transform": "lambda x: x * 0.1"

// Division 
"transform": "lambda x: x / 100.0"

// Power of 10 scaling
"transform": "lambda x: x * 10**-3"  // divide by 1000
```

### Offset Transforms

```json
// Add offset
"transform": "lambda x: x + 273.15"  // Celsius to Kelvin

// Subtract offset
"transform": "lambda x: x - 32768"  // Convert from unsigned to signed

// Combined offset and scale
"transform": "lambda x: (x - 1000) * 0.01"
```

### Unit Conversions

```json
// Temperature conversions
"transform": "lambda x: x * 9/5 + 32"  // °C to °F
"transform": "lambda x: (x - 32) * 5/9"  // °F to °C

// Pressure conversions
"transform": "lambda x: x * 14.5038"  // bar to PSI
"transform": "lambda x: x * 0.0689476"  // PSI to bar

// Power conversions
"transform": "lambda x: x * 0.746"  // HP to kW
"transform": "lambda x: x * 1.341"  // kW to HP
```

### Conditional Transforms

```json
// Clipping/limiting
"transform": "lambda x: max(0, min(100, x))"  // Limit to 0-100

// Conditional scaling
"transform": "lambda x: x * 0.1 if x > 0 else 0"

// Threshold detection
"transform": "lambda x: 1 if x > 100 else 0"

// Error value handling
"transform": "lambda x: None if x == 65535 else x * 0.1"
```

### Bit Manipulation Transforms

```json
// Extract specific bits
"transform": "lambda x: (x >> 8) & 0xFF"  // Get high byte

// Combine bytes
"transform": "lambda x: ((x & 0xFF) << 8) | ((x >> 8) & 0xFF)"  // Swap bytes

// Boolean from bit
"transform": "lambda x: bool(x & 0x01)"  // Check bit 0
```

## Advanced Transform Examples

### Multi-step Calculations

```python
# For complex transforms, you can use multi-line lambdas
"transform": "lambda x: (lambda raw: raw * 0.1 if raw < 32768 else (raw - 65536) * 0.1)(x)"

# Or define a more readable version using nested operations
"transform": "lambda x: {'scaled': x * 0.1, 'offset': x * 0.1 - 100}['scaled'] if x < 1000 else {'scaled': x * 0.1, 'offset': x * 0.1 - 100}['offset']"
```

### Error Handling in Transforms

```json
// Return None for invalid values
"transform": "lambda x: x * 0.1 if 0 <= x <= 65530 else None"

// Replace error codes with zero
"transform": "lambda x: 0 if x in [65535, 65534, 65533] else x * 0.1"

// Use default value for errors
"transform": "lambda x: x * 0.1 if x != 0xFFFF else -999.9"
```

## Transform Implementation in Code

If you need more complex transforms that can't be expressed as lambdas, you can extend the driver:

```python
# In your extended driver class
class CustomTransforms:
    @staticmethod
    def polynomial_correction(x):
        """Apply polynomial correction curve"""
        return 0.0001 * x**2 + 0.95 * x + 1.2
    
    @staticmethod
    def lookup_table(x):
        """Use lookup table for non-linear conversion"""
        table = {
            0: 0.0,
            100: 12.5,
            200: 25.3,
            300: 38.7,
            # ... more values
        }
        # Linear interpolation between points
        if x in table:
            return table[x]
        # Find surrounding points and interpolate
        keys = sorted(table.keys())
        for i in range(len(keys)-1):
            if keys[i] <= x <= keys[i+1]:
                x0, x1 = keys[i], keys[i+1]
                y0, y1 = table[x0], table[x1]
                return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
        return None

# Register custom transforms
def register_custom_transforms(template_engine):
    template_engine.register_transform('polynomial', CustomTransforms.polynomial_correction)
    template_engine.register_transform('lookup', CustomTransforms.lookup_table)
```

## CSV Configuration with Transforms

Transforms can also be specified in CSV registry files:

```csv
Volttron Point Name,Point Address,Modbus Register,Units,Writable,Default Value,Transform,Notes
voltage_l1,0,uint16,V,FALSE,,lambda x: x * 0.1,Line 1 Voltage scaled by 0.1
current_l1,2,uint16,A,FALSE,,lambda x: x / 1000.0,Line 1 Current in mA converted to A
power_total,4,int32,kW,FALSE,,lambda x: x * 0.001,Total Power in W converted to kW
temperature,8,int16,°C,FALSE,,lambda x: (x - 32768) * 0.01,Temperature with offset correction
humidity,10,uint16,%,FALSE,,lambda x: x / 10.0,Humidity scaled by 0.1
status,12,uint16,,FALSE,,lambda x: 'OK' if x == 1 else 'FAULT',Status code to string
```

## Testing Transforms

To test your transforms before deployment:

```python
# Test transform functions
transform = eval("lambda x: x * 0.1")
test_values = [0, 100, 1000, 65535]
for val in test_values:
    result = transform(val)
    print(f"Input: {val}, Output: {result}")

# Validate transform doesn't throw exceptions
try:
    transform = eval("lambda x: x * 0.1")
    transform(100)  # Test with valid value
    transform(0)    # Test with zero
    transform(-1)   # Test with negative
    print("Transform is valid")
except Exception as e:
    print(f"Transform error: {e}")
```

## Performance Considerations

1. **Keep transforms simple** - Complex calculations can slow down polling
2. **Avoid external calls** - Don't make network or database calls in transforms
3. **Handle errors gracefully** - Return None or a default value for invalid inputs
4. **Pre-calculate when possible** - Use lookup tables for complex conversions
5. **Test edge cases** - Ensure transforms handle min/max values and error codes

## Troubleshooting Transforms

Common issues and solutions:

1. **Transform not applied**
   - Check that transform field is properly quoted in JSON
   - Verify lambda syntax is correct
   - Check logs for transform evaluation errors

2. **Wrong values after transform**
   - Print raw and transformed values in logs
   - Test transform function separately
   - Check for integer division issues (use float literals)

3. **Transform causes errors**
   - Add try/except in lambda if needed
   - Check for division by zero
   - Ensure transform handles all possible input values

## Example: Complete Power Meter with Transforms

```json
{
    "driver_config": {
        "gateway": {
            "connection_type": "tcp",
            "address": "192.168.1.100",
            "port": 502
        },
        "units": [
            {
                "unit_id": 1,
                "name": "main_meter",
                "registers": [
                    {
                        "name": "voltage_l1",
                        "address": 0,
                        "type": "uint16",
                        "units": "V",
                        "transform": "lambda x: x * 0.1",
                        "writable": false,
                        "description": "L1 Voltage, scaled from 0.1V units"
                    },
                    {
                        "name": "current_l1",
                        "address": 2,
                        "type": "uint16",
                        "units": "A",
                        "transform": "lambda x: x * 0.001",
                        "writable": false,
                        "description": "L1 Current, converted from mA"
                    },
                    {
                        "name": "power_l1",
                        "address": 4,
                        "type": "int32",
                        "units": "kW",
                        "transform": "lambda x: x * 0.001 if x != -2147483648 else None",
                        "writable": false,
                        "description": "L1 Power, W to kW, invalid value filtered"
                    },
                    {
                        "name": "power_factor_l1",
                        "address": 8,
                        "type": "int16",
                        "units": "",
                        "transform": "lambda x: x / 1000.0",
                        "writable": false,
                        "description": "L1 Power Factor, scaled from 0.001 units"
                    },
                    {
                        "name": "frequency",
                        "address": 10,
                        "type": "uint16",
                        "units": "Hz",
                        "transform": "lambda x: x * 0.01",
                        "writable": false,
                        "description": "Grid Frequency, scaled from 0.01 Hz units"
                    },
                    {
                        "name": "total_energy",
                        "address": 12,
                        "type": "uint32",
                        "units": "kWh",
                        "transform": "lambda x: x * 0.01",
                        "writable": false,
                        "description": "Total Energy, scaled from 0.01 kWh units"
                    },
                    {
                        "name": "meter_status",
                        "address": 16,
                        "type": "uint16",
                        "units": "",
                        "transform": "lambda x: {0: 'Normal', 1: 'Warning', 2: 'Fault', 3: 'Offline'}.get(x, 'Unknown')",
                        "writable": false,
                        "description": "Meter Status, converted from code to string"
                    }
                ]
            }
        ]
    },
    "driver_type": "modbus_enhanced",
    "interval": 10
}
```

This configuration shows various transform types:
- Simple scaling (voltage, current)
- Unit conversion (W to kW)
- Error value handling (power invalid value check)
- Ratio conversion (power factor)
- Status code to string mapping (meter_status)