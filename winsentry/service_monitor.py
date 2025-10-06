"""
Service monitoring functionality
"""

import asyncio
import logging
import os
import subprocess
import time
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime

from .database import Database
from .email_alert import EmailAlert

logger = logging.getLogger(__name__)


@dataclass
class ServiceConfig:
    """Configuration for service monitoring"""
    service_name: str
    interval: int = 30  # seconds
    powershell_script: Optional[str] = None
    powershell_commands: Optional[str] = None
    enabled: bool = True
    last_check: Optional[datetime] = None
    last_status: bool = False
    failure_count: int = 0


class ServiceMonitor:
    """Monitors Windows services for running state"""
    
    def __init__(self, db_path: str = "winsentry.db"):
        self.logger = logging.getLogger(__name__)
        self.monitored_services: Dict[str, ServiceConfig] = {}
        self.monitoring_task: Optional[asyncio.Task] = None
        self.running = False
        self.db = Database(db_path)
        self.email_alert = EmailAlert(db_path)
        
        # Load existing configurations from database
        self._load_configurations()
    
    def _load_configurations(self):
        """Load service configurations from database"""
        try:
            configs = self.db.get_all_service_configs()
            for config in configs:
                service_config = ServiceConfig(
                    service_name=config['service_name'],
                    interval=config['interval'],
                    powershell_script=config['powershell_script'],
                    powershell_commands=config['powershell_commands'],
                    enabled=config['enabled']
                )
                self.monitored_services[config['service_name']] = service_config
                self.logger.info(f"Loaded service configuration: {config['service_name']} (interval: {config['interval']}s)")
        except Exception as e:
            self.logger.error(f"Failed to load service configurations: {e}")
        
    async def add_service(self, service_name: str, interval: int = 30, powershell_script: Optional[str] = None, powershell_commands: Optional[str] = None) -> bool:
        """Add a service to monitor"""
        try:
            # Validate PowerShell script path if provided
            if powershell_script:
                if not await self.validate_powershell_script(powershell_script):
                    return False
            
            # Save to database first
            if not self.db.save_service_config(service_name, interval, powershell_script, powershell_commands, True):
                return False
            
            config = ServiceConfig(
                service_name=service_name,
                interval=interval,
                powershell_script=powershell_script,
                powershell_commands=powershell_commands,
                enabled=True
            )
            self.monitored_services[service_name] = config
            self.logger.info(f"Added service {service_name} to monitoring with interval {interval}s")
            if powershell_script:
                self.logger.info(f"PowerShell recovery script configured: {powershell_script}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to add service {service_name}: {e}")
            return False
    
    async def remove_service(self, service_name: str) -> bool:
        """Remove a service from monitoring"""
        try:
            # Remove from database first
            if not self.db.delete_service_config(service_name):
                return False
            
            if service_name in self.monitored_services:
                del self.monitored_services[service_name]
                self.logger.info(f"Removed service {service_name} from monitoring")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to remove service {service_name}: {e}")
            return False
    
    async def update_service_config(self, service_name: str, interval: Optional[int] = None, 
                                   powershell_script: Optional[str] = None, 
                                   powershell_commands: Optional[str] = None,
                                   enabled: Optional[bool] = None) -> bool:
        """Update service monitoring configuration"""
        try:
            if service_name not in self.monitored_services:
                return False
            
            config = self.monitored_services[service_name]
            if interval is not None:
                config.interval = interval
            if powershell_script is not None:
                config.powershell_script = powershell_script
            if powershell_commands is not None:
                config.powershell_commands = powershell_commands
            if enabled is not None:
                config.enabled = enabled
            
            # Update in database
            if not self.db.save_service_config(service_name, config.interval, config.powershell_script, config.powershell_commands, config.enabled):
                return False
            
            self.logger.info(f"Updated configuration for service {service_name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to update service {service_name}: {e}")
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

    async def is_service_running(self, service_name: str) -> bool:
        """Check if a Windows service is running"""
        try:
            # Use sc query to check service status
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run([
                    'sc', 'query', service_name
                ], capture_output=True, text=True, timeout=10)
            )
            
            if result.returncode != 0:
                self.logger.warning(f"Service {service_name} not found or error querying: {result.stderr}")
                return False
            
            # Check if service is in RUNNING state
            output = result.stdout.lower()
            return 'running' in output
            
        except subprocess.TimeoutExpired:
            self.logger.error(f"Timeout checking service {service_name}")
            return False
        except Exception as e:
            self.logger.error(f"Error checking service {service_name}: {e}")
            return False
    
    async def execute_powershell_script(self, script_path: str, service_name: str) -> bool:
        """Execute a PowerShell script with service name parameter"""
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
            # Pass the service name as a parameter
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
                    '-ServiceName', service_name
                ], capture_output=True, text=True, timeout=30, encoding='utf-8', errors='replace', env=env)
            )
            
            if result.returncode == 0:
                self.logger.info(f"PowerShell script executed successfully for service {service_name}: {script_path}")
                if result.stdout:
                    self.logger.info(f"Script output: {result.stdout}")
                return True
            else:
                self.logger.error(f"PowerShell script failed for service {service_name} (exit code {result.returncode}): {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.error(f"PowerShell script timeout for service {service_name}: {script_path}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to execute PowerShell script for service {service_name} {script_path}: {e}")
            return False
    
    async def _create_unicode_powershell_script(self, commands: str, service_name: str) -> str:
        """Create a PowerShell script with Unicode support"""
        import tempfile
        
        script_content = f"""
# PowerShell script with Unicode support
param([string]$ServiceName = "{service_name}")

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

    async def execute_powershell_commands(self, commands: str, service_name: str = "TestService") -> dict:
        """Execute PowerShell commands directly and return output"""
        import time
        start_time = time.time()
        
        self.logger.info(f"Executing PowerShell commands for service {service_name}: {commands[:100]}...")
        
        try:
            # Create a Unicode-aware PowerShell script
            temp_script_path = await self._create_unicode_powershell_script(commands, service_name)
            
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
                        '-ServiceName', service_name
                    ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60, env=env)
                )
                
                execution_time = int((time.time() - start_time) * 1000)
                
                self.logger.info(f"PowerShell execution completed for service {service_name}: exit_code={result.returncode}, stdout_length={len(result.stdout)}, stderr_length={len(result.stderr)}")
                
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
            self.logger.error(f"PowerShell execution timed out for service {service_name} after {execution_time}ms")
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
            self.logger.error(f"PowerShell execution failed for service {service_name}: {e}")
            return {
                'success': False,
                'stdout': '',
                'stderr': str(e),
                'exit_code': -1,
                'execution_time': execution_time,
                'error': str(e)
            }
    
    async def check_service(self, service_name: str) -> bool:
        """Check if a specific service is running"""
        config = self.monitored_services.get(service_name)
        if not config or not config.enabled:
            return True
        
        is_running = await self.is_service_running(service_name)
        config.last_check = datetime.now()
        config.last_status = is_running
        
        self.logger.debug(f"Service {service_name} check: {'RUNNING' if is_running else 'STOPPED'} at {config.last_check}")
        
        if not is_running:
            config.failure_count += 1
            self.logger.warning(f"Service {service_name} is not running (failure #{config.failure_count})")
            
            # Log to database
            self.db.log_service_check(service_name, "STOPPED", config.failure_count, f"Service {service_name} is stopped (failure #{config.failure_count})")
            
            # Get email configuration for this service
            email_config = self.email_alert.get_service_email_config(service_name)
            
            # Execute PowerShell script or commands after N failures
            if config.failure_count >= email_config.get("powershell_script_failures", 3):
                if config.powershell_script:
                    await self.execute_powershell_script(config.powershell_script, service_name)
                elif config.powershell_commands:
                    result = await self.execute_powershell_commands(config.powershell_commands, service_name)
                    if result['success']:
                        self.logger.info(f"PowerShell commands executed successfully for service {service_name}")
                    else:
                        self.logger.error(f"PowerShell commands failed for service {service_name}: {result.get('stderr', 'Unknown error')}")
            
            # Send email alert after M failures
            if (email_config.get("enabled", False) and 
                config.failure_count >= email_config.get("email_alert_failures", 5) and
                email_config.get("recipients")):
                
                # Only send email if we haven't sent one recently (avoid spam)
                if not hasattr(config, 'last_email_sent') or \
                   (datetime.now() - config.last_email_sent).total_seconds() > 300:  # 5 minutes
                    
                    await self.email_alert.send_service_alert_email(
                        service_name=service_name,
                        recipients=email_config["recipients"],
                        template_name=email_config.get("template", "default"),
                        custom_data={
                            "failure_count": config.failure_count,
                            "message": f"Service {service_name} has been stopped for {config.failure_count} consecutive checks"
                        }
                    )
                    config.last_email_sent = datetime.now()
        else:
            if config.failure_count > 0:
                # Service came back online
                self.db.log_service_check(service_name, "RUNNING", 0, f"Service {service_name} is back running")
                
                # Reset email sent flag
                if hasattr(config, 'last_email_sent'):
                    delattr(config, 'last_email_sent')
                    
            config.failure_count = 0
            
            # Check resource thresholds if service is running
            await self._check_service_resources(service_name)
        
        return is_running
    
    async def _check_service_resources(self, service_name: str):
        """Check resource usage for processes of a service"""
        try:
            # Get processes for the service
            processes = await self.get_service_processes(service_name)
            
            # Log service process metrics
            for process in processes:
                self.db.log_service_process_metrics(
                    service_name=service_name,
                    pid=process['pid'],
                    process_name=process['name'],
                    cpu_percent=process['cpu_percent'],
                    memory_percent=process['memory_percent'],
                    memory_rss_bytes=process['memory_rss']
                )
            
            # Check thresholds
            threshold_result = await self.check_service_resource_thresholds(service_name)
            if threshold_result.get('exceeded', False):
                self.logger.warning(f"Resource thresholds exceeded for service {service_name}: {len(threshold_result.get('alerts', []))} alerts")
            
        except Exception as e:
            self.logger.error(f"Failed to check resources for service {service_name}: {e}")
    
    async def start_monitoring(self):
        """Start the service monitoring loop"""
        if self.running:
            return
        
        self.running = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        self.logger.info("Service monitoring started")
    
    async def stop_monitoring(self):
        """Stop the service monitoring loop"""
        self.running = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        self.logger.info("Service monitoring stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        self.logger.info("Service monitoring loop started")
        while self.running:
            try:
                # Check all monitored services
                for service_name, config in self.monitored_services.items():
                    if config.enabled:
                        self.logger.debug(f"Checking service {service_name}")
                        await self.check_service(service_name)
                
                # Wait for the shortest interval
                if self.monitored_services:
                    min_interval = min(config.interval for config in self.monitored_services.values() if config.enabled)
                    self.logger.debug(f"Waiting {min_interval} seconds before next check")
                    await asyncio.sleep(min_interval)
                else:
                    self.logger.debug("No services to monitor, waiting 30 seconds")
                    await asyncio.sleep(30)  # Default wait if no services
                    
            except asyncio.CancelledError:
                self.logger.info("Service monitoring loop cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in service monitoring loop: {e}")
                await asyncio.sleep(5)  # Wait before retrying
    
    def get_monitored_services(self) -> List[Dict]:
        """Get list of monitored services with their status"""
        services = []
        for service_name, config in self.monitored_services.items():
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
            
            services.append({
                'service_name': service_name,
                'interval': config.interval,
                'powershell_script': config.powershell_script,
                'enabled': config.enabled,
                'last_check': config.last_check.isoformat() if config.last_check else None,
                'last_check_display': last_check_display,
                'last_status': config.last_status,
                'failure_count': config.failure_count,
                'is_running': config.last_status if config.last_check else None
            })
        return services
    
    def get_service_logs(self, service_name: Optional[str] = None) -> List[Dict]:
        """Get logs for service monitoring from database"""
        try:
            return self.db.get_service_logs(service_name, limit=100)
        except Exception as e:
            self.logger.error(f"Failed to get service logs: {e}")
            return []
    
    def cleanup_old_logs(self, days: int = 30) -> int:
        """Clean up old logs from database"""
        try:
            return self.db.cleanup_old_service_logs(days)
        except Exception as e:
            self.logger.error(f"Failed to cleanup old service logs: {e}")
            return 0
    
    def get_database_stats(self) -> Dict:
        """Get database statistics"""
        try:
            return self.db.get_database_stats()
        except Exception as e:
            self.logger.error(f"Failed to get database stats: {e}")
            return {}
    
    async def get_service_processes(self, service_name: str) -> List[Dict]:
        """Get all processes for a specific Windows service with detailed resource usage"""
        try:
            import psutil
            processes = []
            
            # Get all processes and filter by service name
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'username']):
                try:
                    # Check if this process belongs to the service
                    # We'll use the service name to match against process name or command line
                    proc_info = proc.info
                    process_name = proc_info['name'].lower()
                    cmdline = ' '.join(proc_info['cmdline']).lower() if proc_info['cmdline'] else ''
                    
                    # Check if service name appears in process name or command line
                    cmdline_list = proc_info['cmdline'] or []
                    if (service_name.lower() in process_name or 
                        service_name.lower() in cmdline or
                        any(service_name.lower() in arg.lower() for arg in cmdline_list)):
                        
                        process = psutil.Process(proc_info['pid'])
                        
                        # Get CPU and memory usage
                        cpu_percent = process.cpu_percent()
                        memory_info = process.memory_info()
                        memory_percent = process.memory_percent()
                        
                        # Get additional process details
                        try:
                            cmdline_full = process.cmdline()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            cmdline_full = []
                        
                        try:
                            username = process.username()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            username = "Unknown"
                        
                        processes.append({
                            'pid': proc_info['pid'],
                            'name': proc_info['name'],
                            'status': process.status(),
                            'create_time': process.create_time(),
                            'cpu_percent': round(cpu_percent, 2),
                            'memory_rss': memory_info.rss,  # Resident Set Size in bytes
                            'memory_vms': memory_info.vms,  # Virtual Memory Size in bytes
                            'memory_percent': round(memory_percent, 2),
                            'cmdline': cmdline_full,
                            'username': username,
                            'service_name': service_name
                        })
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    # Process may have died or we don't have access
                    continue
            
            return processes
            
        except Exception as e:
            self.logger.error(f"Failed to get processes for service {service_name}: {e}")
            return []
    
    async def check_service_resource_thresholds(self, service_name: str) -> Dict:
        """Check if processes for a service exceed resource thresholds"""
        try:
            # Get service configuration with thresholds
            service_config = self.db.get_service_config(service_name)
            if not service_config:
                return {'exceeded': False, 'alerts': []}
            
            # Get threshold settings
            thresholds = self.db.get_service_thresholds(service_name)
            if not thresholds:
                return {'exceeded': False, 'alerts': []}
            
            # Get current processes for the service
            processes = await self.get_service_processes(service_name)
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
                            'message': f"Service {service_name} process {process['name']} (PID {process['pid']}) CPU usage {process['cpu_percent']}% exceeds threshold {thresholds['cpu_threshold']}%"
                        })
                
                # Check RAM threshold
                if thresholds.get('ram_threshold', 0) > 0:
                    if process['memory_percent'] > thresholds['ram_threshold']:
                        process_alerts.append({
                            'type': 'ram',
                            'value': process['memory_percent'],
                            'threshold': thresholds['ram_threshold'],
                            'message': f"Service {service_name} process {process['name']} (PID {process['pid']}) RAM usage {process['memory_percent']}% exceeds threshold {thresholds['ram_threshold']}%"
                        })
                
                if process_alerts:
                    alerts.extend(process_alerts)
            
            # Send email alerts if configured
            if alerts and thresholds.get('email_alerts_enabled', False):
                await self._send_service_resource_alert_email(service_name, alerts, thresholds)
            
            return {
                'exceeded': len(alerts) > 0,
                'alerts': alerts,
                'processes': processes
            }
            
        except Exception as e:
            self.logger.error(f"Failed to check resource thresholds for service {service_name}: {e}")
            return {'exceeded': False, 'alerts': [], 'error': str(e)}
    
    async def _send_service_resource_alert_email(self, service_name: str, alerts: List[Dict], thresholds: Dict):
        """Send email alert for service resource threshold violations"""
        try:
            email_config = self.email_alert.get_service_email_config(service_name)
            if not email_config.get('enabled', False) or not email_config.get('recipients'):
                return
            
            # Prepare alert summary
            alert_summary = []
            for alert in alerts:
                alert_summary.append(alert['message'])
            
            # Send alert email
            await self.email_alert.send_service_alert_email(
                service_name=service_name,
                recipients=email_config["recipients"],
                template_name=email_config.get("template", "service_default"),
                custom_data={
                    "failure_count": len(alerts),
                    "message": f"Resource threshold violations detected for service {service_name}",
                    "alert_details": "\n".join(alert_summary),
                    "alert_type": "resource_threshold"
                }
            )
            
            self.logger.info(f"Service resource threshold alert sent for {service_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to send service resource alert email: {e}")
    
    async def get_service_resource_summary(self, service_name: str) -> Dict:
        """Get comprehensive resource summary for a service"""
        try:
            processes = await self.get_service_processes(service_name)
            thresholds = self.db.get_service_thresholds(service_name) or {}
            
            # Calculate totals
            total_cpu = sum(p['cpu_percent'] for p in processes)
            total_memory = sum(p['memory_percent'] for p in processes)
            total_memory_rss = sum(p['memory_rss'] for p in processes)
            
            return {
                'service_name': service_name,
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
            self.logger.error(f"Failed to get resource summary for service {service_name}: {e}")
            return {'error': str(e)}
