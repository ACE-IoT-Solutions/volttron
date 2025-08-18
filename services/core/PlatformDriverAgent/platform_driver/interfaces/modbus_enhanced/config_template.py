# -*- coding: utf-8 -*-
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

"""
Configuration Template Engine for Enhanced Modbus Driver

Provides templating capabilities for easy deployment of multiple similar devices.
"""

import logging
import json
import copy
from typing import Dict, List, Any, Optional
from string import Template

_log = logging.getLogger(__name__)


class ConfigTemplateEngine:
    """
    Template engine for generating modbus device configurations.
    
    Features:
    - Register template definitions
    - Variable substitution
    - Bulk configuration generation
    - Template inheritance
    - Auto-offset calculation for register addresses
    """
    
    def __init__(self):
        self.templates: Dict[str, Dict] = {}
        self.base_templates: Dict[str, Dict] = self._load_base_templates()
    
    def _load_base_templates(self) -> Dict[str, Dict]:
        """Load built-in base templates for common device types"""
        return {
            'power_meter_basic': {
                'registers': [
                    {'name': 'voltage_l1', 'address': 0, 'type': 'float', 'units': 'V', 'writable': False},
                    {'name': 'voltage_l2', 'address': 2, 'type': 'float', 'units': 'V', 'writable': False},
                    {'name': 'voltage_l3', 'address': 4, 'type': 'float', 'units': 'V', 'writable': False},
                    {'name': 'current_l1', 'address': 6, 'type': 'float', 'units': 'A', 'writable': False},
                    {'name': 'current_l2', 'address': 8, 'type': 'float', 'units': 'A', 'writable': False},
                    {'name': 'current_l3', 'address': 10, 'type': 'float', 'units': 'A', 'writable': False},
                    {'name': 'power_total', 'address': 12, 'type': 'float', 'units': 'kW', 'writable': False},
                    {'name': 'energy_total', 'address': 14, 'type': 'float', 'units': 'kWh', 'writable': False},
                    {'name': 'power_factor', 'address': 16, 'type': 'float', 'units': '', 'writable': False},
                    {'name': 'frequency', 'address': 18, 'type': 'float', 'units': 'Hz', 'writable': False}
                ]
            },
            'temperature_sensor': {
                'registers': [
                    {'name': 'temperature', 'address': 0, 'type': 'float', 'units': '°C', 'writable': False},
                    {'name': 'humidity', 'address': 2, 'type': 'float', 'units': '%', 'writable': False},
                    {'name': 'setpoint', 'address': 4, 'type': 'float', 'units': '°C', 'writable': True},
                    {'name': 'deadband', 'address': 6, 'type': 'float', 'units': '°C', 'writable': True},
                    {'name': 'status', 'address': 8, 'type': 'uint16', 'units': '', 'writable': False}
                ]
            },
            'digital_io': {
                'registers': [
                    {'name': 'input_1', 'address': 0, 'type': 'bit', 'units': '', 'writable': False},
                    {'name': 'input_2', 'address': 1, 'type': 'bit', 'units': '', 'writable': False},
                    {'name': 'input_3', 'address': 2, 'type': 'bit', 'units': '', 'writable': False},
                    {'name': 'input_4', 'address': 3, 'type': 'bit', 'units': '', 'writable': False},
                    {'name': 'output_1', 'address': 10, 'type': 'bit', 'units': '', 'writable': True},
                    {'name': 'output_2', 'address': 11, 'type': 'bit', 'units': '', 'writable': True},
                    {'name': 'output_3', 'address': 12, 'type': 'bit', 'units': '', 'writable': True},
                    {'name': 'output_4', 'address': 13, 'type': 'bit', 'units': '', 'writable': True}
                ]
            },
            'vfd_drive': {
                'registers': [
                    {'name': 'frequency_command', 'address': 0, 'type': 'uint16', 'units': 'Hz', 'writable': True, 'scale': 0.1},
                    {'name': 'frequency_output', 'address': 1, 'type': 'uint16', 'units': 'Hz', 'writable': False, 'scale': 0.1},
                    {'name': 'current_output', 'address': 2, 'type': 'uint16', 'units': 'A', 'writable': False, 'scale': 0.1},
                    {'name': 'voltage_output', 'address': 3, 'type': 'uint16', 'units': 'V', 'writable': False},
                    {'name': 'motor_speed', 'address': 4, 'type': 'uint16', 'units': 'RPM', 'writable': False},
                    {'name': 'torque', 'address': 5, 'type': 'int16', 'units': '%', 'writable': False},
                    {'name': 'status_word', 'address': 6, 'type': 'uint16', 'units': '', 'writable': False},
                    {'name': 'control_word', 'address': 7, 'type': 'uint16', 'units': '', 'writable': True},
                    {'name': 'fault_code', 'address': 8, 'type': 'uint16', 'units': '', 'writable': False}
                ]
            }
        }
    
    def register_template(self, name: str, template: Dict):
        """
        Register a new device template
        
        :param name: Template name
        :param template: Template definition dictionary
        """
        self.templates[name] = template
        _log.info(f"Registered template: {name}")
    
    def apply_template(self, template_name: str, device_config: Dict) -> List[Dict]:
        """
        Apply a template to generate device register configuration
        
        :param template_name: Name of the template to apply
        :param device_config: Device-specific configuration with variables
        :return: List of register configurations
        """
        # Get template
        if template_name in self.templates:
            template = self.templates[template_name]
        elif template_name in self.base_templates:
            template = self.base_templates[template_name]
        else:
            raise ValueError(f"Template {template_name} not found")
        
        # Deep copy template to avoid modifications
        template = copy.deepcopy(template)
        
        # Apply variable substitutions
        registers = self._process_template(template, device_config)
        
        # Apply register offset if specified
        register_offset = device_config.get('register_offset', 0)
        if register_offset:
            for reg in registers:
                reg['address'] += register_offset
        
        # Apply name prefix if specified
        name_prefix = device_config.get('name_prefix', '')
        if name_prefix:
            for reg in registers:
                reg['name'] = f"{name_prefix}_{reg['name']}"
        
        return registers
    
    def _process_template(self, template: Dict, variables: Dict) -> List[Dict]:
        """
        Process template with variable substitution
        
        :param template: Template dictionary
        :param variables: Variables for substitution
        :return: Processed register list
        """
        registers = template.get('registers', [])
        processed_registers = []
        
        for reg in registers:
            processed_reg = {}
            
            for key, value in reg.items():
                if isinstance(value, str) and '$' in value:
                    # Perform variable substitution
                    tmpl = Template(value)
                    processed_reg[key] = tmpl.safe_substitute(variables)
                else:
                    processed_reg[key] = value
            
            # Apply transforms if specified
            if 'transform' in variables:
                transform_name = variables['transform']
                if transform_name and key == 'name':
                    processed_reg['transform'] = transform_name
            
            processed_registers.append(processed_reg)
        
        return processed_registers
    
    def generate_bulk_config(self, template_name: str, device_specs: List[Dict]) -> Dict:
        """
        Generate configuration for multiple devices using a template
        
        :param template_name: Template to use
        :param device_specs: List of device specifications
        :return: Complete configuration dictionary
        """
        config = {
            'driver_type': 'modbus_enhanced',
            'driver_config': {
                'units': []
            },
            'device_templates': {}
        }
        
        # Add template to config if custom
        if template_name in self.templates:
            config['device_templates'][template_name] = self.templates[template_name]
        
        # Generate configuration for each device
        for spec in device_specs:
            unit_config = {
                'unit_id': spec['unit_id'],
                'name': spec.get('name', f"device_{spec['unit_id']}"),
                'template': template_name
            }
            
            # Add any device-specific overrides
            if 'register_offset' in spec:
                unit_config['register_offset'] = spec['register_offset']
            
            if 'name_prefix' in spec:
                unit_config['name_prefix'] = spec['name_prefix']
            
            config['driver_config']['units'].append(unit_config)
        
        return config
    
    def create_template_from_csv(self, csv_data: List[Dict]) -> Dict:
        """
        Create a template from CSV register data
        
        :param csv_data: List of register dictionaries from CSV
        :return: Template dictionary
        """
        template = {'registers': []}
        
        for row in csv_data:
            register = {
                'name': row.get('register_name', row.get('Volttron Point Name', '')),
                'address': int(row.get('address', row.get('Point Address', 0))),
                'type': self._map_register_type(row.get('type', row.get('Modbus Register', 'uint16'))),
                'units': row.get('units', row.get('Units', '')),
                'writable': self._parse_bool(row.get('writable', row.get('Writable', 'false'))),
            }
            
            # Add optional fields
            if row.get('description', row.get('Notes')):
                register['description'] = row.get('description', row.get('Notes'))
            
            if row.get('scale'):
                register['scale'] = float(row['scale'])
            
            if row.get('mixed_endian', row.get('Mixed Endian')):
                register['mixed_endian'] = self._parse_bool(row.get('mixed_endian', row.get('Mixed Endian', 'false')))
            
            template['registers'].append(register)
        
        return template
    
    def _map_register_type(self, type_str: str) -> str:
        """Map various type strings to standard types"""
        type_map = {
            'bool': 'bit',
            'boolean': 'bit',
            'coil': 'bit',
            'short': 'int16',
            'ushort': 'uint16',
            'word': 'uint16',
            'int': 'int32',
            'uint': 'uint32',
            'dword': 'uint32',
            'long': 'int32',
            'ulong': 'uint32',
            'float32': 'float',
            'real': 'float'
        }
        
        lower_type = type_str.lower()
        return type_map.get(lower_type, lower_type)
    
    def _parse_bool(self, value: str) -> bool:
        """Parse boolean string value"""
        if isinstance(value, bool):
            return value
        
        return value.lower() in ('true', 'yes', '1', 't', 'y')
    
    def validate_template(self, template: Dict) -> List[str]:
        """
        Validate a template for correctness
        
        :param template: Template to validate
        :return: List of validation errors (empty if valid)
        """
        errors = []
        
        if 'registers' not in template:
            errors.append("Template must contain 'registers' field")
            return errors
        
        if not isinstance(template['registers'], list):
            errors.append("'registers' must be a list")
            return errors
        
        register_names = set()
        register_addresses = set()
        
        for i, reg in enumerate(template['registers']):
            # Check required fields
            if 'name' not in reg:
                errors.append(f"Register {i}: missing 'name' field")
            elif reg['name'] in register_names:
                errors.append(f"Register {i}: duplicate name '{reg['name']}'")
            else:
                register_names.add(reg['name'])
            
            if 'address' not in reg:
                errors.append(f"Register {i}: missing 'address' field")
            elif not isinstance(reg['address'], (int, float)):
                errors.append(f"Register {i}: 'address' must be numeric")
            else:
                addr = int(reg['address'])
                if addr in register_addresses:
                    errors.append(f"Register {i}: duplicate address {addr}")
                register_addresses.add(addr)
            
            if 'type' not in reg:
                errors.append(f"Register {i}: missing 'type' field")
            elif reg['type'] not in ['bit', 'int16', 'uint16', 'int32', 'uint32', 'float']:
                errors.append(f"Register {i}: invalid type '{reg['type']}'")
            
            if 'writable' in reg and not isinstance(reg['writable'], bool):
                errors.append(f"Register {i}: 'writable' must be boolean")
        
        return errors
    
    def export_templates(self, filename: str):
        """Export all templates to a JSON file"""
        all_templates = {
            'base_templates': self.base_templates,
            'custom_templates': self.templates
        }
        
        with open(filename, 'w') as f:
            json.dump(all_templates, f, indent=2)
        
        _log.info(f"Exported templates to {filename}")
    
    def import_templates(self, filename: str):
        """Import templates from a JSON file"""
        with open(filename, 'r') as f:
            all_templates = json.load(f)
        
        if 'custom_templates' in all_templates:
            self.templates.update(all_templates['custom_templates'])
        
        _log.info(f"Imported templates from {filename}")