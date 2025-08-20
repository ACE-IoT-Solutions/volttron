#!/usr/bin/env python3
"""
Test script to verify VIPError.from_errno handles both integer and string errno formats
"""

import sys
import errno
from volttron.platform.vip.agent.errors import VIPError, Unreachable, Again, UnknownSubsystem


def test_from_errno():
    """Test VIPError.from_errno with various input formats"""
    
    print("Testing VIPError.from_errno fixes...")
    print("-" * 50)
    
    test_cases = [
        # (input, expected_error_class, description)
        (errno.EHOSTUNREACH, Unreachable, "Integer EHOSTUNREACH"),
        (str(errno.EHOSTUNREACH), Unreachable, "String number EHOSTUNREACH"),
        ("Errno.EHOSTUNREACH", Unreachable, "String 'Errno.EHOSTUNREACH'"),
        (errno.EAGAIN, Again, "Integer EAGAIN"),
        ("Errno.EAGAIN", Again, "String 'Errno.EAGAIN'"),
        (errno.EPROTONOSUPPORT, UnknownSubsystem, "Integer EPROTONOSUPPORT"),
        ("Errno.EPROTONOSUPPORT", UnknownSubsystem, "String 'Errno.EPROTONOSUPPORT'"),
        ("Errno.UNKNOWN_ERROR", VIPError, "Unknown error string (should default)"),
        ("12345", VIPError, "Random number string"),
        (99999, VIPError, "Unknown error number"),
    ]
    
    passed = 0
    failed = 0
    
    for errnum_input, expected_class, description in test_cases:
        try:
            error = VIPError.from_errno(errnum_input, "Test message", "test_peer", "test_subsystem")
            
            if isinstance(error, expected_class):
                print(f"✓ PASS: {description}")
                print(f"  Input: {errnum_input!r} -> {error.__class__.__name__}")
                passed += 1
            else:
                print(f"✗ FAIL: {description}")
                print(f"  Input: {errnum_input!r}")
                print(f"  Expected: {expected_class.__name__}")
                print(f"  Got: {error.__class__.__name__}")
                failed += 1
                
        except Exception as e:
            print(f"✗ ERROR: {description}")
            print(f"  Input: {errnum_input!r}")
            print(f"  Exception: {e}")
            failed += 1
    
    print("-" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    
    return failed == 0


def test_actual_error_case():
    """Test the actual error case from the logs"""
    print("\nTesting actual error case from logs...")
    print("-" * 50)
    
    # This is the actual error string from the logs
    error_string = "Errno.EHOSTUNREACH"
    
    try:
        error = VIPError.from_errno(error_string, "Host unreachable", "platform.bacnet_proxy", "rpc")
        print(f"✓ Successfully created error from '{error_string}'")
        print(f"  Error type: {error.__class__.__name__}")
        print(f"  Error message: {error}")
        
        # Verify it's the correct error type
        assert isinstance(error, Unreachable), f"Expected Unreachable, got {error.__class__.__name__}"
        print("✓ Error is correctly identified as Unreachable")
        
        return True
    except Exception as e:
        print(f"✗ Failed to handle '{error_string}': {e}")
        return False


if __name__ == "__main__":
    success = True
    
    # Run basic tests
    if not test_from_errno():
        success = False
    
    # Test actual error case
    if not test_actual_error_case():
        success = False
    
    if success:
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed")
        sys.exit(1)