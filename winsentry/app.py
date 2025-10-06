"""
Tornado web application for WinSentry
"""


from tornado import web


try:
    # Try absolute imports first (when installed as package)
           from winsentry.handlers import (
               MainHandler,
               EmailConfigPageHandler,
               ServicesHandler,
               ServiceActionHandler,
               PortMonitorHandler,
               PortConfigHandler,
               PortKillHandler,
               PortForceKillHandler,
               DatabaseStatsHandler,
               EmailConfigHandler,
               EmailTemplateHandler,
               PortEmailConfigHandler,
               EmailTestHandler,
               PowerShellExecuteHandler,
               ServiceConfigHandler,
               LogsHandler,
               ServiceMonitorHandler,
               ServiceMonitorConfigHandler,
               ServiceEmailConfigHandler,
               PortProcessHandler,
               PortResourceSummaryHandler,
               PortThresholdHandler,
               PortThresholdCheckHandler,
               ProcessLogsHandler,
               ServiceProcessHandler,
               ServiceResourceSummaryHandler,
               ServiceThresholdHandler,
               ServiceThresholdCheckHandler,
               ServiceProcessLogsHandler
           )
except ImportError:
    # Fall back to relative imports (when running directly)
    from .handlers import (
        MainHandler,
        EmailConfigPageHandler,
        ServicesHandler,
        ServiceActionHandler,
        PortMonitorHandler,
        PortConfigHandler,
        PortKillHandler,
        PortForceKillHandler,
        DatabaseStatsHandler,
        EmailConfigHandler,
        EmailTemplateHandler,
        PortEmailConfigHandler,
        EmailTestHandler,
        PowerShellExecuteHandler,
        ServiceConfigHandler,
        LogsHandler,
        ServiceMonitorHandler,
        ServiceMonitorConfigHandler,
        ServiceEmailConfigHandler,
        PortProcessHandler,
        PortResourceSummaryHandler,
        PortThresholdHandler,
        PortThresholdCheckHandler,
        ProcessLogsHandler,
        ServiceProcessHandler,
        ServiceResourceSummaryHandler,
        ServiceThresholdHandler,
        ServiceThresholdCheckHandler,
        ServiceProcessLogsHandler
    )


class WinSentryApplication(web.Application):
    """Main Tornado application"""
    
    def __init__(self, service_manager, port_monitor, service_monitor):
        self.service_manager = service_manager
        self.port_monitor = port_monitor
        self.service_monitor = service_monitor
        
        handlers = [
            (r"/", MainHandler),
            (r"/email-config", EmailConfigPageHandler),
            (r"/api/services", ServicesHandler, dict(service_manager=service_manager)),
            (r"/api/services/([^/]+)/(start|stop|restart)", ServiceActionHandler, dict(service_manager=service_manager)),
            (r"/api/ports", PortMonitorHandler, dict(port_monitor=port_monitor)),
            (r"/api/ports/config", PortConfigHandler, dict(port_monitor=port_monitor)),
            (r"/api/ports/kill", PortKillHandler, dict(port_monitor=port_monitor)),
            (r"/api/ports/force-kill", PortForceKillHandler, dict(port_monitor=port_monitor)),
            (r"/api/ports/processes", PortProcessHandler, dict(port_monitor=port_monitor)),
            (r"/api/ports/resource-summary", PortResourceSummaryHandler, dict(port_monitor=port_monitor)),
            (r"/api/ports/thresholds", PortThresholdHandler, dict(port_monitor=port_monitor)),
            (r"/api/ports/threshold-check", PortThresholdCheckHandler, dict(port_monitor=port_monitor)),
            (r"/api/process-logs", ProcessLogsHandler, dict(port_monitor=port_monitor)),
            (r"/api/database/stats", DatabaseStatsHandler, dict(port_monitor=port_monitor)),
            (r"/api/email/config", EmailConfigHandler, dict(port_monitor=port_monitor)),
            (r"/api/email/templates", EmailTemplateHandler, dict(port_monitor=port_monitor)),
            (r"/api/email/port-config", PortEmailConfigHandler, dict(port_monitor=port_monitor)),
            (r"/api/email/test", EmailTestHandler, dict(port_monitor=port_monitor)),
            (r"/api/powershell/execute", PowerShellExecuteHandler, dict(port_monitor=port_monitor)),
            (r"/api/service-config", ServiceConfigHandler, dict(service_manager=service_manager)),
            (r"/api/service-monitor", ServiceMonitorHandler, dict(service_monitor=service_monitor)),
            (r"/api/service-monitor/config", ServiceMonitorConfigHandler, dict(service_monitor=service_monitor)),
            (r"/api/service-monitor/email-config", ServiceEmailConfigHandler, dict(service_monitor=service_monitor)),
            (r"/api/service-monitor/processes", ServiceProcessHandler, dict(service_monitor=service_monitor)),
            (r"/api/service-monitor/resource-summary", ServiceResourceSummaryHandler, dict(service_monitor=service_monitor)),
            (r"/api/service-monitor/thresholds", ServiceThresholdHandler, dict(service_monitor=service_monitor)),
            (r"/api/service-monitor/threshold-check", ServiceThresholdCheckHandler, dict(service_monitor=service_monitor)),
            (r"/api/service-process-logs", ServiceProcessLogsHandler, dict(service_monitor=service_monitor)),
            (r"/api/logs", LogsHandler),
               (r"/static/(.*)", web.StaticFileHandler, {"path": "winsentry/static"}),
        ]
        
        settings = {
            "debug": True,
            "template_path": "winsentry/templates",
            "static_path": "winsentry/static",
            "autoescape": None,
        }
        
        super().__init__(handlers, **settings)
        
        # Make managers available to handlers
        self.service_manager = service_manager
        self.port_monitor = port_monitor
