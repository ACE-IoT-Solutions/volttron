#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Unit tests for the Spirae Wave interface driver.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import json
from datetime import datetime, timedelta

# Import the interface module
from platform_driver.interfaces.spirae_wave import Interface, Register


class TestSpiraeWaveRegister(unittest.TestCase):
    """Test cases for the Register class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.register = Register(
            read_only=False,
            volttron_point_name="system/test_point",
            units="kW",
            description="Test Point",
            asset_name="system",
            property_name="test_point",
            property_data={"endpoint": "properties", "group": "Command Info"}
        )
    
    def test_register_initialization(self):
        """Test register is properly initialized."""
        self.assertEqual(self.register.asset_name, "system")
        self.assertEqual(self.register.property_name, "test_point")
        self.assertEqual(self.register.endpoint, "properties")
        self.assertFalse(self.register.read_only)
    
    def test_get_state_boolean(self):
        """Test get_state with boolean values."""
        self.assertTrue(self.register.get_state(True))
        self.assertFalse(self.register.get_state(False))
    
    def test_get_state_numeric(self):
        """Test get_state with numeric values."""
        self.assertEqual(self.register.get_state("10"), 10)
        self.assertEqual(self.register.get_state("10.5"), 10.5)
        self.assertEqual(self.register.get_state(42), 42)
        self.assertEqual(self.register.get_state(3.14), 3.14)
    
    def test_get_state_string(self):
        """Test get_state with string values."""
        self.assertEqual(self.register.get_state("test"), "test")
        self.assertEqual(self.register.get_state(""), "")
    
    def test_get_state_none(self):
        """Test get_state with None value."""
        self.assertIsNone(self.register.get_state(None))


class TestSpiraeWaveInterface(unittest.TestCase):
    """Test cases for the Interface class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.interface = Interface()
        self.config_dict = {
            "url": "https://localhost:18080",
            "username": "admin",
            "password": "admin",
            "verify_ssl": False,
            "timeout": 10
        }
        
        # Sample data for mocking
        self.sample_assets = ["system", "bess", "pv1"]
        self.sample_properties = [
            {
                "name": "System_frequency",
                "displayname": "System Frequency",
                "units": "Hz",
                "group": "Frequency Info",
                "subgroup": "System",
                "value": 60.0
            },
            {
                "name": "System_reset",
                "displayname": "Reset Alarms",
                "units": None,
                "group": "Command Info",
                "subgroup": "System",
                "value": False
            }
        ]
    
    @patch('platform_driver.interfaces.spirae_wave.requests.Session')
    def test_configure_basic(self, mock_session_class):
        """Test basic configuration without asset filtering."""
        # Mock the session and responses
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        
        # Mock authentication response
        auth_response = Mock()
        auth_response.status_code = 200
        auth_response.json.return_value = {"data": "test_token"}
        
        # Mock assets response
        assets_response = Mock()
        assets_response.status_code = 200
        assets_response.json.return_value = self.sample_assets
        
        # Mock properties response
        properties_response = Mock()
        properties_response.status_code = 200
        properties_response.json.return_value = self.sample_properties
        
        # Configure mock to return different responses
        mock_session.post.return_value = auth_response
        mock_session.request.side_effect = [
            assets_response,  # For getting assets
            properties_response,  # For system properties
            Mock(status_code=404),  # For system status
            Mock(status_code=404),  # For system quickview
            properties_response,  # For bess properties
            Mock(status_code=404),  # For bess status
            Mock(status_code=404),  # For bess quickview
            properties_response,  # For pv1 properties
            Mock(status_code=404),  # For pv1 status
            Mock(status_code=404),  # For pv1 quickview
        ]
        
        # Configure the interface
        self.interface.configure(self.config_dict, None)
        
        # Verify configuration
        self.assertEqual(self.interface.url, "https://localhost:18080")
        self.assertEqual(self.interface.username, "admin")
        self.assertEqual(self.interface.password, "admin")
        self.assertFalse(self.interface.verify_ssl)
        self.assertEqual(self.interface.timeout, 10)
        
        # Verify authentication was called
        mock_session.post.assert_called_once()
        
        # Verify token was set
        self.assertEqual(self.interface.token, "test_token")
        
        # Verify registers were created
        self.assertTrue(len(self.interface.point_map) > 0)
    
    def test_configure_missing_credentials(self):
        """Test configuration with missing credentials."""
        invalid_config = {"url": "https://localhost:18080"}
        
        with self.assertRaises(ValueError) as context:
            self.interface.configure(invalid_config, None)
        
        self.assertIn("required configuration parameters", str(context.exception))
    
    @patch('platform_driver.interfaces.spirae_wave.requests.Session')
    def test_asset_property_filtering(self, mock_session_class):
        """Test configuration with asset/property filtering."""
        # Add filtering to config
        self.config_dict["asset_property_map"] = {
            "system": ["System_frequency"],
            "bess": None  # Include all properties
        }
        
        # Mock the session and responses
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        
        # Mock authentication
        auth_response = Mock()
        auth_response.status_code = 200
        auth_response.json.return_value = {"data": "test_token"}
        mock_session.post.return_value = auth_response
        
        # Mock assets response
        assets_response = Mock()
        assets_response.status_code = 200
        assets_response.json.return_value = self.sample_assets
        
        # Mock properties response
        properties_response = Mock()
        properties_response.status_code = 200
        properties_response.json.return_value = self.sample_properties
        
        mock_session.request.side_effect = [
            assets_response,
            properties_response,
            Mock(status_code=404),
            Mock(status_code=404),
            properties_response,
            Mock(status_code=404),
            Mock(status_code=404),
        ]
        
        # Configure the interface
        self.interface.configure(self.config_dict, None)
        
        # Verify filtering was applied
        self.assertIn("system/System_frequency", self.interface.point_map)
        self.assertNotIn("pv1/System_frequency", self.interface.point_map)
    
    @patch('platform_driver.interfaces.spirae_wave.requests.Session')
    def test_authentication_failure(self, mock_session_class):
        """Test handling of authentication failure."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        
        # Mock failed authentication
        auth_response = Mock()
        auth_response.status_code = 401
        auth_response.text = "Invalid credentials"
        mock_session.post.return_value = auth_response
        
        with self.assertRaises(ConnectionError) as context:
            self.interface.configure(self.config_dict, None)
        
        self.assertIn("Authentication failed", str(context.exception))
    
    @patch('platform_driver.interfaces.spirae_wave.Interface._make_request')
    def test_get_point(self):
        """Test getting a single point value."""
        # Create a mock register
        register = Register(
            read_only=True,
            volttron_point_name="system/System_frequency",
            units="Hz",
            description="System Frequency",
            asset_name="system",
            property_name="System_frequency",
            property_data={"endpoint": "properties"}
        )
        
        self.interface.point_map = {"system/System_frequency": register}
        self.interface.register_map = {"system/System_frequency": register}
        
        # Mock the response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "name": "System_frequency",
                "value": 60.01
            }
        ]
        self.interface._make_request.return_value = mock_response
        
        # Get the point
        value = self.interface.get_point("system/System_frequency")
        
        self.assertEqual(value, 60.01)
    
    @patch('platform_driver.interfaces.spirae_wave.Interface._make_request')
    def test_set_point(self):
        """Test setting a point value."""
        # Create a writable register
        register = Register(
            read_only=False,
            volttron_point_name="system/System_reset",
            units=None,
            description="Reset Alarms",
            asset_name="system",
            property_name="System_reset",
            property_data={"endpoint": "properties", "group": "Command Info"}
        )
        
        self.interface.point_map = {"system/System_reset": register}
        self.interface.register_map = {"system/System_reset": register}
        
        # Mock the response
        mock_response = Mock()
        mock_response.status_code = 200
        self.interface._make_request.return_value = mock_response
        
        # Set the point
        result = self.interface._set_point("system/System_reset", True)
        
        self.assertEqual(result, True)
        self.interface._make_request.assert_called_once()
    
    def test_set_readonly_point(self):
        """Test attempting to set a read-only point."""
        # Create a read-only register
        register = Register(
            read_only=True,
            volttron_point_name="system/System_frequency",
            units="Hz",
            description="System Frequency",
            asset_name="system",
            property_name="System_frequency",
            property_data={"endpoint": "properties"}
        )
        
        self.interface.point_map = {"system/System_frequency": register}
        self.interface.register_map = {"system/System_frequency": register}
        
        # Attempt to set the read-only point
        with self.assertRaises(IOError) as context:
            self.interface._set_point("system/System_frequency", 60.0)
        
        self.assertIn("read-only", str(context.exception))
    
    @patch('platform_driver.interfaces.spirae_wave.Interface._make_request')
    def test_scrape_all(self):
        """Test scraping all points."""
        # Create multiple registers
        register1 = Register(
            read_only=True,
            volttron_point_name="system/System_frequency",
            units="Hz",
            description="System Frequency",
            asset_name="system",
            property_name="System_frequency",
            property_data={"endpoint": "properties"}
        )
        
        register2 = Register(
            read_only=True,
            volttron_point_name="system/System_voltage",
            units="V",
            description="System Voltage",
            asset_name="system",
            property_name="System_voltage",
            property_data={"endpoint": "properties"}
        )
        
        self.interface.point_map = {
            "system/System_frequency": register1,
            "system/System_voltage": register2
        }
        
        # Mock the response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"name": "System_frequency", "value": 60.01},
            {"name": "System_voltage", "value": 210.5}
        ]
        self.interface._make_request.return_value = mock_response
        
        # Scrape all points
        results = self.interface._scrape_all()
        
        self.assertEqual(results["system/System_frequency"], 60.01)
        self.assertEqual(results["system/System_voltage"], 210.5)
    
    @patch('platform_driver.interfaces.spirae_wave.requests.Session')
    def test_token_refresh(self, mock_session_class):
        """Test automatic token refresh when expired."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        
        # Set up initial state
        self.interface.session = mock_session
        self.interface.url = "https://localhost:18080"
        self.interface.username = "admin"
        self.interface.password = "admin"
        self.interface.token = "old_token"
        self.interface.token_expiry = datetime.now() - timedelta(hours=1)  # Expired
        
        # Mock authentication response
        auth_response = Mock()
        auth_response.status_code = 200
        auth_response.json.return_value = {"data": "new_token"}
        mock_session.post.return_value = auth_response
        
        # Trigger token refresh
        self.interface._ensure_authenticated()
        
        # Verify new token was obtained
        self.assertEqual(self.interface.token, "new_token")
        self.assertGreater(self.interface.token_expiry, datetime.now())


if __name__ == '__main__':
    unittest.main()