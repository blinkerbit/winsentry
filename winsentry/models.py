"""Pydantic models for WinSentry API and database schemas"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ScriptType(str, Enum):
    """Script type enum"""
    INLINE = "inline"
    FILE = "file"


class MonitorType(str, Enum):
    """Monitor type enum"""
    PORT = "port"
    PROCESS = "process"
    SERVICE = "service"
    SYSTEM = "system"


class AlertCondition(str, Enum):
    """Alert condition enum"""
    STATUS_CHANGE = "status_change"
    DURATION = "duration"
    RECURRING = "recurring"
    THRESHOLD = "threshold"


class SystemMonitorType(str, Enum):
    """System monitor type enum"""
    CPU = "cpu"
    RAM = "ram"
    DISK = "disk"
    PROCESS_CPU = "process_cpu"
    PROCESS_RAM = "process_ram"


# Port Monitoring Models
class MonitoredPortBase(BaseModel):
    """Base model for port monitoring"""
    port_number: int = Field(..., gt=0, le=65535, description="Port number to monitor")
    monitoring_interval: int = Field(default=5, gt=0, description="Check interval in seconds")
    script_type_stopped: ScriptType = Field(default=ScriptType.INLINE)
    script_content_stopped: Optional[str] = None
    script_path_stopped: Optional[str] = None
    script_type_running: ScriptType = Field(default=ScriptType.INLINE)
    script_content_running: Optional[str] = None
    script_path_running: Optional[str] = None
    duration_threshold: int = Field(default=1, gt=0, description="Number of intervals before script execution")
    max_script_executions: int = Field(default=5, gt=0, description="Maximum script retry attempts")
    retry_interval_multiplier: int = Field(default=10, gt=0, description="Multiplier for retry interval (retries every threshold × multiplier)")
    trigger_on_status: str = Field(default="stopped", description="Status that triggers script: 'stopped', 'running', or 'both'")
    enabled: bool = Field(default=True)


class MonitoredPortCreate(MonitoredPortBase):
    """Model for creating a port monitor"""
    pass


class MonitoredPort(MonitoredPortBase):
    """Model for port monitor with database fields"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Process Monitoring Models
class MonitoredProcessBase(BaseModel):
    """Base model for process monitoring"""
    process_id: Optional[int] = Field(None, description="Process ID to monitor")
    process_name: Optional[str] = Field(None, description="Process name for reference")
    monitoring_interval: int = Field(default=5, gt=0)
    script_type_stopped: ScriptType = Field(default=ScriptType.INLINE)
    script_content_stopped: Optional[str] = None
    script_path_stopped: Optional[str] = None
    script_type_running: ScriptType = Field(default=ScriptType.INLINE)
    script_content_running: Optional[str] = None
    script_path_running: Optional[str] = None
    duration_threshold: int = Field(default=1, gt=0)
    max_script_executions: int = Field(default=5, gt=0, description="Maximum script retry attempts")
    retry_interval_multiplier: int = Field(default=10, gt=0, description="Multiplier for retry interval")
    trigger_on_status: str = Field(default="stopped", description="Status that triggers script: 'stopped', 'running', or 'both'")
    enabled: bool = Field(default=True)


class MonitoredProcessCreate(MonitoredProcessBase):
    """Model for creating a process monitor"""
    pass


class MonitoredProcess(MonitoredProcessBase):
    """Model for process monitor with database fields"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Service Monitoring Models
class MonitoredServiceBase(BaseModel):
    """Base model for service monitoring"""
    service_name: str = Field(..., description="Windows service name")
    display_name: Optional[str] = None
    monitoring_interval: int = Field(default=5, gt=0)
    restart_config: Optional[str] = Field(None, description="JSON config for restart behavior")
    state_duration_threshold: int = Field(default=1, gt=0)
    enabled: bool = Field(default=True)


class MonitoredServiceCreate(MonitoredServiceBase):
    """Model for creating a service monitor"""
    pass


class MonitoredService(MonitoredServiceBase):
    """Model for service monitor with database fields"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Supervised Process Models
class SupervisedProcessBase(BaseModel):
    """Base model for supervised processes"""
    name: str = Field(..., description="Friendly name for the supervised process")
    command: str = Field(..., description="PowerShell command to execute")
    working_directory: Optional[str] = Field(None, description="Working directory for the command")
    monitoring_interval: int = Field(default=5, gt=0, description="Check interval in seconds")
    restart_delay: int = Field(default=3, gt=0, description="Seconds to wait before restarting")
    max_restarts: int = Field(default=0, ge=0, description="Maximum restarts (0 = unlimited)")
    enabled: bool = Field(default=True)


class SupervisedProcessCreate(SupervisedProcessBase):
    """Model for creating a supervised process"""
    pass


class SupervisedProcess(SupervisedProcessBase):
    """Model for supervised process with database fields"""
    id: int
    current_pid: Optional[int] = None
    restart_count: int = 0
    last_started_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# System Monitoring Models
class SystemMonitoringBase(BaseModel):
    """Base model for system monitoring"""
    monitor_type: SystemMonitorType
    threshold_value: Optional[float] = Field(None, description="Threshold percentage or value")
    monitoring_interval: int = Field(default=5, gt=0)
    process_reference: Optional[str] = Field(None, description="PID or port for process monitoring")
    drive_letter: Optional[str] = Field(None, description="Drive letter for disk monitoring (e.g., C:)")
    enabled: bool = Field(default=True)


class SystemMonitoringCreate(SystemMonitoringBase):
    """Model for creating a system monitor"""
    pass


class SystemMonitoring(SystemMonitoringBase):
    """Model for system monitor with database fields"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Alert Rules Models
class AlertRuleBase(BaseModel):
    """Base model for alert rules"""
    monitored_item_id: int
    monitored_item_type: MonitorType
    alert_condition: AlertCondition
    condition_value: Optional[str] = Field(None, description="JSON value for condition parameters")
    recurring_schedule: Optional[str] = Field(None, description="Cron-like schedule for recurring alerts")
    template_id: Optional[int] = None
    enabled: bool = Field(default=True)


class AlertRuleCreate(AlertRuleBase):
    """Model for creating an alert rule"""
    recipient_ids: Optional[List[int]] = Field(default_factory=list, description="List of recipient IDs")


class AlertRule(AlertRuleBase):
    """Model for alert rule with database fields"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Email Templates Models
class EmailTemplateBase(BaseModel):
    """Base model for email templates"""
    template_name: str
    subject_template: str
    body_template: str
    variables: Optional[List[str]] = Field(default_factory=list)


class EmailTemplateCreate(EmailTemplateBase):
    """Model for creating an email template"""
    pass


class EmailTemplate(EmailTemplateBase):
    """Model for email template with database fields"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Email Servers Models
class EmailServerBase(BaseModel):
    """Base model for email servers"""
    smtp_host: str
    smtp_port: int = Field(default=587)
    use_ssl: bool = Field(default=True)
    use_tls: bool = Field(default=True)
    username: Optional[str] = None
    password: Optional[str] = None
    from_address: str
    default_template_id: Optional[int] = None
    is_active: bool = Field(default=True)


class EmailServerCreate(EmailServerBase):
    """Model for creating an email server"""
    pass


class EmailServer(EmailServerBase):
    """Model for email server with database fields"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Script Configurations Models
class ScriptConfigBase(BaseModel):
    """Base model for script configurations"""
    script_name: str
    script_type: ScriptType = Field(default=ScriptType.INLINE)
    content: Optional[str] = None
    file_path: Optional[str] = None
    timeout_seconds: int = Field(default=300, gt=0)
    success_handling: Optional[str] = None
    failure_handling: Optional[str] = None


class ScriptConfigCreate(ScriptConfigBase):
    """Model for creating a script configuration"""
    pass


class ScriptConfig(ScriptConfigBase):
    """Model for script configuration with database fields"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Recipients Models
class RecipientBase(BaseModel):
    """Base model for email recipients"""
    email_address: str
    name: Optional[str] = None
    alert_types: Optional[List[str]] = Field(default_factory=list)
    enabled: bool = Field(default=True)


class RecipientCreate(RecipientBase):
    """Model for creating a recipient"""
    pass


class Recipient(RecipientBase):
    """Model for recipient with database fields"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Status Models
class MonitorStatus(BaseModel):
    """Model for monitor status response"""
    item_id: int
    item_type: MonitorType
    status: str
    last_check: datetime
    details: Optional[Dict[str, Any]] = None


class SystemStats(BaseModel):
    """Model for system statistics"""
    cpu_percent: float
    memory_percent: float
    disk_usage: Dict[str, Dict[str, Any]]
    timestamp: datetime

