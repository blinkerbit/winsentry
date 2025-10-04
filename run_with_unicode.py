#!/usr/bin/env python3
"""
Script to run Python applications with proper Unicode support on Windows
"""

import sys
import os
import subprocess
import locale

def setup_unicode_environment():
    """Setup environment for proper Unicode support"""
    try:
        # Set environment variables for Unicode support
        os.environ['PYTHONIOENCODING'] = 'utf-8'
        os.environ['PYTHONLEGACYWINDOWSSTDIO'] = '1'
        
        # Try to set console code page to UTF-8
        try:
            subprocess.run(['chcp', '65001'], shell=True, check=True, capture_output=True)
        except:
            pass  # Ignore if chcp fails
            
        print("Unicode environment configured successfully")
        return True
    except Exception as e:
        print(f"Warning: Could not setup Unicode environment: {e}")
        return False

def run_with_unicode_handling(script_path, *args):
    """Run a Python script with Unicode error handling"""
    try:
        # Setup Unicode environment
        setup_unicode_environment()
        
        # Import and run the script
        sys.path.insert(0, os.path.dirname(script_path))
        
        # Read the script content
        with open(script_path, 'r', encoding='utf-8') as f:
            script_content = f.read()
        
        # Execute the script with proper encoding
        exec(script_content, {'__name__': '__main__'})
        
    except UnicodeEncodeError as e:
        print(f"Unicode encoding error: {e}")
        print("Try running with: python -X utf8 your_script.py")
        return False
    except Exception as e:
        print(f"Error running script: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_with_unicode.py <script_path> [args...]")
        sys.exit(1)
    
    script_path = sys.argv[1]
    args = sys.argv[2:]
    
    if not os.path.exists(script_path):
        print(f"Script not found: {script_path}")
        sys.exit(1)
    
    success = run_with_unicode_handling(script_path, *args)
    sys.exit(0 if success else 1)
