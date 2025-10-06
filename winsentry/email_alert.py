"""
Email alert functionality for WinSentry
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, List, Optional
from datetime import datetime
import json
import os

logger = logging.getLogger(__name__)


class EmailAlert:
    """Email alert manager for WinSentry"""
    
    def __init__(self, db_path: str = "winsentry.db"):
        self.logger = logging.getLogger(__name__)
        self.db_path = db_path
        self.smtp_config = self._load_smtp_config()
        self.email_templates = self._load_email_templates()
    
    def _load_smtp_config(self) -> Dict:
        """Load SMTP configuration from file"""
        config_file = "smtp_config.json"
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    return json.load(f)
            else:
                # Default configuration
                return {
                    "smtp_server": "",
                    "smtp_port": 587,
                    "smtp_username": "",
                    "smtp_password": "",
                    "use_tls": True,
                    "from_email": "",
                    "from_name": "WinSentry Alert System"
                }
        except Exception as e:
            self.logger.error(f"Failed to load SMTP config: {e}")
            return {}
    
    def _save_smtp_config(self, config: Dict) -> bool:
        """Save SMTP configuration to file"""
        try:
            config_file = "smtp_config.json"
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            self.smtp_config = config
            return True
        except Exception as e:
            self.logger.error(f"Failed to save SMTP config: {e}")
            return False
    
    def _load_email_templates(self) -> Dict:
        """Load email templates from file"""
        templates_file = "email_templates.json"
        try:
            if os.path.exists(templates_file):
                with open(templates_file, 'r') as f:
                    return json.load(f)
            else:
                # Default templates
                return {
                    "default": {
                        "subject": "WinSentry Alert - Port {port} is {status}",
                        "body": """Dear Administrator,

This is an automated alert from WinSentry.

Port Details:
- Port: {port}
- Status: {status}
- Failure Count: {failure_count}
- Timestamp: {timestamp}
- Server: {server_name}

Please check the system immediately.

Best regards,
WinSentry Alert System"""
                    },
                    "service_default": {
                        "subject": "WinSentry Alert - Service {service_name} is {status}",
                        "body": """Dear Administrator,

This is an automated alert from WinSentry.

Service Details:
- Service: {service_name}
- Status: {status}
- Failure Count: {failure_count}
- Timestamp: {timestamp}
- Server: {server_name}

Please check the system immediately.

Best regards,
WinSentry Alert System"""
                    }
                }
        except Exception as e:
            self.logger.error(f"Failed to load email templates: {e}")
            return {}
    
    def _save_email_templates(self, templates: Dict) -> bool:
        """Save email templates to file"""
        try:
            templates_file = "email_templates.json"
            with open(templates_file, 'w') as f:
                json.dump(templates, f, indent=2)
            self.email_templates = templates
            return True
        except Exception as e:
            self.logger.error(f"Failed to save email templates: {e}")
            return False
    
    def update_smtp_config(self, config: Dict) -> bool:
        """Update SMTP configuration"""
        try:
            # Validate required fields
            required_fields = ["smtp_server", "smtp_port", "smtp_username", "smtp_password", "from_email"]
            for field in required_fields:
                if not config.get(field):
                    raise ValueError(f"Missing required field: {field}")
            
            # Validate port number
            if not isinstance(config["smtp_port"], int) or config["smtp_port"] <= 0:
                raise ValueError("SMTP port must be a positive integer")
            
            return self._save_smtp_config(config)
        except Exception as e:
            self.logger.error(f"Failed to update SMTP config: {e}")
            return False
    
    def get_smtp_config(self) -> Dict:
        """Get current SMTP configuration"""
        return self.smtp_config.copy()
    
    def add_email_template(self, template_name: str, subject: str, body: str) -> bool:
        """Add or update email template"""
        try:
            if not template_name or not subject or not body:
                raise ValueError("Template name, subject, and body are required")
            
            self.email_templates[template_name] = {
                "subject": subject,
                "body": body
            }
            return self._save_email_templates(self.email_templates)
        except Exception as e:
            self.logger.error(f"Failed to add email template: {e}")
            return False
    
    def get_email_templates(self) -> Dict:
        """Get all email templates"""
        return self.email_templates.copy()
    
    def delete_email_template(self, template_name: str) -> bool:
        """Delete email template"""
        try:
            if template_name in self.email_templates:
                del self.email_templates[template_name]
                return self._save_email_templates(self.email_templates)
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete email template: {e}")
            return False
    
    def test_smtp_connection(self) -> Dict:
        """Test SMTP connection"""
        try:
            if not self.smtp_config.get("smtp_server"):
                return {"success": False, "error": "SMTP server not configured"}
            
            # Create SMTP connection
            server = smtplib.SMTP(self.smtp_config["smtp_server"], self.smtp_config["smtp_port"])
            
            if self.smtp_config.get("use_tls", True):
                server.starttls()
            
            # Login
            server.login(self.smtp_config["smtp_username"], self.smtp_config["smtp_password"])
            server.quit()
            
            return {"success": True, "message": "SMTP connection successful"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def send_alert_email(self, port: int, recipients: List[str], template_name: str = "default", 
                             custom_data: Dict = None) -> bool:
        """Send alert email for port failure"""
        try:
            if not self.smtp_config.get("smtp_server"):
                self.logger.error("SMTP server not configured")
                return False
            
            if not recipients:
                self.logger.error("No recipients specified")
                return False
            
            # Get template
            template = self.email_templates.get(template_name, self.email_templates.get("default"))
            if not template:
                self.logger.error(f"Email template '{template_name}' not found")
                return False
            
            # Prepare email data
            email_data = {
                "port": port,
                "status": "OFFLINE",
                "failure_count": custom_data.get("failure_count", 0) if custom_data else 0,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "server_name": os.environ.get("COMPUTERNAME", "Unknown Server"),
                "message": custom_data.get("message", "") if custom_data else ""
            }
            
            # Format subject and body
            subject = template["subject"].format(**email_data)
            body = template["body"].format(**email_data)
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = f"{self.smtp_config['from_name']} <{self.smtp_config['from_email']}>"
            msg['To'] = ", ".join(recipients)
            msg['Subject'] = subject
            
            # Add body
            msg.attach(MIMEText(body, 'plain'))
            
            # Send email
            server = smtplib.SMTP(self.smtp_config["smtp_server"], self.smtp_config["smtp_port"])
            
            if self.smtp_config.get("use_tls", True):
                server.starttls()
            
            server.login(self.smtp_config["smtp_username"], self.smtp_config["smtp_password"])
            
            text = msg.as_string()
            server.sendmail(self.smtp_config["from_email"], recipients, text)
            server.quit()
            
            self.logger.info(f"Alert email sent for port {port} to {len(recipients)} recipients")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send alert email: {e}")
            return False
    
    def get_port_email_config(self, port: int) -> Dict:
        """Get email configuration for specific port"""
        config_file = f"port_email_config_{port}.json"
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    return json.load(f)
            else:
                return {
                    "enabled": False,
                    "recipients": [],
                    "template": "default",
                    "powershell_script_failures": 3,
                    "email_alert_failures": 5,
                    "custom_data": {}
                }
        except Exception as e:
            self.logger.error(f"Failed to get port email config: {e}")
            return {}
    
    def save_port_email_config(self, port: int, config: Dict) -> bool:
        """Save email configuration for specific port"""
        try:
            config_file = f"port_email_config_{port}.json"
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            self.logger.error(f"Failed to save port email config: {e}")
            return False
    
    def delete_port_email_config(self, port: int) -> bool:
        """Delete email configuration for specific port"""
        try:
            config_file = f"port_email_config_{port}.json"
            if os.path.exists(config_file):
                os.remove(config_file)
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete port email config: {e}")
            return False
    
    def get_all_port_email_configs(self) -> List[Dict]:
        """Get all port email configurations"""
        configs = []
        try:
            # Get all monitored ports
            monitored_ports = self.port_monitor.get_monitored_ports()
            
            for port_config in monitored_ports:
                port = port_config.port
                config = self.get_port_email_config(port)
                config['port'] = port
                config['port_name'] = port_config.name
                configs.append(config)
            
            return configs
        except Exception as e:
            self.logger.error(f"Failed to get all port email configs: {e}")
            return []
    
    # Service monitoring email methods
    async def send_service_alert_email(self, service_name: str, recipients: List[str], template_name: str = "service_default", 
                                     custom_data: Dict = None) -> bool:
        """Send alert email for service failure"""
        try:
            if not self.smtp_config.get("smtp_server"):
                self.logger.error("SMTP server not configured")
                return False
            
            if not recipients:
                self.logger.error("No recipients specified")
                return False
            
            # Get template
            template = self.email_templates.get(template_name, self.email_templates.get("service_default"))
            if not template:
                self.logger.error(f"Email template '{template_name}' not found")
                return False
            
            # Prepare email data
            email_data = {
                "service_name": service_name,
                "status": "STOPPED",
                "failure_count": custom_data.get("failure_count", 0) if custom_data else 0,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "server_name": os.environ.get("COMPUTERNAME", "Unknown Server"),
                "message": custom_data.get("message", "") if custom_data else ""
            }
            
            # Format subject and body
            subject = template["subject"].format(**email_data)
            body = template["body"].format(**email_data)
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = f"{self.smtp_config['from_name']} <{self.smtp_config['from_email']}>"
            msg['To'] = ", ".join(recipients)
            msg['Subject'] = subject
            
            # Add body
            msg.attach(MIMEText(body, 'plain'))
            
            # Send email
            server = smtplib.SMTP(self.smtp_config["smtp_server"], self.smtp_config["smtp_port"])
            
            if self.smtp_config.get("use_tls", True):
                server.starttls()
            
            server.login(self.smtp_config["smtp_username"], self.smtp_config["smtp_password"])
            
            text = msg.as_string()
            server.sendmail(self.smtp_config["from_email"], recipients, text)
            server.quit()
            
            self.logger.info(f"Alert email sent for service {service_name} to {len(recipients)} recipients")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send service alert email: {e}")
            return False
    
    def get_service_email_config(self, service_name: str) -> Dict:
        """Get email configuration for specific service"""
        config_file = f"service_email_config_{service_name}.json"
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    return json.load(f)
            else:
                return {
                    "enabled": False,
                    "recipients": [],
                    "template": "service_default",
                    "powershell_script_failures": 3,
                    "email_alert_failures": 5,
                    "custom_data": {}
                }
        except Exception as e:
            self.logger.error(f"Failed to get service email config: {e}")
            return {}
    
    def save_service_email_config(self, service_name: str, config: Dict) -> bool:
        """Save email configuration for specific service"""
        try:
            config_file = f"service_email_config_{service_name}.json"
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            self.logger.error(f"Failed to save service email config: {e}")
            return False
    
    def delete_service_email_config(self, service_name: str) -> bool:
        """Delete email configuration for specific service"""
        try:
            config_file = f"service_email_config_{service_name}.json"
            if os.path.exists(config_file):
                os.remove(config_file)
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete service email config: {e}")
            return False