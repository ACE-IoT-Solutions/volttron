#!/usr/bin/env python3
"""
Test script to verify improved connection error messages
"""

import os
import sys
import logging
from volttron.platform.vip.agent import Agent

# Set up logging to see our improved error messages
logging.basicConfig(level=logging.ERROR, format='%(message)s')

def test_connection_failure():
    """Test connection failure to see improved error messages"""
    
    print("Testing improved connection error messages...")
    print("-" * 60)
    print("This test will attempt to connect to a non-existent platform")
    print("to demonstrate the improved error messaging.")
    print("-" * 60)
    print()
    
    # Set a fake VOLTTRON_HOME to simulate wrong instance
    os.environ['VOLTTRON_HOME'] = '/tmp/fake_volttron_home'
    
    # Try to connect with a test agent
    try:
        # This should fail and show our improved error messages
        agent = Agent(identity='test-connection-agent')
        agent.core.run()
    except Exception as e:
        # The improved error messages should have been logged
        print("\nAgent failed to connect (expected behavior for this test)")
        print(f"Exception: {e}")
    
    print("\n" + "-" * 60)
    print("Test complete. Check the error messages above.")
    print("The new messages should:")
    print("  1. Clearly show connection details")
    print("  2. Detect if platform is running")
    print("  3. Provide solutions in order of likelihood")
    print("  4. Give specific debugging commands")
    print("  5. NOT misleadingly focus on 'conflicting VIP IDENTITY'")
    print("-" * 60)

if __name__ == "__main__":
    test_connection_failure()