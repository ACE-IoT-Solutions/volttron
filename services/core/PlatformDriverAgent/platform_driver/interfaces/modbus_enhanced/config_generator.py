#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Configuration Generator Tool for Enhanced Modbus Driver

Command-line tool for generating modbus device configurations using templates.
"""

import argparse
import json
import csv
import os
import sys
from typing import Dict, List, Any

from config_template import ConfigTemplateEngine


class ConfigGenerator:
    """
    Configuration generator for enhanced modbus driver
    """
    
    def __init__(self):
        self.template_engine = ConfigTemplateEngine()
    
    def generate_gateway_config(self, connection_type: str, address: str, 
                               port: int = None, **kwargs) -> Dict:
        """
        Generate gateway configuration
        
        :param connection_type: 'tcp' or 'serial'
        :param address: IP address or serial device path
        :param port: Port number for TCP
        :return: Gateway configuration dictionary
        """
        config = {
            'connection_type': connection_type,
            'address': address
        }
        
        if connection_type == 'tcp':
            config['port'] = port or 502
        else:
            config['baudrate'] = kwargs.get('baudrate', 9600)
            config['bytesize'] = kwargs.get('bytesize', 8)
            config['parity'] = kwargs.get('parity', 'N')
            config['stopbits'] = kwargs.get('stopbits', 1)
        
        # Add retry configuration
        config['retry_attempts'] = kwargs.get('retry_attempts', 3)
        config['retry_backoff'] = kwargs.get('retry_backoff', 'exponential')
        config['connection_pool_size'] = kwargs.get('connection_pool_size', 5)
        
        return config
    
    def generate_device_config(self, template: str, unit_id: int, 
                              name: str = None, **kwargs) -> Dict:
        """
        Generate device configuration using a template
        
        :param template: Template name
        :param unit_id: Modbus unit ID
        :param name: Device name
        :return: Device configuration dictionary
        """
        config = {
            'unit_id': unit_id,
            'name': name or f'device_{unit_id}',
            'template': template
        }
        
        # Add any additional parameters
        if 'register_offset' in kwargs:
            config['register_offset'] = kwargs['register_offset']
        
        if 'name_prefix' in kwargs:
            config['name_prefix'] = kwargs['name_prefix']
        
        return config
    
    def generate_multi_unit_config(self, gateway_config: Dict, 
                                  devices: List[Dict]) -> Dict:
        """
        Generate complete configuration for multiple units on a gateway
        
        :param gateway_config: Gateway configuration
        :param devices: List of device configurations
        :return: Complete driver configuration
        """
        return {
            'driver_type': 'modbus_enhanced',
            'driver_config': {
                'gateway': gateway_config,
                'units': devices
            }
        }
    
    def generate_from_csv(self, csv_file: str, template_name: str = None) -> Dict:
        """
        Generate configuration from a CSV file
        
        CSV format:
        unit_id,name,template,register_offset,gateway_address,gateway_port
        
        :param csv_file: Path to CSV file
        :param template_name: Default template name if not in CSV
        :return: Configuration dictionary
        """
        devices_by_gateway = {}
        
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                # Parse gateway info
                gateway_address = row.get('gateway_address', '127.0.0.1')
                gateway_port = int(row.get('gateway_port', 502))
                gateway_key = f"{gateway_address}:{gateway_port}"
                
                if gateway_key not in devices_by_gateway:
                    devices_by_gateway[gateway_key] = {
                        'gateway': self.generate_gateway_config(
                            'tcp', gateway_address, gateway_port
                        ),
                        'devices': []
                    }
                
                # Parse device info
                device = self.generate_device_config(
                    template=row.get('template', template_name),
                    unit_id=int(row['unit_id']),
                    name=row.get('name'),
                    register_offset=int(row.get('register_offset', 0))
                )
                
                devices_by_gateway[gateway_key]['devices'].append(device)
        
        # If single gateway, return simple config
        if len(devices_by_gateway) == 1:
            gw_data = list(devices_by_gateway.values())[0]
            return self.generate_multi_unit_config(
                gw_data['gateway'], 
                gw_data['devices']
            )
        
        # Multiple gateways - return list of configs
        configs = []
        for gw_key, gw_data in devices_by_gateway.items():
            configs.append(self.generate_multi_unit_config(
                gw_data['gateway'],
                gw_data['devices']
            ))
        
        return {'configurations': configs}
    
    def create_example_configs(self, output_dir: str):
        """
        Create example configuration files
        
        :param output_dir: Directory to write example files
        """
        os.makedirs(output_dir, exist_ok=True)
        
        # Example 1: Single gateway with multiple power meters
        config1 = self.generate_multi_unit_config(
            gateway_config=self.generate_gateway_config('tcp', '192.168.1.100', 502),
            devices=[
                self.generate_device_config('power_meter_basic', 1, 'meter_floor1'),
                self.generate_device_config('power_meter_basic', 2, 'meter_floor2'),
                self.generate_device_config('power_meter_basic', 3, 'meter_floor3')
            ]
        )
        
        with open(os.path.join(output_dir, 'multi_power_meters.json'), 'w') as f:
            json.dump(config1, f, indent=2)
        
        # Example 2: Serial RTU with temperature sensors
        config2 = self.generate_multi_unit_config(
            gateway_config=self.generate_gateway_config(
                'serial', '/dev/ttyUSB0',
                baudrate=19200, parity='E'
            ),
            devices=[
                self.generate_device_config('temperature_sensor', i, f'temp_zone_{i}')
                for i in range(1, 11)
            ]
        )
        
        with open(os.path.join(output_dir, 'serial_temp_sensors.json'), 'w') as f:
            json.dump(config2, f, indent=2)
        
        # Example 3: Mixed device types
        config3 = self.generate_multi_unit_config(
            gateway_config=self.generate_gateway_config('tcp', '10.0.0.50', 502),
            devices=[
                self.generate_device_config('power_meter_basic', 1, 'main_meter'),
                self.generate_device_config('vfd_drive', 10, 'pump_vfd_1'),
                self.generate_device_config('vfd_drive', 11, 'pump_vfd_2'),
                self.generate_device_config('digital_io', 20, 'relay_panel'),
                self.generate_device_config('temperature_sensor', 30, 'ambient_temp')
            ]
        )
        
        with open(os.path.join(output_dir, 'mixed_devices.json'), 'w') as f:
            json.dump(config3, f, indent=2)
        
        # Example CSV for bulk generation
        csv_data = [
            ['unit_id', 'name', 'template', 'register_offset', 'gateway_address', 'gateway_port'],
            ['1', 'building_a_meter', 'power_meter_basic', '0', '192.168.1.10', '502'],
            ['2', 'building_b_meter', 'power_meter_basic', '0', '192.168.1.10', '502'],
            ['3', 'building_c_meter', 'power_meter_basic', '0', '192.168.1.10', '502'],
            ['10', 'chiller_1', 'vfd_drive', '0', '192.168.1.20', '502'],
            ['11', 'chiller_2', 'vfd_drive', '0', '192.168.1.20', '502']
        ]
        
        csv_file = os.path.join(output_dir, 'device_list.csv')
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(csv_data)
        
        print(f"Example configurations created in {output_dir}")
        print(f"Files created:")
        print(f"  - multi_power_meters.json")
        print(f"  - serial_temp_sensors.json")
        print(f"  - mixed_devices.json")
        print(f"  - device_list.csv")


def main():
    """Main entry point for command-line tool"""
    parser = argparse.ArgumentParser(
        description='Generate Enhanced Modbus Driver configurations'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Generate command
    gen_parser = subparsers.add_parser('generate', help='Generate configuration')
    gen_parser.add_argument('--gateway-type', choices=['tcp', 'serial'], 
                           default='tcp', help='Gateway connection type')
    gen_parser.add_argument('--address', required=True, 
                           help='Gateway address (IP or device path)')
    gen_parser.add_argument('--port', type=int, default=502, 
                           help='TCP port (default: 502)')
    gen_parser.add_argument('--template', required=True, 
                           help='Device template name')
    gen_parser.add_argument('--units', type=str, required=True,
                           help='Unit IDs (comma-separated or range, e.g., "1,2,3" or "1-10")')
    gen_parser.add_argument('--name-prefix', help='Prefix for device names')
    gen_parser.add_argument('--output', '-o', help='Output file (default: stdout)')
    
    # From CSV command
    csv_parser = subparsers.add_parser('from-csv', help='Generate from CSV file')
    csv_parser.add_argument('csv_file', help='Input CSV file')
    csv_parser.add_argument('--template', help='Default template if not in CSV')
    csv_parser.add_argument('--output', '-o', help='Output file (default: stdout)')
    
    # Examples command
    ex_parser = subparsers.add_parser('examples', help='Create example configurations')
    ex_parser.add_argument('--output-dir', default='./examples', 
                          help='Output directory (default: ./examples)')
    
    # List templates command
    list_parser = subparsers.add_parser('list-templates', 
                                       help='List available templates')
    
    args = parser.parse_args()
    
    generator = ConfigGenerator()
    
    if args.command == 'generate':
        # Parse unit IDs
        unit_ids = []
        for part in args.units.split(','):
            if '-' in part:
                start, end = map(int, part.split('-'))
                unit_ids.extend(range(start, end + 1))
            else:
                unit_ids.append(int(part))
        
        # Generate gateway config
        gateway_config = generator.generate_gateway_config(
            args.gateway_type, args.address, args.port
        )
        
        # Generate device configs
        devices = []
        for unit_id in unit_ids:
            name = f"{args.name_prefix}_{unit_id}" if args.name_prefix else None
            device = generator.generate_device_config(
                args.template, unit_id, name
            )
            devices.append(device)
        
        # Generate complete config
        config = generator.generate_multi_unit_config(gateway_config, devices)
        
        # Output
        output_str = json.dumps(config, indent=2)
        if args.output:
            with open(args.output, 'w') as f:
                f.write(output_str)
            print(f"Configuration written to {args.output}")
        else:
            print(output_str)
    
    elif args.command == 'from-csv':
        config = generator.generate_from_csv(args.csv_file, args.template)
        
        output_str = json.dumps(config, indent=2)
        if args.output:
            with open(args.output, 'w') as f:
                f.write(output_str)
            print(f"Configuration written to {args.output}")
        else:
            print(output_str)
    
    elif args.command == 'examples':
        generator.create_example_configs(args.output_dir)
    
    elif args.command == 'list-templates':
        print("Available templates:")
        print("\nBase templates:")
        for name in generator.template_engine.base_templates:
            print(f"  - {name}")
        
        if generator.template_engine.templates:
            print("\nCustom templates:")
            for name in generator.template_engine.templates:
                print(f"  - {name}")
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()