"""
Main entry point for WinSentry application
"""

import asyncio
import logging
import signal
import sys
import os
from tornado import web, ioloop
from tornado.options import define, options, parse_command_line

# Try to use winloop for better performance on Windows
try:
    import winloop
    winloop.install()
    USING_WINLOOP = True
except ImportError:
    USING_WINLOOP = False

# Try absolute imports first (when installed as package)
from winsentry.app import WinSentryApplication
from winsentry.service_manager import ServiceManager
from winsentry.port_monitor import PortMonitor
from winsentry.service_monitor import ServiceMonitor
from winsentry.system_resource_monitor import SystemResourceMonitor
from winsentry.adhoc_check_manager import AdhocCheckManager
from winsentry.logger import setup_logging


# Configuration options
define("port", default=8888, help="Port to run the server on", type=int)
define("debug", default=False, help="Enable debug mode", type=bool)
define("db_path", default="winsentry.db", help="Path to SQLite database", type=str)
define("log_level", default="INFO", help="Logging level (DEBUG, INFO, WARNING, ERROR)", type=str)


# Global references for cleanup
_port_monitor = None
_service_monitor = None
_resource_monitor = None
_adhoc_check_manager = None
_shutdown_event = None


async def shutdown_monitors(logger):
    """Gracefully stop all monitoring tasks"""
    global _port_monitor, _service_monitor, _resource_monitor, _adhoc_check_manager
    
    logger.info("Stopping monitoring tasks...")
    
    tasks = []
    
    if _port_monitor:
        try:
            tasks.append(_port_monitor.stop_monitoring())
        except Exception as e:
            logger.error(f"Error stopping port monitor: {e}")
    
    if _service_monitor:
        try:
            tasks.append(_service_monitor.stop_monitoring())
        except Exception as e:
            logger.error(f"Error stopping service monitor: {e}")
    
    if _resource_monitor:
        try:
            tasks.append(_resource_monitor.stop_monitoring())
        except Exception as e:
            logger.error(f"Error stopping resource monitor: {e}")
    
    if _adhoc_check_manager:
        try:
            tasks.append(_adhoc_check_manager.stop_monitoring())
        except Exception as e:
            logger.error(f"Error stopping adhoc check manager: {e}")
    
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    
    logger.info("All monitoring tasks stopped")


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger = logging.getLogger(__name__)
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    
    loop = ioloop.IOLoop.current()
    
    async def async_shutdown():
        await shutdown_monitors(logger)
        loop.stop()
    
    loop.add_callback(lambda: asyncio.create_task(async_shutdown()))


def main():
    """Main entry point"""
    global _port_monitor, _service_monitor, _resource_monitor, _adhoc_check_manager
    
    parse_command_line()
    
    # Setup logging
    log_level = getattr(logging, options.log_level.upper(), logging.INFO)
    setup_logging(debug=options.debug)
    logging.getLogger().setLevel(log_level)
    logger = logging.getLogger(__name__)
    
    # Log startup information
    logger.info("=" * 50)
    logger.info("WinSentry - Windows Service & Port Monitor")
    logger.info("=" * 50)
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Using winloop: {USING_WINLOOP}")
    logger.info(f"Debug mode: {options.debug}")
    logger.info(f"Database path: {options.db_path}")
    logger.info(f"Log level: {options.log_level}")
    
    try:
        # Register signal handlers for graceful shutdown
        if sys.platform != 'win32':
            signal.signal(signal.SIGTERM, signal_handler)
            signal.signal(signal.SIGHUP, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        # Initialize managers with database path
        logger.info("Initializing components...")
        
        service_manager = ServiceManager(db_path=options.db_path)
        _port_monitor = PortMonitor(db_path=options.db_path)
        _service_monitor = ServiceMonitor(db_path=options.db_path)
        _resource_monitor = SystemResourceMonitor(db_path=options.db_path)
        _adhoc_check_manager = AdhocCheckManager(db_path=options.db_path)
        
        logger.info("All components initialized successfully")
        
        # Create application
        app = WinSentryApplication(
            service_manager, 
            _port_monitor, 
            _service_monitor, 
            _resource_monitor,
            _adhoc_check_manager
        )
        
        # Start the server
        try:
            app.listen(options.port)
            logger.info(f"Server listening on http://localhost:{options.port}")
        except OSError as e:
            if "address already in use" in str(e).lower() or "only one usage" in str(e).lower():
                logger.error(f"Port {options.port} is already in use. Please use a different port with --port=<port_number>")
                sys.exit(1)
            raise
        
        # Start the event loop
        loop = ioloop.IOLoop.current()
        
        # Start monitoring tasks as background tasks
        def start_monitoring_tasks():
            logger.info("Starting monitoring tasks...")
            asyncio.create_task(_port_monitor.start_monitoring())
            asyncio.create_task(_service_monitor.start_monitoring())
            asyncio.create_task(_resource_monitor.start_monitoring())
            asyncio.create_task(_adhoc_check_manager.start_monitoring())
            logger.info("All monitoring tasks started")
        
        # Schedule the monitoring tasks to start after the loop begins
        loop.add_callback(start_monitoring_tasks)
        
        logger.info("WinSentry is ready and running!")
        logger.info(f"Open your browser at http://localhost:{options.port}")
        
        # Start the event loop
        loop.start()
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Failed to start WinSentry: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("WinSentry shutdown complete")


if __name__ == "__main__":
    main()
