# Transform Functions Reference

The enhanced modbus driver includes all transform functions from the legacy modbus-tk driver plus many additional commonly needed transforms.

## Using Transforms

Transforms can be specified in three ways:

### 1. Named Transforms
Reference a pre-defined transform by name:
```csv
Point Name,Address,Type,Transform
temperature,100,float,scale_0_1
power,102,int32,W_to_kW
status,104,uint16,alarm_status
```

### 2. Parameterized Transforms
Use a transform with parameters:
```csv
Point Name,Address,Type,Transform
voltage,100,float,scale(0.001)
counter,102,int32,mod10k(true)
scaled_value,104,float,scale_reg(scaling_factor)
```

### 3. Lambda Expressions
Define custom transforms inline:
```csv
Point Name,Address,Type,Transform
temperature,100,float,lambda x: x * 0.1 - 50
status,102,uint16,lambda x: 'ON' if x > 100 else 'OFF'
```

## Pre-Canned Transforms

### Legacy Modbus-TK Compatible

| Transform | Description | Example |
|-----------|-------------|---------|
| `scale(multiplier)` | Multiply by a constant | `scale(0.001)` |
| `scale_int(multiplier)` | Multiply and cast to integer | `scale_int(10)` |
| `scale_decimal_int_signed(multiplier)` | Scale with non-standard signing | `scale_decimal_int_signed(0.001)` |
| `mod10k(reverse)` | ION 8600 INT32-M10K format | `mod10k(false)` |
| `mod10k64(reverse)` | PM800 64-bit 10K format | `mod10k64(false)` |
| `mod10k48(reverse)` | PM800 INT48-M10K format | `mod10k48(false)` |
| `scale_reg(reg_name)` | Scale by another register | `scale_reg(scaling_factor)` |
| `scale_reg_pow_10(reg_name)` | Scale by 10^register | `scale_reg_pow_10(exponent)` |

### Common Scaling

| Transform | Description | Multiplier |
|-----------|-------------|------------|
| `scale_0_1` | Multiply by 0.1 | 0.1 |
| `scale_0_01` | Multiply by 0.01 | 0.01 |
| `scale_0_001` | Multiply by 0.001 | 0.001 |
| `scale_0_0001` | Multiply by 0.0001 | 0.0001 |
| `scale_10` | Multiply by 10 | 10 |
| `scale_100` | Multiply by 100 | 100 |
| `scale_1000` | Multiply by 1000 | 1000 |

### Unit Conversions

#### Power
| Transform | Description |
|-----------|-------------|
| `W_to_kW` | Watts to kilowatts |
| `kW_to_W` | Kilowatts to watts |
| `W_to_MW` | Watts to megawatts |
| `MW_to_W` | Megawatts to watts |
| `VAR_to_kVAR` | VAR to kVAR |
| `kVAR_to_VAR` | kVAR to VAR |
| `VA_to_kVA` | VA to kVA |
| `kVA_to_VA` | kVA to VA |

#### Energy
| Transform | Description |
|-----------|-------------|
| `Wh_to_kWh` | Watt-hours to kilowatt-hours |
| `kWh_to_Wh` | Kilowatt-hours to watt-hours |
| `Wh_to_MWh` | Watt-hours to megawatt-hours |
| `MWh_to_Wh` | Megawatt-hours to watt-hours |

#### Current
| Transform | Description |
|-----------|-------------|
| `mA_to_A` | Milliamps to amps |
| `A_to_mA` | Amps to milliamps |

#### Temperature
| Transform | Description |
|-----------|-------------|
| `C_to_F` | Celsius to Fahrenheit |
| `F_to_C` | Fahrenheit to Celsius |
| `C_to_K` | Celsius to Kelvin |
| `K_to_C` | Kelvin to Celsius |

### Percentage and Ratios

| Transform | Description |
|-----------|-------------|
| `ratio_to_percent` | Convert 0-1 to 0-100% |
| `percent_to_ratio` | Convert 0-100% to 0-1 |
| `pf_scale` | Scale power factor (-1000 to 1000) |
| `percent_limit` | Clamp to 0-100% range |

### Error Handling

| Transform | Description |
|-----------|-------------|
| `error_to_none` | Convert error values to None |
| `nan_to_none` | Convert NaN to None |
| `inf_to_none` | Convert infinity to None |

### Status Transforms

| Transform | Description |
|-----------|-------------|
| `bool_to_status` | Convert boolean to ON/OFF |
| `status_to_bool` | Convert ON/OFF to boolean |
| `alarm_status` | Map 0-3 to Normal/Warning/Alarm/Fault |
| `binary_status` | Check bit 0 for Active/Inactive |

### Bit Manipulation

Extract individual bits from a register:

| Transform | Description |
|-----------|-------------|
| `bit_0` through `bit_15` | Extract bit 0-15 |

Example:
```csv
Point Name,Address,Type,Transform
alarm_bit_0,100,uint16,bit_0
alarm_bit_1,100,uint16,bit_1
```

### Calibration and Offsets

| Transform | Description |
|-----------|-------------|
| `offset_1` | Add 1 |
| `offset_minus_1` | Subtract 1 |
| `offset_10` | Add 10 |
| `offset_minus_10` | Subtract 10 |
| `offset_100` | Add 100 |
| `offset_minus_100` | Subtract 100 |

## Examples

### Power Meter
```csv
Point Name,Address,Type,Units,Transform
voltage_l1,0,uint16,V,scale_0_1
current_l1,2,uint16,A,mA_to_A
power_total,4,int32,kW,W_to_kW
power_factor,6,int16,,pf_scale
frequency,8,uint16,Hz,scale_0_01
energy_total,10,uint32,kWh,Wh_to_kWh
meter_status,12,uint16,,alarm_status
```

### Temperature Sensor
```csv
Point Name,Address,Type,Units,Transform
temperature_c,0,float,°C,lambda x: x * 0.1
temperature_f,0,float,°F,lambda x: x * 0.1 * 9/5 + 32
humidity,2,uint16,%,scale_0_1
dewpoint,4,float,°C,lambda x: x * 0.1 - 10
```

### ION Meter with M10K Format
```csv
Point Name,Address,Type,Transform
energy_delivered,100,int32,mod10k(false)
energy_received,102,int32,mod10k(true)
```

### Scaled by Register
```csv
Point Name,Address,Type,Transform
scaling_factor,0,int16,
voltage,10,uint16,scale_reg(scaling_factor)
current,12,uint16,scale_reg_pow_10(scaling_factor)
```

## Creating Custom Transforms

### In Configuration
Use lambda expressions for one-off transforms:
```python
lambda x: x * 0.001 if x < 32768 else None
lambda x: round(x * 0.1, 2)
lambda x: 'High' if x > 100 else 'Low'
```

### Registering New Transforms
To add permanent transforms, register them in your code:
```python
from modbus_enhanced.transforms import transform_registry

# Register a custom transform
transform_registry.register('my_transform', lambda x: x * 42)

# Now use it in configuration
# Transform column: my_transform
```

## Transform with Inverse

Some transforms support inverse operations for writing values back:

```python
def scale_with_inverse(multiplier):
    def forward(x):
        return x * multiplier
    
    def inverse(x):
        return x / multiplier
    
    forward.inverse = inverse
    return forward
```

## Best Practices

1. **Use named transforms** when available for clarity
2. **Document custom transforms** in your configuration
3. **Test edge cases** (0, negative, max values)
4. **Handle errors gracefully** (division by zero, None values)
5. **Consider precision** when scaling floating point values
6. **Use error_to_none** for devices that report error codes