"""
WinSentry Windows Service
This module allows WinSentry to run as a native Windows service.
"""

import sys
import os
import time
import asyncio
import logging
import servicemanager
import win32event
import win32service
import win32serviceutil


class WinSentryService(win32serviceutil.ServiceFramework):
    """Windows Service wrapper for WinSentry"""
    
    _svc_name_ = "WinSentry"
    _svc_display_name_ = "WinSentry Monitoring Service"
    _svc_description_ = "WinSentry - Windows Port, Service, and Resource Monitoring Tool"
    
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.running = False
        self.logger = self._setup_logging()
        
    def _setup_logging(self):
        """Setup logging for the service"""
        # Get the directory where the service is installed
        service_dir = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(service_dir, 'logs')
        
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        log_file = os.path.join(log_dir, 'winsentry-service.log')
        
        logger = logging.getLogger('WinSentryService')
        logger.setLevel(logging.INFO)
        
        # File handler
        handler = logging.FileHandler(log_file)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(handler)
        
        return logger
    
    def SvcStop(self):
        """Called when the service is asked to stop"""
        self.logger.info("Service stop requested")
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        self.running = False
    
    def SvcDoRun(self):
        """Called when the service is asked to start"""
        self.logger.info("Service starting...")
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        self.running = True
        self.main()
    
    def main(self):
        """Main service loop"""
        try:
            # Add the project directory to the path
            service_dir = os.path.dirname(os.path.abspath(__file__))
            if service_dir not in sys.path:
                sys.path.insert(0, service_dir)
            
            self.logger.info(f"Service directory: {service_dir}")
            self.logger.info(f"Python path: {sys.path}")
            
            # Import WinSentry components
            from winsentry.app import WinSentryApplication
            from winsentry.service_manager import ServiceManager
            from winsentry.port_monitor import PortMonitor
            from winsentry.service_monitor import ServiceMonitor
            from winsentry.system_resource_monitor import SystemResourceMonitor
            from winsentry.logger import setup_logging
            
            # Setup logging
            setup_logging(debug=False)
            
            # Get port from environment or default
            port = int(os.environ.get('WINSENTRY_PORT', 8888))
            
            self.logger.info(f"Starting WinSentry on port {port}")
            
            # Initialize managers
            service_manager = ServiceManager()
            port_monitor = PortMonitor()
            service_monitor_instance = ServiceMonitor()
            resource_monitor = SystemResourceMonitor()
            
            # Create application
            app = WinSentryApplication(
                service_manager,
                port_monitor,
                service_monitor_instance,
                resource_monitor
            )
            
            # Start the server
            app.listen(port)
            self.logger.info(f"WinSentry listening on port {port}")
            
            # Create event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Start monitoring tasks
            async def start_monitoring():
                await asyncio.gather(
                    port_monitor.start_monitoring(),
                    service_monitor_instance.start_monitoring(),
                    resource_monitor.start_monitoring()
                )
            
            # Create monitoring task
            monitoring_task = loop.create_task(start_monitoring())
            
            # Run until stop is requested
            while self.running:
                # Check for stop event (non-blocking)
                result = win32event.WaitForSingleObject(self.stop_event, 100)
                if result == win32event.WAIT_OBJECT_0:
                    break
                
                # Run pending asyncio tasks
                loop.run_until_complete(asyncio.sleep(0.1))
            
            # Cleanup
            self.logger.info("Stopping monitoring tasks...")
            monitoring_task.cancel()
            
            try:
                loop.run_until_complete(monitoring_task)
            except asyncio.CancelledError:
                pass
            
            loop.close()
            
            self.logger.info("Service stopped successfully")
            
        except Exception as e:
            self.logger.error(f"Service error: {e}", exc_info=True)
            servicemanager.LogErrorMsg(f"WinSentry service error: {e}")


def install_service():
    """Install the service"""
    try:
        win32serviceutil.InstallService(
            WinSentryService._svc_name_,
            WinSentryService._svc_display_name_,
            startType=win32service.SERVICE_AUTO_START,
            description=WinSentryService._svc_description_
        )
        print(f"Service '{WinSentryService._svc_name_}' installed successfully.")
        print("Use 'sc start WinSentry' to start the service.")
    except Exception as e:
        print(f"Failed to install service: {e}")


def remove_service():
    """Remove the service"""
    try:
        win32serviceutil.RemoveService(WinSentryService._svc_name_)
        print(f"Service '{WinSentryService._svc_name_}' removed successfully.")
    except Exception as e:
        print(f"Failed to remove service: {e}")


if __name__ == '__main__':
    if len(sys.argv) == 1:
        # Running as service
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(WinSentryService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        # Handle command line arguments
        win32serviceutil.HandleCommandLine(WinSentryService)
