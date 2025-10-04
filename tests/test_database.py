#!/usr/bin/env python3
"""
Test script to verify SQLite database functionality
"""

import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_database():
    """Test database functionality"""
    try:
        print("Testing WinSentry database functionality...")
        
        # Test database import
        from winsentry.database import Database
        print("[OK] Database module imported successfully")
        
        # Test database initialization
        db = Database("test_winsentry.db")
        print("[OK] Database initialized successfully")
        
        # Test saving port configuration
        success = db.save_port_config(8080, 30, "C:\\test\\script.ps1", True)
        if success:
            print("[OK] Port configuration saved successfully")
        else:
            print("[ERROR] Failed to save port configuration")
            return False
        
        # Test retrieving port configuration
        config = db.get_port_config(8080)
        if config and config['port'] == 8080:
            print("[OK] Port configuration retrieved successfully")
        else:
            print("[ERROR] Failed to retrieve port configuration")
            return False
        
        # Test logging port check
        success = db.log_port_check(8080, "ONLINE", 0, "Port is online")
        if success:
            print("[OK] Port check logged successfully")
        else:
            print("[ERROR] Failed to log port check")
            return False
        
        # Test getting logs
        logs = db.get_port_logs(8080, limit=10)
        if logs and len(logs) > 0:
            print("[OK] Port logs retrieved successfully")
        else:
            print("[ERROR] Failed to retrieve port logs")
            return False
        
        # Test database stats
        stats = db.get_database_stats()
        if stats and 'port_configs' in stats:
            print("[OK] Database stats retrieved successfully")
        else:
            print("[ERROR] Failed to get database stats")
            return False
        
        # Test cleanup
        success = db.delete_port_config(8080)
        if success:
            print("[OK] Port configuration deleted successfully")
        else:
            print("[ERROR] Failed to delete port configuration")
            return False
        
        # Clean up test database (may fail on Windows due to file locks)
        try:
            if os.path.exists("test_winsentry.db"):
                os.remove("test_winsentry.db")
                print("[OK] Test database cleaned up")
        except Exception as e:
            print(f"[WARNING] Could not delete test database (this is normal on Windows): {e}")
        
        print("\n[OK] All database tests passed!")
        return True
        
    except Exception as e:
        print(f"[ERROR] Database test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_database()
    if not success:
        sys.exit(1)
    print("\nDatabase functionality is working correctly!")
