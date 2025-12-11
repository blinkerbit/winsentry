"""
Windows Service Management using WMI
"""

import asyncio
import logging
import subprocess
from typing import List, Dict, Any, Optional
import win32serviceutil
import win32service
import win32con

logger = logging.getLogger(__name__)


class ServiceManager:
    """Manages Windows services"""
    
    def __init__(self, db_path: str = "winsentry.db"):
        self.logger = logging.getLogger(__name__)
        self.db_path = db_path
        self.service_config = {
            'load_all_services': True,  # Default to load all services
            'disable_auto_refresh': True,  # Default to disable auto-refresh for all services
            'watched_services': [],     # List of specific services to watch
            'excluded_services': []     # List of services to exclude
        }
        self._load_service_config()
    
    def _load_service_config(self):
        """Load service configuration from database"""
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create service_config table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS service_config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            
            # Load configuration
            cursor.execute('SELECT key, value FROM service_config')
            config_data = cursor.fetchall()
            
            for key, value in config_data:
                if key == 'load_all_services':
                    self.service_config['load_all_services'] = value.lower() == 'true'
                elif key == 'disable_auto_refresh':
                    self.service_config['disable_auto_refresh'] = value.lower() == 'true'
                elif key == 'watched_services':
                    self.service_config['watched_services'] = value.split(',') if value else []
                elif key == 'excluded_services':
                    self.service_config['excluded_services'] = value.split(',') if value else []
            
            conn.close()
            self.logger.info(f"Loaded service config: {self.service_config}")
            
        except Exception as e:
            self.logger.error(f"Failed to load service config: {e}")
    
    def save_service_config(self):
        """Save service configuration to database"""
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Save configuration
            cursor.execute('INSERT OR REPLACE INTO service_config (key, value) VALUES (?, ?)',
                         ('load_all_services', str(self.service_config['load_all_services'])))
            cursor.execute('INSERT OR REPLACE INTO service_config (key, value) VALUES (?, ?)',
                         ('disable_auto_refresh', str(self.service_config['disable_auto_refresh'])))
            cursor.execute('INSERT OR REPLACE INTO service_config (key, value) VALUES (?, ?)',
                         ('watched_services', ','.join(self.service_config['watched_services'])))
            cursor.execute('INSERT OR REPLACE INTO service_config (key, value) VALUES (?, ?)',
                         ('excluded_services', ','.join(self.service_config['excluded_services'])))
            
            conn.commit()
            conn.close()
            self.logger.info(f"Saved service config: {self.service_config}")
            
        except Exception as e:
            self.logger.error(f"Failed to save service config: {e}")
    
    def update_service_config(self, load_all_services: bool = None, disable_auto_refresh: bool = None, watched_services: List[str] = None, excluded_services: List[str] = None):
        """Update service configuration"""
        if load_all_services is not None:
            self.service_config['load_all_services'] = load_all_services
        if disable_auto_refresh is not None:
            self.service_config['disable_auto_refresh'] = disable_auto_refresh
        if watched_services is not None:
            self.service_config['watched_services'] = watched_services
        if excluded_services is not None:
            self.service_config['excluded_services'] = excluded_services
        
        self.save_service_config()
    
    def get_service_config(self):
        """Get current service configuration"""
        return self.service_config.copy()
    
    async def get_services(self) -> List[Dict[str, Any]]:
        """Get list of Windows services based on configuration"""
        try:
            services = []
            
            # Check if we should load all services or just watched ones
            if not self.service_config['load_all_services'] and self.service_config['watched_services']:
                # Load only watched services
                services = await self._get_watched_services()
            else:
                # Load all services (with exclusions)
                services = await self._get_all_services()
            
            self.logger.info(f"Loaded {len(services)} services (config: load_all={self.service_config['load_all_services']})")
            return services
            
        except Exception as e:
            self.logger.error(f"Failed to get services: {e}")
            return []
    
    async def _get_all_services(self) -> List[Dict[str, Any]]:
        """Get all services with exclusions"""
        try:
            services = []
            
            # Use WMI to get service information in a non-blocking way
            import wmi
            
            # Run WMI query in executor to avoid blocking with timeout
            loop = asyncio.get_event_loop()
            try:
                wmi_services = await asyncio.wait_for(
                    loop.run_in_executor(None, self._get_wmi_services),
                    timeout=60.0  # 60 second timeout for all services
                )
            except asyncio.TimeoutError:
                self.logger.warning("WMI query timed out, returning empty list")
                return []
            
            for service in wmi_services:
                # Apply exclusions
                if service.Name in self.service_config['excluded_services']:
                    continue
                    
                services.append({
                    'name': service.Name,
                    'display_name': service.DisplayName,
                    'state': service.State,
                    'start_mode': service.StartMode,
                    'process_id': service.ProcessId,
                    'status': service.Status,
                    'description': service.Description or '',
                })
            
            return services
            
        except Exception as e:
            self.logger.error(f"Failed to get all services: {e}")
            return []
    
    async def _get_watched_services(self) -> List[Dict[str, Any]]:
        """Get only watched services"""
        try:
            services = []
            
            for service_name in self.service_config['watched_services']:
                service_info = await self._get_single_service(service_name)
                if service_info:
                    services.append(service_info)
            
            return services
            
        except Exception as e:
            self.logger.error(f"Failed to get watched services: {e}")
            return []
    
    async def _get_single_service(self, service_name: str) -> Dict[str, Any]:
        """Get information for a single service"""
        def _query():
            try:
                import wmi
                import pythoncom
                
                # Initialize COM for this thread
                pythoncom.CoInitialize()
                
                try:
                    c = wmi.WMI()
                    
                    # Query for specific service
                    services = c.Win32_Service(Name=service_name)
                    for service in services:
                        return {
                            'name': service.Name,
                            'display_name': service.DisplayName,
                            'state': service.State,
                            'start_mode': service.StartMode,
                            'process_id': service.ProcessId,
                            'status': service.Status,
                            'description': service.Description or '',
                        }
                    
                    return None
                    
                finally:
                    # Clean up COM
                    pythoncom.CoUninitialize()
                
            except Exception as e:
                return None
        
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _query)
        except Exception as e:
            self.logger.error(f"Failed to get service {service_name}: {e}")
            return None
    
    def _get_wmi_services(self):
        """Get WMI services in a separate thread to avoid blocking"""
        try:
            import wmi
            import pythoncom
            
            # Initialize COM for this thread
            pythoncom.CoInitialize()
            
            try:
                c = wmi.WMI()
                
                # Query with specific properties to reduce data transfer
                services = c.Win32_Service(
                    ["Name", "DisplayName", "State", "StartMode", "ProcessId", "Status", "Description"]
                )
                
                # Return all services, but filter out only the most problematic ones
                filtered_services = []
                for service in services:
                    # Only skip services that are known to cause issues
                    if service.Name and not service.Name.startswith(('WmiPrvSE',)):
                        filtered_services.append(service)
                
                return filtered_services
                
            finally:
                # Clean up COM
                pythoncom.CoUninitialize()
            
        except Exception as e:
            self.logger.error(f"WMI query failed: {e}")
            # Fallback to PowerShell if WMI fails
            return self._get_services_powershell()
    
    def _get_services_powershell(self):
        """Fallback method using PowerShell to get services"""
        try:
            import subprocess
            import json
            
            self.logger.info("Using PowerShell fallback for service enumeration")
            
            # Use PowerShell to get all services with better error handling
            cmd = [
                'powershell.exe', '-ExecutionPolicy', 'Bypass', '-Command',
                '''
                try {
                    Get-Service | Select-Object Name, DisplayName, Status, StartType | 
                    ConvertTo-Json -Compress
                } catch {
                    Write-Error "PowerShell service enumeration failed: $_"
                    exit 1
                }
                '''
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, encoding='utf-8', errors='replace')
            
            if result.returncode == 0 and result.stdout.strip():
                try:
                    services_data = json.loads(result.stdout)
                    if not isinstance(services_data, list):
                        services_data = [services_data]
                    
                    # Convert PowerShell output to WMI-like objects
                    services = []
                    for svc in services_data:
                        class Service:
                            def __init__(self, data):
                                self.Name = data.get('Name', '')
                                self.DisplayName = data.get('DisplayName', '')
                                self.State = 'Running' if data.get('Status') == 'Running' else 'Stopped'
                                self.StartMode = data.get('StartType', 'Unknown')
                                self.ProcessId = 0
                                self.Status = data.get('Status', 'Unknown')
                                self.Description = ''
                        
                        services.append(Service(svc))
                    
                    self.logger.info(f"PowerShell fallback loaded {len(services)} services")
                    return services
                    
                except json.JSONDecodeError as e:
                    self.logger.error(f"Failed to parse PowerShell JSON output: {e}")
                    self.logger.error(f"PowerShell output: {result.stdout[:200]}...")
                    return []
            else:
                self.logger.error(f"PowerShell fallback failed: {result.stderr}")
                return []
                
        except Exception as e:
            self.logger.error(f"PowerShell fallback failed: {e}")
            return []
    
    async def start_service(self, service_name: str) -> Dict[str, Any]:
        """Start a Windows service"""
        def _start():
            try:
                win32serviceutil.StartService(service_name)
                return True
            except Exception as e:
                return str(e)
        
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _start)
            
            if result is True:
                await asyncio.sleep(1)  # Give service time to start
                
                # Check if service started successfully
                status = await self.get_service_status(service_name)
                success = status == "Running"
                
                return {
                    'success': success,
                    'message': f"Service {service_name} {'started' if success else 'failed to start'}"
                }
            else:
                return {
                    'success': False,
                    'message': f"Failed to start service {service_name}: {result}"
                }
            
        except Exception as e:
            self.logger.error(f"Failed to start service {service_name}: {e}")
            return {
                'success': False,
                'message': f"Failed to start service {service_name}: {str(e)}"
            }
    
    async def stop_service(self, service_name: str) -> Dict[str, Any]:
        """Stop a Windows service"""
        def _stop():
            try:
                win32serviceutil.StopService(service_name)
                return True
            except Exception as e:
                return str(e)
        
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _stop)
            
            if result is True:
                await asyncio.sleep(1)  # Give service time to stop
                
                # Check if service stopped successfully
                status = await self.get_service_status(service_name)
                success = status == "Stopped"
                
                return {
                    'success': success,
                    'message': f"Service {service_name} {'stopped' if success else 'failed to stop'}"
                }
            else:
                return {
                    'success': False,
                    'message': f"Failed to stop service {service_name}: {result}"
                }
            
        except Exception as e:
            self.logger.error(f"Failed to stop service {service_name}: {e}")
            return {
                'success': False,
                'message': f"Failed to stop service {service_name}: {str(e)}"
            }
    
    async def restart_service(self, service_name: str) -> Dict[str, Any]:
        """Restart a Windows service"""
        try:
            # Stop service first
            stop_result = await self.stop_service(service_name)
            if not stop_result['success']:
                return stop_result
            
            # Wait a bit before starting
            await asyncio.sleep(2)
            
            # Start service
            start_result = await self.start_service(service_name)
            return start_result
            
        except Exception as e:
            self.logger.error(f"Failed to restart service {service_name}: {e}")
            return {
                'success': False,
                'message': f"Failed to restart service {service_name}: {str(e)}"
            }
    
    async def get_service_status(self, service_name: str) -> Optional[str]:
        """Get the current status of a service"""
        def _query():
            try:
                status = win32serviceutil.QueryServiceStatus(service_name)
                state = status[1]
                
                if state == win32service.SERVICE_RUNNING:
                    return "Running"
                elif state == win32service.SERVICE_STOPPED:
                    return "Stopped"
                elif state == win32service.SERVICE_PAUSED:
                    return "Paused"
                elif state == win32service.SERVICE_START_PENDING:
                    return "Starting"
                elif state == win32service.SERVICE_STOP_PENDING:
                    return "Stopping"
                else:
                    return "Unknown"
            except Exception:
                return None
        
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _query)
        except Exception as e:
            self.logger.error(f"Failed to get status for service {service_name}: {e}")
            return None
