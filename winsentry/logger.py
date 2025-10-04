"""
Logging configuration for WinSentry
"""

import logging
import logging.handlers
import os
from datetime import datetime


def setup_logging(debug=False):
    """Setup logging configuration"""
    
    # Create logs directory if it doesn't exist
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO if not debug else logging.DEBUG)
    console_handler.setFormatter(simple_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler for general logs
    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, 'winsentry.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(file_handler)
    
    # File handler for port monitoring logs
    port_monitor_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, 'port_monitor.log'),
        maxBytes=5*1024*1024,  # 5MB
        backupCount=3
    )
    port_monitor_handler.setLevel(logging.INFO)
    port_monitor_handler.setFormatter(detailed_formatter)
    
    # Create port monitor logger
    port_logger = logging.getLogger('port_monitor')
    port_logger.addHandler(port_monitor_handler)
    port_logger.setLevel(logging.INFO)
    port_logger.propagate = False  # Don't propagate to root logger
    
    # File handler for service management logs
    service_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, 'service_manager.log'),
        maxBytes=5*1024*1024,  # 5MB
        backupCount=3
    )
    service_handler.setLevel(logging.INFO)
    service_handler.setFormatter(detailed_formatter)
    
    # Create service manager logger
    service_logger = logging.getLogger('service_manager')
    service_logger.addHandler(service_handler)
    service_logger.setLevel(logging.INFO)
    service_logger.propagate = False  # Don't propagate to root logger
    
    # Suppress some noisy loggers
    logging.getLogger('tornado.access').setLevel(logging.WARNING)
    logging.getLogger('tornado.application').setLevel(logging.WARNING)
    logging.getLogger('tornado.general').setLevel(logging.WARNING)


class PortMonitorLogger:
    """Specialized logger for port monitoring events"""
    
    def __init__(self):
        self.logger = logging.getLogger('port_monitor')
    
    def log_port_failure(self, port: int, failure_count: int, powershell_script: str = None):
        """Log when a port monitoring fails"""
        message = f"Port {port} is offline (failure #{failure_count})"
        if powershell_script:
            message += f" - Executing recovery script: {powershell_script}"
        
        self.logger.warning(message)
    
    def log_port_recovery(self, port: int):
        """Log when a port comes back online"""
        self.logger.info(f"Port {port} is back online")
    
    def log_script_execution(self, port: int, script_path: str, success: bool):
        """Log PowerShell script execution"""
        status = "successful" if success else "failed"
        self.logger.info(f"Recovery script for port {port} execution {status}: {script_path}")
    
    def log_port_added(self, port: int, interval: int, script: str = None):
        """Log when a port is added to monitoring"""
        message = f"Added port {port} to monitoring (interval: {interval}s)"
        if script:
            message += f" with recovery script: {script}"
        self.logger.info(message)
    
    def log_port_removed(self, port: int):
        """Log when a port is removed from monitoring"""
        self.logger.info(f"Removed port {port} from monitoring")


class ServiceManagerLogger:
    """Specialized logger for service management events"""
    
    def __init__(self):
        self.logger = logging.getLogger('service_manager')
    
    def log_service_action(self, service_name: str, action: str, success: bool):
        """Log service management actions"""
        status = "successful" if success else "failed"
        self.logger.info(f"Service {action} for '{service_name}' {status}")
    
    def log_service_status_change(self, service_name: str, old_status: str, new_status: str):
        """Log service status changes"""
        self.logger.info(f"Service '{service_name}' status changed: {old_status} -> {new_status}")
