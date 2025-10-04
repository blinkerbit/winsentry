#!/usr/bin/env python3
"""
Test script to verify WinSentry installation and basic functionality
"""

import sys
import os

def test_imports():
    """Test that all required modules can be imported"""
    try:
        import tornado
        print("[OK] Tornado imported successfully")
    except ImportError as e:
        print(f"[ERROR] Failed to import Tornado: {e}")
        return False
    
    try:
        import psutil
        print("[OK] psutil imported successfully")
    except ImportError as e:
        print(f"[ERROR] Failed to import psutil: {e}")
        return False
    
    try:
        import win32serviceutil
        print("[OK] pywin32 imported successfully")
    except ImportError as e:
        print(f"[ERROR] Failed to import pywin32: {e}")
        return False
    
    try:
        import wmi
        print("[OK] WMI imported successfully")
    except ImportError as e:
        print(f"[ERROR] Failed to import WMI: {e}")
        return False
    
    return True

def test_winsentry_imports():
    """Test that WinSentry modules can be imported"""
    try:
        from winsentry import main
        print("[OK] WinSentry main module imported successfully")
    except ImportError as e:
        print(f"[ERROR] Failed to import WinSentry main: {e}")
        return False
    
    try:
        from winsentry import service_manager
        print("[OK] WinSentry service_manager imported successfully")
    except ImportError as e:
        print(f"[ERROR] Failed to import WinSentry service_manager: {e}")
        return False
    
    try:
        from winsentry import port_monitor
        print("[OK] WinSentry port_monitor imported successfully")
    except ImportError as e:
        print(f"[ERROR] Failed to import WinSentry port_monitor: {e}")
        return False
    
    return True

def test_basic_functionality():
    """Test basic functionality without starting the server"""
    try:
        from winsentry.service_manager import ServiceManager
        from winsentry.port_monitor import PortMonitor
        
        # Test service manager initialization
        sm = ServiceManager()
        print("[OK] ServiceManager initialized successfully")
        
        # Test port monitor initialization
        pm = PortMonitor()
        print("[OK] PortMonitor initialized successfully")
        
        return True
    except Exception as e:
        print(f"[ERROR] Failed to initialize WinSentry components: {e}")
        return False

def main():
    """Run all tests"""
    print("WinSentry Installation Test")
    print("=" * 40)
    
    all_passed = True
    
    print("\n1. Testing required dependencies...")
    if not test_imports():
        all_passed = False
    
    print("\n2. Testing WinSentry module imports...")
    if not test_winsentry_imports():
        all_passed = False
    
    print("\n3. Testing basic functionality...")
    if not test_basic_functionality():
        all_passed = False
    
    print("\n" + "=" * 40)
    if all_passed:
        print("[OK] All tests passed! WinSentry is ready to use.")
        print("\nTo start WinSentry, run:")
        print("  winsentry")
        print("  or")
        print("  python run_winsentry.py")
        print("  or")
        print("  run_winsentry.bat")
        print("\nThen open your browser to: http://localhost:8888")
    else:
        print("[ERROR] Some tests failed. Please check the error messages above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
