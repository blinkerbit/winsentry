"""Email alert engine for WinSentry"""

import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, List, Optional
from datetime import datetime
import schedule
import threading
import os


class AlertEngine:
    """Manages email alerts based on configured rules"""
    
    def __init__(self, db_manager, log_dir: str = "logs/email_alerts"):
        self.db = db_manager
        self.schedule_thread = None
        self.running = False
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.current_log_file = self._get_current_log_file()
    
    def _get_current_log_file(self) -> str:
        """Get the current log file path based on week number"""
        now = datetime.now()
        week_num = now.isocalendar()[1]
        year = now.year
        return os.path.join(self.log_dir, f"email_alerts_{year}_week{week_num:02d}.log")
    
    def _check_rotation(self):
        """Check if we need to rotate to a new log file"""
        current_file = self._get_current_log_file()
        if current_file != self.current_log_file:
            self.current_log_file = current_file
    
    def _log_email_attempt(self, alert_rule_id: int, recipient_email: str, subject: str, 
                          smtp_config: Dict[str, Any], attempt_data: Dict[str, Any]):
        """Log email sending attempt"""
        self._check_rotation()
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "email_attempt",
            "alert_rule_id": alert_rule_id,
            "recipient_email": recipient_email,
            "subject": subject,
            "smtp_host": smtp_config.get('smtp_host'),
            "smtp_port": smtp_config.get('smtp_port'),
            "from_address": smtp_config.get('from_address'),
            "use_ssl": smtp_config.get('use_ssl', True),
            "use_tls": smtp_config.get('use_tls', True),
            "has_credentials": bool(smtp_config.get('username') and smtp_config.get('password')),
            "trigger_data": attempt_data
        }
        
        self._write_log_entry(log_entry)
    
    def _log_email_result(self, alert_rule_id: int, recipient_email: str, success: bool, 
                         result_data: Dict[str, Any]):
        """Log email sending result"""
        self._check_rotation()
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "email_result",
            "alert_rule_id": alert_rule_id,
            "recipient_email": recipient_email,
            "success": success,
            "error_message": result_data.get("error") if not success else None,
            "execution_time": result_data.get("execution_time"),
            "details": result_data
        }
        
        self._write_log_entry(log_entry)
    
    def _log_alert_rule_lookup(self, alert_rule_id: int, found: bool, error: str = None):
        """Log alert rule lookup result"""
        self._check_rotation()
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "alert_rule_lookup",
            "alert_rule_id": alert_rule_id,
            "found": found,
            "error": error
        }
        
        self._write_log_entry(log_entry)
    
    def _log_template_processing(self, template_id: int, template_name: str, 
                                subject: str, body_length: int, success: bool, error: str = None):
        """Log email template processing"""
        self._check_rotation()
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "template_processing",
            "template_id": template_id,
            "template_name": template_name,
            "subject": subject,
            "body_length": body_length,
            "success": success,
            "error": error
        }
        
        self._write_log_entry(log_entry)
    
    def _log_recipient_lookup(self, alert_rule_id: int, recipient_count: int, 
                            enabled_recipients: List[str]):
        """Log recipient lookup result"""
        self._check_rotation()
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "recipient_lookup",
            "alert_rule_id": alert_rule_id,
            "recipient_count": recipient_count,
            "enabled_recipients": enabled_recipients
        }
        
        self._write_log_entry(log_entry)
    
    def _log_smtp_config_lookup(self, found: bool, smtp_host: str = None, error: str = None):
        """Log SMTP configuration lookup"""
        self._check_rotation()
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "smtp_config_lookup",
            "found": found,
            "smtp_host": smtp_host,
            "error": error
        }
        
        self._write_log_entry(log_entry)
    
    def _write_log_entry(self, entry: Dict[str, Any]):
        """Write a log entry to the current log file"""
        try:
            with open(self.current_log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"Failed to write email alert log entry: {e}")
    
    def send_alert(self, alert_rule_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send an email alert based on alert rule
        
        Args:
            alert_rule_id: Alert rule database ID
            data: Data to populate template variables
        
        Returns:
            Result dictionary with success status
        """
        start_time = datetime.now()
        
        try:
            # Get alert rule
            alert_rows = self.db.execute_query(
                "SELECT * FROM alert_rules WHERE id = ?",
                (alert_rule_id,)
            )
            
            if not alert_rows:
                self._log_alert_rule_lookup(alert_rule_id, False, "Alert rule not found")
                return {"success": False, "error": "Alert rule not found"}
            
            alert_rule = dict(alert_rows[0])
            self._log_alert_rule_lookup(alert_rule_id, True)
            
            if not alert_rule.get("enabled"):
                self._log_alert_rule_lookup(alert_rule_id, False, "Alert rule is disabled")
                return {"success": False, "error": "Alert rule is disabled"}
            
            # Get email template
            template_id = alert_rule.get("template_id")
            if template_id:
                template_rows = self.db.execute_query(
                    "SELECT * FROM email_templates WHERE id = ?",
                    (template_id,)
                )
            else:
                # Use default template
                template_rows = self.db.execute_query(
                    "SELECT * FROM email_templates WHERE template_name = 'default_alert'"
                )
            
            if not template_rows:
                self._log_template_processing(template_id or 0, "default_alert", "", 0, False, "Email template not found")
                return {"success": False, "error": "Email template not found"}
            
            template = dict(template_rows[0])
            
            # Populate template
            try:
                subject = self._populate_template(template["subject_template"], data)
                body = self._populate_template(template["body_template"], data)
                self._log_template_processing(template["id"], template["template_name"], subject, len(body), True)
            except Exception as e:
                self._log_template_processing(template["id"], template["template_name"], "", 0, False, str(e))
                return {"success": False, "error": f"Template processing failed: {str(e)}"}
            
            # Get recipients for this alert
            recipient_rows = self.db.execute_query("""
                SELECT r.* FROM recipients r
                JOIN alert_recipients ar ON r.id = ar.recipient_id
                WHERE ar.alert_id = ? AND r.enabled = 1
            """, (alert_rule_id,))
            
            if not recipient_rows:
                self._log_recipient_lookup(alert_rule_id, 0, [])
                return {"success": False, "error": "No enabled recipients found for this alert"}
            
            recipients = [dict(row) for row in recipient_rows]
            enabled_emails = [r["email_address"] for r in recipients]
            self._log_recipient_lookup(alert_rule_id, len(recipients), enabled_emails)
            
            # Get SMTP configuration
            smtp_rows = self.db.execute_query(
                "SELECT * FROM email_servers WHERE is_active = 1 LIMIT 1"
            )
            
            if not smtp_rows:
                self._log_smtp_config_lookup(False, error="No active SMTP server configured")
                return {"success": False, "error": "No active SMTP server configured"}
            
            smtp_config = dict(smtp_rows[0])
            self._log_smtp_config_lookup(True, smtp_config.get('smtp_host'))
            
            # Send emails
            results = []
            for recipient in recipients:
                # Log email attempt
                self._log_email_attempt(alert_rule_id, recipient["email_address"], subject, smtp_config, data)
                
                # Send email with timing
                email_start = datetime.now()
                result = self._send_email(
                    smtp_config=smtp_config,
                    to_email=recipient["email_address"],
                    subject=subject,
                    body=body
                )
                email_end = datetime.now()
                
                # Add execution time to result
                result["execution_time"] = (email_end - email_start).total_seconds()
                
                # Log email result
                self._log_email_result(alert_rule_id, recipient["email_address"], result.get("success", False), result)
                
                results.append(result)
            
            success_count = sum(1 for r in results if r.get("success"))
            total_time = (datetime.now() - start_time).total_seconds()
            
            return {
                "success": success_count > 0,
                "sent_count": success_count,
                "total_recipients": len(recipients),
                "results": results,
                "total_execution_time": total_time,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            error_msg = str(e)
            self._log_alert_rule_lookup(alert_rule_id, False, error_msg)
            return {
                "success": False,
                "error": error_msg,
                "timestamp": datetime.now().isoformat()
            }
    
    def _populate_template(self, template: str, data: Dict[str, Any]) -> str:
        """Populate template with data"""
        try:
            return template.format(**data)
        except KeyError as e:
            # Missing variable, use placeholder
            return template.replace("{" + str(e).strip("'") + "}", f"<missing:{e}>")
    
    def _send_email(self, smtp_config: Dict[str, Any], to_email: str, subject: str, body: str) -> Dict[str, Any]:
        """
        Send a single email
        
        Returns:
            Result dictionary
        """
        start_time = datetime.now()
        
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = smtp_config['from_address']
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            
            # Connect to SMTP server with proper SSL/TLS handling
            # Port 465 uses SSL (SMTP_SSL), Port 587 uses TLS (SMTP + starttls)
            if smtp_config.get('use_ssl', False) and smtp_config['smtp_port'] == 465:
                # Use SSL for port 465
                server = smtplib.SMTP_SSL(smtp_config['smtp_host'], smtp_config['smtp_port'])
            else:
                # Use regular SMTP connection
                server = smtplib.SMTP(smtp_config['smtp_host'], smtp_config['smtp_port'])
                # Enable debug output for troubleshooting
                server.set_debuglevel(0)
                
                # Use STARTTLS if TLS is enabled (recommended for port 587)
                if smtp_config.get('use_tls', True):
                    server.starttls()
                    server.set_debuglevel(0)  # Reset debug level after STARTTLS
            
            # Login if credentials provided
            if smtp_config.get('username') and smtp_config.get('password'):
                server.login(smtp_config['username'], smtp_config['password'])
            
            # Send email
            server.send_message(msg)
            server.quit()
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return {
                "success": True,
                "recipient": to_email,
                "execution_time": execution_time,
                "timestamp": datetime.now().isoformat()
            }
            
        except smtplib.SMTPAuthenticationError as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            error_msg = f"SMTP Authentication failed: {str(e)}"
            return {
                "success": False,
                "recipient": to_email,
                "error": error_msg,
                "execution_time": execution_time,
                "timestamp": datetime.now().isoformat()
            }
        except smtplib.SMTPConnectError as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            error_msg = f"SMTP Connection failed: {str(e)}"
            return {
                "success": False,
                "recipient": to_email,
                "error": error_msg,
                "execution_time": execution_time,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return {
                "success": False,
                "recipient": to_email,
                "error": str(e),
                "execution_time": execution_time,
                "timestamp": datetime.now().isoformat()
            }
    
    def check_status_change_alert(self, item_type: str, item_id: int, old_status: str, new_status: str) -> List[Dict[str, Any]]:
        """
        Check and send alerts for status changes
        
        Returns:
            List of alert results
        """
        # Get alert rules for status change
        alert_rows = self.db.execute_query("""
            SELECT * FROM alert_rules 
            WHERE monitored_item_type = ? 
            AND monitored_item_id = ? 
            AND alert_condition = 'status_change'
            AND enabled = 1
        """, (item_type, item_id))
        
        results = []
        for alert_row in alert_rows:
            alert = dict(alert_row)
            
            # Check if this specific status change matches
            condition_value = alert.get("condition_value")
            if condition_value:
                try:
                    condition = json.loads(condition_value)
                    expected_from = condition.get("from_status")
                    expected_to = condition.get("to_status")
                    
                    # Skip if doesn't match expected transition
                    if expected_from and expected_from != old_status:
                        continue
                    if expected_to and expected_to != new_status:
                        continue
                except json.JSONDecodeError:
                    pass
            
            # Send alert
            data = {
                "monitored_item_type": item_type,
                "monitored_item_id": item_id,
                "old_status": old_status,
                "new_status": new_status,
                "status": new_status,
                "trigger_reason": f"Status changed from {old_status} to {new_status}",
                "timestamp": datetime.now().isoformat()
            }
            
            result = self.send_alert(alert["id"], data)
            results.append(result)
        
        return results
    
    def check_duration_alert(self, item_type: str, item_id: int, status: str, duration_count: int) -> List[Dict[str, Any]]:
        """
        Check and send alerts for status duration
        
        Args:
            item_type: Type of monitored item
            item_id: ID of monitored item
            status: Current status
            duration_count: Number of consecutive intervals in this status
        
        Returns:
            List of alert results
        """
        # Get alert rules for duration
        alert_rows = self.db.execute_query("""
            SELECT * FROM alert_rules 
            WHERE monitored_item_type = ? 
            AND monitored_item_id = ? 
            AND alert_condition = 'duration'
            AND enabled = 1
        """, (item_type, item_id))
        
        results = []
        for alert_row in alert_rows:
            alert = dict(alert_row)
            
            # Check duration threshold
            condition_value = alert.get("condition_value")
            if condition_value:
                try:
                    condition = json.loads(condition_value)
                    required_status = condition.get("status")
                    required_count = condition.get("interval_count", 1)
                    
                    # Only send if status matches and duration threshold met
                    if required_status == status and duration_count >= required_count:
                        # Send alert
                        data = {
                            "monitored_item_type": item_type,
                            "monitored_item_id": item_id,
                            "status": status,
                            "duration_count": duration_count,
                            "trigger_reason": f"Status '{status}' for {duration_count} intervals",
                            "timestamp": datetime.now().isoformat()
                        }
                        
                        result = self.send_alert(alert["id"], data)
                        results.append(result)
                        
                except json.JSONDecodeError:
                    pass
        
        return results
    
    def check_threshold_alert(self, item_type: str, item_id: int, metric_type: str, current_value: float, threshold: float) -> List[Dict[str, Any]]:
        """
        Check and send alerts for threshold breaches
        
        Returns:
            List of alert results
        """
        if current_value < threshold:
            return []
        
        # Get alert rules for threshold
        alert_rows = self.db.execute_query("""
            SELECT * FROM alert_rules 
            WHERE monitored_item_type = ? 
            AND monitored_item_id = ? 
            AND alert_condition = 'threshold'
            AND enabled = 1
        """, (item_type, item_id))
        
        results = []
        for alert_row in alert_rows:
            alert = dict(alert_row)
            
            # Send alert
            data = {
                "monitored_item_type": item_type,
                "monitored_item_id": item_id,
                "metric_type": metric_type,
                "current_value": current_value,
                "threshold": threshold,
                "trigger_reason": f"{metric_type} threshold exceeded: {current_value:.2f}% > {threshold}%",
                "timestamp": datetime.now().isoformat()
            }
            
            result = self.send_alert(alert["id"], data)
            results.append(result)
        
        return results
    
    def start_recurring_alerts(self):
        """Start background thread for recurring alerts"""
        self.running = True
        self.schedule_thread = threading.Thread(target=self._recurring_alert_loop, daemon=True)
        self.schedule_thread.start()
    
    def _recurring_alert_loop(self):
        """Background loop for recurring alerts"""
        while self.running:
            schedule.run_pending()
            import time
            time.sleep(60)  # Check every minute
    
    def stop(self):
        """Stop the alert engine"""
        self.running = False
        if self.schedule_thread:
            self.schedule_thread.join(timeout=2)
    
    def get_email_log_files(self) -> List[str]:
        """Get list of all email alert log files"""
        try:
            files = [f for f in os.listdir(self.log_dir) if f.endswith('.log')]
            return sorted(files, reverse=True)  # Most recent first
        except FileNotFoundError:
            return []
    
    def read_email_logs(self, filename: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Read email log entries from a log file"""
        if filename is None:
            filename = os.path.basename(self.current_log_file)
        
        filepath = os.path.join(self.log_dir, filename)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Parse JSON lines
            logs = []
            for line in lines:
                line = line.strip()
                if line:
                    try:
                        logs.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            
            # Return latest entries with pagination
            logs.reverse()  # Latest first
            return logs[offset:offset + limit]
            
        except FileNotFoundError:
            return []
        except Exception as e:
            print(f"Error reading email logs: {e}")
            return []
    
    def search_email_logs(self, alert_rule_id: int = None, recipient_email: str = None, 
                         event_type: str = None, success: bool = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Search email logs by various criteria"""
        logs = self.read_email_logs(limit=1000)  # Search recent logs
        
        filtered_logs = []
        for log in logs:
            # Filter by alert rule ID
            if alert_rule_id is not None and log.get("alert_rule_id") != alert_rule_id:
                continue
            
            # Filter by recipient email
            if recipient_email is not None and log.get("recipient_email") != recipient_email:
                continue
            
            # Filter by event type
            if event_type is not None and log.get("event") != event_type:
                continue
            
            # Filter by success status
            if success is not None and log.get("success") != success:
                continue
            
            filtered_logs.append(log)
        
        return filtered_logs[:limit]
    
    def get_email_statistics(self, days: int = 7) -> Dict[str, Any]:
        """Get email sending statistics for the last N days"""
        logs = self.read_email_logs(limit=10000)  # Get more logs for statistics
        
        # Filter logs by date range
        cutoff_date = datetime.now().timestamp() - (days * 24 * 60 * 60)
        recent_logs = []
        
        for log in logs:
            try:
                log_time = datetime.fromisoformat(log["timestamp"]).timestamp()
                if log_time >= cutoff_date:
                    recent_logs.append(log)
            except (ValueError, KeyError):
                continue
        
        # Calculate statistics
        total_attempts = len([log for log in recent_logs if log.get("event") == "email_attempt"])
        successful_sends = len([log for log in recent_logs if log.get("event") == "email_result" and log.get("success")])
        failed_sends = len([log for log in recent_logs if log.get("event") == "email_result" and not log.get("success")])
        
        # Get unique recipients
        recipients = set()
        for log in recent_logs:
            if log.get("recipient_email"):
                recipients.add(log["recipient_email"])
        
        # Get unique alert rules
        alert_rules = set()
        for log in recent_logs:
            if log.get("alert_rule_id"):
                alert_rules.add(log["alert_rule_id"])
        
        # Calculate average execution time
        execution_times = []
        for log in recent_logs:
            if log.get("execution_time") is not None:
                execution_times.append(log["execution_time"])
        
        avg_execution_time = sum(execution_times) / len(execution_times) if execution_times else 0
        
        return {
            "period_days": days,
            "total_attempts": total_attempts,
            "successful_sends": successful_sends,
            "failed_sends": failed_sends,
            "success_rate": (successful_sends / total_attempts * 100) if total_attempts > 0 else 0,
            "unique_recipients": len(recipients),
            "unique_alert_rules": len(alert_rules),
            "average_execution_time": round(avg_execution_time, 3),
            "recipients": list(recipients),
            "alert_rules": list(alert_rules)
        }
    
    def send_test_email(self, smtp_server_id: int = None, recipient_email: str = None) -> Dict[str, Any]:
        """
        Send a test email to verify SMTP configuration
        
        Args:
            smtp_server_id: Specific SMTP server ID to test (optional)
            recipient_email: Email address to send test to (optional)
        
        Returns:
            Result dictionary with test results
        """
        start_time = datetime.now()
        
        try:
            # Get SMTP configuration
            if smtp_server_id:
                smtp_rows = self.db.execute_query(
                    "SELECT * FROM email_servers WHERE id = ? AND is_active = 1",
                    (smtp_server_id,)
                )
            else:
                smtp_rows = self.db.execute_query(
                    "SELECT * FROM email_servers WHERE is_active = 1 LIMIT 1"
                )
            
            if not smtp_rows:
                self._log_smtp_config_lookup(False, error="No active SMTP server found for test")
                return {
                    "success": False,
                    "error": "No active SMTP server found",
                    "timestamp": datetime.now().isoformat()
                }
            
            smtp_config = dict(smtp_rows[0])
            self._log_smtp_config_lookup(True, smtp_config.get('smtp_host'))
            
            # Use provided recipient or get first enabled recipient
            if recipient_email:
                test_recipient = recipient_email
            else:
                recipient_rows = self.db.execute_query(
                    "SELECT email_address FROM recipients WHERE enabled = 1 LIMIT 1"
                )
                if recipient_rows:
                    test_recipient = recipient_rows[0][0]
                else:
                    return {
                        "success": False,
                        "error": "No enabled recipients found and no recipient email provided",
                        "timestamp": datetime.now().isoformat()
                    }
            
            # Create test email content
            test_subject = f"WinSentry Test Email - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            test_body = f"""This is a test email from WinSentry to verify SMTP configuration.

Test Details:
- SMTP Host: {smtp_config.get('smtp_host')}
- SMTP Port: {smtp_config.get('smtp_port')}
- Use SSL: {smtp_config.get('use_ssl', True)}
- Use TLS: {smtp_config.get('use_tls', True)}
- From Address: {smtp_config.get('from_address')}
- Test Time: {datetime.now().isoformat()}

If you receive this email, your SMTP configuration is working correctly.

---
WinSentry Monitoring System
"""
            
            # Log test email attempt
            test_data = {
                "test_type": "smtp_configuration_test",
                "smtp_server_id": smtp_config.get('id'),
                "recipient_email": test_recipient
            }
            self._log_email_attempt(0, test_recipient, test_subject, smtp_config, test_data)
            
            # Send test email
            email_start = datetime.now()
            result = self._send_email(
                smtp_config=smtp_config,
                to_email=test_recipient,
                subject=test_subject,
                body=test_body
            )
            email_end = datetime.now()
            
            # Add execution time to result
            result["execution_time"] = (email_end - email_start).total_seconds()
            result["test_type"] = "smtp_configuration_test"
            result["smtp_server_id"] = smtp_config.get('id')
            
            # Log test email result
            self._log_email_result(0, test_recipient, result.get("success", False), result)
            
            total_time = (datetime.now() - start_time).total_seconds()
            
            return {
                "success": result.get("success", False),
                "test_type": "smtp_configuration_test",
                "smtp_server_id": smtp_config.get('id'),
                "smtp_host": smtp_config.get('smtp_host'),
                "smtp_port": smtp_config.get('smtp_port'),
                "from_address": smtp_config.get('from_address'),
                "recipient_email": test_recipient,
                "subject": test_subject,
                "execution_time": result.get("execution_time"),
                "total_execution_time": total_time,
                "error": result.get("error") if not result.get("success") else None,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            error_msg = str(e)
            self._log_smtp_config_lookup(False, error=f"Test email failed: {error_msg}")
            return {
                "success": False,
                "test_type": "smtp_configuration_test",
                "error": error_msg,
                "timestamp": datetime.now().isoformat()
            }


# Global alert engine instance (will be initialized in app.py)
alert_engine: Optional[AlertEngine] = None

