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
Gateway Manager for Enhanced Modbus Driver

Manages gateway configurations and coordinates access to multiple
unit devices behind a single gateway.
"""

import logging
import hashlib
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from gevent.lock import RLock  # Use gevent's RLock for greenlet safety

_log = logging.getLogger(__name__)


@dataclass
class Gateway:
    """Gateway configuration and metadata"""
    gateway_id: str
    connection_type: str  # 'tcp' or 'serial'
    address: str
    port: Optional[int] = None
    unit_ids: List[int] = field(default_factory=list)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    retry_config: Dict[str, Any] = field(default_factory=dict)
    health_check_interval: int = 60
    last_health_check: float = 0
    is_healthy: bool = True
    error_count: int = 0
    
    def add_unit(self, unit_id: int):
        """Add a unit ID to this gateway"""
        if unit_id not in self.unit_ids:
            self.unit_ids.append(unit_id)
            self.unit_ids.sort()
    
    def remove_unit(self, unit_id: int):
        """Remove a unit ID from this gateway"""
        if unit_id in self.unit_ids:
            self.unit_ids.remove(unit_id)
    
    def get_connection_key(self):
        """Get unique connection key for this gateway"""
        if self.connection_type == 'tcp':
            return f"tcp_{self.address}:{self.port}"
        else:
            return f"serial_{self.address}"


class GatewayManager:
    """
    Manages modbus TCP-to-RTU gateways and their associated unit devices.
    
    Each gateway represents a single TCP connection to a TCP-to-RTU bridge device
    that manages one RTU/ASCII bus with multiple modbus units (0-255).
    
    Features:
    - Single TCP socket per gateway for all units on that bus
    - Unit device registration (unit IDs are unique only per bus)
    - Gateway health monitoring
    - Connection serialization for constrained gateways
    """
    
    def __init__(self):
        self.gateways: Dict[str, Gateway] = {}
        self.unit_to_gateway: Dict[int, str] = {}
        self.gateway_locks: Dict[str, RLock] = {}  # gevent RLocks for serializing access to each gateway
    
    def add_gateway(self, gateway_type: str, address: str, port: Optional[int] = None,
                   gateway_id: Optional[str] = None, **kwargs) -> str:
        """
        Add a new gateway configuration
        
        :param gateway_type: 'tcp' or 'serial'
        :param address: IP address for TCP, device path for serial
        :param port: Port number for TCP connections
        :param gateway_id: Optional gateway ID, auto-generated if not provided
        :param kwargs: Additional gateway configuration
        :return: Gateway ID
        """
        if gateway_id is None:
            # Generate unique gateway ID
            gateway_id = self._generate_gateway_id(gateway_type, address, port)
        
        if gateway_id in self.gateways:
            _log.warning(f"Gateway {gateway_id} already exists, updating configuration")
        
        gateway = Gateway(
            gateway_id=gateway_id,
            connection_type=gateway_type,
            address=address,
            port=port,
            kwargs=kwargs,
            retry_config=kwargs.pop('retry_config', {})
        )
        
        self.gateways[gateway_id] = gateway
        _log.info(f"Added gateway {gateway_id}: {gateway_type} {address}:{port}")
        
        return gateway_id
    
    def _generate_gateway_id(self, gateway_type: str, address: str, 
                            port: Optional[int]) -> str:
        """Generate a unique gateway ID"""
        key = f"{gateway_type}_{address}_{port}"
        return hashlib.md5(key.encode()).hexdigest()[:8]
    
    def assign_unit_to_gateway(self, unit_id: int, gateway_id: str):
        """
        Assign a unit device to a specific gateway
        
        :param unit_id: Modbus unit ID
        :param gateway_id: Gateway ID to assign the unit to
        """
        if gateway_id not in self.gateways:
            raise ValueError(f"Gateway {gateway_id} not found")
        
        # Remove from previous gateway if assigned
        if unit_id in self.unit_to_gateway:
            old_gateway_id = self.unit_to_gateway[unit_id]
            if old_gateway_id != gateway_id:
                self.gateways[old_gateway_id].remove_unit(unit_id)
        
        # Assign to new gateway
        self.gateways[gateway_id].add_unit(unit_id)
        self.unit_to_gateway[unit_id] = gateway_id
        
        _log.debug(f"Assigned unit {unit_id} to gateway {gateway_id}")
    
    def get_gateway(self, gateway_id: str) -> Gateway:
        """
        Get gateway configuration by ID
        
        :param gateway_id: Gateway ID
        :return: Gateway object
        """
        if gateway_id not in self.gateways:
            raise ValueError(f"Gateway {gateway_id} not found")
        
        return self.gateways[gateway_id]
    
    def get_gateway_for_unit(self, unit_id: int) -> Optional[Gateway]:
        """
        Get the gateway assigned to a specific unit
        
        :param unit_id: Modbus unit ID
        :return: Gateway object or None if not assigned
        """
        if unit_id not in self.unit_to_gateway:
            return None
        
        gateway_id = self.unit_to_gateway[unit_id]
        return self.gateways.get(gateway_id)
    
    def get_gateway_address_key(self, gateway_id: str) -> str:
        """
        Get a unique address key for the gateway.
        This is used to identify gateways that share the same physical connection.
        
        :param gateway_id: Gateway ID
        :return: Unique address key
        """
        gateway = self.gateways[gateway_id]
        return gateway.get_connection_key()
    
    def get_units_on_gateway(self, gateway_id: str) -> List[int]:
        """
        Get all unit IDs on a specific gateway
        
        :param gateway_id: Gateway ID
        :return: List of unit IDs on this gateway
        """
        if gateway_id not in self.gateways:
            return []
        return self.gateways[gateway_id].unit_ids
    
    def update_gateway_health(self, gateway_id: str, is_healthy: bool, 
                            error_msg: Optional[str] = None):
        """
        Update health status of a gateway
        
        :param gateway_id: Gateway ID
        :param is_healthy: Health status
        :param error_msg: Optional error message
        """
        if gateway_id not in self.gateways:
            return
        
        gateway = self.gateways[gateway_id]
        gateway.is_healthy = is_healthy
        
        if not is_healthy:
            gateway.error_count += 1
            _log.warning(f"Gateway {gateway_id} marked unhealthy: {error_msg}")
        else:
            gateway.error_count = 0
            _log.debug(f"Gateway {gateway_id} marked healthy")
    
    def get_all_gateways(self) -> Dict[str, Gateway]:
        """Get all registered gateways"""
        return self.gateways.copy()
    
    def get_gateway_status(self) -> Dict[str, Dict]:
        """
        Get status information for all gateways
        
        :return: Dictionary of gateway status information
        """
        status = {}
        
        for gateway_id, gateway in self.gateways.items():
            status[gateway_id] = {
                'connection_type': gateway.connection_type,
                'address': gateway.address,
                'port': gateway.port,
                'unit_count': len(gateway.unit_ids),
                'unit_ids': gateway.unit_ids,
                'is_healthy': gateway.is_healthy,
                'error_count': gateway.error_count,
                'connection_key': gateway.get_connection_key()
            }
        
        return status
    
    def export_configuration(self) -> Dict:
        """
        Export gateway configuration for persistence
        
        :return: Dictionary containing gateway configuration
        """
        config = {
            'gateways': {},
            'unit_assignments': self.unit_to_gateway.copy(),
            'gateway_locks': list(self.gateway_locks.keys())  # Just store which gateways have locks
        }
        
        for gateway_id, gateway in self.gateways.items():
            config['gateways'][gateway_id] = {
                'connection_type': gateway.connection_type,
                'address': gateway.address,
                'port': gateway.port,
                'kwargs': gateway.kwargs,
                'retry_config': gateway.retry_config
            }
        
        return config
    
    def import_configuration(self, config: Dict):
        """
        Import gateway configuration from persistence
        
        :param config: Dictionary containing gateway configuration
        """
        # Clear existing configuration
        self.gateways.clear()
        self.unit_to_gateway.clear()
        
        # Import gateways
        for gateway_id, gw_config in config.get('gateways', {}).items():
            self.add_gateway(
                gateway_type=gw_config['connection_type'],
                address=gw_config['address'],
                port=gw_config.get('port'),
                gateway_id=gateway_id,
                **gw_config.get('kwargs', {})
            )
        
        # Import unit assignments
        for unit_id, gateway_id in config.get('unit_assignments', {}).items():
            self.assign_unit_to_gateway(int(unit_id), gateway_id)
        
        # Recreate locks for gateways
        for gateway_id in config.get('gateway_locks', []):
            self.gateway_locks[gateway_id] = RLock()
        
        _log.info(f"Imported configuration with {len(self.gateways)} gateways")