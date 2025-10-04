#!/usr/bin/env python3
"""
Test script to verify WinSentry imports work correctly
"""

import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all WinSentry modules can be imported"""
    try:
        print("Testing WinSentry imports...")
        
        # Test main module
        from winsentry import main
        print("[OK] winsentry.main imported successfully")
        
        # Test app module
        from winsentry import app
        print("[OK] winsentry.app imported successfully")
        
        # Test service manager
        from winsentry import service_manager
        print("[OK] winsentry.service_manager imported successfully")
        
        # Test port monitor
        from winsentry import port_monitor
        print("[OK] winsentry.port_monitor imported successfully")
        
        # Test handlers
        from winsentry import handlers
        print("[OK] winsentry.handlers imported successfully")
        
        # Test logger
        from winsentry import logger
        print("[OK] winsentry.logger imported successfully")
        
        print("\n[OK] All imports successful!")
        return True
        
    except ImportError as e:
        print(f"[ERROR] Import failed: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = test_imports()
    if not success:
        sys.exit(1)
    print("\nWinSentry is ready to run!")
    print("To start WinSentry, run:")
    print("  python run_winsentry.py")
    print("  or")
    print("  run_winsentry.bat")
