#!/usr/bin/env python3
"""
VOLTTRON ZMQ Connectivity Test Suite
Tests ZMQ functionality after merging 8.1.3 improvements to 9.0.4
"""

import sys
import time
import zmq
import json
import subprocess
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_zmq_version():
    """Test ZMQ version compatibility"""
    logger.info("Testing ZMQ version...")
    version = zmq.zmq_version()
    pyzmq_version = zmq.pyzmq_version()
    
    logger.info(f"ZMQ library version: {version}")
    logger.info(f"PyZMQ version: {pyzmq_version}")
    
    # Check minimum required versions
    assert version >= "4.2.0", f"ZMQ version {version} is too old"
    assert pyzmq_version >= "26.0.0", f"PyZMQ version {pyzmq_version} is too old"
    
    logger.info("✓ ZMQ versions are compatible")
    return True

def test_zmq_socket_types():
    """Test various ZMQ socket types"""
    logger.info("Testing ZMQ socket types...")
    context = zmq.Context()
    
    socket_types = [
        zmq.PAIR, zmq.PUB, zmq.SUB, zmq.REQ, zmq.REP,
        zmq.DEALER, zmq.ROUTER, zmq.PULL, zmq.PUSH
    ]
    
    for socket_type in socket_types:
        try:
            socket = context.socket(socket_type)
            socket.close()
            logger.info(f"✓ Socket type {socket_type} working")
        except Exception as e:
            logger.error(f"✗ Socket type {socket_type} failed: {e}")
            return False
    
    context.term()
    logger.info("✓ All ZMQ socket types working")
    return True

def test_zmq_pubsub():
    """Test ZMQ pub/sub pattern (used by VOLTTRON)"""
    logger.info("Testing ZMQ pub/sub pattern...")
    context = zmq.Context()
    
    # Create publisher
    publisher = context.socket(zmq.PUB)
    publisher.bind("tcp://127.0.0.1:5555")
    
    # Create subscriber
    subscriber = context.socket(zmq.SUB)
    subscriber.connect("tcp://127.0.0.1:5555")
    subscriber.setsockopt(zmq.SUBSCRIBE, b"test")
    
    # Allow connection to establish
    time.sleep(0.1)
    
    # Send message
    test_message = {"type": "test", "data": "Hello VOLTTRON"}
    publisher.send_multipart([b"test", json.dumps(test_message).encode()])
    
    # Receive message
    try:
        topic, message = subscriber.recv_multipart(flags=zmq.NOBLOCK)
        received = json.loads(message.decode())
        assert received == test_message, "Message mismatch"
        logger.info("✓ Pub/Sub pattern working")
        result = True
    except zmq.Again:
        logger.error("✗ No message received")
        result = False
    
    publisher.close()
    subscriber.close()
    context.term()
    
    return result

def test_zmq_router_dealer():
    """Test ZMQ router/dealer pattern (used by VOLTTRON VIP)"""
    logger.info("Testing ZMQ router/dealer pattern...")
    context = zmq.Context()
    
    # Create router
    router = context.socket(zmq.ROUTER)
    router.bind("tcp://127.0.0.1:5556")
    
    # Create dealer
    dealer = context.socket(zmq.DEALER)
    dealer.identity = b"test-dealer"
    dealer.connect("tcp://127.0.0.1:5556")
    
    # Send from dealer
    dealer.send(b"Hello from dealer")
    
    # Receive at router
    identity, message = router.recv_multipart()
    assert identity == b"test-dealer"
    assert message == b"Hello from dealer"
    
    # Reply from router
    router.send_multipart([identity, b"Hello from router"])
    
    # Receive at dealer
    reply = dealer.recv()
    assert reply == b"Hello from router"
    
    logger.info("✓ Router/Dealer pattern working")
    
    router.close()
    dealer.close()
    context.term()
    
    return True

def test_volttron_platform():
    """Test VOLTTRON platform startup"""
    logger.info("Testing VOLTTRON platform startup...")
    
    # Check if VOLTTRON is installed
    try:
        result = subprocess.run(
            ["volttron", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            logger.info(f"✓ VOLTTRON version: {result.stdout.strip()}")
            return True
        else:
            logger.error(f"✗ VOLTTRON not properly installed: {result.stderr}")
            return False
    except FileNotFoundError:
        logger.error("✗ VOLTTRON command not found")
        return False
    except subprocess.TimeoutExpired:
        logger.error("✗ VOLTTRON command timed out")
        return False

def test_agent_communication():
    """Test agent communication patterns"""
    logger.info("Testing agent communication patterns...")
    
    # This would require a running VOLTTRON instance
    # For now, we'll just test the basic setup
    
    try:
        from volttron.platform.vip.agent import Agent
        from volttron.platform import get_home
        
        volttron_home = get_home()
        logger.info(f"✓ VOLTTRON home: {volttron_home}")
        
        # Check if auth file exists
        auth_file = Path(volttron_home) / "auth.json"
        if auth_file.exists():
            logger.info("✓ Auth file found")
        else:
            logger.warning("⚠ Auth file not found (expected for new installation)")
        
        return True
    except ImportError as e:
        logger.error(f"✗ Cannot import VOLTTRON modules: {e}")
        return False

def run_all_tests():
    """Run all ZMQ connectivity tests"""
    logger.info("=" * 60)
    logger.info("VOLTTRON ZMQ Connectivity Test Suite")
    logger.info("=" * 60)
    
    tests = [
        ("ZMQ Version", test_zmq_version),
        ("ZMQ Socket Types", test_zmq_socket_types),
        ("ZMQ Pub/Sub", test_zmq_pubsub),
        ("ZMQ Router/Dealer", test_zmq_router_dealer),
        ("VOLTTRON Platform", test_volttron_platform),
        ("Agent Communication", test_agent_communication),
    ]
    
    results = []
    for test_name, test_func in tests:
        logger.info(f"\nRunning: {test_name}")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"✗ Test failed with exception: {e}")
            results.append((test_name, False))
    
    logger.info("\n" + "=" * 60)
    logger.info("Test Results Summary")
    logger.info("=" * 60)
    
    passed = 0
    failed = 0
    for test_name, result in results:
        status = "PASSED" if result else "FAILED"
        symbol = "✓" if result else "✗"
        logger.info(f"{symbol} {test_name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1
    
    logger.info(f"\nTotal: {passed} passed, {failed} failed")
    
    return failed == 0

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)