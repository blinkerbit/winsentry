"""Background monitoring service for continuous status checks"""

import asyncio
import threading
import time
from datetime import datetime
from typing import Dict, Any, Optional
from collections import defaultdict
import json

from .database import DatabaseManager
from .monitors import PortMonitor, ProcessMonitor, ServiceMonitor
from .script_executor import ScriptExecutor
from .log_manager import MonitoringLogger
from .alert_engine import AlertEngine


class BackgroundMonitor:
    """Manages continuous background monitoring of all configured items"""
    
    def __init__(
        self,
        db: DatabaseManager,
        port_monitor: PortMonitor,
        process_monitor: ProcessMonitor,
        service_monitor: ServiceMonitor,
        system_monitor: Any, # Add system_monitor
        script_executor: ScriptExecutor,
        monitoring_logger: MonitoringLogger,
        alert_engine: AlertEngine
    ):
        self.db = db
        self.port_monitor = port_monitor
        self.process_monitor = process_monitor
        self.service_monitor = service_monitor
        self.system_monitor = system_monitor # Add this
        self.script_executor = script_executor
        self.monitoring_logger = monitoring_logger
        self.alert_engine = alert_engine
        
        # Track status duration for each monitor
        # Format: {(monitor_type, monitor_id): {"status": str, "count": int, "last_check": timestamp, "script_executions": int}}
        self.status_tracker: Dict[tuple, Dict[str, Any]] = defaultdict(lambda: {
            "status": None,
            "count": 0,
            "last_check": None,
            "script_executions": 0,  # Track how many times script has been executed
            "last_script_execution": 0  # Timestamp of last script execution
        })
        
        self.running = False
        self.monitor_threads: Dict[str, threading.Thread] = {}
    
    def start(self):
        """Start background monitoring for all enabled monitors"""
        if self.running:
            return
        
        self.running = True
        print("[MONITOR] Starting background monitoring service...")
        
        # Start a thread for each monitoring type
        self.monitor_threads["ports"] = threading.Thread(target=self._monitor_ports_loop)
        self.monitor_threads["processes"] = threading.Thread(target=self._monitor_processes_loop)
        self.monitor_threads["services"] = threading.Thread(target=self._monitor_services_loop)
        self.monitor_threads["system"] = threading.Thread(target=self._monitor_system_loop)
        
        for thread in self.monitor_threads.values():
            thread.start()
            
        print("[MONITOR] Background monitoring started")
    
    def stop(self):
        """Stop background monitoring"""
        print("[MONITOR] Stopping background monitoring service...")
        self.running = False
        
        # Wait for threads to finish
        for thread in self.monitor_threads.values():
            if thread.is_alive():
                thread.join(timeout=5)
        
        print("[MONITOR] Background monitoring stopped")
    
    def _monitor_ports_loop(self):
        """Background loop for port monitoring"""
        while self.running:
            try:
                # Get all enabled port monitors
                rows = self.db.execute_query(
                    "SELECT * FROM monitored_ports WHERE enabled = 1"
                )
                
                for row in rows:
                    if not self.running:
                        break
                    
                    port = dict(row)
                    self._check_port(port)
                
                # Sleep for 1 second before next iteration
                time.sleep(1)
                
            except Exception as e:
                print(f"[ERROR] Port monitoring loop: {e}")
                time.sleep(5)
    
    def _monitor_processes_loop(self):
        """Background loop for process monitoring"""
        while self.running:
            try:
                # Get all enabled process monitors
                rows = self.db.execute_query(
                    "SELECT * FROM monitored_processes WHERE enabled = 1"
                )
                
                for row in rows:
                    if not self.running:
                        break
                    
                    process = dict(row)
                    self._check_process(process)
                
                # Sleep for 1 second before next iteration
                time.sleep(1)
                
            except Exception as e:
                print(f"[ERROR] Process monitoring loop: {e}")
                time.sleep(5)
    
    def _monitor_services_loop(self):
        """Background loop for service monitoring"""
        while self.running:
            try:
                # Get all enabled service monitors
                rows = self.db.execute_query(
                    "SELECT * FROM monitored_services WHERE enabled = 1"
                )
                
                for row in rows:
                    if not self.running:
                        break
                    
                    service = dict(row)
                    self._check_service(service)
                
                # Sleep for 1 second before next iteration
                time.sleep(1)
                
            except Exception as e:
                print(f"[ERROR] Service monitoring loop: {e}")
                time.sleep(5)

    def _monitor_system_loop(self):
        """Background loop for system monitoring"""
        while self.running:
            try:
                # Get all enabled system monitors
                rows = self.db.execute_query(
                    "SELECT * FROM system_monitoring WHERE enabled = 1"
                )
                
                if not rows:
                    time.sleep(5)
                    continue

                # Get current system stats once for all checks
                current_stats = self.system_monitor.get_system_overview()

                for row in rows:
                    if not self.running:
                        break
                    
                    monitor = dict(row)
                    self._check_system_metric(monitor, current_stats)
                
                # Sleep for 5 seconds before next iteration (system stats don't need rapid checks)
                time.sleep(5)
                
            except Exception as e:
                print(f"[ERROR] System monitoring loop: {e}")
                time.sleep(10)

    def _check_port(self, port: Dict[str, Any]):
        """Check a single port and handle status/script execution"""
        port_id = port['id']
        port_number = port['port_number']
        interval = port['monitoring_interval']
        
        tracker_key = ('port', port_id)
        tracker = self.status_tracker[tracker_key]
        
        # Check if it's time to monitor this port
        now = time.time()
        if tracker['last_check'] and (now - tracker['last_check']) < interval:
            return
        
        # Check port status
        try:
            status_info = self.port_monitor.check_port(port_number)
            current_status = status_info['status']
            
            # Update last check time
            tracker['last_check'] = now
            
            # Initialize tracker on first check by looking at database history
            if tracker['status'] is None:
                last_change = self.db.get_last_status_change('port', port_id)
                if last_change and last_change['status'] == current_status:
                    # Status has been the same since last change
                    # Calculate how many intervals have passed
                    from datetime import datetime
                    last_change_time = datetime.fromisoformat(last_change['changed_at'])
                    time_since_change = (datetime.now() - last_change_time).total_seconds()
                    intervals_since_change = max(1, int(time_since_change / interval))
                    tracker['status'] = current_status
                    tracker['count'] = intervals_since_change
                    print(f"[MONITOR] Initializing Port {port_number}: status={current_status}, count={intervals_since_change} intervals since {last_change_time}")
                else:
                    tracker['status'] = current_status
                    tracker['count'] = 1
            
            # Check if status changed
            elif tracker['status'] != current_status:
                # Status changed - reset counter and script execution tracking
                old_status = tracker['status']
                tracker['status'] = current_status
                tracker['count'] = 1
                tracker['script_executions'] = 0
                tracker['last_script_execution'] = 0
                
                # Record status change in database
                self.db.record_status_change('port', port_id, current_status, {
                    'process_name': status_info.get('process_name'),
                    'pid': status_info.get('pid')
                })
                
                # Log status change
                self.monitoring_logger.log_status_change(
                    'port',
                    port_id,
                    old_status or 'unknown',
                    current_status,
                    {'port_number': port_number}
                )
                
                # Check for status change alerts
                self.alert_engine.check_status_change_alert('port', port_id, old_status, current_status)
            else:
                # Status same - increment counter
                tracker['count'] += 1
                
                # Check if duration threshold reached
                duration_threshold = port.get('duration_threshold', 1)
                if tracker['count'] >= duration_threshold:
                    # Get configuration from database (per-monitor settings)
                    MAX_SCRIPT_EXECUTIONS = port.get('max_script_executions', 5)
                    RETRY_INTERVAL_MULTIPLIER = port.get('retry_interval_multiplier', 10)
                    trigger_on_status = port.get('trigger_on_status', 'stopped')
                    
                    # Check if script should run for this status
                    status_matches = (
                        trigger_on_status == 'both' or
                        trigger_on_status == current_status
                    )
                    
                    if not status_matches:
                        # Status doesn't match trigger condition, skip script execution
                        pass
                    else:
                        # Calculate intervals since last script execution
                        intervals_since_last_script = tracker['count'] - tracker['last_script_execution']
                        retry_interval = duration_threshold * RETRY_INTERVAL_MULTIPLIER
                        
                        # Should execute if:
                        # 1. First time hitting threshold, OR
                        # 2. Enough intervals have passed since last execution AND under max executions
                        should_execute = (
                            tracker['script_executions'] == 0 or  # First time
                            (tracker['script_executions'] < MAX_SCRIPT_EXECUTIONS and 
                             intervals_since_last_script >= retry_interval)  # Periodic retry with limit
                        )
                        
                        if should_execute:
                            tracker['script_executions'] += 1
                            tracker['last_script_execution'] = tracker['count']
                            print(f"[SCRIPT] Attempt {tracker['script_executions']}/{MAX_SCRIPT_EXECUTIONS}")
                            self._execute_port_script(port, current_status, tracker['count'])
                    
                    # Check for duration alerts
                    self.alert_engine.check_duration_alert('port', port_id, current_status, tracker['count'])
        
        except Exception as e:
            print(f"[ERROR] Checking port {port_number}: {e}")
    
    def _check_process(self, process: Dict[str, Any]):
        """Check a single process and handle status/script execution"""
        proc_id = process['id']
        pid = process['process_id']
        interval = process['monitoring_interval']
        
        tracker_key = ('process', proc_id)
        tracker = self.status_tracker[tracker_key]
        
        # Check if it's time to monitor this process
        now = time.time()
        if tracker['last_check'] and (now - tracker['last_check']) < interval:
            return
        
        # Check process status
        try:
            status_info = self.process_monitor.check_process(pid)
            current_status = status_info['status']
            
            # Update last check time
            tracker['last_check'] = now
            
            # Initialize tracker on first check by looking at database history
            if tracker['status'] is None:
                last_change = self.db.get_last_status_change('process', proc_id)
                if last_change and last_change['status'] == current_status:
                    # Status has been the same since last change
                    from datetime import datetime
                    last_change_time = datetime.fromisoformat(last_change['changed_at'])
                    time_since_change = (datetime.now() - last_change_time).total_seconds()
                    intervals_since_change = max(1, int(time_since_change / interval))
                    tracker['status'] = current_status
                    tracker['count'] = intervals_since_change
                    print(f"[MONITOR] Initializing Process {pid}: status={current_status}, count={intervals_since_change} intervals since {last_change_time}")
                else:
                    tracker['status'] = current_status
                    tracker['count'] = 1
            
            # Check if status changed
            elif tracker['status'] != current_status:
                # Status changed - reset counter and script execution tracking
                old_status = tracker['status']
                tracker['status'] = current_status
                tracker['count'] = 1
                tracker['script_executions'] = 0
                tracker['last_script_execution'] = 0
                
                # Record status change in database
                self.db.record_status_change('process', proc_id, current_status, {
                    'process_name': status_info.get('process_name'),
                    'cpu_percent': status_info.get('cpu_percent'),
                    'memory_mb': status_info.get('memory_mb')
                })
                
                # Log status change
                self.monitoring_logger.log_status_change(
                    'process',
                    proc_id,
                    old_status or 'unknown',
                    current_status,
                    {'process_id': pid}
                )
                
                # Check for status change alerts
                self.alert_engine.check_status_change_alert('process', proc_id, old_status, current_status)
            else:
                # Status same - increment counter
                tracker['count'] += 1
                
                # Check if duration threshold reached
                duration_threshold = process.get('duration_threshold', 1)
                if tracker['count'] >= duration_threshold:
                    # Get configuration from database (per-monitor settings)
                    MAX_SCRIPT_EXECUTIONS = process.get('max_script_executions', 5)
                    RETRY_INTERVAL_MULTIPLIER = process.get('retry_interval_multiplier', 10)
                    trigger_on_status = process.get('trigger_on_status', 'stopped')
                    
                    # Check if script should run for this status
                    status_matches = (
                        trigger_on_status == 'both' or
                        trigger_on_status == current_status
                    )
                    
                    if not status_matches:
                        # Status doesn't match trigger condition, skip script execution
                        pass
                    else:
                        intervals_since_last_script = tracker['count'] - tracker['last_script_execution']
                        retry_interval = duration_threshold * RETRY_INTERVAL_MULTIPLIER
                        
                        should_execute = (
                            tracker['script_executions'] == 0 or
                            (tracker['script_executions'] < MAX_SCRIPT_EXECUTIONS and 
                             intervals_since_last_script >= retry_interval)
                        )
                        
                        if should_execute:
                            tracker['script_executions'] += 1
                            tracker['last_script_execution'] = tracker['count']
                            print(f"[SCRIPT] Attempt {tracker['script_executions']}/{MAX_SCRIPT_EXECUTIONS}")
                            self._execute_process_script(process, current_status, tracker['count'])
                    
                    # Check for duration alerts
                    self.alert_engine.check_duration_alert('process', proc_id, current_status, tracker['count'])
        
        except Exception as e:
            print(f"[ERROR] Checking process {pid}: {e}")
    
    def _check_service(self, service: Dict[str, Any]):
        """Check a single service and handle status"""
        svc_id = service['id']
        svc_name = service['service_name']
        interval = service['monitoring_interval']
        
        tracker_key = ('service', svc_id)
        tracker = self.status_tracker[tracker_key]
        
        # Check if it's time to monitor this service
        now = time.time()
        if tracker['last_check'] and (now - tracker['last_check']) < interval:
            return
        
        # Check service status
        try:
            status_info = self.service_monitor.check_service(svc_name)
            current_status = status_info['status']
            
            # Update last check time
            tracker['last_check'] = now
            
            # Initialize tracker on first check by looking at database history
            if tracker['status'] is None:
                last_change = self.db.get_last_status_change('service', svc_id)
                if last_change and last_change['status'] == current_status:
                    # Status has been the same since last change
                    from datetime import datetime
                    last_change_time = datetime.fromisoformat(last_change['changed_at'])
                    time_since_change = (datetime.now() - last_change_time).total_seconds()
                    intervals_since_change = max(1, int(time_since_change / interval))
                    tracker['status'] = current_status
                    tracker['count'] = intervals_since_change
                    print(f"[MONITOR] Initializing Service {svc_name}: status={current_status}, count={intervals_since_change} intervals since {last_change_time}")
                else:
                    tracker['status'] = current_status
                    tracker['count'] = 1
            
            # Check if status changed
            elif tracker['status'] != current_status:
                # Status changed - reset counter and script execution tracking
                old_status = tracker['status']
                tracker['status'] = current_status
                tracker['count'] = 1
                tracker['script_executions'] = 0
                tracker['last_script_execution'] = 0
                
                # Record status change in database
                self.db.record_status_change('service', svc_id, current_status, {
                    'display_name': status_info.get('display_name')
                })
                
                # Log status change
                self.monitoring_logger.log_status_change(
                    'service',
                    svc_id,
                    old_status or 'unknown',
                    current_status,
                    {'service_name': svc_name}
                )
                
                # Check for status change alerts
                self.alert_engine.check_status_change_alert('service', svc_id, old_status, current_status)
            else:
                # Status same - increment counter
                tracker['count'] += 1
                
                # Check for duration alerts
                self.alert_engine.check_duration_alert('service', svc_id, current_status, tracker['count'])
        
        except Exception as e:
            print(f"[ERROR] Checking service {svc_name}: {e}")
    
    def _check_system_metric(self, monitor: Dict[str, Any], stats: Dict[str, Any]):
        """Check a system metric against its threshold and trigger alerts"""
        monitor_key = ("system", monitor["id"])
        last_check_time = self.status_tracker[monitor_key]["last_check"]
        
        # Throttle checks based on monitoring interval
        if last_check_time and (time.time() - last_check_time < monitor["monitoring_interval"]):
            return

        self.status_tracker[monitor_key]["last_check"] = time.time()
        
        metric_type = monitor["monitor_type"]
        threshold = monitor["threshold_value"]
        
        current_value = None
        is_exceeded = False

        if metric_type == 'cpu' and stats['cpu_percent'] > threshold:
            is_exceeded = True
            current_value = stats['cpu_percent']
        elif metric_type == 'ram' and stats['memory']['percent'] > threshold:
            is_exceeded = True
            current_value = stats['memory']['percent']
        elif metric_type == 'disk' and monitor.get('drive_letter'):
            drive = monitor['drive_letter']
            if drive in stats['disk'] and stats['disk'][drive]['percent'] > threshold:
                is_exceeded = True
                current_value = stats['disk'][drive]['percent']

        if is_exceeded:
            self.monitoring_logger.log_event(
                "system", monitor["id"], f"Threshold exceeded for {metric_type.upper()}",
                details={"threshold": threshold, "value": current_value}
            )
            # Trigger an alert
            self.alert_engine.check_threshold_alert(
                item_type="system",
                item_id=monitor["id"],
                metric_type=metric_type,
                current_value=current_value,
                threshold=threshold
            )

    def _execute_port_script(self, port: Dict[str, Any], status: str, duration: int):
        """Execute configured script for a port"""
        if status == "running":
            script_type = port.get("script_type_running")
            script_content = port.get("script_content_running")
            script_path = port.get("script_path_running")
        else:  # 'stopped' or other
            script_type = port.get("script_type_stopped")
            script_content = port.get("script_content_stopped")
            script_path = port.get("script_path_stopped")

        if not script_content and not script_path:
            return
        
        script_type = script_type or 'inline'
        
        print(f"[SCRIPT] Executing script for Port {port['port_number']} (status: {status}, duration: {duration} intervals)")
        
        # Queue script execution
        script_config = {
            'script_type': script_type,
            'content': script_content,
            'file_path': script_path,
            'timeout_seconds': 300
        }
        
        trigger_data = {
            'trigger_type': 'duration_threshold',
            'monitor_type': 'port',
            'monitor_id': port['id'],
            'port_number': port['port_number'],
            'status': status,
            'duration_intervals': duration,
            'reason': f"Port {port['port_number']} {status} for {duration} intervals"
        }
        
        job_id = self.script_executor.execute_script_async(script_config, trigger_data)
        
        print(f"[SCRIPT] Script queued with job ID: {job_id}")
    
    def _execute_process_script(self, process: Dict[str, Any], status: str, duration: int):
        """Execute configured script for a process"""
        if status == "running":
            script_type = process.get("script_type_running")
            script_content = process.get("script_content_running")
            script_path = process.get("script_path_running")
        else:  # 'stopped' or other
            script_type = process.get("script_type_stopped")
            script_content = process.get("script_content_stopped")
            script_path = process.get("script_path_stopped")

        if not script_content and not script_path:
            return
        
        script_type = script_type or 'inline'
        
        print(f"[SCRIPT] Executing script for PID {process['process_id']} (status: {status}, duration: {duration} intervals)")
        
        # Queue script execution
        script_config = {
            'script_type': script_type,
            'content': script_content,
            'file_path': script_path,
            'timeout_seconds': 300
        }
        
        trigger_data = {
            'trigger_type': 'duration_threshold',
            'monitor_type': 'process',
            'monitor_id': process['id'],
            'process_id': process['process_id'],
            'status': status,
            'duration_intervals': duration,
            'reason': f"Process {process['process_id']} {status} for {duration} intervals"
        }
        
        job_id = self.script_executor.execute_script_async(script_config, trigger_data)
        
        print(f"[SCRIPT] Script queued with job ID: {job_id}")

