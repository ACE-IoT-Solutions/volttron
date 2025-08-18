# VOLTTRON Migration Guide: 8.1.3 → 9.0.4

## Overview
This guide documents the migration process for merging VOLTTRON 8.1.3 improvements into 9.0.4 with Python 3.10+ support and UV package management.

## Key Improvements Merged from 8.1.3

### Core Service Enhancements
1. **BACnet Improvements**
   - Fixed binary value reading with `read_property_single`
   - Added synchronous BBMD finder
   - Foreign priority array support
   - Trending loop type support for BACnet objects

2. **MQTT Enhancements**
   - MQTT command publishing to VOLTTRON message bus
   - Improved MQTT-to-VOLTTRON bridging

3. **New Driver Support**
   - Shelly EM Meter Driver
   - Water Heater Interface
   - Venstar thermostat improvements

4. **Service Agents**
   - Ambient weather service
   - CrateHistorian (restored from deprecated)
   - Enhanced error handling for connected meters

## Migration Steps

### 1. Prerequisites
- Python 3.10 or higher
- UV package manager
- Git

### 2. Setup Environment

```bash
# Install UV if not present
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and checkout the merge branch
git clone https://github.com/ACE-IoT-Solutions/volttron.git
cd volttron
git checkout merge-8.1.3-to-9.0.4

# Bootstrap with UV
./bootstrap_uv.sh --all --dev
```

### 3. Build Agents

```bash
# Activate virtual environment
source .venv/bin/activate

# Build all agents
./build_agents.sh --all
```

### 4. Test ZMQ Connectivity

```bash
# Run ZMQ test suite
python test_zmq_connectivity.py
```

### 5. Start VOLTTRON

```bash
# Start the platform
volttron -vv

# In another terminal, check status
vctl status
```

## Configuration Changes

### Python 3.10 Compatibility
The following packages have been updated for Python 3.10:
- `gevent>=24.2.1` (from 21.x)
- `pyzmq>=26.0.2` (with bundled libraries)
- `setuptools>=40.0.0,<=70.0.0`
- All database drivers updated to latest compatible versions

### UV Package Management
Replace traditional pip/virtualenv workflow with UV:
- Use `uv venv` instead of `python -m venv`
- Use `uv pip` instead of `pip`
- Faster dependency resolution and installation

## Breaking Changes

### Deprecated Features
- Python 3.8 and 3.9 support dropped
- Some legacy configuration formats deprecated

### API Changes
- Updated authentication methods in web services
- Modified agent initialization for Python 3.10 async compatibility

## Troubleshooting

### ZMQ Connection Issues
If ZMQ tests fail:
1. Ensure no firewall blocking ports 5555-5560
2. Check `ulimit -n` is at least 1024
3. Rebuild pyzmq with bundled option: `uv pip install pyzmq --config-settings="--zmq=bundled"`

### Agent Compatibility
For custom agents:
1. Update import statements for Python 3.10
2. Replace deprecated gevent patterns
3. Test with `pytest -v tests/`

### Database Connections
If database historians fail:
1. Update connection strings for new driver versions
2. Check database server compatibility
3. Review logs in `$VOLTTRON_HOME/log/`

## Service Agent Status

| Agent | 8.1.3 | 9.0.4 | Status |
|-------|-------|-------|---------|
| ActuatorAgent | ✓ | ✓ | Merged |
| BACnetProxy | ✓ | ✓ | Enhanced |
| PlatformDriver | ✓ | ✓ | Updated |
| MQTTHistorian | ✓ | ✓ | Enhanced |
| SQLHistorian | ✓ | ✓ | Compatible |
| ForwardHistorian | ✓ | ✓ | Compatible |
| VolttronCentral | ✓ | ✓ | Compatible |
| Ambient | ✓ | - | Restored |
| CrateHistorian | ✓ | - | Restored |
| ObixHistoryPublish | ✓ | - | Needs Port |
| WeatherDotGov | ✓ | ✓ | Compatible |

## Performance Improvements

### UV Benefits
- 10-100x faster package installation
- Improved dependency resolution
- Better caching mechanisms
- Reduced disk usage

### Python 3.10 Benefits
- Better async performance
- Improved type hints
- Pattern matching support
- Performance optimizations

## Support

For issues or questions:
- Check logs: `tail -f $VOLTTRON_HOME/log/volttron.log`
- Run diagnostics: `vctl status`
- Test connectivity: `python test_zmq_connectivity.py`

## Next Steps

1. Test your specific agent configurations
2. Update any custom agents for compatibility
3. Monitor performance metrics
4. Report issues to the development team

---

*Generated with Hive Mind Collective Intelligence System*
*Version: 9.0.4-enhanced*
*Date: 2025-08-18*