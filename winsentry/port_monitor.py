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


class PortMonitor:
    """Monitors ports for running processes"""
    
    def __init__(self, db_path: str = "winsentry.db"):
        self.logger = logging.getLogger(__name__)
        self.monitored_ports: Dict[int, PortConfig] = {}
        self.monitoring_task: Optional[asyncio.Task] = None
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
                    enabled=config['enabled']
                )
                self.monitored_ports[config['port']] = port_config
                self.logger.info(f"Loaded port configuration: {config['port']} (interval: {config['interval']}s)")
        except Exception as e:
            self.logger.error(f"Failed to load configurations: {e}")
        
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
            return True
        except Exception as e:
            self.logger.error(f"Failed to add port {port}: {e}")
            return False
    
    async def remove_port(self, port: int) -> bool:
        """Remove a port from monitoring"""
        try:
            # Remove from database first
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
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                result = sock.connect_ex(('localhost', port))
                return result == 0
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
        
        self.logger.debug(f"Port {port} check: {'ONLINE' if is_used else 'OFFLINE'} at {config.last_check}")
        
        if not is_used:
            config.failure_count += 1
            self.logger.warning(f"Port {port} is not in use (failure #{config.failure_count})")
            
            # Log to database
            self.db.log_port_check(port, "OFFLINE", config.failure_count, f"Port {port} is offline (failure #{config.failure_count})")
            
            # Get email configuration for this port
            email_config = self.email_alert.get_port_email_config(port)
            
            # Execute PowerShell script or commands after N failures
            if config.failure_count >= email_config.get("powershell_script_failures", 3):
                if config.powershell_script:
                    await self.execute_powershell_script(config.powershell_script, port)
                elif config.powershell_commands:
                    result = await self.execute_powershell_commands(config.powershell_commands, port)
                    if result['success']:
                        self.logger.info(f"PowerShell commands executed successfully for port {port}")
                    else:
                        self.logger.error(f"PowerShell commands failed for port {port}: {result.get('stderr', 'Unknown error')}")
            
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
        
        return is_used
    
    async def start_monitoring(self):
        """Start the port monitoring loop"""
        if self.running:
            return
        
        self.running = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        self.logger.info("Port monitoring started")
    
    async def stop_monitoring(self):
        """Stop the port monitoring loop"""
        self.running = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        self.logger.info("Port monitoring stopped")
    
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
        """Get list of monitored ports with their status"""
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
                'is_online': config.last_status if config.last_check else None
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
        """Get all processes using a specific port"""
        try:
            import psutil
            processes = []
            
            for conn in psutil.net_connections(kind='inet'):
                if conn.laddr.port == port and conn.status == psutil.CONN_LISTEN:
                    try:
                        process = psutil.Process(conn.pid)
                        processes.append({
                            'pid': conn.pid,
                            'name': process.name(),
                            'status': process.status(),
                            'create_time': process.create_time()
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
