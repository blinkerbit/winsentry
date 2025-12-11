"""
Port monitoring functionality
"""

import asyncio
import logging
import os
import socket
import subprocess
import time
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime

from .database import Database
from .email_alert import EmailAlert

logger = logging.getLogger(__name__)


@dataclass
class PortConfig:
    """Configuration for port monitoring"""
    port: int
    interval: int = 30  # seconds
    powershell_script: Optional[str] = None
    powershell_commands: Optional[str] = None
    enabled: bool = True
    last_check: Optional[datetime] = None
    last_status: bool = False
    failure_count: int = 0
    
    # Recovery script configuration
    recovery_script_delay: int = 20  # Minimum seconds between recovery script executions (default 20 seconds)
    last_recovery_script_run: Optional[datetime] = None  # When recovery script was last executed


class PortMonitor:
    """Monitors ports for running processes"""
    
    def __init__(self, db_path: str = "winsentry.db"):
        self.logger = logging.getLogger(__name__)
        self.monitored_ports: Dict[int, PortConfig] = {}
        self.monitoring_task: Optional[asyncio.Task] = None
        self.port_tasks: Dict[int, asyncio.Task] = {}  # Individual port monitoring tasks
        self.running = False
        self.db = Database(db_path)
        self.email_alert = EmailAlert(db_path)
        
        # Load existing configurations from database
        self._load_configurations()
    
    def _load_configurations(self):
        """Load port configurations from database"""
        try:
            configs = self.db.get_all_port_configs()
            for config in configs:
                port_config = PortConfig(
                    port=config['port'],
                    interval=config['interval'],
                    powershell_script=config['powershell_script'],
                    powershell_commands=config['powershell_commands'],
                    enabled=config['enabled'],
                    recovery_script_delay=config.get('recovery_script_delay', 20)
                )
                self.monitored_ports[config['port']] = port_config
                self.logger.info(f"Loaded port configuration: {config['port']} (interval: {config['interval']}s)")
        except Exception as e:
            self.logger.error(f"Failed to load configurations: {e}")
    
    async def _create_port_monitoring_task(self, port: int) -> asyncio.Task:
        """Create an individual monitoring task for a specific port"""
        async def port_monitoring_loop():
            """Individual monitoring loop for a specific port"""
            config = self.monitored_ports.get(port)
            if not config:
                self.logger.warning(f"Port {port} configuration not found, stopping monitoring task")
                return
            
            self.logger.info(f"Starting individual monitoring task for port {port} (interval: {config.interval}s)")
            
            while self.running and port in self.monitored_ports and config.enabled:
                try:
                    await self.check_port(port)
                    await asyncio.sleep(config.interval)
                    self.logger.debug(f"Port {port} monitoring task slept for {config.interval} seconds")
                except asyncio.CancelledError:
                    self.logger.info(f"Port {port} monitoring task cancelled")
                    break
                except Exception as e:
                    self.logger.error(f"Error in port {port} monitoring task: {e}")
                    await asyncio.sleep(5)  # Wait before retrying
            
            self.logger.info(f"Port {port} monitoring task stopped")
        
        # Create and return the task
        task = asyncio.create_task(port_monitoring_loop())
        return task
    
    async def _start_port_monitoring(self, port: int):
        """Start individual monitoring for a specific port"""
        if port in self.port_tasks:
            # Stop existing task if it exists
            await self._stop_port_monitoring(port)
        
        # Create new monitoring task
        task = await self._create_port_monitoring_task(port)
        self.port_tasks[port] = task
        self.logger.info(f"Started individual monitoring for port {port}")
    
    async def _stop_port_monitoring(self, port: int):
        """Stop individual monitoring for a specific port"""
        if port in self.port_tasks:
            task = self.port_tasks[port]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            del self.port_tasks[port]
            self.logger.info(f"Stopped individual monitoring for port {port}")
        
    async def add_port(self, port: int, interval: int = 30, powershell_script: Optional[str] = None, powershell_commands: Optional[str] = None) -> bool:
        """Add a port to monitor"""
        try:
            # Validate PowerShell script path if provided
            if powershell_script:
                if not await self.validate_powershell_script(powershell_script):
                    return False
            
            # Save to database first
            if not self.db.save_port_config(port, interval, powershell_script, powershell_commands, True):
                return False
            
            config = PortConfig(
                port=port,
                interval=interval,
                powershell_script=powershell_script,
                powershell_commands=powershell_commands,
                enabled=True
            )
            self.monitored_ports[port] = config
            self.logger.info(f"Added port {port} to monitoring with interval {interval}s")
            if powershell_script:
                self.logger.info(f"PowerShell recovery script configured: {powershell_script}")
            
            # Start individual monitoring task for this port
            if self.running:
                await self._start_port_monitoring(port)
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to add port {port}: {e}")
            return False
    
    async def remove_port(self, port: int) -> bool:
        """Remove a port from monitoring"""
        try:
            # Stop individual monitoring task first
            await self._stop_port_monitoring(port)
            
            # Remove from database
            if not self.db.delete_port_config(port):
                return False
            
            if port in self.monitored_ports:
                del self.monitored_ports[port]
                self.logger.info(f"Removed port {port} from monitoring")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to remove port {port}: {e}")
            return False
    
    async def update_port_config(self, port: int, interval: Optional[int] = None, 
                                powershell_script: Optional[str] = None, 
                                powershell_commands: Optional[str] = None,
                                enabled: Optional[bool] = None) -> bool:
        """Update port monitoring configuration"""
        try:
            if port not in self.monitored_ports:
                return False
            
            config = self.monitored_ports[port]
            if interval is not None:
                config.interval = interval
            if powershell_script is not None:
                config.powershell_script = powershell_script
            if powershell_commands is not None:
                config.powershell_commands = powershell_commands
            if enabled is not None:
                config.enabled = enabled
            
            # Update in database
            if not self.db.save_port_config(port, config.interval, config.powershell_script, config.powershell_commands, config.enabled):
                return False
            
            # Restart monitoring task if interval changed or enabled status changed
            if (interval is not None or enabled is not None) and self.running:
                await self._start_port_monitoring(port)
            
            self.logger.info(f"Updated configuration for port {port}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to update port {port}: {e}")
            return False
    
    def _setup_unicode_environment(self) -> dict:
        """Setup environment variables for Unicode support"""
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONLEGACYWINDOWSSTDIO'] = '1'
        env['PYTHONUTF8'] = '1'
        return env
    
    async def _set_console_utf8(self) -> bool:
        """Set console code page to UTF-8"""
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(['chcp', '65001'], 
                                     capture_output=True, text=True, timeout=5)
            )
            return result.returncode == 0
        except Exception:
            return False

    async def validate_powershell_script(self, script_path: str) -> bool:
        """Validate PowerShell script path and file"""
        try:
            import os
            
            # Check if path is provided
            if not script_path or not script_path.strip():
                self.logger.error("PowerShell script path is empty")
                return False
            
            # Check if file exists
            if not os.path.exists(script_path):
                self.logger.error(f"PowerShell script not found: {script_path}")
                return False
            
            # Check if it's a .ps1 file
            if not script_path.lower().endswith('.ps1'):
                self.logger.error(f"PowerShell script must have .ps1 extension: {script_path}")
                return False
            
            # Check if it's a file (not directory)
            if not os.path.isfile(script_path):
                self.logger.error(f"PowerShell script path is not a file: {script_path}")
                return False
            
            # Check if file is readable
            if not os.access(script_path, os.R_OK):
                self.logger.error(f"PowerShell script is not readable: {script_path}")
                return False
            
            self.logger.info(f"PowerShell script validation successful: {script_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to validate PowerShell script {script_path}: {e}")
            return False

    async def is_port_in_use(self, port: int) -> bool:
        """Check if a port is in use"""
        def _check_port():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(2)
                    result = sock.connect_ex(('localhost', port))
                    return result == 0
            except Exception as e:
                return False
        
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _check_port)
            return result
        except Exception as e:
            self.logger.error(f"Error checking port {port}: {e}")
            return False
    
    async def execute_powershell_script(self, script_path: str, port: int) -> bool:
        """Execute a PowerShell script with port parameter"""
        try:
            if not script_path or not script_path.strip():
                return False
            
            # Check if script file exists
            import os
            if not os.path.exists(script_path):
                self.logger.error(f"PowerShell script not found: {script_path}")
                return False
            
            # Validate script extension
            if not script_path.lower().endswith('.ps1'):
                self.logger.error(f"PowerShell script must have .ps1 extension: {script_path}")
                return False
            
            # Execute PowerShell script in a separate thread to avoid blocking
            # Pass the port number as a parameter
            loop = asyncio.get_event_loop()
            
            # Setup Unicode environment
            env = self._setup_unicode_environment()
            
            # Try to set console to UTF-8
            await self._set_console_utf8()
            
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run([
                    'powershell.exe', 
                    '-ExecutionPolicy', 'Bypass', 
                    '-File', script_path,
                    '-Port', str(port)
                ], capture_output=True, text=True, timeout=30, encoding='utf-8', errors='replace', env=env)
            )
            
            if result.returncode == 0:
                self.logger.info(f"PowerShell script executed successfully for port {port}: {script_path}")
                if result.stdout:
                    self.logger.info(f"Script output: {result.stdout}")
                return True
            else:
                self.logger.error(f"PowerShell script failed for port {port} (exit code {result.returncode}): {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.error(f"PowerShell script timeout for port {port}: {script_path}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to execute PowerShell script for port {port} {script_path}: {e}")
            return False
    
    async def _create_unicode_powershell_script(self, commands: str, port: int) -> str:
        """Create a PowerShell script with Unicode support"""
        import tempfile
        
        script_content = f"""
# PowerShell script with Unicode support
param([int]$Port = {port})

# Set console to UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8

# Set environment variables for Python Unicode support
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONLEGACYWINDOWSSTDIO = "1"
$env:PYTHONUTF8 = "1"

# Execute the commands
{commands}
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ps1', delete=False, encoding='utf-8') as temp_file:
            temp_file.write(script_content)
            script_path = temp_file.name
        
        self.logger.debug(f"Created PowerShell script: {script_path}")
        self.logger.debug(f"Script content: {script_content[:200]}...")
        
        return script_path

    async def execute_powershell_commands(self, commands: str, port: int = 9999) -> dict:
        """Execute PowerShell commands directly and return output"""
        import time
        start_time = time.time()
        
        self.logger.info(f"Executing PowerShell commands for port {port}: {commands[:100]}...")
        
        try:
            # Create a Unicode-aware PowerShell script
            temp_script_path = await self._create_unicode_powershell_script(commands, port)
            
            try:
                # Setup Unicode environment
                env = self._setup_unicode_environment()
                
                # Try to set console to UTF-8
                await self._set_console_utf8()
                
                # Execute the temporary script
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: subprocess.run([
                        'powershell.exe', 
                        '-ExecutionPolicy', 'Bypass', 
                        '-File', temp_script_path,
                        '-Port', str(port)
                    ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60, env=env)
                )
                
                execution_time = int((time.time() - start_time) * 1000)
                
                self.logger.info(f"PowerShell execution completed for port {port}: exit_code={result.returncode}, stdout_length={len(result.stdout)}, stderr_length={len(result.stderr)}")
                
                return {
                    'success': result.returncode == 0,
                    'stdout': result.stdout,
                    'stderr': result.stderr,
                    'exit_code': result.returncode,
                    'execution_time': execution_time
                }
                
            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_script_path)
                except:
                    pass
                    
        except subprocess.TimeoutExpired:
            execution_time = int((time.time() - start_time) * 1000)
            self.logger.error(f"PowerShell execution timed out for port {port} after {execution_time}ms")
            return {
                'success': False,
                'stdout': '',
                'stderr': 'PowerShell command execution timed out after 60 seconds',
                'exit_code': -1,
                'execution_time': execution_time,
                'error': 'Command execution timeout'
            }
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            self.logger.error(f"PowerShell execution failed for port {port}: {e}")
            return {
                'success': False,
                'stdout': '',
                'stderr': str(e),
                'exit_code': -1,
                'execution_time': execution_time,
                'error': str(e)
            }
    
    async def check_port(self, port: int) -> bool:
        """Check if a specific port is in use"""
        config = self.monitored_ports.get(port)
        if not config or not config.enabled:
            return True
        
        is_used = await self.is_port_in_use(port)
        config.last_check = datetime.now()
        config.last_status = is_used
        
        # Determine status string
        status = "ONLINE" if is_used else "OFFLINE"
        
        self.logger.debug(f"Port {port} check: {status} at {config.last_check}")
        
        # Always update real-time status in database
        self.db.update_port_status(port, status, config.failure_count)
        
        if not is_used:
            config.failure_count += 1
            self.logger.warning(f"Port {port} is not in use (failure #{config.failure_count})")
            
            # Log to database
            self.db.log_port_check(port, "OFFLINE", config.failure_count, f"Port {port} is offline (failure #{config.failure_count})")
            
            # Get email configuration for this port
            email_config = self.email_alert.get_port_email_config(port)
            
            # Execute PowerShell script or commands after N failures
            # But only if enough time has passed since last recovery script run
            if config.failure_count >= email_config.get("powershell_script_failures", 3):
                # Check if we should wait before running recovery script again
                can_run_recovery = True
                if config.last_recovery_script_run:
                    seconds_since_last_run = (datetime.now() - config.last_recovery_script_run).total_seconds()
                    if seconds_since_last_run < config.recovery_script_delay:
                        remaining_wait = int(config.recovery_script_delay - seconds_since_last_run)
                        self.logger.info(f"Recovery script for port {port} on cooldown. Next run in {remaining_wait}s")
                        can_run_recovery = False
                
                if can_run_recovery:
                    # Prioritize script file path over inline commands
                    if config.powershell_script and config.powershell_script.strip():
                        # Use the .ps1 script file
                        config.last_recovery_script_run = datetime.now()
                        self.logger.info(f"Executing PowerShell script file for port {port}: {config.powershell_script}")
                        success = await self.execute_powershell_script(config.powershell_script, port)
                        if success:
                            self.logger.info(f"PowerShell script executed successfully for port {port}")
                        else:
                            self.logger.error(f"PowerShell script failed for port {port}")
                    elif config.powershell_commands and config.powershell_commands.strip():
                        # Use inline PowerShell commands as fallback
                        config.last_recovery_script_run = datetime.now()
                        self.logger.info(f"Executing inline PowerShell commands for port {port}")
                        result = await self.execute_powershell_commands(config.powershell_commands, port)
                        if result['success']:
                            self.logger.info(f"PowerShell commands executed successfully for port {port}")
                        else:
                            self.logger.error(f"PowerShell commands failed for port {port}: {result.get('stderr', 'Unknown error')}")
                    else:
                        self.logger.warning(f"No recovery script or commands configured for port {port}")
            
            # Send email alert after M failures
            if (email_config.get("enabled", False) and 
                config.failure_count >= email_config.get("email_alert_failures", 5) and
                email_config.get("recipients")):
                
                # Only send email if we haven't sent one recently (avoid spam)
                if not hasattr(config, 'last_email_sent') or \
                   (datetime.now() - config.last_email_sent).total_seconds() > 300:  # 5 minutes
                    
                    await self.email_alert.send_alert_email(
                        port=port,
                        recipients=email_config["recipients"],
                        template_name=email_config.get("template", "default"),
                        custom_data={
                            "failure_count": config.failure_count,
                            "message": f"Port {port} has been offline for {config.failure_count} consecutive checks"
                        }
                    )
                    config.last_email_sent = datetime.now()
        else:
            if config.failure_count > 0:
                # Port came back online
                self.db.log_port_check(port, "ONLINE", 0, f"Port {port} is back online")
                
                # Reset email sent flag
                if hasattr(config, 'last_email_sent'):
                    delattr(config, 'last_email_sent')
                    
            config.failure_count = 0
            
            # Check resource thresholds if port is online
            await self._check_port_resources(port)
        
        return is_used
    
    async def _check_port_resources(self, port: int):
        """Check resource usage for processes on a port"""
        try:
            # Get processes on the port
            processes = await self.get_processes_on_port(port)
            
            # Log process metrics
            for process in processes:
                self.db.log_process_metrics(
                    port=port,
                    pid=process['pid'],
                    process_name=process['name'],
                    cpu_percent=process['cpu_percent'],
                    memory_percent=process['memory_percent'],
                    memory_rss_bytes=process['memory_rss']
                )
            
            # Check thresholds
            threshold_result = await self.check_resource_thresholds(port)
            if threshold_result.get('exceeded', False):
                self.logger.warning(f"Resource thresholds exceeded for port {port}: {len(threshold_result.get('alerts', []))} alerts")
            
        except Exception as e:
            self.logger.error(f"Failed to check resources for port {port}: {e}")
    
    async def start_monitoring(self):
        """Start the port monitoring for all configured ports"""
        if self.running:
            return
        
        self.running = True
        self.logger.info("Starting individual port monitoring tasks")
        
        # Start monitoring tasks for all configured ports
        for port, config in self.monitored_ports.items():
            if config.enabled:
                await self._start_port_monitoring(port)
        
        self.logger.info(f"Port monitoring started for {len(self.port_tasks)} ports")
    
    async def stop_monitoring(self):
        """Stop all port monitoring tasks"""
        self.running = False
        self.logger.info("Stopping all port monitoring tasks")
        
        # Stop all individual port monitoring tasks
        for port in list(self.port_tasks.keys()):
            await self._stop_port_monitoring(port)
        
        # Also stop the old monitoring task if it exists
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("All port monitoring stopped")
    
    def get_monitoring_status(self) -> Dict:
        """Get status of all monitoring tasks"""
        status = {
            'running': self.running,
            'total_ports': len(self.monitored_ports),
            'active_tasks': len(self.port_tasks),
            'port_tasks': {}
        }
        
        for port, task in self.port_tasks.items():
            status['port_tasks'][port] = {
                'running': not task.done(),
                'cancelled': task.cancelled(),
                'exception': str(task.exception()) if task.done() and task.exception() else None
            }
        
        return status
    
    async def cleanup_finished_tasks(self):
        """Clean up finished or failed monitoring tasks"""
        finished_ports = []
        for port, task in self.port_tasks.items():
            if task.done():
                finished_ports.append(port)
                if task.exception():
                    self.logger.error(f"Port {port} monitoring task failed: {task.exception()}")
                else:
                    self.logger.info(f"Port {port} monitoring task finished")
        
        # Remove finished tasks
        for port in finished_ports:
            del self.port_tasks[port]
        
        return len(finished_ports)
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        self.logger.info("Monitoring loop started")
        while self.running:
            try:
                # Check all monitored ports
                for port, config in self.monitored_ports.items():
                    if config.enabled:
                        self.logger.debug(f"Checking port {port}")
                        await self.check_port(port)
                
                # Wait for the shortest interval
                if self.monitored_ports:
                    min_interval = min(config.interval for config in self.monitored_ports.values() if config.enabled)
                    self.logger.debug(f"Waiting {min_interval} seconds before next check")
                    await asyncio.sleep(min_interval)
                else:
                    self.logger.debug("No ports to monitor, waiting 30 seconds")
                    await asyncio.sleep(30)  # Default wait if no ports
                    
            except asyncio.CancelledError:
                self.logger.info("Monitoring loop cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(5)  # Wait before retrying
    
    def get_monitored_ports(self) -> List[Dict]:
        """Get list of monitored ports with their status from database"""
        try:
            # Get real-time status from database
            db_status = self.db.get_port_status()
            
            # Create a mapping of port to database status
            status_map = {status['port']: status for status in db_status}
            
            ports = []
            for port, config in self.monitored_ports.items():
                # Get status from database if available, otherwise use in-memory status
                db_status_info = status_map.get(port, {})
                
                # Format last check timestamp for display
                last_check_display = None
                last_check_timestamp = db_status_info.get('last_check') or (config.last_check.isoformat() if config.last_check else None)
                
                if last_check_timestamp:
                    try:
                        # Parse timestamp - handle both string and datetime objects
                        if isinstance(last_check_timestamp, str):
                            # Use a more robust parsing approach
                            try:
                                # Try parsing with fromisoformat first
                                last_check_dt = datetime.fromisoformat(last_check_timestamp)
                            except ValueError:
                                # Fallback to strptime for different formats
                                try:
                                    last_check_dt = datetime.strptime(last_check_timestamp, "%Y-%m-%dT%H:%M:%S.%f")
                                except ValueError:
                                    try:
                                        last_check_dt = datetime.strptime(last_check_timestamp, "%Y-%m-%dT%H:%M:%S")
                                    except ValueError:
                                        # Last resort - try parsing as is
                                        last_check_dt = datetime.fromisoformat(last_check_timestamp.replace('Z', ''))
                        else:
                            last_check_dt = last_check_timestamp
                        
                        # Show relative time (e.g., "2 minutes ago") and absolute time
                        now = datetime.now()
                        
                        # Ensure both timestamps are in the same timezone (local time)
                        if last_check_dt.tzinfo is None:
                            # If no timezone info, assume local time
                            last_check_local = last_check_dt
                        else:
                            # Convert to local time
                            last_check_local = last_check_dt.astimezone()
                        
                        time_diff = now - last_check_local
                        time_diff_seconds = time_diff.total_seconds()
                        
                        # Handle negative time differences (future timestamps)
                        if time_diff_seconds < 0:
                            last_check_display = "Future timestamp"
                        elif time_diff_seconds < 60:
                            last_check_display = f"{int(time_diff_seconds)}s ago"
                        elif time_diff_seconds < 3600:
                            last_check_display = f"{int(time_diff_seconds/60)}m ago"
                        elif time_diff_seconds < 86400:
                            last_check_display = f"{int(time_diff_seconds/3600)}h ago"
                        else:
                            last_check_display = f"{int(time_diff_seconds/86400)}d ago"
                        
                        # Also include the full timestamp
                        full_timestamp = last_check_local.strftime("%Y-%m-%d %H:%M:%S")
                        last_check_display = f"{last_check_display} ({full_timestamp})"
                    except Exception as e:
                        self.logger.warning(f"Failed to format timestamp for port {port}: {e}")
                        self.logger.warning(f"Timestamp value: {last_check_timestamp}")
                        last_check_display = "Invalid timestamp"
                
                # Format uptime display
                uptime_display = None
                uptime_seconds = db_status_info.get('uptime_seconds', 0)
                if uptime_seconds > 0:
                    if uptime_seconds < 60:
                        uptime_display = f"{uptime_seconds}s"
                    elif uptime_seconds < 3600:
                        uptime_display = f"{int(uptime_seconds/60)}m {uptime_seconds%60}s"
                    elif uptime_seconds < 86400:
                        uptime_display = f"{int(uptime_seconds/3600)}h {int((uptime_seconds%3600)/60)}m"
                    else:
                        uptime_display = f"{int(uptime_seconds/86400)}d {int((uptime_seconds%86400)/3600)}h"
                
                ports.append({
                    'port': port,
                    'interval': config.interval,
                    'powershell_script': config.powershell_script,
                    'enabled': config.enabled,
                    'last_check': last_check_timestamp,
                    'last_check_display': last_check_display,
                    'last_status': db_status_info.get('status', 'unknown'),
                    'failure_count': db_status_info.get('failure_count', config.failure_count),
                    'is_online': db_status_info.get('status') == 'online',
                    'status': db_status_info.get('status', 'unknown'),
                    'uptime_seconds': uptime_seconds,
                    'uptime_display': uptime_display,
                    'total_checks': db_status_info.get('total_checks', 0),
                    'success_rate': db_status_info.get('success_rate', 0),
                    'last_status_change': db_status_info.get('last_status_change')
                })
            
            return ports
            
        except Exception as e:
            self.logger.error(f"Failed to get monitored ports from database: {e}")
            # Fallback to in-memory status
            return self._get_monitored_ports_fallback()
    
    def _get_monitored_ports_fallback(self) -> List[Dict]:
        """Fallback method to get monitored ports from memory"""
        ports = []
        for port, config in self.monitored_ports.items():
            # Format last check timestamp for display
            last_check_display = None
            if config.last_check:
                # Show relative time (e.g., "2 minutes ago") and absolute time
                from datetime import datetime, timezone
                now = datetime.now()
                
                # Ensure both timestamps are in the same timezone (local time)
                if config.last_check.tzinfo is None:
                    # If no timezone info, assume local time
                    last_check_local = config.last_check
                else:
                    # Convert to local time
                    last_check_local = config.last_check.astimezone()
                
                time_diff = now - last_check_local
                time_diff_seconds = time_diff.total_seconds()
                
                # Handle negative time differences (future timestamps)
                if time_diff_seconds < 0:
                    last_check_display = "Future timestamp"
                elif time_diff_seconds < 60:
                    last_check_display = f"{int(time_diff_seconds)}s ago"
                elif time_diff_seconds < 3600:
                    last_check_display = f"{int(time_diff_seconds/60)}m ago"
                elif time_diff_seconds < 86400:
                    last_check_display = f"{int(time_diff_seconds/3600)}h ago"
                else:
                    last_check_display = f"{int(time_diff_seconds/86400)}d ago"
                
                # Also include the full timestamp
                full_timestamp = last_check_local.strftime("%Y-%m-%d %H:%M:%S")
                last_check_display = f"{last_check_display} ({full_timestamp})"
            
            ports.append({
                'port': port,
                'interval': config.interval,
                'powershell_script': config.powershell_script,
                'enabled': config.enabled,
                'last_check': config.last_check.isoformat() if config.last_check else None,
                'last_check_display': last_check_display,
                'last_status': config.last_status,
                'failure_count': config.failure_count,
                'is_online': config.last_status if config.last_check else None,
                'status': 'online' if config.last_status else 'offline',
                'uptime_seconds': 0,
                'uptime_display': None,
                'total_checks': 0,
                'success_rate': 0,
                'last_status_change': None
            })
        return ports
    
    def get_port_logs(self, port: Optional[int] = None) -> List[Dict]:
        """Get logs for port monitoring from database"""
        try:
            return self.db.get_port_logs(port, limit=100)
        except Exception as e:
            self.logger.error(f"Failed to get port logs: {e}")
            return []
    
    async def get_processes_on_port(self, port: int) -> List[Dict]:
        """Get all processes using a specific port with detailed resource usage"""
        def _get_processes():
            try:
                import psutil
                processes = []
                
                for conn in psutil.net_connections(kind='inet'):
                    if conn.laddr.port == port and conn.status == psutil.CONN_LISTEN:
                        try:
                            process = psutil.Process(conn.pid)
                            
                            # Get CPU and memory usage
                            cpu_percent = process.cpu_percent()
                            memory_info = process.memory_info()
                            memory_percent = process.memory_percent()
                            
                            # Get additional process details
                            try:
                                cmdline = process.cmdline()
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                cmdline = []
                            
                            try:
                                username = process.username()
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                username = "Unknown"
                            
                            processes.append({
                                'pid': conn.pid,
                                'name': process.name(),
                                'status': process.status(),
                                'create_time': process.create_time(),
                                'cpu_percent': round(cpu_percent, 2),
                                'memory_rss': memory_info.rss,  # Resident Set Size in bytes
                                'memory_vms': memory_info.vms,  # Virtual Memory Size in bytes
                                'memory_percent': round(memory_percent, 2),
                                'cmdline': cmdline,
                                'username': username,
                                'port': port
                            })
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            # Process may have died or we don't have access
                            continue
                
                return processes
                
            except Exception as e:
                return []
        
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _get_processes)
        except Exception as e:
            self.logger.error(f"Failed to get processes on port {port}: {e}")
            return []
    
    async def kill_process(self, pid: int) -> bool:
        """Kill a process gracefully"""
        def _kill():
            try:
                import psutil
                process = psutil.Process(pid)
                process.terminate()
                
                # Wait for process to terminate
                try:
                    process.wait(timeout=5)
                    return ('success', 'graceful')
                except psutil.TimeoutExpired:
                    # If it doesn't terminate, force kill it
                    process.kill()
                    return ('success', 'force')
                    
            except psutil.NoSuchProcess:
                return ('not_found', None)
            except psutil.AccessDenied:
                return ('access_denied', None)
            except Exception as e:
                return ('error', str(e))
        
        try:
            loop = asyncio.get_event_loop()
            result, detail = await loop.run_in_executor(None, _kill)
            
            if result == 'success':
                if detail == 'graceful':
                    self.logger.info(f"Process {pid} terminated gracefully")
                else:
                    self.logger.info(f"Process {pid} force killed after timeout")
                return True
            elif result == 'not_found':
                self.logger.warning(f"Process {pid} no longer exists")
                return True
            elif result == 'access_denied':
                self.logger.error(f"Access denied when trying to kill process {pid}")
                return False
            else:
                self.logger.error(f"Failed to kill process {pid}: {detail}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to kill process {pid}: {e}")
            return False
    
    async def force_kill_process(self, pid: int) -> bool:
        """Force kill a process immediately"""
        def _kill():
            try:
                import psutil
                process = psutil.Process(pid)
                process.kill()
                return ('success', None)
                
            except psutil.NoSuchProcess:
                return ('not_found', None)
            except psutil.AccessDenied:
                return ('access_denied', None)
            except Exception as e:
                return ('error', str(e))
        
        try:
            loop = asyncio.get_event_loop()
            result, detail = await loop.run_in_executor(None, _kill)
            
            if result == 'success':
                self.logger.info(f"Process {pid} force killed")
                return True
            elif result == 'not_found':
                self.logger.warning(f"Process {pid} no longer exists")
                return True
            elif result == 'access_denied':
                self.logger.error(f"Access denied when trying to force kill process {pid}")
                return False
            else:
                self.logger.error(f"Failed to force kill process {pid}: {detail}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to force kill process {pid}: {e}")
            return False
    
    def cleanup_old_logs(self, days: int = 30) -> int:
        """Clean up old logs from database"""
        try:
            return self.db.cleanup_old_logs(days)
        except Exception as e:
            self.logger.error(f"Failed to cleanup old logs: {e}")
            return 0
    
    def get_database_stats(self) -> Dict:
        """Get database statistics"""
        try:
            return self.db.get_database_stats()
        except Exception as e:
            self.logger.error(f"Failed to get database stats: {e}")
            return {}
    
    async def check_resource_thresholds(self, port: int) -> Dict:
        """Check if processes on a port exceed resource thresholds"""
        try:
            # Get port configuration with thresholds
            port_config = self.db.get_port_config(port)
            if not port_config:
                return {'exceeded': False, 'alerts': []}
            
            # Get threshold settings (we'll add these to the database schema)
            thresholds = self.db.get_port_thresholds(port)
            if not thresholds:
                return {'exceeded': False, 'alerts': []}
            
            # Get current processes on the port
            processes = await self.get_processes_on_port(port)
            alerts = []
            
            for process in processes:
                process_alerts = []
                
                # Check CPU threshold
                if thresholds.get('cpu_threshold', 0) > 0:
                    if process['cpu_percent'] > thresholds['cpu_threshold']:
                        process_alerts.append({
                            'type': 'cpu',
                            'value': process['cpu_percent'],
                            'threshold': thresholds['cpu_threshold'],
                            'message': f"Process {process['name']} (PID {process['pid']}) CPU usage {process['cpu_percent']}% exceeds threshold {thresholds['cpu_threshold']}%"
                        })
                
                # Check RAM threshold
                if thresholds.get('ram_threshold', 0) > 0:
                    if process['memory_percent'] > thresholds['ram_threshold']:
                        process_alerts.append({
                            'type': 'ram',
                            'value': process['memory_percent'],
                            'threshold': thresholds['ram_threshold'],
                            'message': f"Process {process['name']} (PID {process['pid']}) RAM usage {process['memory_percent']}% exceeds threshold {thresholds['ram_threshold']}%"
                        })
                
                if process_alerts:
                    alerts.extend(process_alerts)
            
            # Send email alerts if configured
            if alerts and thresholds.get('email_alerts_enabled', False):
                await self._send_resource_alert_email(port, alerts, thresholds)
            
            return {
                'exceeded': len(alerts) > 0,
                'alerts': alerts,
                'processes': processes
            }
            
        except Exception as e:
            self.logger.error(f"Failed to check resource thresholds for port {port}: {e}")
            return {'exceeded': False, 'alerts': [], 'error': str(e)}
    
    async def _send_resource_alert_email(self, port: int, alerts: List[Dict], thresholds: Dict):
        """Send email alert for resource threshold violations"""
        try:
            email_config = self.email_alert.get_port_email_config(port)
            if not email_config.get('enabled', False) or not email_config.get('recipients'):
                return
            
            # Prepare alert summary
            alert_summary = []
            for alert in alerts:
                alert_summary.append(alert['message'])
            
            # Send alert email
            await self.email_alert.send_alert_email(
                port=port,
                recipients=email_config["recipients"],
                template_name=email_config.get("template", "default"),
                custom_data={
                    "failure_count": len(alerts),
                    "message": f"Resource threshold violations detected on port {port}",
                    "alert_details": "\n".join(alert_summary),
                    "alert_type": "resource_threshold"
                }
            )
            
            self.logger.info(f"Resource threshold alert sent for port {port}")
            
        except Exception as e:
            self.logger.error(f"Failed to send resource alert email: {e}")
    
    async def get_port_resource_summary(self, port: int) -> Dict:
        """Get comprehensive resource summary for a port"""
        try:
            processes = await self.get_processes_on_port(port)
            thresholds = self.db.get_port_thresholds(port) or {}
            
            # Calculate totals
            total_cpu = sum(p['cpu_percent'] for p in processes)
            total_memory = sum(p['memory_percent'] for p in processes)
            total_memory_rss = sum(p['memory_rss'] for p in processes)
            
            return {
                'port': port,
                'process_count': len(processes),
                'total_cpu_percent': round(total_cpu, 2),
                'total_memory_percent': round(total_memory, 2),
                'total_memory_rss_bytes': total_memory_rss,
                'total_memory_rss_mb': round(total_memory_rss / (1024 * 1024), 2),
                'processes': processes,
                'thresholds': thresholds,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get resource summary for port {port}: {e}")
            return {'error': str(e)}
    
    async def get_processes_on_port(self, port: int) -> List[Dict]:
        """Get all processes using a specific port with detailed resource usage"""
        try:
            import psutil
            processes = []
            
            for conn in psutil.net_connections(kind='inet'):
                if conn.laddr.port == port and conn.status == psutil.CONN_LISTEN:
                    try:
                        process = psutil.Process(conn.pid)
                        
                        # Get CPU and memory usage
                        cpu_percent = process.cpu_percent()
                        memory_info = process.memory_info()
                        memory_percent = process.memory_percent()
                        
                        # Get additional process details
                        try:
                            cmdline = process.cmdline()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            cmdline = []
                        
                        try:
                            username = process.username()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            username = "Unknown"
                        
                        processes.append({
                            'pid': conn.pid,
                            'name': process.name(),
                            'status': process.status(),
                            'create_time': process.create_time(),
                            'cpu_percent': round(cpu_percent, 2),
                            'memory_rss': memory_info.rss,  # Resident Set Size in bytes
                            'memory_vms': memory_info.vms,  # Virtual Memory Size in bytes
                            'memory_percent': round(memory_percent, 2),
                            'cmdline': cmdline,
                            'username': username,
                            'port': port
                        })
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        # Process may have died or we don't have access
                        continue
            
            return processes
            
        except Exception as e:
            self.logger.error(f"Failed to get processes on port {port}: {e}")
            return []
    
    async def kill_process(self, pid: int) -> bool:
        """Kill a process gracefully"""
        try:
            import psutil
            process = psutil.Process(pid)
            process.terminate()
            
            # Wait for process to terminate
            try:
                process.wait(timeout=5)
                self.logger.info(f"Process {pid} terminated gracefully")
                return True
            except psutil.TimeoutExpired:
                # If it doesn't terminate, force kill it
                process.kill()
                self.logger.info(f"Process {pid} force killed after timeout")
                return True
                
        except psutil.NoSuchProcess:
            self.logger.warning(f"Process {pid} no longer exists")
            return True
        except psutil.AccessDenied:
            self.logger.error(f"Access denied when trying to kill process {pid}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to kill process {pid}: {e}")
            return False
    
    async def force_kill_process(self, pid: int) -> bool:
        """Force kill a process immediately"""
        try:
            import psutil
            process = psutil.Process(pid)
            process.kill()
            self.logger.info(f"Process {pid} force killed")
            return True
            
        except psutil.NoSuchProcess:
            self.logger.warning(f"Process {pid} no longer exists")
            return True
        except psutil.AccessDenied:
            self.logger.error(f"Access denied when trying to force kill process {pid}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to force kill process {pid}: {e}")
            return False
    
    async def kill_processes_on_port(self, port: int) -> Dict:
        """Kill all processes running on a specific port"""
        try:
            processes = await self.get_processes_on_port(port)
            results = {
                'port': port,
                'total_processes': len(processes),
                'killed_processes': [],
                'failed_processes': [],
                'success': True
            }
            
            for process in processes:
                pid = process['pid']
                success = await self.kill_process(pid)
                if success:
                    results['killed_processes'].append({
                        'pid': pid,
                        'name': process['name']
                    })
                else:
                    results['failed_processes'].append({
                        'pid': pid,
                        'name': process['name']
                    })
                    results['success'] = False
            
            self.logger.info(f"Killed {len(results['killed_processes'])} processes on port {port}")
            return results
            
        except Exception as e:
            self.logger.error(f"Failed to kill processes on port {port}: {e}")
            return {
                'port': port,
                'total_processes': 0,
                'killed_processes': [],
                'failed_processes': [],
                'success': False,
                'error': str(e)
            }
    
    async def force_kill_processes_on_port(self, port: int) -> Dict:
        """Force kill all processes running on a specific port"""
        try:
            processes = await self.get_processes_on_port(port)
            results = {
                'port': port,
                'total_processes': len(processes),
                'killed_processes': [],
                'failed_processes': [],
                'success': True
            }
            
            for process in processes:
                pid = process['pid']
                success = await self.force_kill_process(pid)
                if success:
                    results['killed_processes'].append({
                        'pid': pid,
                        'name': process['name']
                    })
                else:
                    results['failed_processes'].append({
                        'pid': pid,
                        'name': process['name']
                    })
                    results['success'] = False
            
            self.logger.info(f"Force killed {len(results['killed_processes'])} processes on port {port}")
            return results
            
        except Exception as e:
            self.logger.error(f"Failed to force kill processes on port {port}: {e}")
            return {
                'port': port,
                'total_processes': 0,
                'killed_processes': [],
                'failed_processes': [],
                'success': False,
                'error': str(e)
            }


