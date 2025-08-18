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
Register Manager for Enhanced Modbus Driver

Manages register definitions and provides efficient batching for modbus operations.
"""

import logging
from typing import Dict, List, Tuple, Any
from collections import defaultdict

_log = logging.getLogger(__name__)


class RegisterManager:
    """
    Manages modbus registers with support for:
    - Efficient register range merging
    - Multi-unit register tracking
    - Register type categorization
    - Batch operation optimization
    """
    
    def __init__(self, max_batch_size: int = 100):
        """
        Initialize register manager
        
        :param max_batch_size: Maximum registers to read in a single request
        """
        self.max_batch_size = max_batch_size
        self.registers = {}  # point_name -> register
        self.gateway_registers = defaultdict(lambda: defaultdict(list))  # gateway_id -> unit_id -> registers
        self.register_maps = {}  # Optimized register maps for scraping
    
    def add_register(self, register):
        """
        Add a register to the manager
        
        :param register: EnhancedModbusRegister instance
        """
        self.registers[register.point_name] = register
        self.gateway_registers[register.gateway_id][register.unit_id].append(register)
        
        _log.debug(f"Added register {register.point_name} at address {register.address} "
                  f"for unit {register.unit_id} on gateway {register.gateway_id}")
    
    def get_register(self, point_name: str):
        """
        Get register by point name
        
        :param point_name: Point name
        :return: Register object
        """
        if point_name not in self.registers:
            raise KeyError(f"Register {point_name} not found")
        
        return self.registers[point_name]
    
    def build_register_maps(self):
        """
        Build optimized register maps for efficient scraping.
        Groups registers by gateway, unit, type, and merges adjacent ranges.
        """
        self.register_maps = {}
        
        for gateway_id, unit_dict in self.gateway_registers.items():
            self.register_maps[gateway_id] = {}
            
            for unit_id, registers in unit_dict.items():
                self.register_maps[gateway_id][unit_id] = self._build_unit_map(registers)
        
        _log.info(f"Built register maps for {len(self.register_maps)} gateways")
    
    def _build_unit_map(self, registers: List) -> Dict:
        """
        Build optimized register map for a single unit
        
        :param registers: List of registers for the unit
        :return: Dictionary of register type -> merged ranges
        """
        # Categorize registers by type and read/write capability
        categorized = {
            'bit_read_only': [],
            'bit_read_write': [],
            'register_read_only': [],
            'register_read_write': []
        }
        
        for reg in registers:
            if reg.register_type == 'bit':
                if reg.read_only:
                    categorized['bit_read_only'].append(reg)
                else:
                    categorized['bit_read_write'].append(reg)
            else:
                if reg.read_only:
                    categorized['register_read_only'].append(reg)
                else:
                    categorized['register_read_write'].append(reg)
        
        # Merge adjacent registers for each category
        merged_map = {}
        for category, regs in categorized.items():
            if regs:
                merged_map[category] = self._merge_register_ranges(regs)
        
        return merged_map
    
    def _merge_register_ranges(self, registers: List) -> List[Tuple[int, int, List]]:
        """
        Merge adjacent registers into contiguous ranges for efficient reading
        
        :param registers: List of registers to merge
        :return: List of (start_address, end_address, registers) tuples
        """
        if not registers:
            return []
        
        # Sort registers by address
        sorted_regs = sorted(registers, key=lambda r: r.address)
        
        ranges = []
        current_start = sorted_regs[0].address
        current_end = current_start + self._get_register_size(sorted_regs[0]) - 1
        current_regs = [sorted_regs[0]]
        
        for reg in sorted_regs[1:]:
            reg_size = self._get_register_size(reg)
            
            # Check if this register is adjacent to the current range
            # and if adding it wouldn't exceed max batch size
            if (reg.address <= current_end + 1 and 
                reg.address + reg_size - 1 - current_start < self.max_batch_size):
                # Extend current range
                current_end = max(current_end, reg.address + reg_size - 1)
                current_regs.append(reg)
            else:
                # Start new range
                ranges.append((current_start, current_end, current_regs))
                current_start = reg.address
                current_end = current_start + reg_size - 1
                current_regs = [reg]
        
        # Add final range
        ranges.append((current_start, current_end, current_regs))
        
        _log.debug(f"Merged {len(registers)} registers into {len(ranges)} ranges")
        
        return ranges
    
    def _get_register_size(self, register) -> int:
        """
        Get the size of a register in modbus register units
        
        :param register: Register object
        :return: Size in register units
        """
        if register.register_type == 'bit':
            return 1
        elif register.register_type in ['float', 'int32', 'uint32']:
            return 2
        else:  # int16, uint16
            return 1
    
    def get_grouped_registers(self) -> Dict:
        """
        Get registers grouped by gateway and unit for batch operations
        
        :return: Dictionary of gateway_id -> unit_id -> register_type -> ranges
        """
        if not self.register_maps:
            self.build_register_maps()
        
        return self.register_maps
    
    def get_unit_registers(self, gateway_id: str, unit_id: int) -> List:
        """
        Get all registers for a specific unit
        
        :param gateway_id: Gateway ID
        :param unit_id: Unit ID
        :return: List of registers
        """
        return self.gateway_registers.get(gateway_id, {}).get(unit_id, [])
    
    def get_register_statistics(self) -> Dict:
        """
        Get statistics about registered registers
        
        :return: Dictionary of statistics
        """
        stats = {
            'total_registers': len(self.registers),
            'gateways': len(self.gateway_registers),
            'units': sum(len(units) for units in self.gateway_registers.values()),
            'register_types': defaultdict(int),
            'read_only': 0,
            'read_write': 0
        }
        
        for reg in self.registers.values():
            stats['register_types'][reg.register_type] += 1
            if reg.read_only:
                stats['read_only'] += 1
            else:
                stats['read_write'] += 1
        
        # Convert defaultdict to regular dict for JSON serialization
        stats['register_types'] = dict(stats['register_types'])
        
        return stats
    
    def validate_registers(self) -> List[str]:
        """
        Validate register configuration for potential issues
        
        :return: List of validation warnings/errors
        """
        issues = []
        
        # Check for overlapping addresses within same unit
        for gateway_id, unit_dict in self.gateway_registers.items():
            for unit_id, registers in unit_dict.items():
                address_map = {}
                
                for reg in registers:
                    addr = reg.address
                    size = self._get_register_size(reg)
                    
                    for i in range(addr, addr + size):
                        if i in address_map:
                            issues.append(
                                f"Address overlap at {i} for unit {unit_id}: "
                                f"{address_map[i].point_name} and {reg.point_name}"
                            )
                        address_map[i] = reg
        
        # Check for very large gaps in addresses (potential misconfiguration)
        for gateway_id, unit_dict in self.gateway_registers.items():
            for unit_id, registers in unit_dict.items():
                if len(registers) < 2:
                    continue
                
                sorted_regs = sorted(registers, key=lambda r: r.address)
                
                for i in range(len(sorted_regs) - 1):
                    gap = sorted_regs[i + 1].address - (
                        sorted_regs[i].address + self._get_register_size(sorted_regs[i])
                    )
                    
                    if gap > 1000:
                        issues.append(
                            f"Large address gap ({gap}) between {sorted_regs[i].point_name} "
                            f"and {sorted_regs[i + 1].point_name} for unit {unit_id}"
                        )
        
        # Check for duplicate point names
        seen_names = set()
        for name in self.registers.keys():
            if name in seen_names:
                issues.append(f"Duplicate point name: {name}")
            seen_names.add(name)
        
        return issues
    
    def optimize_register_layout(self) -> Dict:
        """
        Suggest optimizations for register layout
        
        :return: Dictionary of optimization suggestions
        """
        suggestions = {
            'merge_opportunities': [],
            'reorder_suggestions': [],
            'batch_optimization': []
        }
        
        for gateway_id, unit_dict in self.register_maps.items():
            for unit_id, type_dict in unit_dict.items():
                for reg_type, ranges in type_dict.items():
                    # Check for small gaps that could be merged
                    for i in range(len(ranges) - 1):
                        gap = ranges[i + 1][0] - ranges[i][1] - 1
                        
                        if 0 < gap <= 5:
                            suggestions['merge_opportunities'].append({
                                'gateway': gateway_id,
                                'unit': unit_id,
                                'type': reg_type,
                                'range1': (ranges[i][0], ranges[i][1]),
                                'range2': (ranges[i + 1][0], ranges[i + 1][1]),
                                'gap': gap
                            })
                    
                    # Check if ranges could be reordered for better batching
                    if len(ranges) > 3:
                        suggestions['batch_optimization'].append({
                            'gateway': gateway_id,
                            'unit': unit_id,
                            'type': reg_type,
                            'current_batches': len(ranges),
                            'registers': sum(len(r[2]) for r in ranges)
                        })
        
        return suggestions
    
    def export_register_map(self) -> Dict:
        """
        Export register map for documentation or analysis
        
        :return: Dictionary containing register mapping
        """
        export_data = {
            'summary': self.get_register_statistics(),
            'registers': {},
            'gateway_mapping': {}
        }
        
        # Export individual registers
        for name, reg in self.registers.items():
            export_data['registers'][name] = {
                'address': reg.address,
                'type': reg.register_type,
                'read_only': reg.read_only,
                'unit_id': reg.unit_id,
                'gateway_id': reg.gateway_id,
                'units': reg.units,
                'description': reg.description
            }
        
        # Export gateway mapping
        for gateway_id, unit_dict in self.register_maps.items():
            export_data['gateway_mapping'][gateway_id] = {}
            
            for unit_id, type_dict in unit_dict.items():
                export_data['gateway_mapping'][gateway_id][unit_id] = {}
                
                for reg_type, ranges in type_dict.items():
                    export_data['gateway_mapping'][gateway_id][unit_id][reg_type] = [
                        {
                            'start': start,
                            'end': end,
                            'count': len(regs),
                            'points': [r.point_name for r in regs]
                        }
                        for start, end, regs in ranges
                    ]
        
        return export_data