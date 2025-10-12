"""File-based logging manager with weekly rotation for WinSentry"""

import os
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path


class LogManager:
    """Manages file-based logging with weekly rotation"""
    
    def __init__(self, log_dir: str = "logs/script_execution"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.current_log_file = self._get_current_log_file()
    
    def _get_current_log_file(self) -> str:
        """Get the current log file path based on week number"""
        now = datetime.now()
        week_num = now.isocalendar()[1]
        year = now.year
        return os.path.join(self.log_dir, f"script_execution_{year}_week{week_num:02d}.log")
    
    def _check_rotation(self):
        """Check if we need to rotate to a new log file"""
        current_file = self._get_current_log_file()
        if current_file != self.current_log_file:
            self.current_log_file = current_file
    
    def log_job_created(self, job_id: str, script_config: Dict[str, Any], trigger_data: Dict[str, Any]):
        """Log when a job is created and queued"""
        self._check_rotation()
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "job_id": job_id,
            "event": "job_created",
            "monitored_item_type": trigger_data.get("type"),
            "monitored_item_id": trigger_data.get("id"),
            "script_config_id": script_config.get("id"),
            "trigger_reason": trigger_data.get("reason"),
            "status": "queued",
            "script_type": script_config.get("script_type", ""),
            "script_content": script_config.get("content", "") if script_config.get("content") else "",
            "script_path": script_config.get("file_path", "")
        }
        
        self._write_log_entry(log_entry)
    
    def log_job_result(self, job_id: str, result_data: Dict[str, Any]):
        """Log the result of a job execution"""
        self._check_rotation()
        
        # Create output directory for this job
        output_dir = os.path.join(self.log_dir, "output")
        os.makedirs(output_dir, exist_ok=True)
        
        # Save stdout to file
        stdout_file = None
        stdout_content = result_data.get("stdout", "")
        if stdout_content:
            stdout_file = os.path.join(output_dir, f"{job_id}_stdout.txt")
            try:
                with open(stdout_file, 'w', encoding='utf-8') as f:
                    f.write(stdout_content)
                stdout_file = os.path.abspath(stdout_file)  # Store absolute path
            except Exception as e:
                print(f"Failed to write stdout file: {e}")
                stdout_file = None
        
        # Save stderr to file
        stderr_file = None
        stderr_content = result_data.get("stderr", "")
        if stderr_content:
            stderr_file = os.path.join(output_dir, f"{job_id}_stderr.txt")
            try:
                with open(stderr_file, 'w', encoding='utf-8') as f:
                    f.write(stderr_content)
                stderr_file = os.path.abspath(stderr_file)  # Store absolute path
            except Exception as e:
                print(f"Failed to write stderr file: {e}")
                stderr_file = None
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "job_id": job_id,
            "event": "job_completed",
            "status": result_data.get("status"),
            "exit_code": result_data.get("exit_code"),
            "execution_time": result_data.get("execution_time"),
            "stdout_file": stdout_file,  # Path to stdout file
            "stderr_file": stderr_file,  # Path to stderr file
            "stdout_size": len(stdout_content) if stdout_content else 0,
            "stderr_size": len(stderr_content) if stderr_content else 0,
            "error_message": result_data.get("error_message"),
            "retry_count": result_data.get("retry_count", 0)
        }
        
        self._write_log_entry(log_entry)
    
    def log_worker_error(self, error_message: str):
        """Log worker process errors"""
        self._check_rotation()
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "worker_error",
            "error_message": error_message
        }
        
        self._write_log_entry(log_entry)
    
    def _write_log_entry(self, entry: Dict[str, Any]):
        """Write a log entry to the current log file"""
        try:
            with open(self.current_log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"Failed to write log entry: {e}")
    
    def get_log_files(self) -> List[str]:
        """Get list of all log files"""
        try:
            files = [f for f in os.listdir(self.log_dir) if f.endswith('.log')]
            return sorted(files, reverse=True)  # Most recent first
        except FileNotFoundError:
            return []
    
    def get_output_file(self, job_id: str, output_type: str = "stdout") -> Optional[str]:
        """Get the path to stdout or stderr file for a job"""
        output_dir = os.path.join(self.log_dir, "output")
        filename = f"{job_id}_{output_type}.txt"
        filepath = os.path.join(output_dir, filename)
        
        if os.path.exists(filepath):
            return os.path.abspath(filepath)
        return None
    
    def read_output_file(self, job_id: str, output_type: str = "stdout") -> Optional[str]:
        """Read the contents of a stdout or stderr file"""
        filepath = self.get_output_file(job_id, output_type)
        if filepath and os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                print(f"Failed to read {output_type} file: {e}")
                return None
        return None
    
    def read_logs(self, filename: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Read log entries from a log file"""
        if filename is None:
            filename = os.path.basename(self.current_log_file)
        
        filepath = os.path.join(self.log_dir, filename)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Parse JSON lines
            logs = []
            for line in lines:
                line = line.strip()
                if line:
                    try:
                        logs.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            
            # Return latest entries with pagination
            logs.reverse()  # Latest first
            return logs[offset:offset + limit]
            
        except FileNotFoundError:
            return []
        except Exception as e:
            print(f"Error reading logs: {e}")
            return []
    
    def search_logs(self, job_id: str) -> List[Dict[str, Any]]:
        """Search for logs by job ID"""
        logs = self.read_logs(limit=1000)  # Search recent logs
        return [log for log in logs if log.get("job_id") == job_id]


class MonitoringLogger:
    """Logger for monitoring status changes"""
    
    def __init__(self, log_dir: str = "logs/monitoring"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.current_log_file = self._get_current_log_file()
    
    def _get_current_log_file(self) -> str:
        """Get the current log file path based on week number"""
        now = datetime.now()
        week_num = now.isocalendar()[1]
        year = now.year
        return os.path.join(self.log_dir, f"monitoring_{year}_week{week_num:02d}.log")
    
    def _check_rotation(self):
        """Check if we need to rotate to a new log file"""
        current_file = self._get_current_log_file()
        if current_file != self.current_log_file:
            self.current_log_file = current_file
    
    def log_status_change(self, item_type: str, item_id: int, old_status: str, new_status: str, details: Dict[str, Any] = None):
        """Log a status change event"""
        self._check_rotation()
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "status_change",
            "item_type": item_type,
            "item_id": item_id,
            "old_status": old_status,
            "new_status": new_status,
            "details": details or {}
        }
        
        self._write_log_entry(log_entry)
    
    def log_check(self, item_type: str, item_id: int, status: str, details: Dict[str, Any] = None):
        """Log a monitoring check"""
        self._check_rotation()
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "check",
            "item_type": item_type,
            "item_id": item_id,
            "status": status,
            "details": details or {}
        }
        
        self._write_log_entry(log_entry)

    def log_event(self, item_type: str, item_id: int, event_message: str, details: Dict[str, Any] = None):
        """Log a generic monitoring event"""
        self._check_rotation()
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": event_message,
            "item_type": item_type,
            "item_id": item_id,
            "details": details or {}
        }
        
        self._write_log_entry(log_entry)
        
    def _write_log_entry(self, entry: Dict[str, Any]):
        """Write a log entry to the current log file"""
        try:
            with open(self.current_log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"Failed to write monitoring log entry: {e}")
    
    def get_log_files(self) -> List[str]:
        """Get list of all monitoring log files"""
        try:
            files = [f for f in os.listdir(self.log_dir) if f.endswith('.log')]
            return sorted(files, reverse=True)  # Most recent first
        except FileNotFoundError:
            return []


# Global instances (will be initialized in app.py)
log_manager: Optional[LogManager] = None
monitoring_logger: Optional[MonitoringLogger] = None

