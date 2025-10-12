"""WinSentry - Windows System Monitoring & Alerting Tool"""

__version__ = "0.1.0"
__author__ = "WinSentry Team"
__description__ = "Windows system monitoring & alerting tool with web UI"

from .database import DatabaseManager
from .models import (
    MonitoredPort,
    MonitoredProcess,
    MonitoredService,
    SystemMonitoring,
    AlertRule,
    EmailTemplate,
    EmailServer,
    ScriptConfig,
    Recipient,
)

__all__ = [
    "__version__",
    "DatabaseManager",
    "MonitoredPort",
    "MonitoredProcess",
    "MonitoredService",
    "SystemMonitoring",
    "AlertRule",
    "EmailTemplate",
    "EmailServer",
    "ScriptConfig",
    "Recipient",
]

