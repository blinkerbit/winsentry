"""
Main entry point for WinSentry application
"""

import asyncio
import logging
import sys
from tornado import web, ioloop
from tornado.options import define, options, parse_command_line


# Try absolute imports first (when installed as package)
from winsentry.app import WinSentryApplication
from winsentry.service_manager import ServiceManager
from winsentry.port_monitor import PortMonitor
from winsentry.logger import setup_logging


define("port", default=8888, help="Port to run the server on", type=int)
define("debug", default=False, help="Enable debug mode", type=bool)


def main():
    """Main entry point"""
    parse_command_line()
    
    # Setup logging
    setup_logging(debug=options.debug)
    logger = logging.getLogger(__name__)
    
    try:
        # Initialize managers
        service_manager = ServiceManager()
        port_monitor = PortMonitor()
        
        # Create application
        app = WinSentryApplication(service_manager, port_monitor)
        
        # Start the server
        logger.info(f"Starting WinSentry on port {options.port}")
        app.listen(options.port)
        
        # Start the event loop
        loop = ioloop.IOLoop.current()
        
        # Start port monitoring as a background task
        def start_monitoring_task():
            asyncio.create_task(port_monitor.start_monitoring())
        
        # Schedule the monitoring task to start after the loop begins
        loop.add_callback(start_monitoring_task)
        
        # Start the event loop
        loop.start()
        
    except KeyboardInterrupt:
        logger.info("Shutting down WinSentry...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Failed to start WinSentry: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
