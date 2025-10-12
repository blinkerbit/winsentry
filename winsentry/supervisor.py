"""Process supervisor for keeping commands alive"""

import subprocess
import threading
import time
import psutil
import os
from datetime import datetime
from typing import Dict, Optional


class ProcessSupervisor:
    """Manages supervised processes that should stay alive"""
    
    def __init__(self, db, monitoring_logger):
        self.db = db
        self.logger = monitoring_logger
        self.supervised_processes: Dict[int, dict] = {}  # process_id -> process info
        self.monitoring_threads: Dict[int, threading.Thread] = {}
        self.running = False
        
    def start(self):
        """Start the supervisor service"""
        self.running = True
        print("🔄 Starting Process Supervisor...")
        
        # Load all enabled supervised processes
        self._load_supervised_processes()
        
    def stop(self):
        """Stop the supervisor service"""
        self.running = False
        print("🛑 Stopping Process Supervisor...")
        
        # Stop all monitoring threads
        for thread in self.monitoring_threads.values():
            if thread.is_alive():
                thread.join(timeout=2)
        
        # Terminate all supervised processes
        for proc_id, proc_info in self.supervised_processes.items():
            if proc_info.get('process'):
                try:
                    proc_info['process'].terminate()
                    print(f"  ✓ Terminated supervised process: {proc_info['name']}")
                except:
                    pass
    
    def _load_supervised_processes(self):
        """Load all enabled supervised processes from database"""
        rows = self.db.execute_query(
            "SELECT * FROM supervised_processes WHERE enabled = 1"
        )
        
        for row in rows:
            proc_data = dict(row)
            proc_id = proc_data['id']
            self.supervised_processes[proc_id] = proc_data
            
            # Start monitoring thread for each process
            thread = threading.Thread(
                target=self._monitor_process,
                args=(proc_id,),
                daemon=True
            )
            thread.start()
            self.monitoring_threads[proc_id] = thread
            
            print(f"  ✓ Started supervising: {proc_data['name']}")
    
    def _monitor_process(self, proc_id: int):
        """Monitor a single supervised process"""
        proc_data = self.supervised_processes.get(proc_id)
        if not proc_data:
            return
        
        process_obj = None
        last_pid = None
        
        while self.running and proc_data.get('enabled', True):
            try:
                # Refresh process data from database
                rows = self.db.execute_query(
                    "SELECT * FROM supervised_processes WHERE id = ?",
                    (proc_id,)
                )
                if not rows:
                    break
                
                proc_data = dict(rows[0])
                self.supervised_processes[proc_id] = proc_data
                
                if not proc_data.get('enabled'):
                    print(f"[SUPERVISOR] Process {proc_data['name']} disabled, stopping monitor")
                    break
                
                # Check if process is running
                is_running = False
                if process_obj and process_obj.poll() is None:
                    is_running = True
                
                # Check restart limits
                max_restarts = proc_data.get('max_restarts', 0)
                restart_count = proc_data.get('restart_count', 0)
                
                if max_restarts > 0 and restart_count >= max_restarts:
                    print(f"[SUPERVISOR] {proc_data['name']} reached max restarts ({max_restarts})")
                    self._log_event(proc_id, 'max_restarts_reached', {
                        'restart_count': restart_count,
                        'max_restarts': max_restarts
                    })
                    break
                
                if not is_running:
                    # Process needs to be started
                    print(f"[SUPERVISOR] Starting process: {proc_data['name']}")
                    
                    # Wait for restart delay if this is a restart
                    if restart_count > 0:
                        restart_delay = proc_data.get('restart_delay', 3)
                        print(f"[SUPERVISOR] Waiting {restart_delay}s before restart...")
                        time.sleep(restart_delay)
                    
                    # Start the process
                    process_obj = self._start_process(proc_data)
                    
                    if process_obj:
                        # Get the PID
                        pid = process_obj.pid
                        last_pid = pid
                        
                        # Update database
                        new_restart_count = restart_count + 1 if restart_count > 0 else 0
                        self.db.execute_update(
                            """UPDATE supervised_processes 
                               SET current_pid = ?, restart_count = ?, 
                                   last_started_at = CURRENT_TIMESTAMP 
                               WHERE id = ?""",
                            (pid, new_restart_count, proc_id)
                        )
                        
                        self._log_event(proc_id, 'started', {
                            'pid': pid,
                            'restart_count': new_restart_count,
                            'command': proc_data['command']
                        })
                        
                        print(f"[SUPERVISOR] ✓ Started {proc_data['name']} (PID: {pid})")
                
                # Sleep for monitoring interval
                monitoring_interval = proc_data.get('monitoring_interval', 5)
                time.sleep(monitoring_interval)
                
            except Exception as e:
                print(f"[SUPERVISOR] Error monitoring {proc_data['name']}: {e}")
                self._log_event(proc_id, 'error', {'error': str(e)})
                time.sleep(5)  # Wait before retrying
    
    def _start_process(self, proc_data: dict) -> Optional[subprocess.Popen]:
        """Start a supervised process"""
        try:
            command = proc_data['command']
            working_dir = proc_data.get('working_directory')
            
            # Validate working directory
            if working_dir and not os.path.exists(working_dir):
                print(f"[SUPERVISOR] Warning: Working directory does not exist: {working_dir}")
                working_dir = None
            
            # Build PowerShell command
            ps_cmd = [
                'powershell.exe',
                '-ExecutionPolicy', 'Bypass',
                '-NoProfile',
                '-Command', f'[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; {command}'
            ]
            
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            
            # Start the process
            process = subprocess.Popen(
                ps_cmd,
                cwd=working_dir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            return process
            
        except Exception as e:
            print(f"[SUPERVISOR] Failed to start process: {e}")
            self._log_event(proc_data['id'], 'start_failed', {'error': str(e)})
            return None
    
    def _log_event(self, proc_id: int, event_type: str, data: dict):
        """Log supervisor events"""
        proc_data = self.supervised_processes.get(proc_id, {})
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'supervisor_id': proc_id,
            'name': proc_data.get('name', 'unknown'),
            'event': event_type,
            **data
        }
        
        # Use the monitoring logger
        self.logger.log_status_change(
            monitor_type='supervised',
            monitor_id=proc_id,
            old_status=None,
            new_status=event_type,
            metadata=data
        )
    
    def add_supervised_process(self, proc_id: int):
        """Add a new process to supervision"""
        rows = self.db.execute_query(
            "SELECT * FROM supervised_processes WHERE id = ? AND enabled = 1",
            (proc_id,)
        )
        
        if rows:
            proc_data = dict(rows[0])
            self.supervised_processes[proc_id] = proc_data
            
            # Start monitoring thread
            thread = threading.Thread(
                target=self._monitor_process,
                args=(proc_id,),
                daemon=True
            )
            thread.start()
            self.monitoring_threads[proc_id] = thread
            
            print(f"[SUPERVISOR] ✓ Added new supervised process: {proc_data['name']}")
    
    def remove_supervised_process(self, proc_id: int):
        """Remove a process from supervision"""
        if proc_id in self.supervised_processes:
            proc_data = self.supervised_processes[proc_id]
            
            # Mark as disabled
            proc_data['enabled'] = False
            
            # Stop the process if running
            if proc_data.get('process'):
                try:
                    proc_data['process'].terminate()
                except:
                    pass
            
            # Remove from tracking
            del self.supervised_processes[proc_id]
            
            print(f"[SUPERVISOR] ✓ Removed supervised process: {proc_data['name']}")
    
    def get_process_status(self, proc_id: int) -> dict:
        """Get status of a supervised process"""
        proc_data = self.supervised_processes.get(proc_id)
        if not proc_data:
            return {'status': 'unknown'}
        
        is_running = False
        pid = proc_data.get('current_pid')
        
        if pid:
            try:
                process = psutil.Process(pid)
                is_running = process.is_running()
            except psutil.NoSuchProcess:
                is_running = False
        
        return {
            'status': 'running' if is_running else 'stopped',
            'pid': pid if is_running else None,
            'restart_count': proc_data.get('restart_count', 0),
            'last_started_at': proc_data.get('last_started_at')
        }


