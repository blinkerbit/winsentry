"""Non-blocking PowerShell script execution using process pool"""

import multiprocessing
import queue
import subprocess
import uuid
import time
import os
from typing import Dict, Any, Optional
from threading import Thread


class ScriptExecutor:
    """Manages non-blocking script execution with worker process pool"""
    
    def __init__(self, max_workers: int = 4, log_manager=None):
        self.max_workers = max_workers
        self.log_manager = log_manager
        self.job_queue = multiprocessing.Queue()
        self.result_queue = multiprocessing.Queue()
        self.job_tracker = {}
        self.workers = []
        self.running = True
        
        # Start worker processes
        for i in range(max_workers):
            worker = multiprocessing.Process(
                target=self._worker_loop,
                args=(self.job_queue, self.result_queue),
                name=f"ScriptWorker-{i}"
            )
            worker.daemon = True
            worker.start()
            self.workers.append(worker)
        
        # Start result processor thread
        self.result_thread = Thread(target=self._process_results, daemon=True)
        self.result_thread.start()
    
    def execute_script_async(self, script_config: Dict[str, Any], trigger_data: Dict[str, Any]) -> str:
        """
        Queue a script for execution and return immediately
        
        Args:
            script_config: Dictionary with script configuration (type, content/path, timeout)
            trigger_data: Dictionary with trigger information (type, id, reason)
        
        Returns:
            job_id: Unique identifier for the job
        """
        job_id = str(uuid.uuid4())
        
        # Log job creation
        if self.log_manager:
            self.log_manager.log_job_created(job_id, script_config, trigger_data)
        
        # Add to queue
        self.job_queue.put((job_id, script_config, trigger_data))
        
        # Track job
        self.job_tracker[job_id] = {
            "status": "queued",
            "queued_time": time.time(),
            "script_config": script_config,
            "trigger_data": trigger_data
        }
        
        return job_id
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of a job"""
        return self.job_tracker.get(job_id)
    
    def _process_results(self):
        """Background thread to process results from workers"""
        while self.running:
            try:
                job_id, result = self.result_queue.get(timeout=1)
                
                # Update job tracker
                if job_id in self.job_tracker:
                    self.job_tracker[job_id].update({
                        "status": result["status"],
                        "completion_time": time.time(),
                        "result": result
                    })
                
                # Log result
                if self.log_manager:
                    self.log_manager.log_job_result(job_id, result)
                    
            except queue.Empty:
                continue
            except Exception as e:
                if self.log_manager:
                    self.log_manager.log_worker_error(f"Result processing error: {str(e)}")
    
    @staticmethod
    def _worker_loop(job_queue, result_queue):
        """Worker process main loop"""
        while True:
            try:
                job_id, script_config, trigger_data = job_queue.get(timeout=1)
                result = ScriptExecutor._execute_job(script_config)
                result_queue.put((job_id, result))
            except queue.Empty:
                continue
            except Exception as e:
                result_queue.put((job_id, {
                    "status": "error",
                    "error_message": str(e),
                    "exit_code": -1
                }))
    
    @staticmethod
    def _execute_job(script_config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a PowerShell script"""
        start_time = time.time()
        
        try:
            script_type = script_config.get("script_type", "inline")
            timeout = script_config.get("timeout_seconds", 300)
            
            if script_type == "file" and script_config.get("file_path"):
                # Execute script from file with UTF-8 encoding
                cmd = [
                    'powershell.exe', 
                    '-ExecutionPolicy', 'Bypass',
                    '-Command', f'[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; & "{script_config["file_path"]}"'
                ]
            else:
                # Execute inline script with UTF-8 encoding
                script_content = script_config.get("content") or script_config.get("script_content", "")
                cmd = [
                    'powershell.exe', 
                    '-ExecutionPolicy', 'Bypass',
                    '-Command', f'[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; {script_content}'
                ]
            
            # Execute with timeout
            # Use bytes mode and decode with UTF-8 to handle Unicode properly
            # Set environment to use UTF-8 encoding
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            try:
                stdout_bytes, stderr_bytes = process.communicate(timeout=timeout)
                execution_time = time.time() - start_time
                
                # Decode with UTF-8, replacing errors instead of failing
                stdout = stdout_bytes.decode('utf-8', errors='replace') if stdout_bytes else ""
                stderr = stderr_bytes.decode('utf-8', errors='replace') if stderr_bytes else ""
                
                return {
                    "status": "completed" if process.returncode == 0 else "failed",
                    "exit_code": process.returncode,
                    "execution_time": execution_time,
                    "stdout": stdout,
                    "stderr": stderr,
                    "error_message": None
                }
            
            except subprocess.TimeoutExpired:
                process.kill()
                stdout_bytes, stderr_bytes = process.communicate()
                execution_time = time.time() - start_time
                
                # Decode with UTF-8, replacing errors instead of failing
                stdout = stdout_bytes.decode('utf-8', errors='replace') if stdout_bytes else ""
                stderr = stderr_bytes.decode('utf-8', errors='replace') if stderr_bytes else ""
                
                return {
                    "status": "timeout",
                    "exit_code": -1,
                    "execution_time": execution_time,
                    "stdout": stdout,
                    "stderr": stderr,
                    "error_message": f"Execution timeout after {timeout} seconds"
                }
        
        except Exception as e:
            execution_time = time.time() - start_time
            
            return {
                "status": "error",
                "exit_code": -1,
                "execution_time": execution_time,
                "stdout": "",
                "stderr": "",
                "error_message": str(e)
            }
    
    def stop(self):
        """Stop the script executor and all workers"""
        self.running = False
        
        # Terminate workers
        for worker in self.workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=2)
        
        # Wait for result thread
        if self.result_thread.is_alive():
            self.result_thread.join(timeout=2)


# Global script executor instance (will be initialized in app.py)
script_executor: Optional[ScriptExecutor] = None

