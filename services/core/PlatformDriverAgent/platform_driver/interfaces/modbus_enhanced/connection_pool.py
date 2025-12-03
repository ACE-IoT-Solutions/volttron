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
Connection Pool Manager for Enhanced Modbus Driver

Manages TCP connections to modbus gateways, ensuring only one socket
is maintained per gateway for all units on that bus. This is critical
for constrained gateways that can only handle a single TCP connection.
"""

import logging
from contextlib import contextmanager
from gevent.lock import RLock
from gevent import sleep
import time
from typing import Dict, Optional

from pymodbus.client.sync import ModbusTcpClient, ModbusSerialClient
from pymodbus.exceptions import ConnectionException
from .connection_singleton import get_connection_singleton

_log = logging.getLogger(__name__)


class ConnectionInfo:
    """Connection configuration information"""
    
    def __init__(self, connection_type, address, port=None, **kwargs):
        self.connection_type = connection_type
        self.address = address
        self.port = port
        self.baudrate = kwargs.get('baudrate', 9600)
        self.bytesize = kwargs.get('bytesize', 8)
        self.parity = kwargs.get('parity', 'N')
        self.stopbits = kwargs.get('stopbits', 1)
        self.timeout = kwargs.get('timeout', 1.0)
        self.retry_on_empty = kwargs.get('retry_on_empty', True)
        self.retry_attempts = kwargs.get('retry_attempts', 3)
    
    def get_key(self):
        """Get unique key for this connection"""
        if self.connection_type == 'tcp':
            return f"tcp_{self.address}:{self.port}"
        else:
            return f"serial_{self.address}_{self.baudrate}"
    
    def create_client(self):
        """Create a new modbus client"""
        if self.connection_type == 'tcp':
            client = ModbusTcpClient(
                host=self.address,
                port=self.port,
                timeout=self.timeout,
                retry_on_empty=self.retry_on_empty,
                retries=self.retry_attempts
            )
        else:
            import serial
            client = ModbusSerialClient(
                method='rtu',
                port=self.address,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=self.parity,
                stopbits=self.stopbits,
                timeout=self.timeout,
                retry_on_empty=self.retry_on_empty,
                retries=self.retry_attempts
            )
        
        return client


class ConnectionPool:
    """
    Manages TCP connections to modbus gateways.
    
    This class handles two deployment modes:
    1. Gateway as device: Manages its own connections directly
    2. Unit as device: Uses the singleton to share connections across greenlets
    
    Key features:
    - Single TCP socket per gateway (critical for constrained gateways)
    - Connection reuse for all units on the same gateway
    - Greenlet-safe serialized access to prevent concurrent operations
    - Automatic connection recovery
    - Connection health monitoring
    """
    
    def __init__(self, connection_timeout=30, use_singleton=False, driver_instance=None):
        """
        Initialize connection pool.

        :param connection_timeout: Timeout for connections
        :param use_singleton: Whether to use the singleton (for unit as device mode)
        :param driver_instance: The driver instance using this pool
        """
        self.connection_timeout = connection_timeout
        self.use_singleton = use_singleton
        self.driver_instance = driver_instance

        # Always initialize these - needed even in singleton mode for health tracking
        self._global_lock = RLock()  # gevent.lock.RLock for greenlet safety
        self._connection_health = {}  # Track connection health

        if use_singleton:
            # Use the process-wide singleton
            self._singleton = get_connection_singleton()
            if driver_instance:
                self._singleton.register_driver_instance(driver_instance)
            # These are not used in singleton mode
            self._connections = None
            self._connection_configs = None
            self._connection_locks = None
        else:
            # Manage connections directly (gateway as device mode)
            self._connections = {}  # Dict of connection_key -> single client
            self._connection_configs = {}  # Dict of connection_key -> ConnectionInfo
            self._connection_locks = {}  # Dict of connection_key -> RLock for serialization
    
    def register_connection(self, connection_info: ConnectionInfo):
        """Register a new gateway connection configuration"""
        key = connection_info.get_key()
        
        if self.use_singleton:
            # Singleton handles registration
            pass
        else:
            with self._global_lock:
                if key not in self._connections:
                    self._connections[key] = None  # Will be created on first use
                    self._connection_configs[key] = connection_info
                    self._connection_locks[key] = RLock()  # Per-gateway lock
                    self._connection_health[key] = {
                        'failures': 0,
                        'last_success': time.time(),
                        'last_failure': None
                    }
                    _log.info(f"Registered gateway connection for {key}")
    
    @contextmanager
    def get_connection(self, gateway):
        """
        Get the single connection for a gateway with serialized access.
        
        This ensures only one TCP socket is used per gateway and operations
        are serialized to prevent concurrent access issues.
        
        :param gateway: Gateway configuration object
        :yields: Modbus client connection
        """
        connection_info = ConnectionInfo(
            connection_type=gateway.connection_type,
            address=gateway.address,
            port=gateway.port,
            **gateway.kwargs
        )
        
        # Register connection if not exists
        self.register_connection(connection_info)
        
        key = connection_info.get_key()
        
        # Get the appropriate lock (singleton or local)
        if self.use_singleton:
            lock = self._singleton.get_connection_lock(key)
        else:
            lock = self._connection_locks[key]
        
        # Acquire the per-gateway lock to serialize access
        with lock:
            try:
                # Get or create the single connection for this gateway
                if self.use_singleton:
                    _log.debug(f"Using singleton for connection to {key}")
                    client = self._singleton.get_or_create_connection(key, connection_info)
                else:
                    _log.debug(f"Using local connection pool for {key}")
                    client = self._get_or_create_connection(key)
                
                # Test connection and reconnect if needed
                if not self._test_connection(client):
                    _log.info(f"Connection test failed for {key}, reconnecting...")
                    if self.use_singleton:
                        self._singleton.reset_connection(key)
                        client = self._singleton.get_or_create_connection(key, connection_info)
                    else:
                        if self._connections[key]:
                            try:
                                self._connections[key].close()
                            except:
                                pass
                        self._connections[key] = None
                        client = self._get_or_create_connection(key)
                
                # Update health status
                self._update_health(key, success=True)
                
                yield client
                
            except Exception as e:
                _log.error(f"Connection error for {key}: {e}")
                _log.debug(f"Exception type: {type(e).__name__}, use_singleton: {self.use_singleton}")
                self._update_health(key, success=False)

                # Mark connection as broken
                if self.use_singleton:
                    _log.debug(f"Resetting singleton connection for {key}")
                    self._singleton.reset_connection(key)
                else:
                    _log.debug(f"Nullifying local connection for {key}")
                    if self._connections[key]:
                        try:
                            self._connections[key].close()
                        except:
                            pass
                    self._connections[key] = None
                raise
    
    def _get_or_create_connection(self, key):
        """
        Get or create the single connection for this gateway.
        
        :param key: Connection key
        :return: Modbus client
        """
        if self._connections[key] is None:
            # Create new connection
            config = self._connection_configs[key]
            client = config.create_client()
            
            if not client.connect():
                raise ConnectionException(f"Failed to connect to {key}")
            
            self._connections[key] = client
            _log.info(f"Created connection for gateway {key}")
        
        return self._connections[key]
    
    def _test_connection(self, client):
        """
        Test if a connection is still valid at the socket level.

        IMPORTANT: This tests TCP socket connectivity, NOT Modbus protocol responses.
        A Modbus exception (e.g., illegal address) is still a valid connection.
        We only want to detect broken sockets, not device-specific errors.
        """
        try:
            # Try multiple methods to test socket connectivity

            # Method 1: Check if socket exists and is connected
            if hasattr(client, 'socket') and client.socket is not None:
                try:
                    # For TCP sockets, check if the socket is still connected
                    # by examining the socket object directly
                    sock = client.socket
                    if hasattr(sock, 'fileno'):
                        # If we can get the file descriptor, socket is valid
                        _ = sock.fileno()
                        return True
                except (OSError, AttributeError):
                    # Socket is closed or invalid
                    return False

            # Method 2: Try is_socket_open() if available (may fail in some pymodbus versions)
            if hasattr(client, 'is_socket_open'):
                try:
                    return client.is_socket_open()
                except AttributeError as e:
                    # Some pymodbus versions have is_socket_open() but it fails
                    # with AttributeError: '_in_waiting' on TCP clients
                    _log.debug(f"is_socket_open() failed with {e}, falling back to socket check")
                    # Fall through to next method

            # Method 3: Check connect() status
            if hasattr(client, 'connect'):
                # If socket doesn't exist, connection is not valid
                return hasattr(client, 'socket') and client.socket is not None

            # Default: assume not connected
            return False

        except Exception as e:
            _log.debug(f"Connection test exception: {e}")
            return False
    
    def _update_health(self, key, success):
        """Update connection health statistics"""
        with self._global_lock:
            # Initialize health tracking for this key if it doesn't exist
            if key not in self._connection_health:
                self._connection_health[key] = {
                    'failures': 0,
                    'last_success': None,
                    'last_failure': None
                }

            health = self._connection_health[key]
            if success:
                health['failures'] = 0
                health['last_success'] = time.time()
            else:
                health['failures'] += 1
                health['last_failure'] = time.time()
    
    def get_connection_status(self):
        """Get status of all gateway connections"""
        status = {}
        with self._global_lock:
            if self.use_singleton:
                # In singleton mode, we only track health, not connections
                for key, health in self._connection_health.items():
                    status[key] = {
                        'connected': 'unknown (singleton mode)',
                        'health': dict(health)
                    }
            else:
                # In local mode, we track both connections and health
                for key in self._connections:
                    status[key] = {
                        'connected': self._connections[key] is not None,
                        'health': dict(self._connection_health.get(key, {}))
                    }
        return status
    
    def close_all(self):
        """Close all gateway connections"""
        if self.use_singleton:
            # In singleton mode, don't close connections - they're managed by the singleton
            _log.info("Singleton mode - connections managed by singleton, not closing")
            return

        with self._global_lock:
            for key, client in self._connections.items():
                if client:
                    try:
                        client.close()
                    except:
                        pass

            self._connections.clear()
            self._connection_configs.clear()
            self._connection_locks.clear()
            self._connection_health.clear()

        _log.info("All gateway connections closed")