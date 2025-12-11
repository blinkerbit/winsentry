"""
Scheduled Task Manager for WinSentry

Provides cron-like scheduling for:
- Script execution
- Command execution
- Service status checks
With email notifications
"""

import asyncio
import logging
import subprocess
import os
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import re

logger = logging.getLogger(__name__)


class ScheduleType(Enum):
    INTERVAL = "interval"  # Run every X seconds/minutes/hours
    CRON = "cron"  # Cron-like expression
    ONCE = "once"  # Run once at specified time
    DAILY = "daily"  # Run daily at specified time


@dataclass
class ScheduledTask:
    """Configuration for a scheduled task"""
    task_id: str
    name: str
    schedule_type: ScheduleType
    schedule_value: str  # e.g., "300" for interval, "0 9 * * *" for cron, "09:00" for daily
    
    # Task definition (one of these should be set)
    script_path: Optional[str] = None  # Path to script file
    command: Optional[str] = None  # Direct command to run
    powershell_script: Optional[str] = None  # PowerShell commands
    
    working_directory: Optional[str] = None
    enabled: bool = True
    
    # Email configuration
    email_on_success: bool = False
    email_on_failure: bool = True
    email_recipients: List[str] = field(default_factory=list)
    
    # Runtime state
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    last_result: Optional[str] = None
    last_output: Optional[str] = None
    run_count: int = 0
    failure_count: int = 0


class ScheduledTaskManager:
    """Manages scheduled tasks with cron-like functionality"""
    
    def __init__(self, db_path: str = "winsentry.db"):
        self.logger = logging.getLogger(__name__)
        self.db_path = db_path
        self.tasks: Dict[str, ScheduledTask] = {}
        self.task_handles: Dict[str, asyncio.Task] = {}
        self._running = False
        self.email_alert = None
        
        self._load_configurations()
    
    def _get_email_alert(self):
        """Get or create EmailAlert instance"""
        if self.email_alert is None:
            from .email_alert import EmailAlert
            self.email_alert = EmailAlert(self.db_path)
        return self.email_alert
    
    def _load_configurations(self):
        """Load scheduled task configurations from database"""
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            self._ensure_tables_exist(cursor, conn)
            
            cursor.execute('''
                SELECT task_id, name, schedule_type, schedule_value, script_path,
                       command, powershell_script, working_directory, enabled,
                       email_on_success, email_on_failure, email_recipients
                FROM scheduled_tasks
            ''')
            
            for row in cursor.fetchall():
                task_id = row[0]
                recipients = row[11].split(',') if row[11] else []
                
                try:
                    schedule_type = ScheduleType(row[2])
                except ValueError:
                    schedule_type = ScheduleType.INTERVAL
                
                task = ScheduledTask(
                    task_id=task_id,
                    name=row[1],
                    schedule_type=schedule_type,
                    schedule_value=row[3],
                    script_path=row[4],
                    command=row[5],
                    powershell_script=row[6],
                    working_directory=row[7],
                    enabled=bool(row[8]),
                    email_on_success=bool(row[9]),
                    email_on_failure=bool(row[10]),
                    email_recipients=recipients
                )
                
                task.next_run = self._calculate_next_run(task)
                self.tasks[task_id] = task
                
                self.logger.info(f"Loaded scheduled task: {task_id} ({row[1]})")
            
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Failed to load scheduled task configurations: {e}")
    
    def _ensure_tables_exist(self, cursor, conn):
        """Ensure required database tables exist"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scheduled_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                schedule_type TEXT NOT NULL,
                schedule_value TEXT NOT NULL,
                script_path TEXT,
                command TEXT,
                powershell_script TEXT,
                working_directory TEXT,
                enabled BOOLEAN NOT NULL DEFAULT 1,
                email_on_success BOOLEAN DEFAULT 0,
                email_on_failure BOOLEAN DEFAULT 1,
                email_recipients TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scheduled_task_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                status TEXT NOT NULL,
                output TEXT,
                error TEXT,
                execution_time_ms INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES scheduled_tasks (task_id)
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_scheduled_task_logs_task_id ON scheduled_task_logs(task_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_scheduled_task_logs_timestamp ON scheduled_task_logs(timestamp)')
        
        conn.commit()
    
    def _calculate_next_run(self, task: ScheduledTask) -> Optional[datetime]:
        """Calculate the next run time for a task"""
        now = datetime.now()
        
        if task.schedule_type == ScheduleType.INTERVAL:
            # Parse interval in seconds
            try:
                interval = int(task.schedule_value)
                if task.last_run:
                    return task.last_run + timedelta(seconds=interval)
                return now + timedelta(seconds=interval)
            except ValueError:
                self.logger.error(f"Invalid interval value: {task.schedule_value}")
                return None
        
        elif task.schedule_type == ScheduleType.DAILY:
            # Parse time in HH:MM format
            try:
                hour, minute = map(int, task.schedule_value.split(':'))
                next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if next_run <= now:
                    next_run += timedelta(days=1)
                return next_run
            except ValueError:
                self.logger.error(f"Invalid daily time value: {task.schedule_value}")
                return None
        
        elif task.schedule_type == ScheduleType.CRON:
            # Simplified cron parsing (minute hour day month weekday)
            return self._parse_cron_next_run(task.schedule_value, now)
        
        elif task.schedule_type == ScheduleType.ONCE:
            # Parse datetime in ISO format
            try:
                return datetime.fromisoformat(task.schedule_value)
            except ValueError:
                self.logger.error(f"Invalid once datetime value: {task.schedule_value}")
                return None
        
        return None
    
    def _parse_cron_next_run(self, cron_expr: str, now: datetime) -> Optional[datetime]:
        """Parse a simplified cron expression and find next run time"""
        try:
            parts = cron_expr.strip().split()
            if len(parts) != 5:
                self.logger.error(f"Invalid cron expression: {cron_expr}")
                return None
            
            minute, hour, day, month, weekday = parts
            
            # Start from the next minute
            next_time = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
            
            # Try to find a matching time within the next year
            for _ in range(525600):  # Max 1 year of minutes
                if self._cron_matches(next_time, minute, hour, day, month, weekday):
                    return next_time
                next_time += timedelta(minutes=1)
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error parsing cron expression: {e}")
            return None
    
    def _cron_matches(self, dt: datetime, minute: str, hour: str, 
                      day: str, month: str, weekday: str) -> bool:
        """Check if a datetime matches a cron pattern"""
        def matches_field(field_value: int, pattern: str) -> bool:
            if pattern == '*':
                return True
            
            # Handle ranges (e.g., 1-5)
            if '-' in pattern:
                start, end = map(int, pattern.split('-'))
                return start <= field_value <= end
            
            # Handle step values (e.g., */5)
            if pattern.startswith('*/'):
                step = int(pattern[2:])
                return field_value % step == 0
            
            # Handle lists (e.g., 1,3,5)
            if ',' in pattern:
                values = list(map(int, pattern.split(',')))
                return field_value in values
            
            # Exact match
            try:
                return field_value == int(pattern)
            except ValueError:
                return False
        
        return (matches_field(dt.minute, minute) and
                matches_field(dt.hour, hour) and
                matches_field(dt.day, day) and
                matches_field(dt.month, month) and
                matches_field(dt.weekday(), weekday))
    
    async def add_task(self, task_id: str, name: str, schedule_type: str,
                       schedule_value: str, script_path: Optional[str] = None,
                       command: Optional[str] = None, powershell_script: Optional[str] = None,
                       working_directory: Optional[str] = None,
                       email_on_success: bool = False, email_on_failure: bool = True,
                       email_recipients: List[str] = None) -> bool:
        """Add a scheduled task"""
        try:
            if not script_path and not command and not powershell_script:
                self.logger.error("At least one of script_path, command, or powershell_script required")
                return False
            
            try:
                sched_type = ScheduleType(schedule_type)
            except ValueError:
                self.logger.error(f"Invalid schedule type: {schedule_type}")
                return False
            
            recipients = email_recipients or []
            
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            self._ensure_tables_exist(cursor, conn)
            
            cursor.execute('''
                INSERT OR REPLACE INTO scheduled_tasks 
                (task_id, name, schedule_type, schedule_value, script_path,
                 command, powershell_script, working_directory, enabled,
                 email_on_success, email_on_failure, email_recipients, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (task_id, name, schedule_type, schedule_value, script_path,
                  command, powershell_script, working_directory,
                  email_on_success, email_on_failure, ','.join(recipients)))
            
            conn.commit()
            conn.close()
            
            task = ScheduledTask(
                task_id=task_id,
                name=name,
                schedule_type=sched_type,
                schedule_value=schedule_value,
                script_path=script_path,
                command=command,
                powershell_script=powershell_script,
                working_directory=working_directory,
                email_on_success=email_on_success,
                email_on_failure=email_on_failure,
                email_recipients=recipients
            )
            
            task.next_run = self._calculate_next_run(task)
            self.tasks[task_id] = task
            
            # Start task if running
            if self._running:
                await self._start_task_scheduler(task_id)
            
            self.logger.info(f"Added scheduled task: {task_id} ({name})")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add scheduled task: {e}")
            return False
    
    async def remove_task(self, task_id: str) -> bool:
        """Remove a scheduled task"""
        try:
            await self._stop_task_scheduler(task_id)
            
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM scheduled_tasks WHERE task_id = ?', (task_id,))
            cursor.execute('DELETE FROM scheduled_task_logs WHERE task_id = ?', (task_id,))
            
            conn.commit()
            conn.close()
            
            if task_id in self.tasks:
                del self.tasks[task_id]
            
            self.logger.info(f"Removed scheduled task: {task_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to remove scheduled task: {e}")
            return False
    
    async def run_task(self, task_id: str) -> Dict:
        """Execute a task immediately"""
        if task_id not in self.tasks:
            return {'success': False, 'error': f'Task {task_id} not found'}
        
        task = self.tasks[task_id]
        start_time = datetime.now()
        
        try:
            output = ""
            error = ""
            success = False
            
            if task.script_path:
                # Run script file
                result = await self._run_script(task.script_path, task.working_directory)
                output = result.get('output', '')
                error = result.get('error', '')
                success = result.get('success', False)
                
            elif task.command:
                # Run shell command
                result = await self._run_command(task.command, task.working_directory)
                output = result.get('output', '')
                error = result.get('error', '')
                success = result.get('success', False)
                
            elif task.powershell_script:
                # Run PowerShell commands
                result = await self._run_powershell(task.powershell_script, task.working_directory)
                output = result.get('output', '')
                error = result.get('error', '')
                success = result.get('success', False)
            
            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
            
            # Update task state
            task.last_run = datetime.now()
            task.next_run = self._calculate_next_run(task)
            task.last_result = 'success' if success else 'failed'
            task.last_output = output or error
            task.run_count += 1
            
            if not success:
                task.failure_count += 1
            
            # Log the execution
            self._log_task_execution(task_id, 'success' if success else 'failed', 
                                     output, error, execution_time)
            
            # Send email if configured
            if success and task.email_on_success:
                await self._send_task_email(task, 'success', output)
            elif not success and task.email_on_failure:
                await self._send_task_email(task, 'failed', error or output)
            
            return {
                'success': success,
                'output': output,
                'error': error,
                'execution_time_ms': execution_time
            }
            
        except Exception as e:
            self.logger.error(f"Error running task {task_id}: {e}")
            task.failure_count += 1
            
            if task.email_on_failure:
                await self._send_task_email(task, 'error', str(e))
            
            return {'success': False, 'error': str(e)}
    
    async def _run_script(self, script_path: str, 
                          working_directory: Optional[str]) -> Dict:
        """Run a script file"""
        def _execute():
            try:
                cwd = working_directory or os.path.dirname(script_path)
                
                # Determine how to run based on extension
                ext = os.path.splitext(script_path)[1].lower()
                
                if ext == '.ps1':
                    cmd = ['powershell.exe', '-ExecutionPolicy', 'Bypass', '-File', script_path]
                elif ext == '.py':
                    cmd = ['python', script_path]
                elif ext == '.bat' or ext == '.cmd':
                    cmd = ['cmd.exe', '/c', script_path]
                else:
                    cmd = [script_path]
                
                result = subprocess.run(
                    cmd,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=3600,
                    encoding='utf-8',
                    errors='replace'
                )
                
                return {
                    'success': result.returncode == 0,
                    'output': result.stdout,
                    'error': result.stderr
                }
                
            except subprocess.TimeoutExpired:
                return {'success': False, 'error': 'Script execution timed out'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
        
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _execute)
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _run_command(self, command: str, 
                           working_directory: Optional[str]) -> Dict:
        """Run a shell command"""
        def _execute():
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    cwd=working_directory,
                    capture_output=True,
                    text=True,
                    timeout=3600,
                    encoding='utf-8',
                    errors='replace'
                )
                
                return {
                    'success': result.returncode == 0,
                    'output': result.stdout,
                    'error': result.stderr
                }
                
            except subprocess.TimeoutExpired:
                return {'success': False, 'error': 'Command execution timed out'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
        
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _execute)
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _run_powershell(self, script: str, 
                               working_directory: Optional[str]) -> Dict:
        """Run PowerShell commands"""
        def _execute():
            try:
                cmd = ['powershell.exe', '-ExecutionPolicy', 'Bypass', '-Command', script]
                
                result = subprocess.run(
                    cmd,
                    cwd=working_directory,
                    capture_output=True,
                    text=True,
                    timeout=3600,
                    encoding='utf-8',
                    errors='replace'
                )
                
                return {
                    'success': result.returncode == 0,
                    'output': result.stdout,
                    'error': result.stderr
                }
                
            except subprocess.TimeoutExpired:
                return {'success': False, 'error': 'PowerShell execution timed out'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
        
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _execute)
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _send_task_email(self, task: ScheduledTask, status: str, output: str):
        """Send email notification for task execution"""
        if not task.email_recipients:
            return
        
        try:
            email_alert = self._get_email_alert()
            
            subject = f"WinSentry: Scheduled Task {status.upper()} - {task.name}"
            
            body = f"""
            Scheduled Task Execution Report
            
            Task: {task.name}
            Task ID: {task.task_id}
            Status: {status.upper()}
            Schedule: {task.schedule_type.value} - {task.schedule_value}
            Executed: {datetime.now().isoformat()}
            
            Output:
            {output[:2000] if output else 'No output'}
            """
            
            await email_alert.send_alert_email(
                port=0,
                recipients=task.email_recipients,
                template_name='scheduled_task',
                custom_data={
                    'task_name': task.name,
                    'task_id': task.task_id,
                    'status': status,
                    'output': output[:2000] if output else '',
                    'subject': subject,
                    'body': body
                }
            )
            
        except Exception as e:
            self.logger.error(f"Failed to send task email: {e}")
    
    def _log_task_execution(self, task_id: str, status: str, output: str, 
                            error: str, execution_time: int):
        """Log task execution to database"""
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO scheduled_task_logs 
                (task_id, status, output, error, execution_time_ms)
                VALUES (?, ?, ?, ?, ?)
            ''', (task_id, status, output[:10000] if output else None, 
                  error[:10000] if error else None, execution_time))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Failed to log task execution: {e}")
    
    async def _task_scheduler_loop(self, task_id: str):
        """Scheduler loop for a single task"""
        while self._running and task_id in self.tasks:
            try:
                task = self.tasks[task_id]
                
                if not task.enabled:
                    await asyncio.sleep(60)
                    continue
                
                now = datetime.now()
                
                if task.next_run and now >= task.next_run:
                    self.logger.info(f"Running scheduled task: {task.name}")
                    await self.run_task(task_id)
                
                # Sleep until next check (every 10 seconds)
                await asyncio.sleep(10)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in task scheduler for {task_id}: {e}")
                await asyncio.sleep(60)
    
    async def _start_task_scheduler(self, task_id: str):
        """Start scheduler for a specific task"""
        if task_id in self.task_handles:
            return
        
        task = asyncio.create_task(self._task_scheduler_loop(task_id))
        self.task_handles[task_id] = task
        self.logger.info(f"Started scheduler for task: {task_id}")
    
    async def _stop_task_scheduler(self, task_id: str):
        """Stop scheduler for a specific task"""
        if task_id in self.task_handles:
            self.task_handles[task_id].cancel()
            try:
                await self.task_handles[task_id]
            except asyncio.CancelledError:
                pass
            del self.task_handles[task_id]
            self.logger.info(f"Stopped scheduler for task: {task_id}")
    
    async def start_monitoring(self):
        """Start all task schedulers"""
        self._running = True
        
        for task_id in self.tasks:
            await self._start_task_scheduler(task_id)
        
        self.logger.info("Started scheduled task monitoring")
    
    async def stop_monitoring(self):
        """Stop all task schedulers"""
        self._running = False
        
        for task_id in list(self.task_handles.keys()):
            await self._stop_task_scheduler(task_id)
        
        self.logger.info("Stopped scheduled task monitoring")
    
    def get_tasks(self) -> List[Dict]:
        """Get all scheduled tasks"""
        return [
            {
                'task_id': t.task_id,
                'name': t.name,
                'schedule_type': t.schedule_type.value,
                'schedule_value': t.schedule_value,
                'script_path': t.script_path,
                'command': t.command,
                'powershell_script': t.powershell_script,
                'working_directory': t.working_directory,
                'enabled': t.enabled,
                'email_on_success': t.email_on_success,
                'email_on_failure': t.email_on_failure,
                'email_recipients': t.email_recipients,
                'last_run': t.last_run.isoformat() if t.last_run else None,
                'next_run': t.next_run.isoformat() if t.next_run else None,
                'last_result': t.last_result,
                'run_count': t.run_count,
                'failure_count': t.failure_count
            }
            for t in self.tasks.values()
        ]
    
    def get_task_logs(self, task_id: Optional[str] = None, 
                      limit: int = 100) -> List[Dict]:
        """Get task execution logs"""
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if task_id:
                cursor.execute('''
                    SELECT task_id, status, output, error, execution_time_ms, timestamp
                    FROM scheduled_task_logs 
                    WHERE task_id = ?
                    ORDER BY timestamp DESC LIMIT ?
                ''', (task_id, limit))
            else:
                cursor.execute('''
                    SELECT task_id, status, output, error, execution_time_ms, timestamp
                    FROM scheduled_task_logs 
                    ORDER BY timestamp DESC LIMIT ?
                ''', (limit,))
            
            logs = []
            for row in cursor.fetchall():
                logs.append({
                    'task_id': row['task_id'],
                    'status': row['status'],
                    'output': row['output'],
                    'error': row['error'],
                    'execution_time_ms': row['execution_time_ms'],
                    'timestamp': row['timestamp']
                })
            
            conn.close()
            return logs
            
        except Exception as e:
            self.logger.error(f"Failed to get task logs: {e}")
            return []
