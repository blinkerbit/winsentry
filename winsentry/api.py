"""API endpoints for WinSentry"""

import json
import os
from fastapi import APIRouter, HTTPException, Request, Depends
from typing import List, Dict, Any, Optional

from .models import (
    MonitoredPort, MonitoredPortCreate,
    MonitoredProcess, MonitoredProcessCreate,
    MonitoredService, MonitoredServiceCreate,
    SupervisedProcess, SupervisedProcessCreate,
    SystemMonitoring, SystemMonitoringCreate,
    AlertRule, AlertRuleCreate,
    EmailTemplate, EmailTemplateCreate,
    EmailServer, EmailServerCreate,
    ScriptConfig, ScriptConfigCreate,
    Recipient, RecipientCreate,
    MonitorStatus, SystemStats
)

router = APIRouter()


# Dependency to get database from app state
def get_db(request: Request):
    return request.app.state.db


# Health Check
@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": "0.1.0"}


# Port Monitoring Endpoints
@router.get("/ports", response_model=List[Dict[str, Any]])
async def get_monitored_ports(db=Depends(get_db)):
    """Get all monitored ports"""
    rows = db.execute_query("SELECT * FROM monitored_ports ORDER BY port_number")
    ports = []
    for row in rows:
        port_dict = dict(row)
        port_dict['script_type'] = port_dict.get('script_type_stopped')
        port_dict['script_content'] = port_dict.get('script_content_stopped')
        port_dict['script_path'] = port_dict.get('script_path_stopped')
        ports.append(port_dict)
    return ports


@router.post("/ports", response_model=Dict[str, Any])
async def create_monitored_port(port: MonitoredPortCreate, db=Depends(get_db)):
    """Create a new monitored port"""
    query = """
        INSERT INTO monitored_ports (
            port_number, monitoring_interval, 
            script_type_stopped, script_content_stopped, script_path_stopped,
            script_type_running, script_content_running, script_path_running,
            duration_threshold, max_script_executions,
            retry_interval_multiplier, trigger_on_status, enabled
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        port.port_number, port.monitoring_interval,
        port.script_type_stopped.value, port.script_content_stopped, port.script_path_stopped,
        port.script_type_running.value, port.script_content_running, port.script_path_running,
        port.duration_threshold, port.max_script_executions,
        port.retry_interval_multiplier, port.trigger_on_status, port.enabled
    )
    
    port_id = db.execute_insert(query, params)
    row = db.execute_query("SELECT * FROM monitored_ports WHERE id = ?", (port_id,))[0]
    return dict(row)


@router.put("/ports/{port_id}", response_model=Dict[str, Any])
async def update_monitored_port(port_id: int, port: MonitoredPortCreate, db=Depends(get_db)):
    """Update a monitored port"""
    query = """
        UPDATE monitored_ports 
        SET port_number=?, monitoring_interval=?, 
            script_type_stopped=?, script_content_stopped=?, script_path_stopped=?,
            script_type_running=?, script_content_running=?, script_path_running=?,
            duration_threshold=?, max_script_executions=?, 
            retry_interval_multiplier=?, trigger_on_status=?, enabled=?, 
            updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """
    params = (
        port.port_number, port.monitoring_interval,
        port.script_type_stopped.value, port.script_content_stopped, port.script_path_stopped,
        port.script_type_running.value, port.script_content_running, port.script_path_running,
        port.duration_threshold, port.max_script_executions,
        port.retry_interval_multiplier, port.trigger_on_status, port.enabled, port_id
    )
    
    db.execute_update(query, params)
    row = db.execute_query("SELECT * FROM monitored_ports WHERE id = ?", (port_id,))[0]
    return dict(row)


@router.delete("/ports/{port_id}")
async def delete_monitored_port(port_id: int, db=Depends(get_db)):
    """Delete a monitored port"""
    db.execute_update("DELETE FROM monitored_ports WHERE id = ?", (port_id,))
    return {"message": "Port deleted successfully"}


@router.get("/ports/{port_id}/status")
async def check_port_status(port_id: int, request: Request, db=Depends(get_db)):
    """Check current status of a monitored port"""
    rows = db.execute_query("SELECT * FROM monitored_ports WHERE id = ?", (port_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Port not found")
    
    port = dict(rows[0])
    port_monitor = request.app.state.port_monitor
    status = port_monitor.check_port(port["port_number"])
    
    # Get last status change
    last_change = db.get_last_status_change("port", port_id)
    
    # Record status change if status is different or if it's the first check
    if not last_change or last_change["status"] != status["status"]:
        db.record_status_change("port", port_id, status["status"], {
            "process_name": status.get("process_name"),
            "pid": status.get("pid")
        })
        status["last_status_change"] = status["timestamp"]
    else:
        status["last_status_change"] = last_change["changed_at"]
    
    return status


@router.post("/ports/{port_id}/execute-script")
async def execute_port_script(port_id: int, request: Request, db=Depends(get_db), status: Optional[str] = None):
    """Manually execute the script for a monitored port"""
    rows = db.execute_query("SELECT * FROM monitored_ports WHERE id = ?", (port_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Port not found")
    
    port = dict(rows[0])

    script_state = status or port.get("trigger_on_status", "stopped")
    if script_state not in ("stopped", "running", "both"):
        raise HTTPException(status_code=400, detail="Invalid script status requested")

    # Determine which script configuration to use
    if script_state == "running":
        script_type = port.get("script_type_running") or "inline"
        script_content = port.get("script_content_running")
        script_path = port.get("script_path_running")
    elif script_state == "stopped":
        script_type = port.get("script_type_stopped") or "inline"
        script_content = port.get("script_content_stopped")
        script_path = port.get("script_path_stopped")
    else:  # both -> default to stopped script for manual trigger
        script_type = port.get("script_type_stopped") or "inline"
        script_content = port.get("script_content_stopped")
        script_path = port.get("script_path_stopped")

    # Check if script is configured
    if not script_content and not script_path:
        raise HTTPException(status_code=400, detail=f"No {script_state} script configured for this port")
    
    # Queue script execution
    script_executor = request.app.state.script_executor
    script_config = {
        "script_type": script_type,
        "content": script_content,
        "file_path": script_path,
        "timeout_seconds": 300
    }
    
    trigger_data = {
        "type": "port",
        "id": port_id,
        "reason": f"Manual execution ({script_state}) for Port {port['port_number']}"
    }
    
    job_id = script_executor.execute_script_async(script_config, trigger_data)
    
    return {
        "status": "queued",
        "job_id": job_id,
        "message": f"Script execution ({script_state}) queued for port {port['port_number']}"
    }


@router.post("/ports/{port_id}/toggle-auto-execute")
async def toggle_port_auto_execute(port_id: int, enabled: bool, db=Depends(get_db)):
    """Toggle automatic script execution for a monitored port"""
    rows = db.execute_query("SELECT * FROM monitored_ports WHERE id = ?", (port_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Port not found")
    
    query = "UPDATE monitored_ports SET enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
    db.execute_update(query, (enabled, port_id))
    
    return {
        "status": "success",
        "port_id": port_id,
        "auto_execute_enabled": enabled,
        "message": f"Auto-execute {'enabled' if enabled else 'disabled'} for port monitoring"
    }


@router.post("/ports/{port_id}/kill-process")
async def kill_port_process(port_id: int, force: bool = False, request: Request = None, db=Depends(get_db)):
    """Kill the process listening on a monitored port"""
    import psutil
    import signal
    
    rows = db.execute_query("SELECT * FROM monitored_ports WHERE id = ?", (port_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Port not found")
    
    port = dict(rows[0])
    port_number = port["port_number"]
    
    # Find the process on this port
    port_monitor = request.app.state.port_monitor
    status = port_monitor.check_port(port_number)
    
    if status["status"] == "stopped":
        raise HTTPException(status_code=400, detail=f"No process listening on port {port_number}")
    
    pid = status.get("pid")
    if not pid:
        raise HTTPException(status_code=400, detail=f"Could not identify process on port {port_number}")
    
    try:
        process = psutil.Process(pid)
        process_name = process.name()
        
        if force:
            # Force kill (SIGKILL)
            process.kill()
            action = "force killed"
        else:
            # Normal termination (SIGTERM)
            process.terminate()
            action = "terminated"
        
        return {
            "status": "success",
            "pid": pid,
            "process_name": process_name,
            "port": port_number,
            "action": action,
            "message": f"Process {process_name} (PID: {pid}) {action} successfully"
        }
    except psutil.NoSuchProcess:
        raise HTTPException(status_code=404, detail=f"Process with PID {pid} not found")
    except psutil.AccessDenied:
        raise HTTPException(status_code=403, detail=f"Access denied. Run as administrator to kill this process")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to kill process: {str(e)}")


# Process Monitoring Endpoints
@router.get("/processes", response_model=List[Dict[str, Any]])
async def get_monitored_processes(db=Depends(get_db)):
    """Get all monitored processes"""
    rows = db.execute_query("SELECT * FROM monitored_processes ORDER BY id")
    procs = []
    for row in rows:
        proc_dict = dict(row)
        proc_dict['script_type'] = proc_dict.get('script_type_stopped')
        proc_dict['script_content'] = proc_dict.get('script_content_stopped')
        proc_dict['script_path'] = proc_dict.get('script_path_stopped')
        procs.append(proc_dict)
    return procs


@router.post("/processes", response_model=Dict[str, Any])
async def create_monitored_process(process: MonitoredProcessCreate, db=Depends(get_db)):
    """Create a new monitored process"""
    query = """
        INSERT INTO monitored_processes (
            process_id, process_name, monitoring_interval, 
            script_type_stopped, script_content_stopped, script_path_stopped,
            script_type_running, script_content_running, script_path_running,
            duration_threshold, max_script_executions, 
            retry_interval_multiplier, trigger_on_status, enabled
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        process.process_id, process.process_name, process.monitoring_interval,
        process.script_type_stopped.value, process.script_content_stopped, process.script_path_stopped, 
        process.script_type_running.value, process.script_content_running, process.script_path_running,
        process.duration_threshold, process.max_script_executions,
        process.retry_interval_multiplier, process.trigger_on_status, process.enabled
    )
    
    proc_id = db.execute_insert(query, params)
    row = db.execute_query("SELECT * FROM monitored_processes WHERE id = ?", (proc_id,))[0]
    return dict(row)


@router.put("/processes/{process_id}", response_model=Dict[str, Any])
async def update_monitored_process(process_id: int, process: MonitoredProcessCreate, db=Depends(get_db)):
    """Update a monitored process"""
    query = """
        UPDATE monitored_processes 
        SET process_id=?, process_name=?, monitoring_interval=?, 
            script_type_stopped=?, script_content_stopped=?, script_path_stopped=?,
            script_type_running=?, script_content_running=?, script_path_running=?,
            duration_threshold=?, max_script_executions=?, 
            retry_interval_multiplier=?, trigger_on_status=?, enabled=?,
            updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """
    params = (
        process.process_id, process.process_name, process.monitoring_interval,
        process.script_type_stopped.value, process.script_content_stopped, process.script_path_stopped,
        process.script_type_running.value, process.script_content_running, process.script_path_running,
        process.duration_threshold, process.max_script_executions,
        process.retry_interval_multiplier, process.trigger_on_status, process.enabled, process_id
    )
    
    db.execute_update(query, params)
    row = db.execute_query("SELECT * FROM monitored_processes WHERE id = ?", (process_id,))[0]
    return dict(row)


@router.delete("/processes/{process_id}")
async def delete_monitored_process(process_id: int, db=Depends(get_db)):
    """Delete a monitored process"""
    db.execute_update("DELETE FROM monitored_processes WHERE id = ?", (process_id,))
    return {"message": "Process deleted successfully"}


@router.get("/processes/{process_id}/status")
async def check_process_status(process_id: int, request: Request, db=Depends(get_db)):
    """Check current status of a monitored process"""
    rows = db.execute_query("SELECT * FROM monitored_processes WHERE id = ?", (process_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Process not found")
    
    proc = dict(rows[0])
    process_monitor = request.app.state.process_monitor
    status = process_monitor.check_process(proc["process_id"])
    
    # Get last status change
    last_change = db.get_last_status_change("process", process_id)
    
    # Record status change if status is different or if it's the first check
    if not last_change or last_change["status"] != status["status"]:
        db.record_status_change("process", process_id, status["status"], {
            "process_name": status.get("process_name"),
            "cpu_percent": status.get("cpu_percent"),
            "memory_mb": status.get("memory_mb")
        })
        status["last_status_change"] = status["timestamp"]
    else:
        status["last_status_change"] = last_change["changed_at"]
    
    return status


@router.post("/processes/{process_id}/execute-script")
async def execute_process_script(process_id: int, request: Request, db=Depends(get_db), status: Optional[str] = None):
    """Manually execute the script for a monitored process"""
    rows = db.execute_query("SELECT * FROM monitored_processes WHERE id = ?", (process_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Process not found")
    
    proc = dict(rows[0])
    
    script_state = status or proc.get("trigger_on_status", "stopped")
    if script_state not in ("stopped", "running", "both"):
        raise HTTPException(status_code=400, detail="Invalid script status requested")

    # Determine which script configuration to use
    if script_state == "running":
        script_type = proc.get("script_type_running") or "inline"
        script_content = proc.get("script_content_running")
        script_path = proc.get("script_path_running")
    else:  # 'stopped' or 'both' -> default to stopped for manual trigger
        script_type = proc.get("script_type_stopped") or "inline"
        script_content = proc.get("script_content_stopped")
        script_path = proc.get("script_path_stopped")

    # Check if script is configured
    if not script_content and not script_path:
        raise HTTPException(status_code=400, detail=f"No {script_state} script configured for this process")
    
    # Queue script execution
    script_executor = request.app.state.script_executor
    script_config = {
        "script_type": script_type,
        "content": script_content,
        "file_path": script_path,
        "timeout_seconds": 300
    }
    
    trigger_data = {
        "type": "process",
        "id": process_id,
        "reason": f"Manual execution ({script_state}) for Process {proc.get('process_name') or proc.get('process_id')}"
    }
    
    job_id = script_executor.execute_script_async(script_config, trigger_data)
    
    return {
        "status": "queued",
        "job_id": job_id,
        "message": f"Script execution ({script_state}) queued for process {proc.get('process_name') or proc.get('process_id')}"
    }


@router.post("/processes/{process_id}/toggle-auto-execute")
async def toggle_process_auto_execute(process_id: int, enabled: bool, db=Depends(get_db)):
    """Toggle automatic script execution for a monitored process"""
    rows = db.execute_query("SELECT * FROM monitored_processes WHERE id = ?", (process_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Process not found")
    
    query = "UPDATE monitored_processes SET enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
    db.execute_update(query, (enabled, process_id))
    
    return {
        "status": "success",
        "process_id": process_id,
        "auto_execute_enabled": enabled,
        "message": f"Auto-execute {'enabled' if enabled else 'disabled'} for process monitoring"
    }


@router.post("/processes/{process_id}/kill-process")
async def kill_monitored_process(process_id: int, force: bool = False, request: Request = None, db=Depends(get_db)):
    """Kill a monitored process"""
    import psutil
    
    rows = db.execute_query("SELECT * FROM monitored_processes WHERE id = ?", (process_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Process not found")
    
    proc = dict(rows[0])
    pid = proc["process_id"]
    
    try:
        process = psutil.Process(pid)
        process_name = process.name()
        
        if force:
            # Force kill (SIGKILL)
            process.kill()
            action = "force killed"
        else:
            # Normal termination (SIGTERM)
            process.terminate()
            action = "terminated"
        
        return {
            "status": "success",
            "pid": pid,
            "process_name": process_name,
            "action": action,
            "message": f"Process {process_name} (PID: {pid}) {action} successfully"
        }
    except psutil.NoSuchProcess:
        raise HTTPException(status_code=404, detail=f"Process with PID {pid} not found")
    except psutil.AccessDenied:
        raise HTTPException(status_code=403, detail=f"Access denied. Run as administrator to kill this process")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to kill process: {str(e)}")


# Service Monitoring Endpoints
@router.get("/services", response_model=List[Dict[str, Any]])
async def get_monitored_services(db=Depends(get_db)):
    """Get all monitored services"""
    rows = db.execute_query("SELECT * FROM monitored_services ORDER BY service_name")
    return [dict(row) for row in rows]


@router.post("/services", response_model=Dict[str, Any])
async def create_monitored_service(service: MonitoredServiceCreate, db=Depends(get_db)):
    """Create a new monitored service"""
    query = """
        INSERT INTO monitored_services (service_name, display_name, monitoring_interval, 
                   restart_config, state_duration_threshold, enabled)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    params = (
        service.service_name, service.display_name, service.monitoring_interval,
        service.restart_config,
        service.state_duration_threshold, service.enabled
    )
    
    svc_id = db.execute_insert(query, params)
    row = db.execute_query("SELECT * FROM monitored_services WHERE id = ?", (svc_id,))[0]
    return dict(row)


@router.delete("/services/{service_id}")
async def delete_monitored_service(service_id: int, db=Depends(get_db)):
    """Delete a monitored service"""
    db.execute_update("DELETE FROM monitored_services WHERE id = ?", (service_id,))
    return {"message": "Service deleted successfully"}


@router.get("/services/{service_id}/status")
async def check_service_status(service_id: int, request: Request, db=Depends(get_db)):
    """Check current status of a monitored service"""
    rows = db.execute_query("SELECT * FROM monitored_services WHERE id = ?", (service_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Service not found")
    
    svc = dict(rows[0])
    service_monitor = request.app.state.service_monitor
    status = service_monitor.check_service(svc["service_name"])
    
    # Get last status change
    last_change = db.get_last_status_change("service", service_id)
    
    # Record status change if status is different or if it's the first check
    if not last_change or last_change["status"] != status["status"]:
        db.record_status_change("service", service_id, status["status"], {
            "display_name": status.get("display_name")
        })
        status["last_status_change"] = status["timestamp"]
    else:
        status["last_status_change"] = last_change["changed_at"]
    
    return status


@router.post("/services/{service_id}/execute-script")
async def execute_service_script(service_id: int, request: Request, db=Depends(get_db)):
    """Manually execute the script for a monitored service"""
    rows = db.execute_query("SELECT * FROM monitored_services WHERE id = ?", (service_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Service not found")
    
    svc = dict(rows[0])
    
    # Check if script is configured
    if not svc.get("script_content") and not svc.get("script_path"):
        raise HTTPException(status_code=400, detail="No script configured for this service")
    
    # Queue script execution
    script_executor = request.app.state.script_executor
    script_config = {
        "script_type": svc.get("script_type", "inline"),
        "content": svc.get("script_content"),
        "file_path": svc.get("script_path"),
        "timeout_seconds": 300
    }
    
    trigger_data = {
        "type": "service",
        "id": service_id,
        "reason": f"Manual execution for Service {svc['service_name']}"
    }
    
    job_id = script_executor.execute_script_async(script_config, trigger_data)
    
    return {
        "status": "queued",
        "job_id": job_id,
        "message": f"Script execution queued for service {svc['service_name']}"
    }


@router.post("/services/{service_id}/toggle-auto-execute")
async def toggle_service_auto_execute(service_id: int, enabled: bool, db=Depends(get_db)):
    """Toggle automatic script execution for a monitored service"""
    rows = db.execute_query("SELECT * FROM monitored_services WHERE id = ?", (service_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Service not found")
    
    query = "UPDATE monitored_services SET enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
    db.execute_update(query, (enabled, service_id))
    
    return {
        "status": "success",
        "service_id": service_id,
        "auto_execute_enabled": enabled,
        "message": f"Auto-execute {'enabled' if enabled else 'disabled'} for service monitoring"
    }


@router.post("/services/{service_id}/restart")
async def restart_service(service_id: int, request: Request, db=Depends(get_db)):
    """Restart a Windows service"""
    rows = db.execute_query("SELECT * FROM monitored_services WHERE id = ?", (service_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Service not found")
    
    svc = dict(rows[0])
    service_monitor = request.app.state.service_monitor
    result = service_monitor.restart_service(svc["service_name"])
    
    return result


# Supervised Process Endpoints
@router.get("/supervised", response_model=List[Dict[str, Any]])
async def get_supervised_processes(db=Depends(get_db)):
    """Get all supervised processes"""
    rows = db.execute_query("SELECT * FROM supervised_processes ORDER BY name")
    return [dict(row) for row in rows]


@router.post("/supervised", response_model=Dict[str, Any])
async def create_supervised_process(process: SupervisedProcessCreate, db=Depends(get_db)):
    """Create a new supervised process"""
    query = """
        INSERT INTO supervised_processes (name, command, working_directory, 
                   monitoring_interval, restart_delay, max_restarts, enabled)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        process.name, process.command, process.working_directory,
        process.monitoring_interval, process.restart_delay, 
        process.max_restarts, process.enabled
    )
    
    proc_id = db.execute_insert(query, params)
    row = db.execute_query("SELECT * FROM supervised_processes WHERE id = ?", (proc_id,))[0]
    return dict(row)


@router.put("/supervised/{process_id}", response_model=Dict[str, Any])
async def update_supervised_process(process_id: int, process: SupervisedProcessCreate, db=Depends(get_db)):
    """Update a supervised process"""
    query = """
        UPDATE supervised_processes 
        SET name=?, command=?, working_directory=?, monitoring_interval=?, 
            restart_delay=?, max_restarts=?, enabled=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """
    params = (
        process.name, process.command, process.working_directory,
        process.monitoring_interval, process.restart_delay,
        process.max_restarts, process.enabled, process_id
    )
    
    db.execute_update(query, params)
    row = db.execute_query("SELECT * FROM supervised_processes WHERE id = ?", (process_id,))[0]
    return dict(row)


@router.delete("/supervised/{process_id}")
async def delete_supervised_process(process_id: int, db=Depends(get_db)):
    """Delete a supervised process"""
    db.execute_update("DELETE FROM supervised_processes WHERE id = ?", (process_id,))
    return {"message": "Supervised process deleted"}


@router.post("/supervised/{process_id}/start")
async def start_supervised_process(process_id: int, request: Request, db=Depends(get_db)):
    """Manually start a supervised process"""
    rows = db.execute_query("SELECT * FROM supervised_processes WHERE id = ?", (process_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Supervised process not found")
    
    # This will be handled by the supervisor service
    return {"message": "Start signal sent to supervisor", "process_id": process_id}


@router.post("/supervised/{process_id}/stop")
async def stop_supervised_process(process_id: int, db=Depends(get_db)):
    """Manually stop a supervised process"""
    rows = db.execute_query("SELECT * FROM supervised_processes WHERE id = ?", (process_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Supervised process not found")
    
    proc = dict(rows[0])
    if proc.get('current_pid'):
        import psutil
        try:
            process = psutil.Process(proc['current_pid'])
            process.terminate()
            # Clear PID from database
            db.execute_update("UPDATE supervised_processes SET current_pid = NULL WHERE id = ?", (process_id,))
            return {"message": "Process terminated", "pid": proc['current_pid']}
        except psutil.NoSuchProcess:
            return {"message": "Process not running"}
    
    return {"message": "Process not running"}


# System Monitoring Endpoints
@router.get("/system", response_model=List[Dict[str, Any]])
async def get_system_monitoring(db=Depends(get_db)):
    """Get all system monitoring configurations"""
    rows = db.execute_query("SELECT * FROM system_monitoring ORDER BY monitor_type")
    return [dict(row) for row in rows]


@router.post("/system", response_model=Dict[str, Any])
async def create_system_monitoring(config: SystemMonitoringCreate, db=Depends(get_db)):
    """Create a new system monitoring configuration"""
    query = """
        INSERT INTO system_monitoring (monitor_type, threshold_value, 
                   monitoring_interval, process_reference, drive_letter, enabled)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    params = (
        config.monitor_type.value, config.threshold_value, config.monitoring_interval,
        config.process_reference, config.drive_letter, config.enabled
    )
    
    sys_id = db.execute_insert(query, params)
    row = db.execute_query("SELECT * FROM system_monitoring WHERE id = ?", (sys_id,))[0]
    return dict(row)


@router.delete("/system/{system_id}")
async def delete_system_monitoring(system_id: int, db=Depends(get_db)):
    """Delete a system monitoring configuration"""
    db.execute_update("DELETE FROM system_monitoring WHERE id = ?", (system_id,))
    return {"message": "System monitoring deleted successfully"}


@router.get("/system/stats")
async def get_system_stats(request: Request):
    """Get current system statistics"""
    system_monitor = request.app.state.system_monitor
    stats = system_monitor.get_system_overview()
    return stats


# Alert Rules Endpoints
@router.get("/alerts", response_model=List[Dict[str, Any]])
async def get_alert_rules(db=Depends(get_db)):
    """Get all alert rules"""
    rows = db.execute_query("SELECT * FROM alert_rules ORDER BY monitored_item_type, monitored_item_id")
    return [dict(row) for row in rows]


@router.post("/alerts", response_model=Dict[str, Any])
async def create_alert_rule(alert: AlertRuleCreate, db=Depends(get_db)):
    """Create a new alert rule"""
    query = """
        INSERT INTO alert_rules (monitored_item_id, monitored_item_type, alert_condition,
                   condition_value, recurring_schedule, template_id, enabled)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        alert.monitored_item_id, alert.monitored_item_type.value, alert.alert_condition.value,
        alert.condition_value, alert.recurring_schedule, alert.template_id, alert.enabled
    )
    
    alert_id = db.execute_insert(query, params)
    
    # Add recipients
    if alert.recipient_ids:
        for recipient_id in alert.recipient_ids:
            db.execute_insert(
                "INSERT INTO alert_recipients (alert_id, recipient_id) VALUES (?, ?)",
                (alert_id, recipient_id)
            )
    
    row = db.execute_query("SELECT * FROM alert_rules WHERE id = ?", (alert_id,))[0]
    return dict(row)


@router.delete("/alerts/{alert_id}")
async def delete_alert_rule(alert_id: int, db=Depends(get_db)):
    """Delete an alert rule"""
    db.execute_update("DELETE FROM alert_rules WHERE id = ?", (alert_id,))
    return {"message": "Alert rule deleted successfully"}


# Email Templates Endpoints
@router.get("/templates", response_model=List[Dict[str, Any]])
async def get_email_templates(db=Depends(get_db)):
    """Get all email templates"""
    rows = db.execute_query("SELECT * FROM email_templates ORDER BY template_name")
    return [dict(row) for row in rows]


@router.post("/templates", response_model=Dict[str, Any])
async def create_email_template(template: EmailTemplateCreate, db=Depends(get_db)):
    """Create a new email template"""
    query = """
        INSERT INTO email_templates (template_name, subject_template, body_template, variables)
        VALUES (?, ?, ?, ?)
    """
    params = (
        template.template_name, template.subject_template, template.body_template,
        json.dumps(template.variables) if template.variables else None
    )
    
    tmpl_id = db.execute_insert(query, params)
    row = db.execute_query("SELECT * FROM email_templates WHERE id = ?", (tmpl_id,))[0]
    return dict(row)


@router.delete("/templates/{template_id}")
async def delete_email_template(template_id: int, db=Depends(get_db)):
    """Delete an email template"""
    db.execute_update("DELETE FROM email_templates WHERE id = ?", (template_id,))
    return {"message": "Email template deleted successfully"}


# SMTP Server Endpoints
@router.get("/smtp", response_model=List[Dict[str, Any]])
async def get_email_servers(db=Depends(get_db)):
    """Get all email server configurations"""
    rows = db.execute_query("SELECT * FROM email_servers ORDER BY smtp_host")
    return [dict(row) for row in rows]


@router.post("/smtp", response_model=Dict[str, Any])
async def create_email_server(server: EmailServerCreate, db=Depends(get_db)):
    """Create a new email server configuration"""
    query = """
        INSERT INTO email_servers (smtp_host, smtp_port, use_ssl, use_tls, username, 
                   password, from_address, default_template_id, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        server.smtp_host, server.smtp_port, server.use_ssl, server.use_tls, server.username,
        server.password, server.from_address, server.default_template_id, server.is_active
    )
    
    srv_id = db.execute_insert(query, params)
    row = db.execute_query("SELECT * FROM email_servers WHERE id = ?", (srv_id,))[0]
    return dict(row)


@router.delete("/smtp/{server_id}")
async def delete_email_server(server_id: int, db=Depends(get_db)):
    """Delete an email server configuration"""
    db.execute_update("DELETE FROM email_servers WHERE id = ?", (server_id,))
    return {"message": "Email server deleted successfully"}


# Script Configurations Endpoints
@router.get("/scripts", response_model=List[Dict[str, Any]])
async def get_script_configs(db=Depends(get_db)):
    """Get all script configurations"""
    rows = db.execute_query("SELECT * FROM script_configs ORDER BY script_name")
    return [dict(row) for row in rows]


@router.post("/scripts", response_model=Dict[str, Any])
async def create_script_config(script: ScriptConfigCreate, db=Depends(get_db)):
    """Create a new script configuration"""
    query = """
        INSERT INTO script_configs (script_name, script_type, content, file_path,
                   timeout_seconds, success_handling, failure_handling)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        script.script_name, script.script_type.value, script.content, script.file_path,
        script.timeout_seconds, script.success_handling, script.failure_handling
    )
    
    scr_id = db.execute_insert(query, params)
    row = db.execute_query("SELECT * FROM script_configs WHERE id = ?", (scr_id,))[0]
    return dict(row)


@router.post("/scripts/execute")
async def execute_script(script_config_id: int, trigger_data: Dict[str, Any], request: Request, db=Depends(get_db)):
    """Queue a script for execution"""
    rows = db.execute_query("SELECT * FROM script_configs WHERE id = ?", (script_config_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Script configuration not found")
    
    script_config = dict(rows[0])
    script_executor = request.app.state.script_executor
    job_id = script_executor.execute_script_async(script_config, trigger_data)
    
    return {"job_id": job_id, "status": "queued"}


@router.get("/scripts/jobs/{job_id}")
async def get_job_status(job_id: str, request: Request):
    """Get status of a script execution job"""
    script_executor = request.app.state.script_executor
    status = script_executor.get_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return status


@router.get("/scripts/jobs/{job_id}/output/{output_type}")
async def get_job_output(job_id: str, output_type: str, request: Request):
    """Get stdout or stderr output for a script execution job"""
    if output_type not in ["stdout", "stderr"]:
        raise HTTPException(status_code=400, detail="output_type must be 'stdout' or 'stderr'")
    
    log_manager = request.app.state.log_manager
    
    # Get the file path
    filepath = log_manager.get_output_file(job_id, output_type)
    if not filepath:
        raise HTTPException(status_code=404, detail=f"No {output_type} file found for job {job_id}")
    
    # Read the content
    content = log_manager.read_output_file(job_id, output_type)
    if content is None:
        raise HTTPException(status_code=500, detail=f"Failed to read {output_type} file")
    
    return {
        "job_id": job_id,
        "output_type": output_type,
        "filepath": filepath,
        "content": content,
        "size": len(content)
    }


# Recipients Endpoints
@router.get("/recipients", response_model=List[Dict[str, Any]])
async def get_recipients(db=Depends(get_db)):
    """Get all recipients"""
    rows = db.execute_query("SELECT * FROM recipients ORDER BY email_address")
    return [dict(row) for row in rows]


@router.post("/recipients", response_model=Dict[str, Any])
async def create_recipient(recipient: RecipientCreate, db=Depends(get_db)):
    """Create a new recipient"""
    query = """
        INSERT INTO recipients (email_address, name, alert_types, enabled)
        VALUES (?, ?, ?, ?)
    """
    params = (
        recipient.email_address, recipient.name,
        json.dumps(recipient.alert_types) if recipient.alert_types else None,
        recipient.enabled
    )
    
    rec_id = db.execute_insert(query, params)
    row = db.execute_query("SELECT * FROM recipients WHERE id = ?", (rec_id,))[0]
    return dict(row)


@router.delete("/recipients/{recipient_id}")
async def delete_recipient(recipient_id: int, db=Depends(get_db)):
    """Delete a recipient"""
    db.execute_update("DELETE FROM recipients WHERE id = ?", (recipient_id,))
    return {"message": "Recipient deleted successfully"}


# Logs Endpoints
@router.get("/logs/scripts")
async def get_script_logs(request: Request, limit: int = 100, offset: int = 0):
    """Get script execution logs"""
    log_manager = request.app.state.log_manager
    logs = log_manager.read_logs(limit=limit, offset=offset)
    return {"logs": logs, "total": len(logs)}


@router.get("/logs/files")
async def get_log_files(request: Request):
    """Get list of log files with full paths"""
    log_manager = request.app.state.log_manager
    monitoring_logger = request.app.state.monitoring_logger
    
    # Get script execution log files with full paths
    script_files = []
    for filename in log_manager.get_log_files():
        full_path = os.path.join(log_manager.log_dir, filename)
        script_files.append({
            "name": filename,
            "path": full_path,
            "type": "script_execution"
        })
    
    # Get monitoring log files with full paths
    monitoring_files = []
    for filename in monitoring_logger.get_log_files():
        full_path = os.path.join(monitoring_logger.log_dir, filename)
        monitoring_files.append({
            "name": filename,
            "path": full_path,
            "type": "monitoring"
        })
    
    return {
        "script_execution": script_files,
        "monitoring": monitoring_files,
        "all": script_files + monitoring_files
    }


@router.get("/logs/monitoring")
async def get_monitoring_logs(request: Request):
    """Get monitoring logs"""
    monitoring_logger = request.app.state.monitoring_logger
    # Read recent monitoring logs
    return {"message": "Monitoring logs endpoint"}

