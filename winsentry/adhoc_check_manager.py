"""
Adhoc Check Manager - Handles on-demand and scheduled checks for services and processes
"""

import asyncio
import logging
import uuid
import json
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict

from .database import Database
from .email_alert import EmailAlert

logger = logging.getLogger(__name__)


@dataclass
class ScheduledCheck:
    """Configuration for a scheduled adhoc check"""
    id: str
    name: str
    check_type: str  # 'service' or 'process'
    target_name: str
    expected_state: str  # 'running', 'stopped', 'any'
    schedule: Dict[str, str]  # {'day_of_week': '0', 'time': '14:00'}
    actions: Dict[str, bool] = field(default_factory=dict)
    powershell_script: str = ''
    email_recipients: str = ''
    enabled: bool = True
    last_run: Optional[datetime] = None
    last_status: Optional[str] = None  # 'pass', 'fail', 'error'
    created_at: datetime = field(default_factory=datetime.now)


class AdhocCheckManager:
    """Manages adhoc and scheduled checks for services and processes"""
    
    def __init__(self, db_path: str = "winsentry.db"):
        self.logger = logging.getLogger(__name__)
        self.db = Database(db_path)
        self.email_alert = EmailAlert(db_path)
        self.scheduled_checks: Dict[str, ScheduledCheck] = {}
        self.monitoring_task: Optional[asyncio.Task] = None
        self.running = False
        
        self._ensure_tables_exist()
        self._load_scheduled_checks()
    
    def _ensure_tables_exist(self):
        """Ensure required database tables exist"""
        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS adhoc_checks (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    check_type TEXT NOT NULL,
                    target_name TEXT NOT NULL,
                    expected_state TEXT DEFAULT 'running',
                    schedule TEXT,
                    actions TEXT,
                    powershell_script TEXT,
                    email_recipients TEXT,
                    enabled INTEGER DEFAULT 1,
                    last_run TEXT,
                    last_status TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS adhoc_check_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    check_id TEXT,
                    check_type TEXT,
                    target_name TEXT,
                    expected_state TEXT,
                    current_state TEXT,
                    status TEXT,
                    actions_taken TEXT,
                    message TEXT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self.db.commit()
        except Exception as e:
            self.logger.error(f"Failed to create adhoc check tables: {e}")
    
    def _load_scheduled_checks(self):
        """Load scheduled checks from database"""
        try:
            rows = self.db.fetch_all(
                "SELECT * FROM adhoc_checks WHERE enabled = 1"
            )
            
            for row in rows:
                check = ScheduledCheck(
                    id=row['id'],
                    name=row['name'],
                    check_type=row['check_type'],
                    target_name=row['target_name'],
                    expected_state=row['expected_state'] or 'running',
                    schedule=json.loads(row['schedule'] or '{}'),
                    actions=json.loads(row['actions'] or '{}'),
                    powershell_script=row['powershell_script'] or '',
                    email_recipients=row['email_recipients'] or '',
                    enabled=bool(row['enabled']),
                    last_run=datetime.fromisoformat(row['last_run']) if row['last_run'] else None,
                    last_status=row['last_status'],
                    created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else datetime.now()
                )
                self.scheduled_checks[check.id] = check
            
            self.logger.info(f"Loaded {len(self.scheduled_checks)} scheduled checks")
        except Exception as e:
            self.logger.error(f"Failed to load scheduled checks: {e}")
    
    async def start_monitoring(self):
        """Start the scheduled check monitoring loop"""
        self.running = True
        self.logger.info("Starting adhoc check scheduler")
        
        while self.running:
            try:
                await self._check_scheduled_runs()
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in adhoc check scheduler: {e}")
                await asyncio.sleep(60)
        
        self.logger.info("Adhoc check scheduler stopped")
    
    async def stop_monitoring(self):
        """Stop the scheduled check monitoring"""
        self.running = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
    
    async def _check_scheduled_runs(self):
        """Check if any scheduled checks need to run"""
        now = datetime.now()
        current_day = now.weekday()  # 0=Monday, 6=Sunday
        # Convert to Sunday=0 format
        current_day_sunday = (current_day + 1) % 7
        current_time = now.strftime('%H:%M')
        
        for check_id, check in self.scheduled_checks.items():
            if not check.enabled:
                continue
            
            schedule = check.schedule
            day_of_week = schedule.get('day_of_week', '*')
            scheduled_time = schedule.get('time', '00:00')
            
            # Check if this check should run now
            should_run = False
            
            if day_of_week == '*':
                # Every day
                if current_time == scheduled_time:
                    should_run = True
            elif str(day_of_week) == str(current_day_sunday):
                if current_time == scheduled_time:
                    should_run = True
            
            if should_run:
                # Check if we already ran this check in the last minute
                if check.last_run and (now - check.last_run).total_seconds() < 60:
                    continue
                
                self.logger.info(f"Running scheduled check: {check.name}")
                await self.run_scheduled_check(check_id)
    
    async def run_check(self, check_type: str, target_name: str, expected_state: str,
                       actions: Dict[str, bool], powershell_script: str = '',
                       email_recipients: str = '') -> Dict[str, Any]:
        """Run an adhoc check immediately"""
        try:
            # Get current state
            if check_type == 'service':
                current_state = await self._check_service_state(target_name)
            else:
                current_state = await self._check_process_state(target_name)
            
            # Determine if check passed
            if expected_state == 'any':
                status = 'pass'
            elif expected_state == current_state:
                status = 'pass'
            else:
                status = 'fail'
            
            actions_taken = []
            message = ''
            
            # Take actions if check failed
            if status == 'fail':
                if actions.get('start_service') and check_type == 'service' and current_state == 'stopped':
                    success = await self._start_service(target_name)
                    actions_taken.append('start_service: ' + ('success' if success else 'failed'))
                    if success:
                        current_state = 'running'
                        message = f"Service {target_name} started successfully"
                
                if actions.get('stop_service') and check_type == 'service' and current_state == 'running':
                    success = await self._stop_service(target_name)
                    actions_taken.append('stop_service: ' + ('success' if success else 'failed'))
                    if success:
                        current_state = 'stopped'
                        message = f"Service {target_name} stopped successfully"
                
                if actions.get('run_script') and powershell_script:
                    success, output = await self._run_powershell(powershell_script, target_name)
                    actions_taken.append('run_script: ' + ('success' if success else 'failed'))
                    if output:
                        message = output[:200]
                
                if actions.get('send_email') and email_recipients:
                    await self._send_alert_email(
                        check_type, target_name, expected_state, current_state, email_recipients
                    )
                    actions_taken.append('email_sent')
            
            # Log the check result
            self._log_check_result(
                None, check_type, target_name, expected_state, current_state,
                status, actions_taken, message
            )
            
            return {
                'success': True,
                'check_type': check_type,
                'target_name': target_name,
                'expected_state': expected_state,
                'current_state': current_state,
                'status': status,
                'actions_taken': actions_taken,
                'message': message
            }
            
        except Exception as e:
            self.logger.error(f"Error running adhoc check: {e}")
            return {
                'success': False,
                'check_type': check_type,
                'target_name': target_name,
                'expected_state': expected_state,
                'current_state': 'error',
                'status': 'error',
                'actions_taken': [],
                'message': str(e)
            }
    
    async def schedule_check(self, name: str, check_type: str, target_name: str,
                            expected_state: str, schedule: Dict[str, str],
                            actions: Dict[str, bool], powershell_script: str = '',
                            email_recipients: str = '') -> Dict[str, Any]:
        """Schedule a new adhoc check"""
        try:
            check_id = str(uuid.uuid4())[:8]
            
            check = ScheduledCheck(
                id=check_id,
                name=name,
                check_type=check_type,
                target_name=target_name,
                expected_state=expected_state,
                schedule=schedule,
                actions=actions,
                powershell_script=powershell_script,
                email_recipients=email_recipients
            )
            
            # Save to database
            self.db.execute("""
                INSERT INTO adhoc_checks 
                (id, name, check_type, target_name, expected_state, schedule, actions, 
                 powershell_script, email_recipients, enabled, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                check.id, check.name, check.check_type, check.target_name,
                check.expected_state, json.dumps(check.schedule), json.dumps(check.actions),
                check.powershell_script, check.email_recipients, 1, 
                check.created_at.isoformat()
            ))
            self.db.commit()
            
            # Add to in-memory dict
            self.scheduled_checks[check_id] = check
            
            self.logger.info(f"Scheduled check '{name}' created with ID {check_id}")
            
            return {
                'success': True,
                'id': check_id,
                'message': f"Check '{name}' scheduled successfully"
            }
            
        except Exception as e:
            self.logger.error(f"Error scheduling check: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_scheduled_checks(self) -> List[Dict[str, Any]]:
        """Get all scheduled checks"""
        checks = []
        for check_id, check in self.scheduled_checks.items():
            checks.append({
                'id': check.id,
                'name': check.name,
                'check_type': check.check_type,
                'target_name': check.target_name,
                'expected_state': check.expected_state,
                'schedule': check.schedule,
                'actions': check.actions,
                'last_run': check.last_run.isoformat() if check.last_run else None,
                'last_status': check.last_status,
                'enabled': check.enabled
            })
        return checks
    
    async def delete_scheduled_check(self, check_id: str) -> bool:
        """Delete a scheduled check"""
        try:
            if check_id in self.scheduled_checks:
                del self.scheduled_checks[check_id]
            
            self.db.execute("DELETE FROM adhoc_checks WHERE id = ?", (check_id,))
            self.db.commit()
            
            self.logger.info(f"Deleted scheduled check {check_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error deleting scheduled check: {e}")
            return False
    
    async def run_scheduled_check(self, check_id: str) -> Optional[Dict[str, Any]]:
        """Run a specific scheduled check"""
        check = self.scheduled_checks.get(check_id)
        if not check:
            return None
        
        result = await self.run_check(
            check_type=check.check_type,
            target_name=check.target_name,
            expected_state=check.expected_state,
            actions=check.actions,
            powershell_script=check.powershell_script,
            email_recipients=check.email_recipients
        )
        
        # Update check status
        check.last_run = datetime.now()
        check.last_status = result.get('status', 'error')
        
        # Update database
        self.db.execute("""
            UPDATE adhoc_checks SET last_run = ?, last_status = ? WHERE id = ?
        """, (check.last_run.isoformat(), check.last_status, check_id))
        self.db.commit()
        
        return result
    
    async def _check_service_state(self, service_name: str) -> str:
        """Check the current state of a Windows service"""
        def _check():
            try:
                import win32serviceutil
                import win32service
                
                status = win32serviceutil.QueryServiceStatus(service_name)
                state = status[1]
                
                if state == win32service.SERVICE_RUNNING:
                    return 'running'
                elif state == win32service.SERVICE_STOPPED:
                    return 'stopped'
                elif state == win32service.SERVICE_PAUSED:
                    return 'paused'
                else:
                    return 'unknown'
            except Exception:
                return 'error'
        
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _check)
        except Exception as e:
            self.logger.error(f"Error checking service state: {e}")
            return 'error'

    async def _check_process_state(self, process_name: str) -> str:
        """Check if a process is running"""
        def _check():
            try:
                import psutil
                
                for proc in psutil.process_iter(['name']):
                    if proc.info['name'] and proc.info['name'].lower() == process_name.lower():
                        return 'running'
                
                return 'stopped'
            except Exception:
                return 'error'
        
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _check)
        except Exception as e:
            self.logger.error(f"Error checking process state: {e}")
            return 'error'

    async def _start_service(self, service_name: str) -> bool:
        """Start a Windows service"""
        def _start():
            try:
                import win32serviceutil
                win32serviceutil.StartService(service_name)
                return True
            except Exception:
                return False
        
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _start)
            if result:
                await asyncio.sleep(3)  # Wait for service to start
            return result
        except Exception as e:
            self.logger.error(f"Error starting service {service_name}: {e}")
            return False
    
    async def _stop_service(self, service_name: str) -> bool:
        """Stop a Windows service"""
        def _stop():
            try:
                import win32serviceutil
                win32serviceutil.StopService(service_name)
                return True
            except Exception:
                return False
        
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _stop)
            if result:
                await asyncio.sleep(3)  # Wait for service to stop
            return result
        except Exception as e:
            self.logger.error(f"Error stopping service {service_name}: {e}")
            return False
    
    async def _run_powershell(self, script: str, target_name: str) -> tuple:
        """Run a PowerShell script"""
        try:
            # Replace placeholder variables
            script = script.replace('$TARGET_NAME', target_name)
            script = script.replace('$SERVICE_NAME', target_name)
            
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: subprocess.run(
                ['powershell', '-ExecutionPolicy', 'Bypass', '-Command', script],
                capture_output=True, text=True, timeout=60
            ))
            
            success = result.returncode == 0
            output = result.stdout if success else result.stderr
            
            return success, output
        except Exception as e:
            self.logger.error(f"Error running PowerShell script: {e}")
            return False, str(e)
    
    async def _send_alert_email(self, check_type: str, target_name: str,
                               expected_state: str, current_state: str,
                               recipients: str):
        """Send an alert email"""
        try:
            recipient_list = [r.strip() for r in recipients.split(',') if r.strip()]
            if not recipient_list:
                return
            
            subject = f"WinSentry Alert: {check_type.title()} Check Failed - {target_name}"
            body = f"""
Adhoc Check Alert

Type: {check_type.title()}
Target: {target_name}
Expected State: {expected_state}
Current State: {current_state}

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

This is an automated alert from WinSentry.
"""
            
            await self.email_alert.send_email(recipient_list, subject, body)
            self.logger.info(f"Alert email sent to {recipients}")
        except Exception as e:
            self.logger.error(f"Failed to send alert email: {e}")
    
    def _log_check_result(self, check_id: Optional[str], check_type: str, target_name: str,
                         expected_state: str, current_state: str, status: str,
                         actions_taken: List[str], message: str):
        """Log check result to database"""
        try:
            self.db.execute("""
                INSERT INTO adhoc_check_logs
                (check_id, check_type, target_name, expected_state, current_state, 
                 status, actions_taken, message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                check_id, check_type, target_name, expected_state, current_state,
                status, json.dumps(actions_taken), message
            ))
            self.db.commit()
        except Exception as e:
            self.logger.error(f"Failed to log check result: {e}")
