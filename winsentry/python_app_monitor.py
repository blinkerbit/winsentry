"""
Python Application Monitoring for WinSentry

Monitors Python applications by:
- Start script path and working directory
- Automatic restart on failure (up to 3 attempts)
- Email alerts for restart success/failure
"""

import asyncio
import logging
import os
import subprocess
import signal
import psutil
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class AppStatus(Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    STARTING = "starting"
    RESTARTING = "restarting"
    FAILED = "failed"


@dataclass
class PythonAppConfig:
    """Configuration for Python application monitoring"""
    app_id: str  # Unique identifier for the app
    name: str  # Display name
    script_path: str  # Path to the Python script or start command
    working_directory: str  # Working directory for the app
    python_executable: str = "python"  # Python interpreter path
    arguments: str = ""  # Additional command line arguments
    interval: int = 30  # Check interval in seconds
    max_restart_attempts: int = 3  # Maximum restart attempts before giving up
    restart_delay: int = 5  # Delay between restart attempts in seconds
    enabled: bool = True
    
    # Runtime state
    pid: Optional[int] = None
    status: AppStatus = AppStatus.STOPPED
    last_check: Optional[datetime] = None
    last_started: Optional[datetime] = None
    restart_count: int = 0
    failure_count: int = 0
    
    # Email alert configuration
    email_alerts_enabled: bool = True
    email_recipients: List[str] = field(default_factory=list)


class PythonAppMonitor:
    """Monitors Python applications and manages their lifecycle"""
    
    def __init__(self, db_path: str = "winsentry.db"):
        self.logger = logging.getLogger(__name__)
        self.db_path = db_path
        self.monitored_apps: Dict[str, PythonAppConfig] = {}
        self.monitoring_tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        self._main_task: Optional[asyncio.Task] = None
        
        # Import email alert lazily
        self.email_alert = None
        
        # Load configurations from database
        self._load_configurations()
    
    def _get_email_alert(self):
        """Get or create EmailAlert instance"""
        if self.email_alert is None:
            from .email_alert import EmailAlert
            self.email_alert = EmailAlert(self.db_path)
        return self.email_alert
    
    def _load_configurations(self):
        """Load Python app configurations from database"""
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Ensure table exists
            self._ensure_tables_exist(cursor, conn)
            
            cursor.execute('''
                SELECT app_id, name, script_path, working_directory, python_executable,
                       arguments, interval_seconds, max_restart_attempts, restart_delay,
                       enabled, email_alerts_enabled, email_recipients
                FROM python_app_configs
            ''')
            
            for row in cursor.fetchall():
                app_id = row[0]
                recipients = row[11].split(',') if row[11] else []
                
                self.monitored_apps[app_id] = PythonAppConfig(
                    app_id=app_id,
                    name=row[1],
                    script_path=row[2],
                    working_directory=row[3],
                    python_executable=row[4] or "python",
                    arguments=row[5] or "",
                    interval=row[6],
                    max_restart_attempts=row[7],
                    restart_delay=row[8],
                    enabled=bool(row[9]),
                    email_alerts_enabled=bool(row[10]),
                    email_recipients=recipients
                )
                
                self.logger.info(f"Loaded Python app config: {app_id} ({row[1]})")
            
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Failed to load Python app configurations: {e}")
    
    def _ensure_tables_exist(self, cursor, conn):
        """Ensure required database tables exist"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS python_app_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                script_path TEXT NOT NULL,
                working_directory TEXT NOT NULL,
                python_executable TEXT DEFAULT 'python',
                arguments TEXT,
                interval_seconds INTEGER NOT NULL DEFAULT 30,
                max_restart_attempts INTEGER DEFAULT 3,
                restart_delay INTEGER DEFAULT 5,
                enabled BOOLEAN NOT NULL DEFAULT 1,
                email_alerts_enabled BOOLEAN DEFAULT 1,
                email_recipients TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS python_app_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id TEXT NOT NULL,
                status TEXT NOT NULL,
                pid INTEGER,
                restart_count INTEGER DEFAULT 0,
                message TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (app_id) REFERENCES python_app_configs (app_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS python_app_status (
                app_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                pid INTEGER,
                last_check TIMESTAMP,
                last_started TIMESTAMP,
                restart_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                FOREIGN KEY (app_id) REFERENCES python_app_configs (app_id)
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_python_app_logs_app_id ON python_app_logs(app_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_python_app_logs_timestamp ON python_app_logs(timestamp)')
        
        conn.commit()
    
    async def add_app(self, app_id: str, name: str, script_path: str, 
                      working_directory: str, python_executable: str = "python",
                      arguments: str = "", interval: int = 30,
                      max_restart_attempts: int = 3, restart_delay: int = 5,
                      email_alerts_enabled: bool = True, 
                      email_recipients: List[str] = None) -> bool:
        """Add a Python application to monitor"""
        try:
            # Validate paths
            if not os.path.isabs(script_path):
                script_path = os.path.join(working_directory, script_path)
            
            if not os.path.exists(script_path):
                self.logger.error(f"Script not found: {script_path}")
                return False
            
            if not os.path.isdir(working_directory):
                self.logger.error(f"Working directory not found: {working_directory}")
                return False
            
            recipients = email_recipients or []
            
            # Save to database
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            self._ensure_tables_exist(cursor, conn)
            
            cursor.execute('''
                INSERT OR REPLACE INTO python_app_configs 
                (app_id, name, script_path, working_directory, python_executable,
                 arguments, interval_seconds, max_restart_attempts, restart_delay,
                 enabled, email_alerts_enabled, email_recipients, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, CURRENT_TIMESTAMP)
            ''', (app_id, name, script_path, working_directory, python_executable,
                  arguments, interval, max_restart_attempts, restart_delay,
                  email_alerts_enabled, ','.join(recipients)))
            
            conn.commit()
            conn.close()
            
            # Add to monitored apps
            self.monitored_apps[app_id] = PythonAppConfig(
                app_id=app_id,
                name=name,
                script_path=script_path,
                working_directory=working_directory,
                python_executable=python_executable,
                arguments=arguments,
                interval=interval,
                max_restart_attempts=max_restart_attempts,
                restart_delay=restart_delay,
                email_alerts_enabled=email_alerts_enabled,
                email_recipients=recipients
            )
            
            # Start monitoring if running
            if self._running:
                await self._start_app_monitoring(app_id)
            
            self.logger.info(f"Added Python app to monitor: {app_id} ({name})")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add Python app: {e}")
            return False
    
    async def remove_app(self, app_id: str) -> bool:
        """Remove a Python application from monitoring"""
        try:
            # Stop monitoring
            await self._stop_app_monitoring(app_id)
            
            # Remove from database
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM python_app_configs WHERE app_id = ?', (app_id,))
            cursor.execute('DELETE FROM python_app_logs WHERE app_id = ?', (app_id,))
            cursor.execute('DELETE FROM python_app_status WHERE app_id = ?', (app_id,))
            
            conn.commit()
            conn.close()
            
            # Remove from memory
            if app_id in self.monitored_apps:
                del self.monitored_apps[app_id]
            
            self.logger.info(f"Removed Python app from monitoring: {app_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to remove Python app: {e}")
            return False
    
    async def is_app_running_async(self, app_id: str) -> bool:
        """Check if a Python application is running (async version)"""
        def _check():
            if app_id not in self.monitored_apps:
                return False
            
            app = self.monitored_apps[app_id]
            if app.pid is None:
                return False
            
            try:
                process = psutil.Process(app.pid)
                return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return False
        
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _check)
        except Exception:
            return False
    
    def is_app_running(self, app_id: str) -> bool:
        """Check if a Python application is running (sync version)"""
        if app_id not in self.monitored_apps:
            return False
        
        app = self.monitored_apps[app_id]
        if app.pid is None:
            return False
        
        try:
            process = psutil.Process(app.pid)
            return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False
    
    async def _find_app_process_async(self, app: PythonAppConfig) -> Optional[int]:
        """Find the PID of a running Python app by its script path (async)"""
        def _find():
            try:
                script_name = os.path.basename(app.script_path)
                
                for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cwd']):
                    try:
                        info = proc.info
                        cmdline = info.get('cmdline') or []
                        
                        # Check if this is a Python process running our script
                        if len(cmdline) >= 2:
                            if 'python' in cmdline[0].lower():
                                for arg in cmdline[1:]:
                                    if script_name in arg or app.script_path in arg:
                                        return info['pid']
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                
                return None
                
            except Exception as e:
                return None
        
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _find)
        except Exception as e:
            self.logger.error(f"Error finding app process: {e}")
            return None
    
    def _find_app_process(self, app: PythonAppConfig) -> Optional[int]:
        """Find the PID of a running Python app by its script path (sync version)"""
        try:
            script_name = os.path.basename(app.script_path)
            
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cwd']):
                try:
                    info = proc.info
                    cmdline = info.get('cmdline') or []
                    
                    # Check if this is a Python process running our script
                    if len(cmdline) >= 2:
                        if 'python' in cmdline[0].lower():
                            for arg in cmdline[1:]:
                                if script_name in arg or app.script_path in arg:
                                    return info['pid']
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error finding app process: {e}")
            return None
    
    async def start_app(self, app_id: str) -> Dict:
        """Start a Python application"""
        if app_id not in self.monitored_apps:
            return {'success': False, 'message': f'App {app_id} not found'}
        
        app = self.monitored_apps[app_id]
        
        try:
            # Check if already running
            if await self.is_app_running_async(app_id):
                return {'success': True, 'message': f'App {app.name} is already running', 'pid': app.pid}
            
            # Build command
            cmd = [app.python_executable, app.script_path]
            if app.arguments:
                cmd.extend(app.arguments.split())
            
            # Start process in executor to avoid blocking
            def _start():
                try:
                    process = subprocess.Popen(
                        cmd,
                        cwd=app.working_directory,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
                    )
                    return process
                except Exception as e:
                    return str(e)
            
            self.logger.info(f"Starting app {app.name}: {' '.join(cmd)}")
            
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _start)
            
            if isinstance(result, str):
                return {'success': False, 'message': f'App failed to start: {result}'}
            
            process = result
            
            # Wait briefly to see if it started successfully
            await asyncio.sleep(2)
            
            if process.poll() is None:
                # Process is still running
                app.pid = process.pid
                app.status = AppStatus.RUNNING
                app.last_started = datetime.now()
                app.restart_count = 0
                
                self._update_app_status(app)
                self._log_app_event(app_id, 'started', app.pid, 0, f'App started successfully')
                
                return {'success': True, 'message': f'App {app.name} started', 'pid': app.pid}
            else:
                # Process exited immediately
                stderr = process.stderr.read().decode() if process.stderr else ''
                return {'success': False, 'message': f'App failed to start: {stderr}'}
            
        except Exception as e:
            self.logger.error(f"Failed to start app {app_id}: {e}")
            return {'success': False, 'message': str(e)}
    
    async def stop_app(self, app_id: str, force: bool = False) -> Dict:
        """Stop a Python application"""
        if app_id not in self.monitored_apps:
            return {'success': False, 'message': f'App {app_id} not found'}
        
        app = self.monitored_apps[app_id]
        
        if app.pid is None:
            return {'success': True, 'message': f'App {app.name} is not running'}
        
        def _stop():
            try:
                process = psutil.Process(app.pid)
                
                if force:
                    process.kill()
                else:
                    process.terminate()
                
                # Wait for process to end
                process.wait(timeout=10)
                return True
                
            except psutil.NoSuchProcess:
                return True
            except psutil.TimeoutExpired:
                # Force kill if graceful shutdown failed
                try:
                    process.kill()
                    return True
                except:
                    return False
            except Exception as e:
                return str(e)
        
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _stop)
            
            app.pid = None
            app.status = AppStatus.STOPPED
            
            self._update_app_status(app)
            self._log_app_event(app_id, 'stopped', None, 0, 'App stopped')
            
            if result is True:
                return {'success': True, 'message': f'App {app.name} stopped'}
            else:
                return {'success': False, 'message': f'Error stopping app: {result}'}
            
        except Exception as e:
            self.logger.error(f"Failed to stop app {app_id}: {e}")
            return {'success': False, 'message': str(e)}
    
    async def restart_app(self, app_id: str) -> Dict:
        """Restart a Python application"""
        await self.stop_app(app_id)
        await asyncio.sleep(2)
        return await self.start_app(app_id)
    
    async def _attempt_restart(self, app: PythonAppConfig) -> bool:
        """Attempt to restart an app with retry logic"""
        app.status = AppStatus.RESTARTING
        
        for attempt in range(1, app.max_restart_attempts + 1):
            app.restart_count = attempt
            self.logger.info(f"Restart attempt {attempt}/{app.max_restart_attempts} for {app.name}")
            
            self._log_app_event(
                app.app_id, 'restart_attempt', None, attempt,
                f'Restart attempt {attempt}/{app.max_restart_attempts}'
            )
            
            result = await self.start_app(app.app_id)
            
            if result['success']:
                # Send success email
                await self._send_restart_email(app, attempt, True)
                return True
            
            # Wait before next attempt
            if attempt < app.max_restart_attempts:
                await asyncio.sleep(app.restart_delay)
        
        # All attempts failed
        app.status = AppStatus.FAILED
        app.failure_count += 1
        self._update_app_status(app)
        
        self._log_app_event(
            app.app_id, 'restart_failed', None, app.max_restart_attempts,
            f'All {app.max_restart_attempts} restart attempts failed'
        )
        
        # Send failure email
        await self._send_restart_email(app, app.max_restart_attempts, False)
        
        return False
    
    async def _send_restart_email(self, app: PythonAppConfig, attempts: int, success: bool):
        """Send email notification about restart attempt"""
        if not app.email_alerts_enabled or not app.email_recipients:
            return
        
        try:
            email_alert = self._get_email_alert()
            
            status = "SUCCESS" if success else "FAILED"
            subject = f"WinSentry: Python App Restart {status} - {app.name}"
            
            body = f"""
            Python Application Restart Notification
            
            Application: {app.name}
            App ID: {app.app_id}
            Status: {status}
            Restart Attempts: {attempts}/{app.max_restart_attempts}
            Script: {app.script_path}
            Working Directory: {app.working_directory}
            Time: {datetime.now().isoformat()}
            
            {'The application has been successfully restarted.' if success else 
             'All restart attempts have failed. Manual intervention may be required.'}
            """
            
            await email_alert.send_alert_email(
                port=0,  # Not port-related
                recipients=app.email_recipients,
                template_name='python_app_restart',
                custom_data={
                    'app_name': app.name,
                    'app_id': app.app_id,
                    'status': status,
                    'attempts': attempts,
                    'max_attempts': app.max_restart_attempts,
                    'script_path': app.script_path,
                    'working_directory': app.working_directory,
                    'success': success,
                    'subject': subject,
                    'body': body
                }
            )
            
        except Exception as e:
            self.logger.error(f"Failed to send restart email for {app.name}: {e}")
    
    async def check_app(self, app_id: str) -> Dict:
        """Check the status of a Python application"""
        if app_id not in self.monitored_apps:
            return {'success': False, 'message': f'App {app_id} not found'}
        
        app = self.monitored_apps[app_id]
        app.last_check = datetime.now()
        
        was_running = app.status == AppStatus.RUNNING
        is_running = await self.is_app_running_async(app_id)
        
        if not is_running and app.pid is not None:
            # Try to find the process if PID is stale
            found_pid = await self._find_app_process_async(app)
            if found_pid:
                app.pid = found_pid
                is_running = True
        
        if is_running:
            app.status = AppStatus.RUNNING
            self._update_app_status(app)
            self._log_app_event(app_id, 'running', app.pid, 0, 'App is running')
            
            return {
                'success': True,
                'status': 'running',
                'pid': app.pid,
                'app_name': app.name
            }
        else:
            # App is not running
            if was_running or app.status == AppStatus.RUNNING:
                # App stopped unexpectedly
                self.logger.warning(f"App {app.name} stopped unexpectedly, attempting restart")
                
                self._log_app_event(app_id, 'stopped_unexpectedly', None, 0, 
                                   'App stopped unexpectedly')
                
                # Attempt restart
                restart_success = await self._attempt_restart(app)
                
                return {
                    'success': restart_success,
                    'status': 'restarted' if restart_success else 'failed',
                    'pid': app.pid if restart_success else None,
                    'app_name': app.name,
                    'restart_attempts': app.restart_count
                }
            else:
                # App was already stopped
                app.status = AppStatus.STOPPED
                self._update_app_status(app)
                
                return {
                    'success': True,
                    'status': 'stopped',
                    'pid': None,
                    'app_name': app.name
                }
    
    def _update_app_status(self, app: PythonAppConfig):
        """Update app status in database"""
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO python_app_status 
                (app_id, status, pid, last_check, last_started, restart_count, failure_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (app.app_id, app.status.value, app.pid, 
                  app.last_check.isoformat() if app.last_check else None,
                  app.last_started.isoformat() if app.last_started else None,
                  app.restart_count, app.failure_count))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Failed to update app status: {e}")
    
    def _log_app_event(self, app_id: str, status: str, pid: Optional[int], 
                       restart_count: int, message: str):
        """Log an app event to database"""
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO python_app_logs (app_id, status, pid, restart_count, message)
                VALUES (?, ?, ?, ?, ?)
            ''', (app_id, status, pid, restart_count, message))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Failed to log app event: {e}")
    
    async def _start_app_monitoring(self, app_id: str):
        """Start monitoring for a specific app"""
        if app_id in self.monitoring_tasks:
            return
        
        app = self.monitored_apps.get(app_id)
        if not app or not app.enabled:
            return
        
        async def monitoring_loop():
            while self._running and app_id in self.monitored_apps:
                try:
                    app = self.monitored_apps[app_id]
                    if app.enabled:
                        await self.check_app(app_id)
                    await asyncio.sleep(app.interval)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self.logger.error(f"Error in monitoring loop for {app_id}: {e}")
                    await asyncio.sleep(30)
        
        task = asyncio.create_task(monitoring_loop())
        self.monitoring_tasks[app_id] = task
        self.logger.info(f"Started monitoring for app: {app_id}")
    
    async def _stop_app_monitoring(self, app_id: str):
        """Stop monitoring for a specific app"""
        if app_id in self.monitoring_tasks:
            self.monitoring_tasks[app_id].cancel()
            try:
                await self.monitoring_tasks[app_id]
            except asyncio.CancelledError:
                pass
            del self.monitoring_tasks[app_id]
            self.logger.info(f"Stopped monitoring for app: {app_id}")
    
    async def start_monitoring(self):
        """Start monitoring all configured apps"""
        self._running = True
        self.logger.info("Starting Python app monitoring")
        
        for app_id in self.monitored_apps:
            await self._start_app_monitoring(app_id)
    
    async def stop_monitoring(self):
        """Stop all monitoring"""
        self._running = False
        
        for app_id in list(self.monitoring_tasks.keys()):
            await self._stop_app_monitoring(app_id)
        
        self.logger.info("Stopped Python app monitoring")
    
    def get_monitored_apps(self) -> List[Dict]:
        """Get list of all monitored apps with their status"""
        apps = []
        
        for app_id, app in self.monitored_apps.items():
            apps.append({
                'app_id': app.app_id,
                'name': app.name,
                'script_path': app.script_path,
                'working_directory': app.working_directory,
                'python_executable': app.python_executable,
                'arguments': app.arguments,
                'interval': app.interval,
                'max_restart_attempts': app.max_restart_attempts,
                'restart_delay': app.restart_delay,
                'enabled': app.enabled,
                'status': app.status.value,
                'pid': app.pid,
                'last_check': app.last_check.isoformat() if app.last_check else None,
                'last_started': app.last_started.isoformat() if app.last_started else None,
                'restart_count': app.restart_count,
                'failure_count': app.failure_count,
                'email_alerts_enabled': app.email_alerts_enabled,
                'email_recipients': app.email_recipients
            })
        
        return apps
    
    def get_app_logs(self, app_id: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Get app monitoring logs"""
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if app_id:
                cursor.execute('''
                    SELECT app_id, status, pid, restart_count, message, timestamp
                    FROM python_app_logs WHERE app_id = ?
                    ORDER BY timestamp DESC LIMIT ?
                ''', (app_id, limit))
            else:
                cursor.execute('''
                    SELECT app_id, status, pid, restart_count, message, timestamp
                    FROM python_app_logs
                    ORDER BY timestamp DESC LIMIT ?
                ''', (limit,))
            
            logs = []
            for row in cursor.fetchall():
                logs.append({
                    'app_id': row['app_id'],
                    'status': row['status'],
                    'pid': row['pid'],
                    'restart_count': row['restart_count'],
                    'message': row['message'],
                    'timestamp': row['timestamp']
                })
            
            conn.close()
            return logs
            
        except Exception as e:
            self.logger.error(f"Failed to get app logs: {e}")
            return []
