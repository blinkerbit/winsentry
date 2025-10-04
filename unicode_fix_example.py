#!/usr/bin/env python3
"""
Example of how to fix Unicode encoding issues in Python scripts
"""

import sys
import os

def setup_unicode_support():
    """Setup Unicode support for Windows console"""
    if sys.platform == 'win32':
        # Set environment variables
        os.environ['PYTHONIOENCODING'] = 'utf-8'
        os.environ['PYTHONLEGACYWINDOWSSTDIO'] = '1'
        
        # Try to set console code page
        try:
            import subprocess
            subprocess.run(['chcp', '65001'], shell=True, check=True, capture_output=True)
        except:
            pass

def safe_print(text):
    """Print text with Unicode error handling"""
    try:
        print(text)
    except UnicodeEncodeError:
        # Fallback: encode to ASCII with replacement characters
        print(text.encode('ascii', 'replace').decode('ascii'))

def print_banner_safe():
    """Example of a safe banner printing function"""
    banner = """
    ╔══════════════════════════════════════╗
    ║          Your Application            ║
    ║        Unicode Safe Banner           ║
    ╚══════════════════════════════════════╝
    """
    
    # Method 1: Use safe_print
    safe_print(banner)
    
    # Method 2: Use try/except
    try:
        print(banner)
    except UnicodeEncodeError as e:
        print("Application Banner (Unicode characters replaced)")
        print("=" * 40)

def main():
    """Main function with Unicode support"""
    # Setup Unicode support
    setup_unicode_support()
    
    # Print banner safely
    print_banner_safe()
    
    print("Application started successfully!")

if __name__ == "__main__":
    main()
