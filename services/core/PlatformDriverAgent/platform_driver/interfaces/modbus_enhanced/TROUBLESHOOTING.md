# Enhanced Modbus Driver Troubleshooting Guide

## Common Configuration Issues

### Issue: Driver going into legacy mode instead of gateway device mode

**Symptom:**
```
platform_driver.interfaces.modbus_enhanced INFO: Deployment mode: legacy
```

**Causes and Solutions:**

1. **Malformed units configuration**
   
   ❌ **Incorrect** (single dict with duplicate keys):
   ```json
   "units": {
       "unit_id": "1", "name": "power_meter_1",
       "unit_id": "2", "name": "power_meter_2"
   }
   ```
   
   ✅ **Correct** (list of dicts):
   ```json
   "units": [
       {"unit_id": 1, "name": "power_meter_1"},
       {"unit_id": 2, "name": "power_meter_2"}
   ]
   ```

2. **Missing gateway configuration**
   
   Ensure your driver_config has a "gateway" section:
   ```json
   "driver_config": {
       "gateway": {
           "connection_type": "tcp",
           "address": "192.168.1.100",
           "port": 502
       },
       "units": [...]
   }
   ```

### Issue: No registers being configured

**Symptom:**
```
platform_driver.interfaces.modbus_enhanced.register_manager INFO: Built register maps for 0 gateways
WARNING: no results for device
```

**Causes and Solutions:**

1. **Registry config not being parsed**
   
   Check that your registry_config maps unit IDs as strings:
   ```json
   "registry_config": {
       "1": "config://registry.csv",  // Unit ID as string
       "2": "config://registry.csv"
   }
   ```

2. **CSV format issues**
   
   Ensure your CSV has the correct headers:
   ```csv
   Volttron Point Name,Point Address,Modbus Register,Units,Writable,Default Value,Notes
   temperature,0,float,°C,FALSE,,Temperature reading
   ```

### Issue: Wrong address key

**Symptom:**
```
ValueError: Gateway configuration must include 'address' or 'device_address'
```

**Solution:**
Use "address" in gateway config (though "device_address" is supported for backward compatibility):
```json
"gateway": {
    "address": "192.168.1.100",  // Preferred
    // "device_address": "192.168.1.100"  // Also supported
}
```

## Configuration Modes

### Gateway Device Mode
- One VOLTTRON device represents a gateway with multiple modbus units
- Point names are prefixed with unit names (e.g., "power_meter_1.voltage")
- Registry config is a dict mapping unit IDs to CSV files

### Unit Device Mode  
- Each modbus unit is a separate VOLTTRON device
- Uses singleton for connection sharing
- Registry config is a single CSV file

### Legacy Mode
- Backward compatibility with existing modbus driver configs
- Single unit per device
- No gateway concept

## Registry CSV Format

### Standard VOLTTRON Format
```csv
Volttron Point Name,Point Address,Modbus Register,Units,Writable,Default Value,Notes
active_energy,1,float,MWhr,TRUE,0,Active Energy
voltage,5,uint16,V,FALSE,,Line Voltage
status_bit,10,bool,,FALSE,,Status bit
```

### Modbus Register Types
- `bool` or `bit` - Single bit (coil/discrete input)
- `uint16` - Unsigned 16-bit integer (default)
- `int16` - Signed 16-bit integer
- `uint32` - Unsigned 32-bit integer (2 registers)
- `int32` - Signed 32-bit integer (2 registers)
- `float` - 32-bit floating point (2 registers)

### Important Notes
- Point Address is the starting modbus address (0-based or 1-based depending on device)
- Float and 32-bit integers use 2 consecutive registers
- Writable must be "TRUE" or "FALSE" (case insensitive)

## Debug Steps

1. **Check deployment mode in logs:**
   ```
   grep "Deployment mode:" /var/log/volttron.log
   ```

2. **Verify configuration is loaded:**
   ```
   grep "Registry config is" /var/log/volttron.log
   ```

3. **Check for parsing errors:**
   ```
   grep "WARNING\|ERROR" /var/log/volttron.log | grep modbus_enhanced
   ```

4. **Verify gateway is added:**
   ```
   grep "Added gateway" /var/log/volttron.log
   ```

5. **Check register count:**
   ```
   grep "Built register maps" /var/log/volttron.log
   ```

## Example Configurations

See the `examples/` directory for complete working configurations:
- `gateway_device_config.json` - Gateway with multiple units
- `corrected_device_config.json` - Fixed common configuration issues
- `corrected_registry.csv` - Properly formatted registry file