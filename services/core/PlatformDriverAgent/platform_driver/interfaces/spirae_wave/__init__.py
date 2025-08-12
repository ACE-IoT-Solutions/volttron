# -*- coding: utf-8 -*- {{{
# vim: set fenc=utf-8 ft=python sw=4 ts=4 sts=4 et:
#
# Copyright 2020, Battelle Memorial Institute.
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
#
# This material was prepared as an account of work sponsored by an agency of
# the United States Government. Neither the United States Government nor the
# United States Department of Energy, nor Battelle, nor any of their
# employees, nor any jurisdiction or organization that has cooperated in the
# development of these materials, makes any warranty, express or
# implied, or assumes any legal liability or responsibility for the accuracy,
# completeness, or usefulness or any information, apparatus, product,
# software, or process disclosed, or represents that its use would not infringe
# privately owned rights. Reference herein to any specific commercial product,
# process, or service by trade name, trademark, manufacturer, or otherwise
# does not necessarily constitute or imply its endorsement, recommendation, or
# favoring by the United States Government or any agency thereof, or
# Battelle Memorial Institute. The views and opinions of authors expressed
# herein do not necessarily state or reflect those of the
# United States Government or any agency thereof.
#
# PACIFIC NORTHWEST NATIONAL LABORATORY operated by
# BATTELLE for the UNITED STATES DEPARTMENT OF ENERGY
# under Contract DE-AC05-76RL01830
# }}}

import logging
import grequests
import requests  # Still needed for Session compatibility
import json
import gevent
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from gevent.lock import RLock
from urllib.parse import urljoin
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from requests.exceptions import RequestException, Timeout, ConnectionError as RequestsConnectionError

from platform_driver.interfaces import BaseInterface, BaseRegister, BasicRevert

# Suppress SSL warnings if verify=False is used
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

_log = logging.getLogger(__name__)

HTTP_STATUS_OK = 200
DEFAULT_TIMEOUT = 30
TOKEN_REFRESH_INTERVAL = timedelta(hours=1)


class Register(BaseRegister):
    """Register class for Spirae Wave system points."""
    
    def __init__(self, read_only, volttron_point_name, units, description, asset_name, property_name, property_data):
        super(Register, self).__init__(
            "byte",
            read_only,
            volttron_point_name,
            units,
            description=description
        )
        self.asset_name = asset_name
        self.property_name = property_name
        self.property_data = property_data
        
    def get_state(self, value, collect_string_values=True):
        """Convert value to appropriate type based on property data.
        
        Args:
            value: The raw value from the API
            collect_string_values: If False, only return numeric values
            
        Returns:
            Converted value or None if string values are filtered out
        """
        if value is None:
            return None
        
        # Handle boolean values - always convert to float
        if isinstance(value, bool):
            return 1.0 if value else 0.0
            
        # Try to convert to numeric
        try:
            # First try to convert to float
            numeric_value = float(value)
            # Return as float to ensure consistency
            return numeric_value
        except (ValueError, TypeError):
            # Value is a string
            if collect_string_values:
                return str(value)
            else:
                # Filter out string values when not collecting them
                return None


class Interface(BasicRevert, BaseInterface):
    """Interface for Spirae Wave system integration."""
    
    def __init__(self, **kwargs):
        super(Interface, self).__init__(**kwargs)
        self.url = None
        self.username = None
        self.password = None
        self.verify_ssl = True
        self.timeout = DEFAULT_TIMEOUT
        self.token = None
        self.token_expiry = None
        self.session = None
        self.asset_property_map = None
        self.asset_cache = {}
        self.lock = RLock()  # Use gevent RLock for greenlet safety
        self.discovered_assets = []
        self.register_map = {}
        self.collect_string_values = True  # Default to collecting all values
        
    def configure(self, config_dict, registry_config_str):
        """Configure the interface with connection parameters and discover registers."""
        try:
            # Extract configuration parameters
            self.url = config_dict.get('url', '').rstrip('/')
            self.username = config_dict.get('username')
            self.password = config_dict.get('password')
            self.verify_ssl = config_dict.get('verify_ssl', True)
            self.timeout = config_dict.get('timeout', DEFAULT_TIMEOUT)
            self.collect_string_values = config_dict.get('collect_string_values', True)
            
            # Validate required parameters
            if not all([self.url, self.username, self.password]):
                raise ValueError("URL, username, and password are required configuration parameters")
            
            # Parse optional asset/property map for filtering
            self.asset_property_map = config_dict.get('asset_property_map', {})
            
            # Initialize session
            self.session = requests.Session()
            self.session.verify = self.verify_ssl
            
            # Authenticate and get initial token
            self._authenticate()
            
            # Discover assets and their properties
            self._discover_and_generate_registers()
            
            # Parse any additional registry configuration
            if registry_config_str:
                self._parse_registry_config(registry_config_str)
                
            _log.info(f"Spirae Wave interface configured successfully with {len(self.point_map)} registers")
            
        except Exception as e:
            _log.error(f"Failed to configure Spirae Wave interface: {e}")
            raise
    
    def _authenticate(self):
        """Authenticate with the Spirae Wave system and obtain a token."""
        try:
            login_url = urljoin(self.url, '/login')
            # Use grequests for async operation
            req = grequests.post(
                login_url,
                json={'username': self.username, 'password': self.password},
                timeout=self.timeout,
                verify=self.verify_ssl
            )
            response = grequests.map([req], exception_handler=self._exception_handler)[0]
            
            if response is None:
                raise ConnectionError("Authentication request failed - no response received")
            
            if response.status_code != HTTP_STATUS_OK:
                raise ConnectionError(f"Authentication failed with status {response.status_code}: {response.text}")
            
            data = response.json()
            self.token = data.get('data')
            
            if not self.token:
                raise ValueError("No token received from authentication response")
            
            self.token_expiry = datetime.now() + TOKEN_REFRESH_INTERVAL
            self.session.headers.update({'Token': self.token})
            
            _log.debug("Successfully authenticated with Spirae Wave system")
            
        except (RequestException, RequestsConnectionError, Timeout) as e:
            _log.error(f"Network error during authentication: {e}")
            raise ConnectionError(f"Failed to connect to Spirae Wave system: {e}")
        except Exception as e:
            _log.error(f"Authentication error: {e}")
            raise
    
    def _exception_handler(self, request, exception):
        """Handle exceptions from grequests."""
        _log.error(f"Request failed: {request.url} - {exception}")
        return None
    
    def _ensure_authenticated(self):
        """Ensure we have a valid authentication token, refreshing if necessary."""
        with self.lock:
            if not self.token or datetime.now() >= self.token_expiry:
                _log.debug("Token expired or missing, re-authenticating")
                self._authenticate()
    
    def _discover_and_generate_registers(self):
        """Discover available assets and generate registers from their properties."""
        try:
            # Get list of assets
            assets_url = urljoin(self.url, '/assets')
            response = self._make_request('GET', assets_url)
            
            if response.status_code != HTTP_STATUS_OK:
                raise ConnectionError(f"Failed to fetch assets: {response.status_code}")
            
            self.discovered_assets = response.json()
            _log.info(f"Discovered {len(self.discovered_assets)} assets")
            
            # Generate registers for each asset
            for asset in self.discovered_assets:
                # Check if we should include this asset based on filter map
                if self.asset_property_map and asset not in self.asset_property_map:
                    _log.debug(f"Skipping asset {asset} - not in filter map")
                    continue
                
                self._generate_registers_for_asset(asset)
            
        except Exception as e:
            _log.error(f"Failed to discover assets and generate registers: {e}")
            raise
    
    def _generate_registers_for_asset(self, asset_name):
        """Generate registers for a specific asset by fetching its properties."""
        try:
            # Fetch properties for the asset (only endpoint needed)
            properties_url = urljoin(self.url, f'/assets/{asset_name}/properties')
            
            response = self._make_request('GET', properties_url)
            
            if response.status_code != HTTP_STATUS_OK:
                _log.warning(f"Failed to fetch properties for asset {asset_name}: status {response.status_code}")
                return
            
            properties = response.json()
            
            if not isinstance(properties, list):
                _log.warning(f"Unexpected properties format for asset {asset_name}: {type(properties)}")
                return
            
            # Create registers from properties
            for prop in properties:
                if not isinstance(prop, dict):
                    continue
                
                property_name = prop.get('name')
                if not property_name:
                    continue
                
                # Check if we should include this property based on filter map
                if self.asset_property_map:
                    if asset_name in self.asset_property_map:
                        allowed_props = self.asset_property_map[asset_name]
                        if allowed_props and property_name not in allowed_props:
                            _log.debug(f"Skipping property {property_name} for asset {asset_name}")
                            continue
                
                # Create unique volttron point name
                volttron_point_name = f"{asset_name}/{property_name}"
                
                # Determine if property is writable
                # Properties with 'Command' in their group are typically writable
                group = prop.get('group', '')
                read_only = 'Command' not in group
                
                # Check if we should skip this property based on value type
                # Do a preliminary check if string values are disabled
                if not self.collect_string_values:
                    sample_value = prop.get('value')
                    if sample_value is not None:
                        # Try to convert the sample value
                        try:
                            # Check if it's boolean or numeric
                            if isinstance(sample_value, bool):
                                pass  # Booleans are OK, will be converted to float
                            else:
                                float(sample_value)  # Try numeric conversion
                        except (ValueError, TypeError):
                            # It's a string value and we're not collecting strings
                            _log.debug(f"Skipping string property {property_name} for asset {asset_name}")
                            continue
                
                # Create register
                register = Register(
                    read_only=read_only,
                    volttron_point_name=volttron_point_name,
                    units=prop.get('units', ''),
                    description=prop.get('displayname', property_name),
                    asset_name=asset_name,
                    property_name=property_name,
                    property_data={
                        'group': group,
                        'subgroup': prop.get('subgroup', ''),
                        'value': prop.get('value')
                    }
                )
                
                # Add to point map and register map
                self.insert_register(register)
                self.register_map[volttron_point_name] = register
                
                _log.debug(f"Added register: {volttron_point_name} (read_only={read_only})")
            
        except Exception as e:
            _log.error(f"Failed to generate registers for asset {asset_name}: {e}")
    
    def _parse_registry_config(self, registry_config_str):
        """Parse additional registry configuration if provided."""
        try:
            if isinstance(registry_config_str, str):
                registry_config = json.loads(registry_config_str)
            else:
                registry_config = registry_config_str
            
            # Process any additional register definitions from config
            for reg_def in registry_config:
                if 'Point Name' not in reg_def:
                    continue
                
                point_name = reg_def['Point Name']
                
                # Check if this register was already auto-discovered
                if point_name not in self.point_map:
                    # Parse asset and property from point name
                    parts = point_name.split('/')
                    if len(parts) >= 2:
                        asset_name = parts[0]
                        property_name = '/'.join(parts[1:])
                        
                        register = Register(
                            read_only=reg_def.get('Writable', 'FALSE').upper() != 'TRUE',
                            volttron_point_name=reg_def.get('Volttron Point Name', point_name),
                            units=reg_def.get('Units', ''),
                            description=reg_def.get('Description', point_name),
                            asset_name=asset_name,
                            property_name=property_name,
                            property_data={}
                        )
                        
                        self.insert_register(register)
                        self.register_map[register.point_name] = register
                        
        except Exception as e:
            _log.warning(f"Failed to parse registry configuration: {e}")
    
    def _make_request(self, method, url, **kwargs):
        """Make an HTTP request with automatic token refresh using grequests."""
        self._ensure_authenticated()
        
        try:
            kwargs['timeout'] = kwargs.get('timeout', self.timeout)
            kwargs['verify'] = kwargs.get('verify', self.verify_ssl)
            
            # Add token header
            headers = kwargs.get('headers', {})
            headers.update(self.session.headers)
            kwargs['headers'] = headers
            
            # Create grequests based on method
            if method.upper() == 'GET':
                req = grequests.get(url, **kwargs)
            elif method.upper() == 'POST':
                req = grequests.post(url, **kwargs)
            elif method.upper() == 'PUT':
                req = grequests.put(url, **kwargs)
            elif method.upper() == 'DELETE':
                req = grequests.delete(url, **kwargs)
            else:
                req = grequests.request(method, url, **kwargs)
            
            # Execute request asynchronously
            response = grequests.map([req], exception_handler=self._exception_handler)[0]
            
            if response is None:
                raise ConnectionError(f"Request to {url} failed - no response received")
            
            # Check if token expired and retry
            if response.status_code == 401:
                _log.debug("Received 401, re-authenticating and retrying")
                self._authenticate()
                
                # Update headers with new token
                headers.update(self.session.headers)
                kwargs['headers'] = headers
                
                # Retry request
                if method.upper() == 'GET':
                    req = grequests.get(url, **kwargs)
                elif method.upper() == 'POST':
                    req = grequests.post(url, **kwargs)
                else:
                    req = grequests.request(method, url, **kwargs)
                    
                response = grequests.map([req], exception_handler=self._exception_handler)[0]
                
                if response is None:
                    raise ConnectionError(f"Retry request to {url} failed after re-authentication")
            
            return response
            
        except Timeout:
            _log.error(f"Request timeout for {url}")
            raise
        except (RequestException, RequestsConnectionError) as e:
            _log.error(f"Request failed for {url}: {e}")
            raise
        except Exception as e:
            _log.error(f"Unexpected error in request to {url}: {e}")
            raise
    
    def get_point(self, point_name, **kwargs):
        """Get a single point value from the device."""
        try:
            register = self.get_register_by_name(point_name)
            
            # Build URL for the asset properties
            url = urljoin(self.url, f'/assets/{register.asset_name}/properties')
            
            response = self._make_request('GET', url)
            
            if response.status_code != HTTP_STATUS_OK:
                _log.error(f"Failed to get point {point_name}: status {response.status_code}")
                raise IOError(f"Failed to read point {point_name}")
            
            # Parse response and find the specific property
            properties = response.json()
            
            if isinstance(properties, list):
                for prop in properties:
                    if prop.get('name') == register.property_name:
                        value = prop.get('value')
                        result = register.get_state(value, self.collect_string_values)
                        if result is None and not self.collect_string_values:
                            _log.debug(f"Filtered out string value for {point_name}")
                        return result
            
            _log.warning(f"Property {register.property_name} not found in response")
            return None
            
        except Exception as e:
            _log.error(f"Error getting point {point_name}: {e}")
            raise
    
    def _set_point(self, point_name, value, **kwargs):
        """Set a point value on the device."""
        try:
            register = self.get_register_by_name(point_name)
            
            if register.read_only:
                raise IOError(f"Trying to write to read-only point: {point_name}")
            
            # Build URL for setting the property
            url = urljoin(self.url, f'/assets/{register.asset_name}/properties/{register.property_name}')
            
            # Prepare the value payload
            payload = {'value': value}
            
            response = self._make_request('POST', url, json=payload)
            
            if response.status_code not in [HTTP_STATUS_OK, 201, 204]:
                _log.error(f"Failed to set point {point_name}: status {response.status_code}")
                raise IOError(f"Failed to write point {point_name}")
            
            _log.debug(f"Successfully set {point_name} to {value}")
            return value
            
        except Exception as e:
            _log.error(f"Error setting point {point_name}: {e}")
            raise
    
    def _scrape_all(self):
        """Read all points from the device using batch requests."""
        results = {}
        
        try:
            self._ensure_authenticated()
            
            # Group registers by asset for efficient fetching
            assets_to_fetch = {}
            for point_name, register in self.point_map.items():
                if register.asset_name not in assets_to_fetch:
                    assets_to_fetch[register.asset_name] = []
                assets_to_fetch[register.asset_name].append((point_name, register))
            
            # Build batch requests - one per asset
            batch_requests = []
            request_map = {}  # Map request to asset/registers
            
            for asset_name, registers in assets_to_fetch.items():
                url = urljoin(self.url, f'/assets/{asset_name}/properties')
                
                # Create request with headers
                headers = dict(self.session.headers)
                req = grequests.get(
                    url,
                    headers=headers,
                    timeout=self.timeout,
                    verify=self.verify_ssl
                )
                
                batch_requests.append(req)
                request_map[req] = (asset_name, registers)
            
            # Execute all requests in parallel
            responses = grequests.map(
                batch_requests,
                exception_handler=self._exception_handler,
                size=10  # Limit concurrent requests
            )
            
            # Process responses
            for req, response in zip(batch_requests, responses):
                asset_name, registers = request_map[req]
                
                if response is None:
                    _log.warning(f"No response for properties on asset {asset_name}")
                    for point_name, _ in registers:
                        results[point_name] = None
                    continue
                
                if response.status_code == 401:
                    # Token expired, re-authenticate and retry this specific request
                    _log.debug("Token expired during scrape_all, re-authenticating")
                    self._authenticate()
                    
                    # Retry this specific request
                    headers = dict(self.session.headers)
                    retry_req = grequests.get(
                        req.url,
                        headers=headers,
                        timeout=self.timeout,
                        verify=self.verify_ssl
                    )
                    retry_response = grequests.map([retry_req], exception_handler=self._exception_handler)[0]
                    response = retry_response if retry_response else response
                
                if response and response.status_code == HTTP_STATUS_OK:
                    try:
                        properties = response.json()
                        
                        if isinstance(properties, list):
                            # Create a map for quick lookup
                            prop_map = {prop.get('name'): prop.get('value') 
                                      for prop in properties if isinstance(prop, dict)}
                            
                            # Extract values for our registers
                            for point_name, register in registers:
                                if register.property_name in prop_map:
                                    value = prop_map[register.property_name]
                                    result = register.get_state(value, self.collect_string_values)
                                    # Only add to results if value passes filter
                                    if result is not None or self.collect_string_values:
                                        results[point_name] = result
                                else:
                                    results[point_name] = None
                        else:
                            _log.warning(f"Unexpected response format for properties on {asset_name}")
                            for point_name, _ in registers:
                                results[point_name] = None
                                
                    except Exception as e:
                        _log.error(f"Failed to parse response for properties on {asset_name}: {e}")
                        for point_name, _ in registers:
                            results[point_name] = None
                else:
                    _log.warning(f"Failed to fetch properties for asset {asset_name}: status {response.status_code if response else 'None'}")
                    for point_name, _ in registers:
                        results[point_name] = None
            
            return results
            
        except Exception as e:
            _log.error(f"Error in scrape_all: {e}")
            # Return partial results if available
            return results