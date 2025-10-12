"""Windows service monitoring module"""

import subprocess
from typing import Dict, Any, Optional, List
from datetime import datetime


class ServiceMonitor:
    """Monitors Windows services"""
    
    def __init__(self):
        self.status_history = {}  # Track status for duration-based triggers
    
    def check_service(self, service_name: str) -> Dict[str, Any]:
        """
        Check Windows service status
        
        Returns:
            Dictionary with service status and info
        """
        try:
            # Use sc query to get service status
            result = subprocess.run(
                ['sc', 'query', service_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                output = result.stdout
                
                # Parse status from output
                status = "unknown"
                if "RUNNING" in output:
                    status = "running"
                elif "STOPPED" in output:
                    status = "stopped"
                elif "START_PENDING" in output:
                    status = "start_pending"
                elif "STOP_PENDING" in output:
                    status = "stop_pending"
                elif "PAUSED" in output:
                    status = "paused"
                
                return {
                    "status": status,
                    "service_name": service_name,
                    "timestamp": datetime.now().isoformat(),
                    "details": output,
                    "error": None
                }
            else:
                return {
                    "status": "not_found",
                    "service_name": service_name,
                    "timestamp": datetime.now().isoformat(),
                    "details": result.stderr,
                    "error": "Service not found or inaccessible"
                }
                
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "service_name": service_name,
                "timestamp": datetime.now().isoformat(),
                "details": "",
                "error": "Timeout querying service"
            }
        except Exception as e:
            return {
                "status": "error",
                "service_name": service_name,
                "timestamp": datetime.now().isoformat(),
                "details": "",
                "error": str(e)
            }
    
    def restart_service(self, service_name: str) -> Dict[str, Any]:
        """
        Restart a Windows service
        
        Returns:
            Dictionary with operation result
        """
        try:
            # Stop service
            stop_result = subprocess.run(
                ['sc', 'stop', service_name],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Wait a moment
            import time
            time.sleep(2)
            
            # Start service
            start_result = subprocess.run(
                ['sc', 'start', service_name],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if start_result.returncode == 0:
                return {
                    "success": True,
                    "service_name": service_name,
                    "action": "restart",
                    "message": "Service restarted successfully",
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "success": False,
                    "service_name": service_name,
                    "action": "restart",
                    "message": f"Failed to start service: {start_result.stderr}",
                    "timestamp": datetime.now().isoformat()
                }
                
        except Exception as e:
            return {
                "success": False,
                "service_name": service_name,
                "action": "restart",
                "message": f"Error restarting service: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    def start_service(self, service_name: str) -> Dict[str, Any]:
        """Start a Windows service"""
        try:
            result = subprocess.run(
                ['sc', 'start', service_name],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return {
                "success": result.returncode == 0,
                "service_name": service_name,
                "action": "start",
                "message": result.stdout if result.returncode == 0 else result.stderr,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "success": False,
                "service_name": service_name,
                "action": "start",
                "message": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def stop_service(self, service_name: str) -> Dict[str, Any]:
        """Stop a Windows service"""
        try:
            result = subprocess.run(
                ['sc', 'stop', service_name],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return {
                "success": result.returncode == 0,
                "service_name": service_name,
                "action": "stop",
                "message": result.stdout if result.returncode == 0 else result.stderr,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "success": False,
                "service_name": service_name,
                "action": "stop",
                "message": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def update_status_history(self, item_id: int, status: str) -> int:
        """
        Update status history and return consecutive count
        
        Args:
            item_id: Monitored item ID
            status: Current status
        
        Returns:
            Number of consecutive intervals with this status
        """
        if item_id not in self.status_history:
            self.status_history[item_id] = {"status": status, "count": 1}
            return 1
        
        if self.status_history[item_id]["status"] == status:
            self.status_history[item_id]["count"] += 1
        else:
            self.status_history[item_id] = {"status": status, "count": 1}
        
        return self.status_history[item_id]["count"]
    
    def get_all_services(self) -> List[Dict[str, Any]]:
        """Get list of all Windows services"""
        try:
            result = subprocess.run(
                ['sc', 'query', 'type=', 'service', 'state=', 'all'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            services = []
            if result.returncode == 0:
                # Parse service list from output
                lines = result.stdout.split('\n')
                current_service = {}
                
                for line in lines:
                    line = line.strip()
                    if line.startswith('SERVICE_NAME:'):
                        if current_service:
                            services.append(current_service)
                        current_service = {"service_name": line.split(':', 1)[1].strip()}
                    elif line.startswith('DISPLAY_NAME:'):
                        current_service["display_name"] = line.split(':', 1)[1].strip()
                    elif line.startswith('STATE'):
                        parts = line.split()
                        if len(parts) >= 3:
                            current_service["status"] = parts[3].lower()
                
                if current_service:
                    services.append(current_service)
            
            return services
            
        except Exception as e:
            print(f"Error listing services: {e}")
            return []

