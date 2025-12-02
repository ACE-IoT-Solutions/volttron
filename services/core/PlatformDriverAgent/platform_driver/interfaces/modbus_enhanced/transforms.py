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
Pre-canned transform functions for the enhanced modbus driver.

This module provides commonly used transform functions that can be referenced
by name in registry configurations. It includes all transforms from the legacy
modbus-tk driver plus additional commonly needed transforms.
"""

import math
import logging

_log = logging.getLogger(__name__)


class TransformRegistry:
    """Registry of named transform functions"""
    
    def __init__(self):
        self._transforms = {}
        self._register_builtin_transforms()
    
    def register(self, name, func):
        """Register a transform function by name"""
        self._transforms[name] = func
    
    def get(self, name):
        """Get a transform function by name"""
        return self._transforms.get(name)
    
    def list_transforms(self):
        """List all available transform names"""
        return sorted(self._transforms.keys())
    
    def _register_builtin_transforms(self):
        """Register all built-in transform functions"""

        # Note: Parametric transforms (scale, scale_int, etc.) are NOT registered here
        # because they require parameters. They are handled by create_transform() which
        # calls the factory functions (scale(), scale_int(), etc.) with arguments.
        #
        # Only simple transforms (lambdas and no-arg functions) are pre-registered.
        
        # Additional common transforms
        self.register('scale_0_1', lambda x: x * 0.1)
        self.register('scale_0_01', lambda x: x * 0.01)
        self.register('scale_0_001', lambda x: x * 0.001)
        self.register('scale_0_0001', lambda x: x * 0.0001)
        self.register('scale_10', lambda x: x * 10)
        self.register('scale_100', lambda x: x * 100)
        self.register('scale_1000', lambda x: x * 1000)
        
        # Unit conversions
        self.register('mA_to_A', lambda x: x / 1000.0)
        self.register('A_to_mA', lambda x: x * 1000.0)
        self.register('W_to_kW', lambda x: x * 0.001)
        self.register('kW_to_W', lambda x: x * 1000.0)
        self.register('W_to_MW', lambda x: x * 0.000001)
        self.register('MW_to_W', lambda x: x * 1000000.0)
        self.register('VAR_to_kVAR', lambda x: x * 0.001)
        self.register('kVAR_to_VAR', lambda x: x * 1000.0)
        self.register('VA_to_kVA', lambda x: x * 0.001)
        self.register('kVA_to_VA', lambda x: x * 1000.0)
        self.register('Wh_to_kWh', lambda x: x * 0.001)
        self.register('kWh_to_Wh', lambda x: x * 1000.0)
        self.register('Wh_to_MWh', lambda x: x * 0.000001)
        self.register('MWh_to_Wh', lambda x: x * 1000000.0)
        
        # Temperature conversions
        self.register('C_to_F', lambda x: x * 9/5 + 32)
        self.register('F_to_C', lambda x: (x - 32) * 5/9)
        self.register('C_to_K', lambda x: x + 273.15)
        self.register('K_to_C', lambda x: x - 273.15)
        
        # Percentage and ratio transforms
        self.register('ratio_to_percent', lambda x: x * 100.0)
        self.register('percent_to_ratio', lambda x: x / 100.0)
        self.register('pf_scale', lambda x: x / 1000.0 if -1000 <= x <= 1000 else None)
        self.register('percent_limit', lambda x: min(100.0, max(0.0, x)))
        
        # Error value handling
        self.register('error_to_none', lambda x: None if x in [65535, 65534, 32768, -32768, -2147483648] else x)
        self.register('nan_to_none', lambda x: None if math.isnan(x) else x)
        self.register('inf_to_none', lambda x: None if math.isinf(x) else x)
        
        # Status and state transforms
        self.register('bool_to_status', lambda x: 'ON' if x else 'OFF')
        self.register('status_to_bool', lambda x: 1 if x in ['ON', 'on', '1', 'true', 'True'] else 0)
        self.register('alarm_status', lambda x: {0: 'Normal', 1: 'Warning', 2: 'Alarm', 3: 'Fault'}.get(x, 'Unknown'))
        self.register('binary_status', lambda x: 'Active' if x & 1 else 'Inactive')
        
        # Bit manipulation
        self.register('bit_0', lambda x: (x >> 0) & 1)
        self.register('bit_1', lambda x: (x >> 1) & 1)
        self.register('bit_2', lambda x: (x >> 2) & 1)
        self.register('bit_3', lambda x: (x >> 3) & 1)
        self.register('bit_4', lambda x: (x >> 4) & 1)
        self.register('bit_5', lambda x: (x >> 5) & 1)
        self.register('bit_6', lambda x: (x >> 6) & 1)
        self.register('bit_7', lambda x: (x >> 7) & 1)
        self.register('bit_8', lambda x: (x >> 8) & 1)
        self.register('bit_9', lambda x: (x >> 9) & 1)
        self.register('bit_10', lambda x: (x >> 10) & 1)
        self.register('bit_11', lambda x: (x >> 11) & 1)
        self.register('bit_12', lambda x: (x >> 12) & 1)
        self.register('bit_13', lambda x: (x >> 13) & 1)
        self.register('bit_14', lambda x: (x >> 14) & 1)
        self.register('bit_15', lambda x: (x >> 15) & 1)
        
        # Register combining (for split values)
        self.register('combine_bytes', lambda high, low: (high << 8) | low)
        self.register('combine_words', lambda high, low: (high << 16) | low)
        
        # Calibration and offset
        self.register('offset_1', lambda x: x + 1)
        self.register('offset_minus_1', lambda x: x - 1)
        self.register('offset_10', lambda x: x + 10)
        self.register('offset_minus_10', lambda x: x - 10)
        self.register('offset_100', lambda x: x + 100)
        self.register('offset_minus_100', lambda x: x - 100)


# Global transform registry instance
transform_registry = TransformRegistry()


# Legacy modbus-tk compatible transform functions

def scale(multiplier):
    """
    Scales modbus register values on reading.
    
    :param multiplier: Scale multiplier, eg 0.001
    :return: Transform function
    """
    multiplier = float(multiplier) if isinstance(multiplier, str) else multiplier
    
    def func(value):
        return value * multiplier
    
    func.inverse = lambda x: x / multiplier if multiplier != 0 else None
    return func


def scale_int(multiplier):
    """
    Same as scale, except casts return value to integer.
    
    :param multiplier: Scale multiplier, eg 0.001
    :return: Transform function
    """
    multiplier = float(multiplier) if isinstance(multiplier, str) else multiplier
    
    def func(value):
        return int(value * multiplier)
    
    func.inverse = lambda x: int(x / multiplier) if multiplier != 0 else None
    return func


def scale_decimal_int_signed(multiplier):
    """
    Scales modbus float value stored as decimal number,
    not using standard signing rollover (as PM800 Power Factor).
    
    :param multiplier: Scale multiplier, eg 0.001
    :return: Transform function
    """
    multiplier = float(multiplier) if isinstance(multiplier, str) else multiplier
    
    def func(value):
        if value < 0:
            return multiplier * (0 - (value + 32768))
        else:
            return multiplier * value
    
    def inverse_func(value):
        if value < 0:
            return (0 - (value / multiplier)) - 0xFFFF
        else:
            return value / multiplier
    
    func.inverse = inverse_func
    return func


def mod10k(reverse=False):
    """
    Converts ION 8600 INT32-M10K register format.
    
    :param reverse: If True, reverses high/low order (ION6200)
    :return: Transform function
    """
    reverse = reverse in [True, 'true', 'True', '1', 1]
    
    def func(value):
        high = (value >> 16) & 0xFFFF
        low = value & 0xFFFF
        if not reverse:
            return high * 10000 + low
        else:
            return low * 10000 + high
    
    return func


def mod10k64(reverse=False):
    """
    Converts PM800 64 bit 10K format.
    
    :param reverse: If True, reverses register order
    :return: Transform function
    """
    reverse = reverse in [True, 'true', 'True', '1', 1]
    
    def func(value):
        r4 = (value >> 48) & 0xFFFF
        r3 = (value >> 32) & 0xFFFF
        r2 = (value >> 16) & 0xFFFF
        r1 = value & 0xFFFF
        if not reverse:
            return (r1 * 10000**3) + (r2 * 10000**2) + (r3 * 10000) + r4
        else:
            return (r4 * 10000**3) + (r3 * 10000**2) + (r2 * 10000) + r1
    
    return func


def mod10k48(reverse=False):
    """
    Converts PM800 INT48-M10K register format.
    
    :param reverse: If True, reverses register order
    :return: Transform function
    """
    reverse = reverse in [True, 'true', 'True', '1', 1]
    
    def func(value):
        r4 = (value >> 48) & 0xFFFF
        r3 = (value >> 32) & 0xFFFF
        r2 = (value >> 16) & 0xFFFF
        r1 = value & 0xFFFF
        if not reverse:
            return (r2 * 10000**2) + (r3 * 10000) + r4
        else:
            return (r1 * 10000**2) + (r2 * 10000) + r3
    
    return func


def scale_reg(reg_name):
    """
    Scales modbus register value by another register's value.
    
    :param reg_name: Name of scaling register
    :return: Transform function with register dependency
    """
    def func(value, scaling_register_value):
        try:
            return value / scaling_register_value
        except ZeroDivisionError:
            return None
    
    func.inverse = lambda value, scaling_register_value: value * scaling_register_value
    func.register_args = [reg_name]
    return func


def scale_reg_pow_10(reg_name):
    """
    Scales by 10 raised to power of another register's value.
    
    :param reg_name: Name of scaling register containing exponent
    :return: Transform function with register dependency
    """
    def func(value, scaling_register_value):
        return value * pow(10, float(scaling_register_value))
    
    func.inverse = lambda value, scaling_register_value: value / pow(10, float(scaling_register_value))
    func.register_args = [reg_name]
    return func


def create_transform(transform_str):
    """
    Create a transform function from a string specification.
    
    Supports:
    - Named transforms: "scale_0_001"
    - Parameterized transforms: "scale(0.001)"
    - Lambda expressions: "lambda x: x * 0.001"
    
    :param transform_str: Transform specification string
    :return: Transform function or None
    """
    if not transform_str:
        return None
    
    transform_str = transform_str.strip()
    
    # Check for lambda expression
    if transform_str.startswith('lambda'):
        try:
            return eval(transform_str)
        except Exception as e:
            _log.error(f"Error parsing lambda transform '{transform_str}': {e}")
            return None
    
    # Check for parameterized transform like "scale(0.001)"
    if '(' in transform_str and ')' in transform_str:
        import re
        match = re.match(r'(\w+)\((.*)\)', transform_str)
        if match:
            func_name = match.group(1)
            arg = match.group(2)
            
            # Handle known parameterized transforms
            if func_name == 'scale':
                return scale(arg)
            elif func_name == 'scale_int':
                return scale_int(arg)
            elif func_name == 'scale_decimal_int_signed':
                return scale_decimal_int_signed(arg)
            elif func_name == 'mod10k':
                return mod10k(arg.lower() == 'true' if arg else False)
            elif func_name == 'mod10k64':
                return mod10k64(arg.lower() == 'true' if arg else False)
            elif func_name == 'mod10k48':
                return mod10k48(arg.lower() == 'true' if arg else False)
            elif func_name == 'scale_reg':
                return scale_reg(arg)
            elif func_name == 'scale_reg_pow_10':
                return scale_reg_pow_10(arg)
    
    # Check for named transform
    transform = transform_registry.get(transform_str)
    if transform:
        return transform
    
    _log.warning(f"Unknown transform: {transform_str}")
    return None


def get_available_transforms():
    """Get list of all available transform names"""
    return transform_registry.list_transforms()