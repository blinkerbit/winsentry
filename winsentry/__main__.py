"""Main entry point for WinSentry - run with: python -m winsentry"""

import os
import sys
import argparse
import uvicorn
from pathlib import Path

def get_default_data_dir():
    """Get default data directory path"""
    if sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA", os.getcwd())
    else:
        base = os.path.expanduser("~/.local/share")
    return os.path.join(base, "winsentry", "data")

def get_default_log_dir():
    """Get default log directory path"""
    if sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA", os.getcwd())
    else:
        base = os.path.expanduser("~/.local/share")
    return os.path.join(base, "winsentry", "logs")

def main():
    """Main entry point for WinSentry"""
    parser = argparse.ArgumentParser(
        description="WinSentry - Windows System Monitoring & Alerting Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m winsentry
  python -m winsentry --host 0.0.0.0 --port 8000
  python -m winsentry --workers 8 --data-dir C:\\monitoring\\data
        """
    )
    
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind the web server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for the web interface (default: 8000)"
    )
    parser.add_argument(
        "--data-dir",
        default=get_default_data_dir(),
        help=f"Directory for database storage (default: {get_default_data_dir()})"
    )
    parser.add_argument(
        "--log-dir",
        default=get_default_log_dir(),
        help=f"Directory for log files (default: {get_default_log_dir()})"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of script execution workers (default: 4)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development (default: False)"
    )
    
    args = parser.parse_args()
    
    # Create necessary directories
    os.makedirs(args.data_dir, exist_ok=True)
    os.makedirs(args.log_dir, exist_ok=True)
    os.makedirs(os.path.join(args.log_dir, "monitoring"), exist_ok=True)
    os.makedirs(os.path.join(args.log_dir, "script_execution"), exist_ok=True)
    
    # Set environment variables for the app to use
    os.environ["WINSENTRY_DATA_DIR"] = args.data_dir
    os.environ["WINSENTRY_LOG_DIR"] = args.log_dir
    os.environ["WINSENTRY_WORKERS"] = str(args.workers)
    
    print(f"🚀 Starting WinSentry v{__import__('winsentry').__version__}")
    print(f"📊 Web interface: http://{args.host}:{args.port}")
    print(f"💾 Data directory: {args.data_dir}")
    print(f"📝 Log directory: {args.log_dir}")
    print(f"   - Script execution logs: {os.path.join(args.log_dir, 'script_execution')}")
    print(f"   - Monitoring logs: {os.path.join(args.log_dir, 'monitoring')}")
    print(f"⚙️  Script workers: {args.workers}")
    print(f"\nPress Ctrl+C to stop the service\n")
    
    # Import and initialize the app
    from .app import create_app
    from .database import DatabaseManager
    
    # Initialize database
    db_path = os.path.join(args.data_dir, "monitoring.db")
    db = DatabaseManager(db_path)
    
    # Create the FastAPI app
    app = create_app(db=db, log_dir=args.log_dir, workers=args.workers)
    
    # Run the server
    try:
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down WinSentry...")
        sys.exit(0)

if __name__ == "__main__":
    main()

