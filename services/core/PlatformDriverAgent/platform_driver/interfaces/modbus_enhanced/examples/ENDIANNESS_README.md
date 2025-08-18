# Endianness Configuration Guide

The enhanced modbus driver supports various endianness configurations for different devices. This is crucial when dealing with multi-register values (float, int32, uint32) from different manufacturers.

## Understanding Endianness

For multi-register values, there are two levels of byte ordering:

1. **Byte Order**: Order of bytes within each 16-bit register
   - Big-endian (`>` or `big`): Most significant byte first (default)
   - Little-endian (`<` or `little`): Least significant byte first

2. **Word Order**: Order of 16-bit registers for 32-bit values
   - Big-endian (`>` or `big`): High word (register) first (default)
   - Little-endian (`<` or `low`): Low word (register) first

## Common Endianness Patterns

For a float value stored in registers at addresses 100-101:

| Pattern | Byte Order | Word Order | Bytes Layout | Description |
|---------|------------|------------|--------------|-------------|
| ABCD | big | big | A B C D | Standard Modbus (default) |
| CDAB | little | little | C D A B | Mixed/Swapped endian |
| DCBA | little | little | D C B A | Full little-endian |
| BADC | little | big | B A D C | Little bytes, big words |

Where A is the most significant byte and D is the least significant.

## Configuration Methods

### CSV Format

Add these columns to your CSV registry configuration:

```csv
Volttron Point Name,Point Address,Modbus Register,Units,Writable,Mixed Endian,Byte Order,Word Order
energy,100,float,kWh,FALSE,FALSE,big,big
power,102,float,kW,FALSE,TRUE,,
temperature,104,float,°C,FALSE,FALSE,little,little
counter,106,uint32,counts,FALSE,FALSE,big,low
```

### JSON Format

Specify in register definitions:

```json
{
  "name": "energy",
  "address": 100,
  "type": "float",
  "byte_order": "big",
  "word_order": "big"
}
```

### Legacy Mixed Endian

For backward compatibility, `mixed_endian: true` is equivalent to:
- CSV: `Mixed Endian` column = `TRUE`
- JSON: `"mixed_endian": true`
- Sets byte_order to little-endian

## Supported Values

### Byte Order
- `>`, `big`, `be` - Big-endian (default)
- `<`, `little`, `le` - Little-endian

### Word Order
- `>`, `big`, `high` - High word first (default)
- `<`, `little`, `le`, `low` - Low word first

## Examples by Device Type

### Schneider Electric Meters
Often use CDAB (mixed endian):
```json
{
  "type": "float",
  "mixed_endian": true
}
```

### Siemens PLCs
Typically use DCBA (full little-endian):
```json
{
  "type": "float",
  "byte_order": "little",
  "word_order": "little"
}
```

### Standard Modbus Devices
Use ABCD (big-endian):
```json
{
  "type": "float",
  "byte_order": "big",
  "word_order": "big"
}
```
Or simply omit the endianness settings to use defaults.

### Some Solar Inverters
Use low word first for 32-bit counters:
```json
{
  "type": "uint32",
  "byte_order": "big",
  "word_order": "low"
}
```

## Testing Endianness

If you're unsure about a device's endianness:

1. Read a known value (like a constant or slowly changing value)
2. Try different endianness settings
3. The correct setting will produce the expected value

For example, if a temperature should read ~25.0°C but shows:
- 0.0 or huge number: Wrong endianness
- -12345.67: Wrong endianness
- 25.3: Correct endianness

## 16-bit Values

For 16-bit values (int16, uint16), only byte_order applies:
```json
{
  "type": "uint16",
  "byte_order": "little"
}
```

## Combining with Transforms

Endianness is applied first, then transforms:
```json
{
  "type": "float",
  "byte_order": "little",
  "word_order": "little",
  "transform": "lambda x: x * 0.001"
}
```

This reads the value with little-endian byte and word order, then scales it by 0.001.