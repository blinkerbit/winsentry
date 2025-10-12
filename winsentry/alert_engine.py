"""Email alert engine for WinSentry"""

import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, List, Optional
from datetime import datetime
import schedule
import threading


class AlertEngine:
    """Manages email alerts based on configured rules"""
    
    def __init__(self, db_manager):
        self.db = db_manager
        self.schedule_thread = None
        self.running = False
    
    def send_alert(self, alert_rule_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send an email alert based on alert rule
        
        Args:
            alert_rule_id: Alert rule database ID
            data: Data to populate template variables
        
        Returns:
            Result dictionary with success status
        """
        try:
            # Get alert rule
            alert_rows = self.db.execute_query(
                "SELECT * FROM alert_rules WHERE id = ?",
                (alert_rule_id,)
            )
            
            if not alert_rows:
                return {"success": False, "error": "Alert rule not found"}
            
            alert_rule = dict(alert_rows[0])
            
            if not alert_rule.get("enabled"):
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
                return {"success": False, "error": "Email template not found"}
            
            template = dict(template_rows[0])
            
            # Get recipients for this alert
            recipient_rows = self.db.execute_query("""
                SELECT r.* FROM recipients r
                JOIN alert_recipients ar ON r.id = ar.recipient_id
                WHERE ar.alert_id = ? AND r.enabled = 1
            """, (alert_rule_id,))
            
            if not recipient_rows:
                return {"success": False, "error": "No enabled recipients found for this alert"}
            
            recipients = [dict(row) for row in recipient_rows]
            
            # Get SMTP configuration
            smtp_rows = self.db.execute_query(
                "SELECT * FROM email_servers WHERE is_active = 1 LIMIT 1"
            )
            
            if not smtp_rows:
                return {"success": False, "error": "No active SMTP server configured"}
            
            smtp_config = dict(smtp_rows[0])
            
            # Populate template
            subject = self._populate_template(template["subject_template"], data)
            body = self._populate_template(template["body_template"], data)
            
            # Send emails
            results = []
            for recipient in recipients:
                result = self._send_email(
                    smtp_config=smtp_config,
                    to_email=recipient["email_address"],
                    subject=subject,
                    body=body
                )
                results.append(result)
            
            success_count = sum(1 for r in results if r.get("success"))
            
            return {
                "success": success_count > 0,
                "sent_count": success_count,
                "total_recipients": len(recipients),
                "results": results,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
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
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = smtp_config['from_address']
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            
            # Connect to SMTP server
            if smtp_config.get('use_ssl', True):
                server = smtplib.SMTP_SSL(smtp_config['smtp_host'], smtp_config['smtp_port'])
            else:
                server = smtplib.SMTP(smtp_config['smtp_host'], smtp_config['smtp_port'])
                if smtp_config.get('use_tls', True):
                    server.starttls()
            
            # Login if credentials provided
            if smtp_config.get('username') and smtp_config.get('password'):
                server.login(smtp_config['username'], smtp_config['password'])
            
            # Send email
            server.send_message(msg)
            server.quit()
            
            return {
                "success": True,
                "recipient": to_email,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "success": False,
                "recipient": to_email,
                "error": str(e),
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


# Global alert engine instance (will be initialized in app.py)
alert_engine: Optional[AlertEngine] = None

