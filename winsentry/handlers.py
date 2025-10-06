"""
Tornado request handlers for WinSentry API
"""

import json
import logging

from tornado.web import RequestHandler


logger = logging.getLogger(__name__)


class BaseHandler(RequestHandler):
    """Base handler with common functionality"""
    
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
        self.set_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
    
    def options(self):
        self.set_status(204)
        self.finish()
    
    def write_json(self, data, status=200):
        self.set_status(status)
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(data, default=str))


class MainHandler(BaseHandler):
    """Main page handler"""
    
    async def get(self):
        self.render("index.html")


class EmailConfigPageHandler(BaseHandler):
    """Email configuration page handler"""
    
    async def get(self):
        self.render("email_config.html")


class ServicesHandler(BaseHandler):
    """Handle service-related requests"""
    
    def initialize(self, service_manager):
        self.service_manager = service_manager
    
    async def get(self):
        """Get list of all services"""
        try:
            services = await self.service_manager.get_services()
            self.write_json({
                'success': True,
                'services': services
            })
        except Exception as e:
            logger.error(f"Failed to get services: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class ServiceActionHandler(BaseHandler):
    """Handle service actions (start, stop, restart)"""
    
    def initialize(self, service_manager):
        self.service_manager = service_manager
    
    async def post(self, service_name, action):
        """Execute service action"""
        try:
            if action == "start":
                result = await self.service_manager.start_service(service_name)
            elif action == "stop":
                result = await self.service_manager.stop_service(service_name)
            elif action == "restart":
                result = await self.service_manager.restart_service(service_name)
            else:
                self.write_json({
                    'success': False,
                    'error': f"Invalid action: {action}"
                }, 400)
                return
            
            self.write_json(result)
            
        except Exception as e:
            logger.error(f"Failed to {action} service {service_name}: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class PortMonitorHandler(BaseHandler):
    """Handle port monitoring requests"""
    
    def initialize(self, port_monitor):
        self.port_monitor = port_monitor
    
    async def get(self):
        """Get list of monitored ports"""
        try:
            ports = self.port_monitor.get_monitored_ports()
            self.write_json({
                'success': True,
                'ports': ports
            })
        except Exception as e:
            logger.error(f"Failed to get monitored ports: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)
    
    async def post(self):
        """Add a new port to monitor"""
        try:
            data = json.loads(self.request.body)
            port = int(data.get('port'))
            interval = int(data.get('interval', 30))
            powershell_script = data.get('powershell_script')
            powershell_commands = data.get('powershell_commands')
            
            # Validate port number
            if port < 1 or port > 65535:
                self.write_json({
                    'success': False,
                    'error': 'Port number must be between 1 and 65535'
                }, 400)
                return
            
            # Validate interval
            if interval < 5 or interval > 3600:
                self.write_json({
                    'success': False,
                    'error': 'Check interval must be between 5 and 3600 seconds'
                }, 400)
                return
            
            success = await self.port_monitor.add_port(port, interval, powershell_script, powershell_commands)
            
            if success:
                message = f"Port {port} added to monitoring with interval {interval}s"
                if powershell_script:
                    message += f" and PowerShell script: {powershell_script}"
                if powershell_commands:
                    message += f" and PowerShell commands configured"
            else:
                message = f"Failed to add port {port} to monitoring"
                if powershell_script:
                    message += " - PowerShell script validation failed"
            
            self.write_json({
                'success': success,
                'message': message
            })
            
        except ValueError as e:
            self.write_json({
                'success': False,
                'error': f"Invalid input: {str(e)}"
            }, 400)
        except Exception as e:
            logger.error(f"Failed to add port: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)
    
    async def delete(self):
        """Remove a port from monitoring"""
        try:
            data = json.loads(self.request.body)
            port = int(data.get('port'))
            
            success = await self.port_monitor.remove_port(port)
            
            self.write_json({
                'success': success,
                'message': f"Port {port} {'removed' if success else 'not found'} from monitoring"
            })
            
        except Exception as e:
            logger.error(f"Failed to remove port: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class PortConfigHandler(BaseHandler):
    """Handle port configuration updates"""
    
    def initialize(self, port_monitor):
        self.port_monitor = port_monitor
    
    async def get(self):
        """Get port configuration"""
        try:
            port = int(self.get_argument('port'))
            config = self.port_monitor.db.get_port_config(port)
            
            if config:
                self.write_json({
                    'success': True,
                    'config': config
                })
            else:
                self.write_json({
                    'success': False,
                    'error': f'Port {port} configuration not found'
                })
                
        except Exception as e:
            logger.error(f"Failed to get port config: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)
    
    async def post(self):
        """Save port configuration"""
        try:
            data = json.loads(self.request.body)
            port = int(data.get('port'))
            interval = data.get('interval')
            powershell_script = data.get('powershell_script')
            powershell_commands = data.get('powershell_commands')
            enabled = data.get('enabled')
            
            # Check if port exists, if not create it, if yes update it
            if port in self.port_monitor.monitored_ports:
                # Update existing port
                success = await self.port_monitor.update_port_config(
                    port, interval, powershell_script, powershell_commands, enabled
                )
                message = f"Port {port} configuration {'updated' if success else 'failed to update'}"
            else:
                # Add new port
                success = await self.port_monitor.add_port(
                    port, interval, powershell_script, powershell_commands
                )
                if success and enabled is not None:
                    await self.port_monitor.update_port_config(port, enabled=enabled)
                message = f"Port {port} configuration {'saved' if success else 'failed to save'}"
            
            self.write_json({
                'success': success,
                'message': message
            })
            
        except Exception as e:
            logger.error(f"Failed to save port config: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)
    
    async def put(self):
        """Update port configuration"""
        try:
            data = json.loads(self.request.body)
            port = int(data.get('port'))
            interval = data.get('interval')
            powershell_script = data.get('powershell_script')
            powershell_commands = data.get('powershell_commands')
            enabled = data.get('enabled')
            
            success = await self.port_monitor.update_port_config(
                port, interval, powershell_script, powershell_commands, enabled
            )
            
            self.write_json({
                'success': success,
                'message': f"Port {port} configuration {'updated' if success else 'failed to update'}"
            })
            
        except Exception as e:
            logger.error(f"Failed to update port config: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class LogsHandler(BaseHandler):
    """Handle log requests"""
    
    async def get(self):
        """Get monitoring logs"""
        try:
            port = self.get_argument('port', None)
            port = int(port) if port else None
            
            # Get logs from port monitor
            app = self.application
            logs = app.port_monitor.get_port_logs(port)
            
            self.write_json({
                'success': True,
                'logs': logs
            })
            
        except Exception as e:
            logger.error(f"Failed to get logs: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class PortKillHandler(BaseHandler):
    """Handle killing processes on specific ports"""
    
    def initialize(self, port_monitor):
        self.port_monitor = port_monitor
    
    async def post(self):
        """Kill process using a specific port"""
        try:
            data = json.loads(self.request.body)
            port = int(data.get('port'))
            
            # Get processes using the port
            processes = await self.port_monitor.get_processes_on_port(port)
            
            if not processes:
                self.write_json({
                    'success': False,
                    'message': f'No processes found using port {port}'
                })
                return
            
            killed_count = 0
            for process in processes:
                try:
                    await self.port_monitor.kill_process(process['pid'])
                    killed_count += 1
                    logger.info(f"Killed process {process['pid']} ({process['name']}) using port {port}")
                except Exception as e:
                    logger.error(f"Failed to kill process {process['pid']}: {e}")
            
            self.write_json({
                'success': True,
                'message': f'Killed {killed_count} process(es) using port {port}'
            })
            
        except Exception as e:
            logger.error(f"Failed to kill processes on port: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class PortForceKillHandler(BaseHandler):
    """Handle force killing all processes on specific ports"""
    
    def initialize(self, port_monitor):
        self.port_monitor = port_monitor
    
    async def post(self):
        """Force kill all processes using a specific port"""
        try:
            data = json.loads(self.request.body)
            port = int(data.get('port'))
            
            # Get all processes using the port
            processes = await self.port_monitor.get_processes_on_port(port)
            
            if not processes:
                self.write_json({
                    'success': False,
                    'message': f'No processes found using port {port}'
                })
                return
            
            killed_count = 0
            for process in processes:
                try:
                    await self.port_monitor.force_kill_process(process['pid'])
                    killed_count += 1
                    logger.info(f"Force killed process {process['pid']} ({process['name']}) using port {port}")
                except Exception as e:
                    logger.error(f"Failed to force kill process {process['pid']}: {e}")
            
            self.write_json({
                'success': True,
                'message': f'Force killed {killed_count} process(es) using port {port}'
            })
            
        except Exception as e:
            logger.error(f"Failed to force kill processes on port: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class DatabaseStatsHandler(BaseHandler):
    """Handle database statistics requests"""
    
    def initialize(self, port_monitor):
        self.port_monitor = port_monitor
    
    async def get(self):
        """Get database statistics"""
        try:
            stats = self.port_monitor.get_database_stats()
            self.write_json({
                'success': True,
                'stats': stats
            })
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)
    
    async def post(self):
        """Clean up old logs"""
        try:
            data = json.loads(self.request.body)
            days = int(data.get('days', 30))
            
            cleaned_count = self.port_monitor.cleanup_old_logs(days)
            
            self.write_json({
                'success': True,
                'message': f'Cleaned up {cleaned_count} old log entries',
                'cleaned_count': cleaned_count
            })
            
        except Exception as e:
            logger.error(f"Failed to cleanup logs: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class EmailConfigHandler(BaseHandler):
    """Handle email configuration requests"""
    
    def initialize(self, port_monitor):
        self.port_monitor = port_monitor
    
    async def get(self):
        """Get SMTP configuration"""
        try:
            smtp_config = self.port_monitor.email_alert.get_smtp_config()
            # Don't return password for security
            if 'smtp_password' in smtp_config:
                smtp_config['smtp_password'] = '***' if smtp_config['smtp_password'] else ''
            
            self.write_json({
                'success': True,
                'smtp_config': smtp_config
            })
        except Exception as e:
            logger.error(f"Failed to get SMTP config: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)
    
    async def post(self):
        """Update SMTP configuration"""
        try:
            data = json.loads(self.request.body)
            success = self.port_monitor.email_alert.update_smtp_config(data)
            
            self.write_json({
                'success': success,
                'message': 'SMTP configuration updated' if success else 'Failed to update SMTP configuration'
            })
        except Exception as e:
            logger.error(f"Failed to update SMTP config: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class EmailTemplateHandler(BaseHandler):
    """Handle email template requests"""
    
    def initialize(self, port_monitor):
        self.port_monitor = port_monitor
    
    async def get(self):
        """Get all email templates"""
        try:
            templates = self.port_monitor.email_alert.get_email_templates()
            self.write_json({
                'success': True,
                'templates': templates
            })
        except Exception as e:
            logger.error(f"Failed to get email templates: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)
    
    async def post(self):
        """Add or update email template"""
        try:
            data = json.loads(self.request.body)
            template_name = data.get('template_name')
            subject = data.get('subject')
            body = data.get('body')
            
            if not template_name or not subject or not body:
                self.write_json({
                    'success': False,
                    'error': 'Template name, subject, and body are required'
                }, 400)
                return
            
            success = self.port_monitor.email_alert.add_email_template(template_name, subject, body)
            
            self.write_json({
                'success': success,
                'message': f'Template {template_name} {"added" if success else "failed to add"}'
            })
        except Exception as e:
            logger.error(f"Failed to add email template: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)
    
    async def delete(self):
        """Delete email template"""
        try:
            data = json.loads(self.request.body)
            template_name = data.get('template_name')
            
            if not template_name:
                self.write_json({
                    'success': False,
                    'error': 'Template name is required'
                }, 400)
                return
            
            success = self.port_monitor.email_alert.delete_email_template(template_name)
            
            self.write_json({
                'success': success,
                'message': f'Template {template_name} {"deleted" if success else "not found"}'
            })
        except Exception as e:
            logger.error(f"Failed to delete email template: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class PortEmailConfigHandler(BaseHandler):
    """Handle port-specific email configuration"""
    
    def initialize(self, port_monitor):
        self.port_monitor = port_monitor
    
    async def get(self):
        """Get email configuration for a specific port or all ports"""
        try:
            if 'port' in self.request.arguments:
                # Get specific port configuration
                port = int(self.get_argument('port'))
                config = self.port_monitor.email_alert.get_port_email_config(port)
                
                self.write_json({
                    'success': True,
                    'config': config
                })
            else:
                # Get all port configurations
                configs = self.port_monitor.email_alert.get_all_port_email_configs()
                
                self.write_json({
                    'success': True,
                    'configs': configs
                })
        except Exception as e:
            logger.error(f"Failed to get port email config: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)
    
    async def post(self):
        """Save email configuration for a specific port"""
        try:
            data = json.loads(self.request.body)
            port = int(data.get('port'))
            config = data.get('config', {})
            
            success = self.port_monitor.email_alert.save_port_email_config(port, config)
            
            self.write_json({
                'success': success,
                'message': f'Email configuration for port {port} {"saved" if success else "failed to save"}'
            })
        except Exception as e:
            logger.error(f"Failed to save port email config: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)
    
    async def delete(self):
        """Delete email configuration for a specific port"""
        try:
            data = json.loads(self.request.body)
            port = int(data.get('port'))
            
            success = self.port_monitor.email_alert.delete_port_email_config(port)
            
            self.write_json({
                'success': success,
                'message': f'Email configuration for port {port} {"deleted" if success else "not found"}'
            })
        except Exception as e:
            logger.error(f"Failed to delete port email config: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class EmailTestHandler(BaseHandler):
    """Handle email testing"""
    
    def initialize(self, port_monitor):
        self.port_monitor = port_monitor
    
    async def post(self):
        """Test SMTP connection and send test email"""
        try:
            data = json.loads(self.request.body)
            test_type = data.get('type', 'connection')
            
            if test_type == 'connection':
                # Test SMTP connection
                result = self.port_monitor.email_alert.test_smtp_connection()
                self.write_json(result)
            elif test_type == 'email':
                # Send test email
                recipients = data.get('recipients', [])
                if not recipients:
                    self.write_json({
                        'success': False,
                        'error': 'Recipients are required for test email'
                    })
                    return
                
                success = await self.port_monitor.email_alert.send_alert_email(
                    port=9999,  # Test port
                    recipients=recipients,
                    template_name="default",
                    custom_data={
                        "failure_count": 1,
                        "message": "This is a test email from WinSentry"
                    }
                )
                
                self.write_json({
                    'success': success,
                    'message': 'Test email sent successfully' if success else 'Failed to send test email'
                })
            else:
                self.write_json({
                    'success': False,
                    'error': 'Invalid test type'
                })
        except Exception as e:
            logger.error(f"Failed to test email: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class PowerShellExecuteHandler(BaseHandler):
    """Handle PowerShell command execution"""
    
    def initialize(self, port_monitor):
        self.port_monitor = port_monitor
    
    async def post(self):
        """Execute PowerShell commands and return output"""
        try:
            data = json.loads(self.request.body)
            commands = data.get('commands', '')
            port = data.get('port', 9999)
            
            if not commands.strip():
                self.write_json({
                    'success': False,
                    'error': 'No PowerShell commands provided'
                })
                return
            
            # Execute PowerShell commands
            result = await self.port_monitor.execute_powershell_commands(commands, port)
            
            self.write_json({
                'success': result['success'],
                'stdout': result['stdout'],
                'stderr': result['stderr'],
                'exit_code': result['exit_code'],
                'execution_time': result['execution_time'],
                'error': result.get('error')
            })
            
        except Exception as e:
            logger.error(f"Failed to execute PowerShell commands: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class ServiceConfigHandler(BaseHandler):
    """Handle service configuration"""
    
    def initialize(self, service_manager):
        self.service_manager = service_manager
    
    async def get(self):
        """Get current service configuration"""
        try:
            config = self.service_manager.get_service_config()
            self.write_json({
                'success': True,
                'config': config
            })
        except Exception as e:
            logger.error(f"Failed to get service config: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)
    
    async def post(self):
        """Update service configuration"""
        try:
            data = json.loads(self.request.body)
            
            load_all_services = data.get('load_all_services')
            disable_auto_refresh = data.get('disable_auto_refresh')
            watched_services = data.get('watched_services', [])
            excluded_services = data.get('excluded_services', [])
            
            self.service_manager.update_service_config(
                load_all_services=load_all_services,
                disable_auto_refresh=disable_auto_refresh,
                watched_services=watched_services,
                excluded_services=excluded_services
            )
            
            self.write_json({
                'success': True,
                'message': 'Service configuration updated successfully',
                'config': self.service_manager.get_service_config()
            })
            
        except Exception as e:
            logger.error(f"Failed to update service config: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class ServiceMonitorHandler(BaseHandler):
    """Handle service monitoring requests"""
    
    def initialize(self, service_monitor):
        self.service_monitor = service_monitor
    
    async def get(self):
        """Get monitored services"""
        try:
            services = self.service_monitor.get_monitored_services()
            self.write_json({
                'success': True,
                'services': services
            })
        except Exception as e:
            logger.error(f"Failed to get monitored services: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class ServiceMonitorConfigHandler(BaseHandler):
    """Handle service monitoring configuration"""
    
    def initialize(self, service_monitor):
        self.service_monitor = service_monitor
    
    async def post(self):
        """Add or update service monitoring configuration"""
        try:
            data = json.loads(self.request.body)
            
            service_name = data.get('service_name')
            interval = data.get('interval', 30)
            powershell_script = data.get('powershell_script')
            powershell_commands = data.get('powershell_commands')
            
            if not service_name:
                self.write_json({
                    'success': False,
                    'error': 'Service name is required'
                }, 400)
                return
            
            # Validate interval
            if not isinstance(interval, int) or interval < 5:
                self.write_json({
                    'success': False,
                    'error': 'Interval must be an integer >= 5 seconds'
                }, 400)
                return
            
            success = await self.service_monitor.add_service(
                service_name=service_name,
                interval=interval,
                powershell_script=powershell_script,
                powershell_commands=powershell_commands
            )
            
            if success:
                self.write_json({
                    'success': True,
                    'message': f'Service {service_name} added to monitoring'
                })
            else:
                self.write_json({
                    'success': False,
                    'error': f'Failed to add service {service_name} to monitoring'
                }, 500)
                
        except Exception as e:
            logger.error(f"Failed to configure service monitoring: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)
    
    async def put(self):
        """Update service monitoring configuration"""
        try:
            data = json.loads(self.request.body)
            
            service_name = data.get('service_name')
            interval = data.get('interval')
            powershell_script = data.get('powershell_script')
            powershell_commands = data.get('powershell_commands')
            enabled = data.get('enabled')
            
            if not service_name:
                self.write_json({
                    'success': False,
                    'error': 'Service name is required'
                }, 400)
                return
            
            success = await self.service_monitor.update_service_config(
                service_name=service_name,
                interval=interval,
                powershell_script=powershell_script,
                powershell_commands=powershell_commands,
                enabled=enabled
            )
            
            if success:
                self.write_json({
                    'success': True,
                    'message': f'Service {service_name} configuration updated'
                })
            else:
                self.write_json({
                    'success': False,
                    'error': f'Failed to update service {service_name} configuration'
                }, 500)
                
        except Exception as e:
            logger.error(f"Failed to update service monitoring: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)
    
    async def delete(self):
        """Remove service from monitoring"""
        try:
            service_name = self.get_argument('service_name')
            
            if not service_name:
                self.write_json({
                    'success': False,
                    'error': 'Service name is required'
                }, 400)
                return
            
            success = await self.service_monitor.remove_service(service_name)
            
            if success:
                self.write_json({
                    'success': True,
                    'message': f'Service {service_name} removed from monitoring'
                })
            else:
                self.write_json({
                    'success': False,
                    'error': f'Failed to remove service {service_name} from monitoring'
                }, 500)
                
        except Exception as e:
            logger.error(f"Failed to remove service monitoring: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class ServiceEmailConfigHandler(BaseHandler):
    """Handle service email configuration"""
    
    def initialize(self, service_monitor):
        self.service_monitor = service_monitor
    
    async def get(self):
        """Get service email configuration"""
        try:
            service_name = self.get_argument('service_name')
            
            if not service_name:
                self.write_json({
                    'success': False,
                    'error': 'Service name is required'
                }, 400)
                return
            
            config = self.service_monitor.email_alert.get_service_email_config(service_name)
            self.write_json({
                'success': True,
                'config': config
            })
            
        except Exception as e:
            logger.error(f"Failed to get service email config: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)
    
    async def post(self):
        """Save service email configuration"""
        try:
            data = json.loads(self.request.body)
            
            service_name = data.get('service_name')
            config = data.get('config', {})
            
            if not service_name:
                self.write_json({
                    'success': False,
                    'error': 'Service name is required'
                }, 400)
                return
            
            success = self.service_monitor.email_alert.save_service_email_config(service_name, config)
            
            if success:
                self.write_json({
                    'success': True,
                    'message': f'Email configuration saved for service {service_name}'
                })
            else:
                self.write_json({
                    'success': False,
                    'error': f'Failed to save email configuration for service {service_name}'
                }, 500)
                
        except Exception as e:
            logger.error(f"Failed to save service email config: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)
    
    async def delete(self):
        """Delete service email configuration"""
        try:
            service_name = self.get_argument('service_name')
            
            if not service_name:
                self.write_json({
                    'success': False,
                    'error': 'Service name is required'
                }, 400)
                return
            
            success = self.service_monitor.email_alert.delete_service_email_config(service_name)
            
            if success:
                self.write_json({
                    'success': True,
                    'message': f'Email configuration deleted for service {service_name}'
                })
            else:
                self.write_json({
                    'success': False,
                    'error': f'Failed to delete email configuration for service {service_name}'
                }, 500)
                
        except Exception as e:
            logger.error(f"Failed to delete service email config: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class PortProcessHandler(BaseHandler):
    """Handle port process monitoring requests"""
    
    def initialize(self, port_monitor):
        self.port_monitor = port_monitor
    
    async def get(self):
        """Get processes on a specific port"""
        try:
            port = int(self.get_argument('port'))
            
            processes = await self.port_monitor.get_processes_on_port(port)
            
            self.write_json({
                'success': True,
                'port': port,
                'processes': processes,
                'process_count': len(processes)
            })
            
        except ValueError:
            self.write_json({
                'success': False,
                'error': 'Invalid port number'
            }, 400)
        except Exception as e:
            logger.error(f"Failed to get processes for port: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class PortResourceSummaryHandler(BaseHandler):
    """Handle port resource summary requests"""
    
    def initialize(self, port_monitor):
        self.port_monitor = port_monitor
    
    async def get(self):
        """Get comprehensive resource summary for a port"""
        try:
            port = int(self.get_argument('port'))
            
            summary = await self.port_monitor.get_port_resource_summary(port)
            
            self.write_json({
                'success': True,
                'summary': summary
            })
            
        except ValueError:
            self.write_json({
                'success': False,
                'error': 'Invalid port number'
            }, 400)
        except Exception as e:
            logger.error(f"Failed to get resource summary for port: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class PortThresholdHandler(BaseHandler):
    """Handle port resource threshold configuration"""
    
    def initialize(self, port_monitor):
        self.port_monitor = port_monitor
    
    async def get(self):
        """Get port resource thresholds"""
        try:
            port = int(self.get_argument('port'))
            
            thresholds = self.port_monitor.db.get_port_thresholds(port)
            
            self.write_json({
                'success': True,
                'port': port,
                'thresholds': thresholds or {}
            })
            
        except ValueError:
            self.write_json({
                'success': False,
                'error': 'Invalid port number'
            }, 400)
        except Exception as e:
            logger.error(f"Failed to get port thresholds: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)
    
    async def post(self):
        """Set port resource thresholds"""
        try:
            data = json.loads(self.request.body)
            
            port = data.get('port')
            cpu_threshold = data.get('cpu_threshold', 0)
            ram_threshold = data.get('ram_threshold', 0)
            email_alerts_enabled = data.get('email_alerts_enabled', False)
            
            if not port:
                self.write_json({
                    'success': False,
                    'error': 'Port number is required'
                }, 400)
                return
            
            # Validate thresholds
            if cpu_threshold < 0 or cpu_threshold > 100:
                self.write_json({
                    'success': False,
                    'error': 'CPU threshold must be between 0 and 100'
                }, 400)
                return
            
            if ram_threshold < 0 or ram_threshold > 100:
                self.write_json({
                    'success': False,
                    'error': 'RAM threshold must be between 0 and 100'
                }, 400)
                return
            
            success = self.port_monitor.db.save_port_thresholds(
                port=port,
                cpu_threshold=cpu_threshold,
                ram_threshold=ram_threshold,
                email_alerts_enabled=email_alerts_enabled
            )
            
            if success:
                self.write_json({
                    'success': True,
                    'message': f'Thresholds saved for port {port}',
                    'thresholds': {
                        'port': port,
                        'cpu_threshold': cpu_threshold,
                        'ram_threshold': ram_threshold,
                        'email_alerts_enabled': email_alerts_enabled
                    }
                })
            else:
                self.write_json({
                    'success': False,
                    'error': f'Failed to save thresholds for port {port}'
                }, 500)
                
        except Exception as e:
            logger.error(f"Failed to save port thresholds: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)
    
    async def delete(self):
        """Delete port resource thresholds"""
        try:
            port = int(self.get_argument('port'))
            
            success = self.port_monitor.db.delete_port_thresholds(port)
            
            if success:
                self.write_json({
                    'success': True,
                    'message': f'Thresholds deleted for port {port}'
                })
            else:
                self.write_json({
                    'success': False,
                    'error': f'Failed to delete thresholds for port {port}'
                }, 500)
                
        except ValueError:
            self.write_json({
                'success': False,
                'error': 'Invalid port number'
            }, 400)
        except Exception as e:
            logger.error(f"Failed to delete port thresholds: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class PortThresholdCheckHandler(BaseHandler):
    """Handle port threshold checking"""
    
    def initialize(self, port_monitor):
        self.port_monitor = port_monitor
    
    async def get(self):
        """Check if port processes exceed thresholds"""
        try:
            port = int(self.get_argument('port'))
            
            result = await self.port_monitor.check_resource_thresholds(port)
            
            self.write_json({
                'success': True,
                'port': port,
                'result': result
            })
            
        except ValueError:
            self.write_json({
                'success': False,
                'error': 'Invalid port number'
            }, 400)
        except Exception as e:
            logger.error(f"Failed to check port thresholds: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class ProcessLogsHandler(BaseHandler):
    """Handle process monitoring logs"""
    
    def initialize(self, port_monitor):
        self.port_monitor = port_monitor
    
    async def get(self):
        """Get process monitoring logs"""
        try:
            port = self.get_argument('port', None)
            limit = int(self.get_argument('limit', 100))
            
            if port:
                port = int(port)
            
            logs = self.port_monitor.db.get_process_logs(port, limit)
            
            self.write_json({
                'success': True,
                'logs': logs,
                'log_count': len(logs)
            })
            
        except ValueError:
            self.write_json({
                'success': False,
                'error': 'Invalid port number or limit'
            }, 400)
        except Exception as e:
            logger.error(f"Failed to get process logs: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class ServiceProcessHandler(BaseHandler):
    """Handle service process monitoring requests"""
    
    def initialize(self, service_monitor):
        self.service_monitor = service_monitor
    
    async def get(self):
        """Get processes for a specific service"""
        try:
            service_name = self.get_argument('service_name')
            
            processes = await self.service_monitor.get_service_processes(service_name)
            
            self.write_json({
                'success': True,
                'service_name': service_name,
                'processes': processes,
                'process_count': len(processes)
            })
            
        except Exception as e:
            logger.error(f"Failed to get processes for service: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class ServiceResourceSummaryHandler(BaseHandler):
    """Handle service resource summary requests"""
    
    def initialize(self, service_monitor):
        self.service_monitor = service_monitor
    
    async def get(self):
        """Get comprehensive resource summary for a service"""
        try:
            service_name = self.get_argument('service_name')
            
            summary = await self.service_monitor.get_service_resource_summary(service_name)
            
            self.write_json({
                'success': True,
                'summary': summary
            })
            
        except Exception as e:
            logger.error(f"Failed to get resource summary for service: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class ServiceThresholdHandler(BaseHandler):
    """Handle service resource threshold configuration"""
    
    def initialize(self, service_monitor):
        self.service_monitor = service_monitor
    
    async def get(self):
        """Get service resource thresholds"""
        try:
            service_name = self.get_argument('service_name')
            
            thresholds = self.service_monitor.db.get_service_thresholds(service_name)
            
            self.write_json({
                'success': True,
                'service_name': service_name,
                'thresholds': thresholds or {}
            })
            
        except Exception as e:
            logger.error(f"Failed to get service thresholds: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)
    
    async def post(self):
        """Set service resource thresholds"""
        try:
            data = json.loads(self.request.body)
            
            service_name = data.get('service_name')
            cpu_threshold = data.get('cpu_threshold', 0)
            ram_threshold = data.get('ram_threshold', 0)
            email_alerts_enabled = data.get('email_alerts_enabled', False)
            
            if not service_name:
                self.write_json({
                    'success': False,
                    'error': 'Service name is required'
                }, 400)
                return
            
            # Validate thresholds
            if cpu_threshold < 0 or cpu_threshold > 100:
                self.write_json({
                    'success': False,
                    'error': 'CPU threshold must be between 0 and 100'
                }, 400)
                return
            
            if ram_threshold < 0 or ram_threshold > 100:
                self.write_json({
                    'success': False,
                    'error': 'RAM threshold must be between 0 and 100'
                }, 400)
                return
            
            success = self.service_monitor.db.save_service_thresholds(
                service_name=service_name,
                cpu_threshold=cpu_threshold,
                ram_threshold=ram_threshold,
                email_alerts_enabled=email_alerts_enabled
            )
            
            if success:
                self.write_json({
                    'success': True,
                    'message': f'Thresholds saved for service {service_name}',
                    'thresholds': {
                        'service_name': service_name,
                        'cpu_threshold': cpu_threshold,
                        'ram_threshold': ram_threshold,
                        'email_alerts_enabled': email_alerts_enabled
                    }
                })
            else:
                self.write_json({
                    'success': False,
                    'error': f'Failed to save thresholds for service {service_name}'
                }, 500)
                
        except Exception as e:
            logger.error(f"Failed to save service thresholds: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)
    
    async def delete(self):
        """Delete service resource thresholds"""
        try:
            service_name = self.get_argument('service_name')
            
            success = self.service_monitor.db.delete_service_thresholds(service_name)
            
            if success:
                self.write_json({
                    'success': True,
                    'message': f'Thresholds deleted for service {service_name}'
                })
            else:
                self.write_json({
                    'success': False,
                    'error': f'Failed to delete thresholds for service {service_name}'
                }, 500)
                
        except Exception as e:
            logger.error(f"Failed to delete service thresholds: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class ServiceThresholdCheckHandler(BaseHandler):
    """Handle service threshold checking"""
    
    def initialize(self, service_monitor):
        self.service_monitor = service_monitor
    
    async def get(self):
        """Check if service processes exceed thresholds"""
        try:
            service_name = self.get_argument('service_name')
            
            result = await self.service_monitor.check_service_resource_thresholds(service_name)
            
            self.write_json({
                'success': True,
                'service_name': service_name,
                'result': result
            })
            
        except Exception as e:
            logger.error(f"Failed to check service thresholds: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)


class ServiceProcessLogsHandler(BaseHandler):
    """Handle service process monitoring logs"""
    
    def initialize(self, service_monitor):
        self.service_monitor = service_monitor
    
    async def get(self):
        """Get service process monitoring logs"""
        try:
            service_name = self.get_argument('service_name', None)
            limit = int(self.get_argument('limit', 100))
            
            logs = self.service_monitor.db.get_service_process_logs(service_name, limit)
            
            self.write_json({
                'success': True,
                'logs': logs,
                'log_count': len(logs)
            })
            
        except ValueError:
            self.write_json({
                'success': False,
                'error': 'Invalid limit parameter'
            }, 400)
        except Exception as e:
            logger.error(f"Failed to get service process logs: {e}")
            self.write_json({
                'success': False,
                'error': str(e)
            }, 500)