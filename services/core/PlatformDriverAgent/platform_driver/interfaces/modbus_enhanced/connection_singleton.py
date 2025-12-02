# -*- coding: utf-8 -*-
"""
Connection Singleton for Enhanced Modbus Driver

Provides a process-wide singleton to manage TCP connections to gateways,
ensuring that multiple driver instances (running in separate greenlets) can share
the same TCP socket when they're communicating with units on the same gateway.

Uses gevent's RLock for greenlet-safe synchronization.
"""

import logging
from gevent.lock import RLock
from gevent import sleep
import time
from typing import Dict, Optional
import weakref

from pymodbus.client.sync import ModbusTcpClient, ModbusSerialClient
from pymodbus.exceptions import ConnectionException

_log = logging.getLogger(__name__)


class ConnectionSingleton:
    """
    Process-wide singleton that manages all gateway connections.
    
    This is critical for the "unit as device" deployment pattern where each
    unit gets its own VOLTTRON device (and thus its own driver instance in a
    separate greenlet), but units on the same gateway must share the single
    TCP connection.
    
    Uses gevent.lock.RLock for greenlet-safe synchronization.
    """
    
    _instance = None
    _lock = RLock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(ConnectionSingleton, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        with self._lock:
            if self._initialized:
                return
                
            self._connections = {}  # gateway_key -> client
            self._connection_locks = {}  # gateway_key -> RLock
            self._connection_configs = {}  # gateway_key -> config
            self._reference_counts = {}  # gateway_key -> count
            self._driver_instances = weakref.WeakSet()  # Track driver instances
            self._initialized = True
            
            _log.info("ConnectionSingleton initialized")
    
    def register_driver_instance(self, driver):
        """
        Register a driver instance that's using this singleton.
        We use weak references to avoid preventing garbage collection.
        """
        self._driver_instances.add(driver)
        _log.debug(f"Registered driver instance, total active: {len(self._driver_instances)}")
    
    def get_connection_lock(self, gateway_key: str) -> RLock:
        """
        Get or create a lock for a specific gateway.
        
        :param gateway_key: Unique gateway identifier
        :return: RLock for this gateway
        """
        with self._lock:
            if gateway_key not in self._connection_locks:
                self._connection_locks[gateway_key] = RLock()
                self._reference_counts[gateway_key] = 0
                _log.debug(f"Created lock for gateway {gateway_key}")
            
            self._reference_counts[gateway_key] += 1
            return self._connection_locks[gateway_key]
    
    def get_or_create_connection(self, gateway_key: str, connection_info) -> Optional[object]:
        """
        Get or create a connection for a gateway.
        Must be called while holding the gateway lock!

        :param gateway_key: Unique gateway identifier
        :param connection_info: Connection configuration
        :return: Modbus client
        """
        _log.debug(f"Singleton get_or_create_connection called for {gateway_key}")
        _log.debug(f"Connection exists: {gateway_key in self._connections and self._connections.get(gateway_key) is not None}")

        if gateway_key not in self._connections or self._connections[gateway_key] is None:
            # Create new connection
            if connection_info.connection_type == 'tcp':
                client = ModbusTcpClient(
                    host=connection_info.address,
                    port=connection_info.port,
                    timeout=connection_info.timeout,
                    retry_on_empty=connection_info.retry_on_empty,
                    retries=connection_info.retry_attempts
                )
            else:
                import serial
                client = ModbusSerialClient(
                    method='rtu',
                    port=connection_info.address,
                    baudrate=connection_info.baudrate,
                    bytesize=connection_info.bytesize,
                    parity=connection_info.parity,
                    stopbits=connection_info.stopbits,
                    timeout=connection_info.timeout,
                    retry_on_empty=connection_info.retry_on_empty,
                    retries=connection_info.retry_attempts
                )
            
            if not client.connect():
                raise ConnectionException(f"Failed to connect to {gateway_key}")
            
            self._connections[gateway_key] = client
            self._connection_configs[gateway_key] = connection_info
            _log.info(f"Created shared connection for gateway {gateway_key}")
        
        return self._connections[gateway_key]
    
    def close_connection(self, gateway_key: str, force: bool = False):
        """
        Close a connection if no longer needed.
        
        :param gateway_key: Unique gateway identifier
        :param force: Force close even if references exist
        """
        with self._lock:
            if gateway_key not in self._reference_counts:
                return
            
            self._reference_counts[gateway_key] -= 1
            
            if force or self._reference_counts[gateway_key] <= 0:
                if gateway_key in self._connections and self._connections[gateway_key]:
                    try:
                        self._connections[gateway_key].close()
                    except:
                        pass
                    self._connections[gateway_key] = None
                    _log.info(f"Closed connection for gateway {gateway_key}")
                
                if self._reference_counts[gateway_key] <= 0:
                    del self._reference_counts[gateway_key]
                    del self._connection_locks[gateway_key]
                    if gateway_key in self._connection_configs:
                        del self._connection_configs[gateway_key]
    
    def reset_connection(self, gateway_key: str):
        """
        Reset a connection (close and allow recreation on next use).
        
        :param gateway_key: Unique gateway identifier
        """
        with self._lock:
            if gateway_key in self._connections and self._connections[gateway_key]:
                try:
                    self._connections[gateway_key].close()
                except:
                    pass
                self._connections[gateway_key] = None
                _log.info(f"Reset connection for gateway {gateway_key}")
    
    def get_status(self) -> Dict:
        """
        Get status of all managed connections.
        
        :return: Status dictionary
        """
        with self._lock:
            status = {
                'active_drivers': len(self._driver_instances),
                'gateways': {}
            }
            
            for gateway_key in self._connections:
                status['gateways'][gateway_key] = {
                    'connected': self._connections[gateway_key] is not None,
                    'reference_count': self._reference_counts.get(gateway_key, 0)
                }
            
            return status
    
    @classmethod
    def cleanup(cls):
        """
        Clean up all connections (typically called at shutdown).
        """
        if cls._instance:
            with cls._lock:
                instance = cls._instance
                if instance and instance._initialized:
                    for gateway_key in list(instance._connections.keys()):
                        instance.close_connection(gateway_key, force=True)
                    
                    instance._connections.clear()
                    instance._connection_locks.clear()
                    instance._connection_configs.clear()
                    instance._reference_counts.clear()
                    
                    _log.info("ConnectionSingleton cleaned up")


# Module-level accessor
_connection_singleton = None

def get_connection_singleton():
    """Get the process-wide connection singleton."""
    global _connection_singleton
    if _connection_singleton is None:
        _connection_singleton = ConnectionSingleton()
    return _connection_singleton