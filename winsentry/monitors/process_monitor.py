"""Process monitoring module"""

import psutil
from typing import Dict, Any, Optional
from datetime import datetime


class ProcessMonitor:
    """Monitors processes by PID"""
    
    def __init__(self):
        self.status_history = {}  # Track status for duration-based triggers
    
    def check_process(self, pid: int) -> Dict[str, Any]:
        """
        Check if a process with the specified PID is running
        
        Returns:
            Dictionary with status, process info, and timestamp
        """
        try:
            if psutil.pid_exists(pid):
                try:
                    process = psutil.Process(pid)
                    
                    # Check if process is actually running (not zombie)
                    if process.is_running() and process.status() != psutil.STATUS_ZOMBIE:
                        return {
                            "status": "running",
                            "pid": pid,
                            "process_name": process.name(),
                            "process_cmdline": " ".join(process.cmdline()),
                            "cpu_percent": process.cpu_percent(interval=0.1),
                            "memory_percent": process.memory_percent(),
                            "memory_mb": process.memory_info().rss / (1024 * 1024),
                            "timestamp": datetime.now().isoformat(),
                            "error": None
                        }
                    else:
                        return {
                            "status": "stopped",
                            "pid": pid,
                            "process_name": None,
                            "process_cmdline": None,
                            "cpu_percent": 0,
                            "memory_percent": 0,
                            "memory_mb": 0,
                            "timestamp": datetime.now().isoformat(),
                            "error": "Process exists but not running (zombie)"
                        }
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    return {
                        "status": "stopped",
                        "pid": pid,
                        "process_name": None,
                        "process_cmdline": None,
                        "cpu_percent": 0,
                        "memory_percent": 0,
                        "memory_mb": 0,
                        "timestamp": datetime.now().isoformat(),
                        "error": str(e)
                    }
            else:
                return {
                    "status": "stopped",
                    "pid": pid,
                    "process_name": None,
                    "process_cmdline": None,
                    "cpu_percent": 0,
                    "memory_percent": 0,
                    "memory_mb": 0,
                    "timestamp": datetime.now().isoformat(),
                    "error": None
                }
                
        except Exception as e:
            return {
                "status": "error",
                "pid": pid,
                "process_name": None,
                "process_cmdline": None,
                "cpu_percent": 0,
                "memory_percent": 0,
                "memory_mb": 0,
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
    
    def get_all_processes(self) -> list:
        """Get list of all running processes"""
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'username']):
            try:
                processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return processes

