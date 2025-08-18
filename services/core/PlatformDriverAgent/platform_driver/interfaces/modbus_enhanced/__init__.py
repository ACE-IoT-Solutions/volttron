# -*- coding: utf-8 -*- {{{
# vim: set fenc=utf-8 ft=python sw=4 ts=4 sts=4 et:
#
# Copyright 2025, ACE IoT Solutions LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# }}}

"""
Enhanced Modbus Driver for VOLTTRON Platform

This driver provides comprehensive modbus support with the following features:
- Serial (RTU) and TCP connectivity  
- Multiple unit devices sharing a single gateway TCP connection
- Single socket per gateway for constrained TCP-to-RTU bridges
- Serialized access to prevent concurrent operations on same bus
- Template-based configuration for easy deployment
- Backward compatibility with existing modbus drivers
- Advanced error handling and retry logic
- Health monitoring and reporting
"""

import logging
import struct
import json
import csv
from io import StringIO
from typing import Dict, List, Optional, Any, Union
from collections import defaultdict
from gevent import monkey, sleep
from gevent.lock import RLock  # Use gevent's RLock for greenlet safety

monkey.patch_socket()

from pymodbus.client.sync import ModbusTcpClient, ModbusSerialClient
from pymodbus.exceptions import ConnectionException, ModbusIOException, ModbusException
from pymodbus.constants import Defaults

from platform_driver.interfaces import BaseInterface, BaseRegister, BasicRevert, DriverInterfaceError
from volttron.platform.agent import utils
from .connection_pool import ConnectionPool
from .gateway_manager import GatewayManager
from .config_template import ConfigTemplateEngine
from .register_manager import RegisterManager
from .transforms import create_transform, transform_registry

utils.setup_logging()
_log = logging.getLogger(__name__)

modbus_logger = logging.getLogger("pymodbus")
modbus_logger.setLevel(logging.WARNING)


class EnhancedModbusRegister(BaseRegister):
    """Enhanced register with multi-unit support"""
    
    def __init__(self, address, register_type, read_only, point_name, units, 
                 unit_id=1, gateway_id=None, description='', 
                 mixed_endian=False, transform=None, byte_order='>', word_order='>'):
        super().__init__(register_type, read_only, point_name, units, description=description)
        self.address = address
        self.unit_id = unit_id
        self.gateway_id = gateway_id
        self.mixed_endian = mixed_endian  # Legacy support
        self.byte_order = byte_order  # '>' for big-endian, '<' for little-endian  
        self.word_order = word_order  # '>' for high word first, '<' for low word first
        self.transform = transform
        self._parse_struct = None
        self._setup_struct()
    
    def _setup_struct(self):
        """Setup parsing struct based on register type and endianness"""
        if self.register_type == 'bit':
            self.python_type = bool
        elif self.register_type in ['int16', 'uint16']:
            # Single register - only byte order matters
            byte_order = '<' if self.mixed_endian else self.byte_order
            format_char = 'H' if self.register_type == 'uint16' else 'h'
            self._parse_struct = struct.Struct(f'{byte_order}{format_char}')
            self.python_type = int
        elif self.register_type in ['int32', 'uint32']:
            # Two registers - both byte and word order matter
            byte_order = '<' if self.mixed_endian else self.byte_order
            format_char = 'I' if self.register_type == 'uint32' else 'i'
            self._parse_struct = struct.Struct(f'{byte_order}{format_char}')
            self.python_type = int
            # Note: word_order handled in parse_value for 32-bit values
        elif self.register_type == 'float':
            # Two registers - both byte and word order matter
            byte_order = '<' if self.mixed_endian else self.byte_order
            self._parse_struct = struct.Struct(f'{byte_order}f')
            self.python_type = float
            # Note: word_order handled in parse_value for float values
        else:
            self._parse_struct = struct.Struct(f'{self.byte_order}H')
            self.python_type = int
    
    def get_register_type(self):
        """
        Return register type for base interface compatibility
        :return: (register_type, read_only) tuple
        """
        # Map our types to base interface types
        if self.register_type == 'bit':
            return ('bit', self.read_only)
        else:
            # All other types (float, int16, uint16, int32, uint32) are 'byte' type
            return ('byte', self.read_only)
    
    def get_register_count(self):
        """
        Get the number of modbus registers this point uses
        :return: Number of 16-bit registers
        """
        if self.register_type == 'bit':
            return 1
        elif self.register_type in ['float', 'int32', 'uint32']:
            return 2  # 32-bit values use 2 registers
        else:  # int16, uint16
            return 1
    
    def parse_value(self, raw_data):
        """Parse raw modbus data into proper value"""
        if self.register_type == 'bit':
            return bool(raw_data[0] if isinstance(raw_data, (list, tuple)) else raw_data)
        
        if self._parse_struct:
            if isinstance(raw_data, bytes):
                byte_data = raw_data
            else:
                # Convert register values to bytes
                byte_data = b''.join(struct.pack('>H', r) for r in raw_data)
            
            # Handle word order for 32-bit values (2 registers)
            if self.register_type in ['float', 'int32', 'uint32'] and len(byte_data) == 4:
                if self.word_order == '<':
                    # Swap words (16-bit chunks) for low word first
                    byte_data = byte_data[2:4] + byte_data[0:2]
            
            value = self._parse_struct.unpack(byte_data)[0]
            
            # Apply transform if defined
            if self.transform:
                value = self.transform(value)
            
            return value
        
        return raw_data


class Interface(BasicRevert, BaseInterface):
    """
    Enhanced Modbus Interface with multi-unit gateway support.
    
    Architecture:
    - Each gateway represents a single TCP-to-RTU bridge device
    - Only one TCP socket is maintained per gateway
    - All units on the same bus share the gateway's single connection
    - Operations are serialized to prevent concurrent access issues
    - Unit IDs (0-255) are unique only within each bus, not globally
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.connection_pool = None
        self.gateway_manager = None
        self.template_engine = None
        self.register_manager = None
        self.gateways = {}
        self.unit_configs = {}
        self.health_status = defaultdict(dict)
        self._lock = RLock()  # gevent.lock.RLock for greenlet-safe synchronization
    
    def configure(self, config_dict, registry_config):
        """
        Configure the enhanced modbus driver
        
        Supports three configuration modes:
        1. Gateway as device with multiple units (each unit has its registry_config)
        2. Unit as device (uses singleton for connection sharing)
        3. Legacy single unit mode
        
        :param config_dict: Driver configuration dictionary
        :param registry_config: Register configuration - can be CSV string or parsed list
        """
        _log.info("Configuring Enhanced Modbus Driver")
        _log.debug(f"config_dict: {config_dict}")
        _log.debug(f"registry_config type: {type(registry_config)}")
        
        # Parse registry config if it's a string (CSV format)
        if isinstance(registry_config, str):
            _log.debug(f"Registry config is a string, parsing as CSV")
            registry_config_lst = self._parse_csv_config(registry_config)
        elif isinstance(registry_config, dict):
            _log.debug(f"Registry config dict keys: {list(registry_config.keys())}")
            _log.debug(f"Registry config dict values (first 100 chars): {str(registry_config)[:100]}")
            
            # Check if dict values are strings (CSV content or file paths) that need parsing
            first_value = next(iter(registry_config.values())) if registry_config else None
            
            if first_value and isinstance(first_value, str):
                if '\n' in first_value:
                    # Values are CSV strings, parse them
                    _log.debug(f"Registry config is a dict with CSV string values, parsing each")
                    parsed_config = {}
                    for key, csv_content in registry_config.items():
                        if isinstance(csv_content, str):
                            parsed_config[key] = self._parse_csv_config(csv_content)
                        else:
                            parsed_config[key] = csv_content
                    registry_config_lst = parsed_config
                elif first_value.startswith('config://'):
                    # Values are config file paths - platform driver should have loaded them
                    # but if not, log a warning
                    _log.warning(f"Registry config contains file paths ({first_value}), but files not loaded. "
                                "Platform driver should resolve config:// paths. "
                                "Attempting to continue with empty registry.")
                    registry_config_lst = {}
                else:
                    # Values might be single-line CSV or other format
                    _log.debug(f"Registry config is a dict with string values, attempting to parse")
                    parsed_config = {}
                    for key, value in registry_config.items():
                        if isinstance(value, str):
                            # Try to parse as CSV even without newlines
                            try:
                                parsed = self._parse_csv_config(value)
                                if parsed:
                                    parsed_config[key] = parsed
                                else:
                                    _log.warning(f"No registers parsed from unit {key} config")
                            except Exception as e:
                                _log.error(f"Error parsing config for unit {key}: {e}")
                        else:
                            parsed_config[key] = value
                    registry_config_lst = parsed_config
            else:
                _log.debug(f"Registry config is a dict, using as-is")
                registry_config_lst = registry_config
        else:
            _log.debug(f"Registry config is type {type(registry_config)}, using as-is")
            registry_config_lst = registry_config
        
        # The config_dict IS the driver_config (platform driver passes it directly)
        driver_config = config_dict
        
        # Determine deployment mode
        if 'gateway' in driver_config and 'units' in driver_config:
            # Gateway as device mode - multiple units with their own registry configs
            deployment_mode = 'gateway_device'
            use_singleton = False
        elif 'gateway' in driver_config and 'unit_id' in driver_config:
            # Unit as device mode - single unit, uses singleton
            deployment_mode = 'unit_device'
            use_singleton = True
        else:
            # Legacy mode - check for traditional modbus config keys
            deployment_mode = 'legacy'
            use_singleton = False
        
        _log.info(f"Deployment mode: {deployment_mode}")
        
        # Initialize components
        self.connection_pool = ConnectionPool(use_singleton=use_singleton, driver_instance=self)
        self.gateway_manager = GatewayManager()
        self.template_engine = ConfigTemplateEngine()
        self.register_manager = RegisterManager()
        self.deployment_mode = deployment_mode
        
        # Configure based on mode
        if deployment_mode == 'gateway_device':
            self._configure_gateway_device(driver_config, registry_config_lst)
        elif deployment_mode == 'unit_device':
            self._configure_unit_device(driver_config, registry_config_lst)
        else:
            # Legacy format - convert to enhanced
            self._configure_legacy(driver_config, registry_config_lst)
        
        # Build register maps for efficient scraping
        self.register_manager.build_register_maps()
        
        _log.info(f"Enhanced Modbus Driver configured successfully in {deployment_mode} mode")
    
    def _parse_csv_config(self, csv_string):
        """
        Parse CSV configuration string into list of register dictionaries
        
        :param csv_string: CSV format registry configuration
        :return: List of register configuration dictionaries
        """
        config = []
        
        try:
            # Use csv.DictReader to parse the CSV string
            reader = csv.DictReader(StringIO(csv_string))
            
            for row in reader:
                # Skip empty rows
                if not row.get('Volttron Point Name') and not row.get('Point Name'):
                    continue
                config.append(row)
            
            _log.debug(f"Parsed {len(config)} register configurations from CSV")
            
        except Exception as e:
            _log.error(f"Error parsing CSV configuration: {e}")
            # If CSV parsing fails, try to handle as a list
            # In case it's already parsed somehow
            if isinstance(csv_string, list):
                return csv_string
            raise
        
        return config
    
    def _configure_gateway_device(self, driver_config, registry_config_data):
        """
        Configure gateway as device mode.
        
        In this mode:
        - The gateway is the VOLTTRON device
        - Multiple units are configured, each with its own registry_config
        - All units share the single gateway connection
        
        :param driver_config: Driver configuration dictionary
        :param registry_config_data: Can be:
            - Dict mapping unit_id to register lists
            - List of registers (applied to all units)
            - Empty dict/None (check for registers in unit configs)
        """
        gateway_config = driver_config['gateway']
        
        # Setup gateway connection (support both 'address' and 'device_address' for compatibility)
        gateway_address = gateway_config.get('address', gateway_config.get('device_address'))
        if not gateway_address:
            raise ValueError("Gateway configuration must include 'address' or 'device_address'")
            
        gateway_id = self.gateway_manager.add_gateway(
            gateway_type=gateway_config.get('connection_type', 'tcp'),
            address=gateway_address,
            port=gateway_config.get('port', 502),
            baudrate=gateway_config.get('baudrate', 9600),
            retry_config={
                'attempts': gateway_config.get('retry_attempts', 3),
                'backoff': gateway_config.get('retry_backoff', 'exponential')
            }
        )
        
        # Process unit configurations (backward compatible with 'slaves' key)
        units = driver_config.get('units', driver_config.get('slaves', []))
        templates = driver_config.get('device_templates', {})
        
        for unit_config in units:
            _log.debug(f"Processing unit config: {unit_config}")
            # Support both 'unit_id' and 'slave_id' for backward compatibility
            unit_id = unit_config.get('unit_id', unit_config.get('slave_id'))
            # Handle both string and int unit_ids
            try:
                unit_id = int(unit_id)
            except (ValueError, TypeError):
                _log.warning(f"Invalid unit_id: {unit_id}, skipping")
                continue
                
            unit_id_str = str(unit_id)
            template_name = unit_config.get('template')
            
            # Get registers for this unit - check multiple sources
            registers = []
            
            # 1. Check if registry_config_data has unit-specific config (dict)
            if isinstance(registry_config_data, dict) and unit_id_str in registry_config_data:
                _log.debug(f"Looking for unit {unit_id_str} in registry_config_data keys: {list(registry_config_data.keys())}")
                unit_data = registry_config_data[unit_id_str]
                _log.debug(f"Found unit {unit_id_str} data, type: {type(unit_data)}")
                if isinstance(unit_data, str):
                    registers = self._parse_csv_config(unit_data)
                elif isinstance(unit_data, list):
                    registers = unit_data
                else:
                    _log.warning(f"Unknown registry data type for unit {unit_id}: {type(unit_data)}")
            
            # 2. Check if unit config has embedded registers
            elif 'registers' in unit_config and unit_config['registers']:
                _log.debug(f"Using embedded registers for unit {unit_id}")
                registers = unit_config['registers']
            
            # 3. Check for template
            elif template_name and template_name in templates:
                _log.debug(f"Using template {template_name} for unit {unit_id}")
                registers = self.template_engine.apply_template(
                    templates[template_name],
                    unit_config
                )
            
            # 4. If registry_config_data is a list, use it for all units
            elif isinstance(registry_config_data, list):
                _log.debug(f"Using registry_config_data list for unit {unit_id}, length: {len(registry_config_data)}")
                if registry_config_data:
                    _log.debug(f"First item in list: {registry_config_data[0] if registry_config_data else 'empty'}")
                registers = registry_config_data
            
            # 5. Empty fallback
            else:
                _log.warning(f"No registers found for unit {unit_id} ({unit_config.get('name', 'unnamed')})")
                _log.debug(f"registry_config_data type: {type(registry_config_data)}")
                _log.debug(f"registry_config_data: {registry_config_data}")
                registers = []
            
            _log.info(f"Unit {unit_id} ({unit_config.get('name', 'unnamed')}): {len(registers)} registers")
            
            # Assign unit to gateway
            self.gateway_manager.assign_unit_to_gateway(unit_id, gateway_id)
            
            # Add registers for this unit
            _log.debug(f"Processing {len(registers)} registers for unit {unit_id}")
            for idx, reg_dict in enumerate(registers):
                _log.debug(f"Processing register {idx+1}/{len(registers)} for unit {unit_id}")
                # Skip non-dictionary entries
                if not isinstance(reg_dict, dict):
                    _log.warning(f"Skipping non-dictionary register entry for unit {unit_id}")
                    continue
                
                # Detect format by checking for CSV-style keys
                if 'Point Address' in reg_dict or 'Volttron Point Name' in reg_dict:
                    # CSV format - handle various CSV header variations
                    point_name = reg_dict.get('Volttron Point Name', '')
                    if not point_name:
                        _log.debug(f"Skipping register with no point name: {reg_dict}")
                        continue
                    
                    # Get address from Point Address field
                    try:
                        address = int(reg_dict.get('Point Address', 0))
                    except (ValueError, TypeError):
                        _log.error(f"Invalid Point Address for {point_name}: {reg_dict.get('Point Address')}")
                        continue
                    
                    # Try to get register type from either 'Modbus Register' or 'Type' field
                    register_type = reg_dict.get('Modbus Register', reg_dict.get('Type', 'uint16')).lower()
                    if register_type == 'bool':
                        register_type = 'bit'
                    # Handle struct format strings that might be in either field
                    elif register_type.startswith('>') or register_type.startswith('<'):
                        # It's a struct format string, try to infer the type
                        if 'f' in register_type:
                            register_type = 'float'
                        elif 'i' in register_type or 'I' in register_type:
                            register_type = 'int32' if 'i' in register_type else 'uint32'
                        elif 'h' in register_type or 'H' in register_type:
                            register_type = 'int16' if 'h' in register_type else 'uint16'
                        else:
                            register_type = 'uint16'  # Default
                    
                    # Prefix point name with unit name for gateway device mode
                    full_point_name = f"{unit_config['name']}/{point_name}"
                    
                    # Parse transform if provided
                    transform = None
                    transform_str = reg_dict.get('Transform', '').strip()
                    if transform_str:
                        transform = create_transform(transform_str)
                        if not transform:
                            _log.warning(f"Could not create transform for {point_name}: {transform_str}")
                    
                    # Parse endianness settings
                    byte_order = '>'
                    word_order = '>'
                    if 'Byte Order' in reg_dict:
                        byte_order = '<' if reg_dict['Byte Order'].lower() in ['little', '<', 'le'] else '>'
                    elif 'Mixed Endian' in reg_dict and reg_dict['Mixed Endian'].lower() == 'true':
                        byte_order = '<'  # Mixed endian typically means little-endian bytes
                    
                    if 'Word Order' in reg_dict:
                        word_order = '<' if reg_dict['Word Order'].lower() in ['little', '<', 'le', 'low'] else '>'
                    
                    register = EnhancedModbusRegister(
                        address=address,
                        register_type=register_type,
                        read_only=reg_dict.get('Writable', '').lower() != 'true',
                        point_name=full_point_name,
                        units=reg_dict.get('Units', ''),
                        unit_id=unit_id,
                        gateway_id=gateway_id,
                        description=reg_dict.get('Notes', ''),
                        mixed_endian=reg_dict.get('Mixed Endian', '').lower() == 'true',
                        transform=transform,
                        byte_order=byte_order,
                        word_order=word_order
                    )
                elif 'address' in reg_dict:
                    # JSON/dict format
                    # Parse transform if provided
                    transform = None
                    if 'transform' in reg_dict:
                        transform_str = reg_dict['transform']
                        if isinstance(transform_str, str):
                            transform = create_transform(transform_str)
                            if not transform:
                                _log.warning(f"Could not create transform: {transform_str}")
                        elif callable(transform_str):
                            transform = transform_str  # Already a callable
                        else:
                            _log.warning(f"Transform is not callable: {transform_str}")
                    
                    # Parse endianness settings
                    byte_order = '>'
                    word_order = '>'
                    if 'byte_order' in reg_dict:
                        byte_order = '<' if reg_dict['byte_order'] in ['little', '<', 'le'] else '>'
                    elif reg_dict.get('mixed_endian', False):
                        byte_order = '<'
                    
                    if 'word_order' in reg_dict:
                        word_order = '<' if reg_dict['word_order'] in ['little', '<', 'le', 'low'] else '>'
                    
                    register = EnhancedModbusRegister(
                        address=reg_dict['address'],
                        register_type=reg_dict.get('type', 'uint16'),
                        read_only=not reg_dict.get('writable', False),
                        point_name=f"{unit_config['name']}/{reg_dict['name']}",
                        units=reg_dict.get('units', ''),
                        unit_id=unit_id,
                        gateway_id=gateway_id,
                        description=reg_dict.get('description', ''),
                        mixed_endian=reg_dict.get('mixed_endian', False),
                        transform=transform,
                        byte_order=byte_order,
                        word_order=word_order
                    )
                else:
                    _log.warning(f"Register dict missing required fields (Point Address or address): {reg_dict}")
                    continue
                
                self.register_manager.add_register(register)
                _log.debug(f"Added register {register.point_name} to register_manager")
                
                self.insert_register(register)
                _log.debug(f"Inserted register {register.point_name} to interface")
                
                # Set default values if specified
                if not register.read_only:
                    default_value = reg_dict.get('Default Value', '').strip()
                    if default_value:
                        try:
                            _log.debug(f"Setting default value {default_value} for {register.point_name}")
                            self.set_default(register.point_name, register.python_type(default_value))
                        except (ValueError, TypeError) as e:
                            _log.warning(f"Could not set default value {default_value} for {register.point_name}: {e}")
                        except Exception as e:
                            _log.error(f"Unexpected error setting default for {register.point_name}: {e}")
            
            self.unit_configs[unit_id] = unit_config
            _log.debug(f"Completed configuration for unit {unit_id}")
    
    def _configure_legacy(self, config_dict, registry_config_lst):
        """Configure using legacy format for backward compatibility"""
        # Convert legacy config to enhanced format
        connection_type = 'tcp' if 'port' in config_dict else 'serial'
        
        gateway_id = self.gateway_manager.add_gateway(
            gateway_type=connection_type,
            address=config_dict.get('device_address', config_dict.get('ip_address')),
            port=config_dict.get('port', 502) if connection_type == 'tcp' else None,
            baudrate=config_dict.get('baudrate', 9600)
        )
        
        unit_id = config_dict.get('slave_id', config_dict.get('unit_id', 1))
        
        # Process legacy register configuration
        for reg_dict in registry_config_lst:
            # Check if reg_dict is actually a dictionary
            if not isinstance(reg_dict, dict):
                _log.warning(f"Skipping non-dictionary entry in registry config: {type(reg_dict)}")
                continue
                
            if not reg_dict.get('Volttron Point Name'):
                continue
            
            register_type = reg_dict.get('Modbus Register', 'uint16').lower()
            if register_type == 'bool':
                register_type = 'bit'
            
            # Parse transform if provided
            transform = None
            transform_str = reg_dict.get('Transform', '').strip()
            if transform_str:
                transform = create_transform(transform_str)
                if not transform:
                    _log.warning(f"Could not create transform: {transform_str}")
            
            # Parse endianness settings
            byte_order = '>'
            word_order = '>'
            if 'Byte Order' in reg_dict:
                byte_order = '<' if reg_dict['Byte Order'].lower() in ['little', '<', 'le'] else '>'
            elif reg_dict.get('Mixed Endian', '').lower() == 'true':
                byte_order = '<'
            
            if 'Word Order' in reg_dict:
                word_order = '<' if reg_dict['Word Order'].lower() in ['little', '<', 'le', 'low'] else '>'
            
            register = EnhancedModbusRegister(
                address=int(reg_dict['Point Address']),
                register_type=register_type,
                read_only=reg_dict.get('Writable', '').lower() != 'true',
                point_name=reg_dict['Volttron Point Name'],
                units=reg_dict.get('Units', ''),
                unit_id=unit_id,
                gateway_id=gateway_id,
                description=reg_dict.get('Notes', ''),
                mixed_endian=reg_dict.get('Mixed Endian', '').lower() == 'true',
                transform=transform,
                byte_order=byte_order,
                word_order=word_order
            )
            
            self.register_manager.add_register(register)
            self.insert_register(register)
            
            # Set default values
            if not register.read_only:
                default_value = reg_dict.get('Default Value', '').strip()
                if default_value:
                    self.set_default(register.point_name, register.python_type(default_value))
        
        self.unit_configs[unit_id] = {'name': f'unit_{unit_id}', 'unit_id': unit_id}
    
    def _configure_unit_device(self, driver_config, registry_config_lst):
        """
        Configure unit as device mode.
        
        In this mode:
        - Each unit is its own VOLTTRON device
        - Each gets its own driver instance
        - Connections are shared via singleton
        """
        gateway_config = driver_config['gateway']
        unit_id = driver_config.get('unit_id', driver_config.get('slave_id', 1))
        
        # Setup gateway connection (support both 'address' and 'device_address' for compatibility)
        gateway_address = gateway_config.get('address', gateway_config.get('device_address'))
        if not gateway_address:
            raise ValueError("Gateway configuration must include 'address' or 'device_address'")
            
        gateway_id = self.gateway_manager.add_gateway(
            gateway_type=gateway_config.get('connection_type', 'tcp'),
            address=gateway_address,
            port=gateway_config.get('port', 502),
            baudrate=gateway_config.get('baudrate', 9600),
            retry_config={
                'attempts': gateway_config.get('retry_attempts', 3),
                'backoff': gateway_config.get('retry_backoff', 'exponential')
            }
        )
        
        # Process registers for this single unit
        for reg_dict in registry_config_lst:
            # Check if reg_dict is actually a dictionary
            if not isinstance(reg_dict, dict):
                _log.warning(f"Skipping non-dictionary entry in registry config: {type(reg_dict)}")
                continue
                
            if not reg_dict.get('Volttron Point Name'):
                continue
            
            register_type = reg_dict.get('Modbus Register', 'uint16').lower()
            if register_type == 'bool':
                register_type = 'bit'
            
            # Parse transform if provided
            transform = None
            transform_str = reg_dict.get('Transform', '').strip()
            if transform_str:
                transform = create_transform(transform_str)
                if not transform:
                    _log.warning(f"Could not create transform: {transform_str}")
            
            # Parse endianness settings
            byte_order = '>'
            word_order = '>'
            if 'Byte Order' in reg_dict:
                byte_order = '<' if reg_dict['Byte Order'].lower() in ['little', '<', 'le'] else '>'
            elif reg_dict.get('Mixed Endian', '').lower() == 'true':
                byte_order = '<'
            
            if 'Word Order' in reg_dict:
                word_order = '<' if reg_dict['Word Order'].lower() in ['little', '<', 'le', 'low'] else '>'
            
            register = EnhancedModbusRegister(
                address=int(reg_dict['Point Address']),
                register_type=register_type,
                read_only=reg_dict.get('Writable', '').lower() != 'true',
                point_name=reg_dict['Volttron Point Name'],
                units=reg_dict.get('Units', ''),
                unit_id=unit_id,
                gateway_id=gateway_id,
                description=reg_dict.get('Notes', ''),
                mixed_endian=reg_dict.get('Mixed Endian', '').lower() == 'true',
                transform=transform,
                byte_order=byte_order,
                word_order=word_order
            )
            
            self.register_manager.add_register(register)
            self.insert_register(register)
            
            # Set default values
            if not register.read_only:
                default_value = reg_dict.get('Default Value', '').strip()
                if default_value:
                    self.set_default(register.point_name, register.python_type(default_value))
        
        self.unit_configs[unit_id] = {'name': f'unit_{unit_id}', 'unit_id': unit_id}
    
    def get_point(self, point_name):
        """Get single point value"""
        register = self.get_register_by_name(point_name)
        gateway = self.gateway_manager.get_gateway(register.gateway_id)
        
        with self.connection_pool.get_connection(gateway) as client:
            try:
                if register.register_type == 'bit':
                    if register.read_only:
                        response = client.read_discrete_inputs(register.address, 1, unit=register.unit_id)
                    else:
                        response = client.read_coils(register.address, 1, unit=register.unit_id)
                    value = response.bits[0]
                else:
                    count = 2 if register.register_type in ['float', 'int32', 'uint32'] else 1
                    if register.read_only:
                        response = client.read_input_registers(register.address, count, unit=register.unit_id)
                    else:
                        response = client.read_holding_registers(register.address, count, unit=register.unit_id)
                    value = register.parse_value(response.registers)
                
                self._update_health_status(register.unit_id, True)
                return value
                
            except (ConnectionException, ModbusIOException, ModbusException) as e:
                _log.error(f"Error reading point {point_name}: {e}")
                self._update_health_status(register.unit_id, False, str(e))
                return None
    
    def _set_point(self, point_name, value):
        """Set single point value"""
        register = self.get_register_by_name(point_name)
        if register.read_only:
            raise IOError(f"Trying to write to read-only point: {point_name}")
        
        gateway = self.gateway_manager.get_gateway(register.gateway_id)
        
        with self.connection_pool.get_connection(gateway) as client:
            try:
                if register.register_type == 'bit':
                    response = client.write_coil(register.address, value, unit=register.unit_id)
                else:
                    # Convert value to registers
                    if register.register_type in ['float', 'int32', 'uint32']:
                        packed = register._parse_struct.pack(value)
                        # Handle word order when writing
                        if register.word_order == '<':
                            # Swap words before unpacking to registers
                            packed = packed[2:4] + packed[0:2]
                        registers = struct.unpack('>HH', packed)
                        response = client.write_registers(register.address, registers, unit=register.unit_id)
                    else:
                        response = client.write_register(register.address, int(value), unit=register.unit_id)
                
                self._update_health_status(register.unit_id, True)
                return self.get_point(point_name)
                
            except (ConnectionException, ModbusIOException, ModbusException) as e:
                _log.error(f"Error writing point {point_name}: {e}")
                self._update_health_status(register.unit_id, False, str(e))
                raise IOError(f"Error writing to point {point_name}: {e}")
    
    def _scrape_all(self):
        """Scrape all points efficiently using batched requests"""
        result_dict = {}
        
        # Group registers by gateway and unit for efficient batching
        grouped_registers = self.register_manager.get_grouped_registers()
        
        for gateway_id, unit_groups in grouped_registers.items():
            gateway = self.gateway_manager.get_gateway(gateway_id)
            
            with self.connection_pool.get_connection(gateway) as client:
                for unit_id, register_groups in unit_groups.items():
                    try:
                        # Scrape all register types for this unit
                        unit_results = self._scrape_unit(client, unit_id, register_groups)
                        result_dict.update(unit_results)
                        self._update_health_status(unit_id, True)
                        
                        # Yield to other greenlets periodically
                        sleep(0)  # Cooperative yield
                        
                    except (ConnectionException, ModbusIOException, ModbusException) as e:
                        _log.error(f"Error scraping unit {unit_id}: {e}")
                        self._update_health_status(unit_id, False, str(e))
        
        return result_dict
    
    def _scrape_unit(self, client, unit_id, register_groups):
        """Scrape all registers for a specific unit"""
        results = {}
        
        for register_type, ranges in register_groups.items():
            for start, end, registers in ranges:
                try:
                    if 'bit' in register_type:
                        # Read coils/discrete inputs
                        count = end - start + 1
                        if 'read_only' in register_type:
                            response = client.read_discrete_inputs(start, count, unit=unit_id)
                        else:
                            response = client.read_coils(start, count, unit=unit_id)
                        
                        for reg in registers:
                            idx = reg.address - start
                            results[reg.point_name] = response.bits[idx]
                    else:
                        # Read holding/input registers
                        count = end - start + 1
                        if 'read_only' in register_type:
                            response = client.read_input_registers(start, count, unit=unit_id)
                        else:
                            response = client.read_holding_registers(start, count, unit=unit_id)
                        
                        for reg in registers:
                            idx = reg.address - start
                            reg_count = 2 if reg.register_type in ['float', 'int32', 'uint32'] else 1
                            raw_data = response.registers[idx:idx + reg_count]
                            results[reg.point_name] = reg.parse_value(raw_data)
                            
                except Exception as e:
                    _log.error(f"Error reading {register_type} at {start}-{end} for unit {unit_id}: {e}")
        
        return results
    
    def _update_health_status(self, unit_id, success, error_msg=None):
        """Update health status for a unit device"""
        with self._lock:
            self.health_status[unit_id] = {
                'online': success,
                'last_update': utils.get_aware_utc_now(),
                'error': error_msg
            }
    
    def get_health_status(self):
        """Get health status of all unit devices"""
        with self._lock:
            return dict(self.health_status)