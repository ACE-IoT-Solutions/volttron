#!/usr/bin/env python3
"""
Test script to verify secret key obfuscation in logs
"""

import sys
from volttron.platform.vip.agent.core import obfuscate_sensitive_data


def test_obfuscation():
    """Test various obfuscation scenarios"""
    
    print("Testing Secret Key Obfuscation...")
    print("-" * 60)
    
    test_cases = [
        # (input, expected_contains, description)
        (
            "ShortStr",
            "ShortStr",
            "Short strings should not be obfuscated"
        ),
        (
            "/home/user/.volttron/run/vip.socket",
            "/home/user/.volttron/run/vip.socket",
            "File paths should not be obfuscated"
        ),
        (
            "ipc://@/home/user/.volttron/run/vip.socket",
            "ipc://@/home/user/.volttron/run/vip.socket",
            "IPC addresses should not be obfuscated"
        ),
        (
            "tcp://127.0.0.1:22916",
            "tcp://127.0.0.1:22916",
            "Plain TCP addresses should not be obfuscated"
        ),
        (
            "xDk0oJAW7hVGikvUxjEYl1RYtQ8OZ7b2i8sUe7k2YZ8=",
            "xDk0...YZ8=",
            "CURVE keys should be obfuscated"
        ),
        (
            "THISISAVERYLONGSECRETKEYABCDEFGHIJKLMNOPQRS",
            "THIS...PQRS",
            "Long secret keys should be obfuscated"
        ),
        (
            "tcp://pubkey123456789:secretkey123456789:serverkey123456789@127.0.0.1:22916",
            "tcp://pubk...6789:secr...6789:serv...6789@127.0.0.1:22916",
            "TCP addresses with embedded keys should have keys obfuscated"
        ),
        (
            None,
            None,
            "None should return None"
        ),
        (
            "",
            "",
            "Empty string should return empty"
        ),
    ]
    
    passed = 0
    failed = 0
    
    for input_data, expected_pattern, description in test_cases:
        result = obfuscate_sensitive_data(input_data)
        
        # Check if result matches expected pattern
        if expected_pattern is None:
            success = result is None
        elif "..." in str(expected_pattern):
            # For obfuscated data, check pattern
            success = (
                result is not None and
                "..." in result and
                result.startswith(expected_pattern.split("...")[0]) and
                result.endswith(expected_pattern.split("...")[-1])
            )
        else:
            # For non-obfuscated data, should match exactly
            success = result == expected_pattern
        
        if success:
            print(f"✓ PASS: {description}")
            if input_data and len(str(input_data)) > 40:
                print(f"  Input:  {str(input_data)[:40]}...")
            else:
                print(f"  Input:  {input_data}")
            print(f"  Output: {result}")
            passed += 1
        else:
            print(f"✗ FAIL: {description}")
            print(f"  Input:    {input_data}")
            print(f"  Expected: {expected_pattern}")
            print(f"  Got:      {result}")
            failed += 1
        print()
    
    print("-" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    
    return failed == 0


def test_security():
    """Test that sensitive data is actually hidden"""
    print("\nSecurity Test: Ensuring secrets are hidden...")
    print("-" * 60)
    
    # Test with a realistic CURVE key
    secret_key = "xDk0oJAW7hVGikvUxjEYl1RYtQ8OZ7b2i8sUe7k2YZ8="
    obfuscated = obfuscate_sensitive_data(secret_key)
    
    # The middle part should be hidden
    middle_exposed = secret_key[4:-4] in obfuscated
    
    if not middle_exposed and "..." in obfuscated:
        print("✓ Secret key middle portion is properly hidden")
        print(f"  Original: {secret_key}")
        print(f"  Obfuscated: {obfuscated}")
        return True
    else:
        print("✗ SECURITY ISSUE: Secret key not properly hidden!")
        print(f"  Original: {secret_key}")
        print(f"  Obfuscated: {obfuscated}")
        return False


if __name__ == "__main__":
    success = True
    
    # Run functionality tests
    if not test_obfuscation():
        success = False
    
    # Run security test
    if not test_security():
        success = False
    
    if success:
        print("\n✓ All tests passed! Secret keys will be properly obfuscated in logs.")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed")
        sys.exit(1)