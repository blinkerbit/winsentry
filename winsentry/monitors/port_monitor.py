"""Port monitoring module"""

import psutil
from typing import Dict, Any, Optional
from datetime import datetime


class PortMonitor:
    """Monitors processes bound to specific ports"""
    
    def __init__(self):
        self.status_history = {}  # Track status for duration-based triggers
    
    def check_port(self, port: int) -> Dict[str, Any]:
        """
        Check if a process is listening on the specified port
        
        Returns:
            Dictionary with status, process info, and timestamp
        """
        try:
            connections = psutil.net_connections(kind='inet')
            
            for conn in connections:
                if conn.laddr.port == port and conn.status == psutil.CONN_LISTEN:
                    # Port is in use (running)
                    try:
                        process = psutil.Process(conn.pid)
                        return {
                            "status": "running",
                            "port": port,
                            "pid": conn.pid,
                            "process_name": process.name(),
                            "process_cmdline": " ".join(process.cmdline()),
                            "timestamp": datetime.now().isoformat(),
                            "error": None
                        }
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        return {
                            "status": "running",
                            "port": port,
                            "pid": conn.pid,
                            "process_name": "unknown",
                            "process_cmdline": "",
                            "timestamp": datetime.now().isoformat(),
                            "error": None
                        }
            
            # No process listening on this port (stopped)
            return {
                "status": "stopped",
                "port": port,
                "pid": None,
                "process_name": None,
                "process_cmdline": None,
                "timestamp": datetime.now().isoformat(),
                "error": None
            }
            
        except Exception as e:
            return {
                "status": "error",
                "port": port,
                "pid": None,
                "process_name": None,
                "process_cmdline": None,
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
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
    
    def get_process_by_port(self, port: int) -> Optional[int]:
        """Get PID of process listening on port"""
        result = self.check_port(port)
        return result.get("pid")

