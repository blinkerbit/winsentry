"""System statistics monitoring module"""

import psutil
from typing import Dict, Any, List
from datetime import datetime


class SystemMonitor:
    """Monitors system resources (CPU, RAM, disk)"""
    
    def __init__(self):
        self.threshold_history = {}  # Track threshold breaches
    
    def get_cpu_usage(self) -> float:
        """Get overall CPU usage percentage"""
        return psutil.cpu_percent(interval=1)
    
    def get_memory_usage(self) -> Dict[str, Any]:
        """Get memory usage statistics"""
        mem = psutil.virtual_memory()
        return {
            "total_mb": mem.total / (1024 * 1024),
            "used_mb": mem.used / (1024 * 1024),
            "available_mb": mem.available / (1024 * 1024),
            "percent": mem.percent
        }
    
    def get_disk_usage(self, drive: str = None) -> Dict[str, Dict[str, Any]]:
        """
        Get disk usage for all drives or a specific drive
        
        Args:
            drive: Optional drive letter (e.g., 'C:')
        
        Returns:
            Dictionary of disk usage per drive
        """
        disk_info = {}
        
        if drive:
            # Check specific drive
            try:
                usage = psutil.disk_usage(drive + '\\' if not drive.endswith('\\') else drive)
                disk_info[drive] = {
                    "total_gb": usage.total / (1024 ** 3),
                    "used_gb": usage.used / (1024 ** 3),
                    "free_gb": usage.free / (1024 ** 3),
                    "percent": usage.percent
                }
            except Exception as e:
                disk_info[drive] = {"error": str(e)}
        else:
            # Get all drives
            for partition in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disk_info[partition.device] = {
                        "mountpoint": partition.mountpoint,
                        "fstype": partition.fstype,
                        "total_gb": usage.total / (1024 ** 3),
                        "used_gb": usage.used / (1024 ** 3),
                        "free_gb": usage.free / (1024 ** 3),
                        "percent": usage.percent
                    }
                except (PermissionError, OSError):
                    # Skip drives that can't be accessed
                    continue
        
        return disk_info
    
    def get_process_stats(self, pid: int) -> Dict[str, Any]:
        """
        Get CPU and memory stats for a specific process
        
        Args:
            pid: Process ID
        
        Returns:
            Dictionary with process resource usage
        """
        try:
            process = psutil.Process(pid)
            
            if process.is_running():
                return {
                    "pid": pid,
                    "name": process.name(),
                    "cpu_percent": process.cpu_percent(interval=0.5),
                    "memory_percent": process.memory_percent(),
                    "memory_mb": process.memory_info().rss / (1024 * 1024),
                    "num_threads": process.num_threads(),
                    "status": process.status(),
                    "timestamp": datetime.now().isoformat(),
                    "error": None
                }
            else:
                return {
                    "pid": pid,
                    "error": "Process not running"
                }
                
        except psutil.NoSuchProcess:
            return {
                "pid": pid,
                "error": "Process not found"
            }
        except psutil.AccessDenied:
            return {
                "pid": pid,
                "error": "Access denied"
            }
        except Exception as e:
            return {
                "pid": pid,
                "error": str(e)
            }
    
    def check_threshold(self, monitor_type: str, current_value: float, threshold: float, item_id: int) -> Dict[str, Any]:
        """
        Check if current value exceeds threshold
        
        Args:
            monitor_type: Type of monitoring (cpu, ram, disk, etc.)
            current_value: Current measured value
            threshold: Threshold value
            item_id: Monitored item ID
        
        Returns:
            Dictionary with threshold check result
        """
        exceeded = current_value >= threshold
        
        # Track history
        if item_id not in self.threshold_history:
            self.threshold_history[item_id] = {
                "exceeded": exceeded,
                "count": 1 if exceeded else 0,
                "last_value": current_value
            }
        else:
            if exceeded:
                self.threshold_history[item_id]["count"] += 1
            else:
                self.threshold_history[item_id]["count"] = 0
            
            self.threshold_history[item_id]["exceeded"] = exceeded
            self.threshold_history[item_id]["last_value"] = current_value
        
        return {
            "monitor_type": monitor_type,
            "current_value": current_value,
            "threshold": threshold,
            "exceeded": exceeded,
            "consecutive_count": self.threshold_history[item_id]["count"],
            "timestamp": datetime.now().isoformat()
        }
    
    def get_system_overview(self) -> Dict[str, Any]:
        """Get overall system statistics"""
        return {
            "cpu_percent": self.get_cpu_usage(),
            "memory": self.get_memory_usage(),
            "disk": self.get_disk_usage(),
            "timestamp": datetime.now().isoformat()
        }

