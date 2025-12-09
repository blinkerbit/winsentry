"""
WinSentry - Windows Service and Port Monitoring Tool

A comprehensive monitoring solution for Windows systems providing:
- Python Application Monitoring (with auto-restart)
- Windows Service Monitoring
- Port Monitoring
- Scheduled Task/Script Execution
- System Resource Monitoring (CPU, RAM, Disk)
- Email Alerting
"""

__version__ = "1.0.0"
__author__ = "WinSentry Team"

from .database import Database
from .port_monitor import PortMonitor
from .service_monitor import ServiceMonitor
from .service_manager import ServiceManager
from .email_alert import EmailAlert
from .python_app_monitor import PythonAppMonitor
from .system_resource_monitor import SystemResourceMonitor
from .scheduled_task_manager import ScheduledTaskManager

__all__ = [
    'Database',
    'PortMonitor',
    'ServiceMonitor',
    'ServiceManager',
    'EmailAlert',
    'PythonAppMonitor',
    'SystemResourceMonitor',
    'ScheduledTaskManager',
]
