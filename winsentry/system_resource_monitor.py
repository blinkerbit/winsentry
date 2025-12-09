"""
System Resource Monitoring for WinSentry

Monitors system-wide resources:
- CPU usage
- RAM usage  
- Drive space
With configurable thresholds and email alerts
"""

import asyncio
import logging
import psutil
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ResourceThreshold:
    """Configuration for resource monitoring thresholds"""
    resource_type: str  # 'cpu', 'ram', 'disk'
    threshold_percent: float  # Threshold percentage (0-100)
    drive_letter: Optional[str] = None  # For disk monitoring (e.g., 'C:')
    enabled: bool = True
    email_alerts_enabled: bool = True
    email_recipients: List[str] = field(default_factory=list)
    check_interval: int = 60  # Check interval in seconds
    
    # State
    last_value: float = 0.0
    last_check: Optional[datetime] = None
    alert_sent: bool = False  # Track if alert was already sent for current breach


class SystemResourceMonitor:
    """Monitors system-wide CPU, RAM, and disk resources"""
    
    def __init__(self, db_path: str = "winsentry.db"):
        self.logger = logging.getLogger(__name__)
        self.db_path = db_path
        self.thresholds: Dict[str, ResourceThreshold] = {}
        self._running = False
        self._monitoring_task: Optional[asyncio.Task] = None
        self.email_alert = None
        
        self._load_configurations()
    
    def _get_email_alert(self):
        """Get or create EmailAlert instance"""
        if self.email_alert is None:
            from .email_alert import EmailAlert
            self.email_alert = EmailAlert(self.db_path)
        return self.email_alert
    
    def _load_configurations(self):
        """Load resource threshold configurations from database"""
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            self._ensure_tables_exist(cursor, conn)
            
            cursor.execute('''
                SELECT id, resource_type, threshold_percent, drive_letter,
                       enabled, email_alerts_enabled, email_recipients, check_interval
                FROM system_resource_thresholds
            ''')
            
            for row in cursor.fetchall():
                threshold_id = f"{row[1]}_{row[3]}" if row[3] else row[1]
                recipients = row[6].split(',') if row[6] else []
                
                self.thresholds[threshold_id] = ResourceThreshold(
                    resource_type=row[1],
                    threshold_percent=row[2],
                    drive_letter=row[3],
                    enabled=bool(row[4]),
                    email_alerts_enabled=bool(row[5]),
                    email_recipients=recipients,
                    check_interval=row[7] or 60
                )
                
                self.logger.info(f"Loaded resource threshold: {threshold_id} = {row[2]}%")
            
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Failed to load resource configurations: {e}")
    
    def _ensure_tables_exist(self, cursor, conn):
        """Ensure required database tables exist"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_resource_thresholds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resource_type TEXT NOT NULL,
                threshold_percent REAL NOT NULL,
                drive_letter TEXT,
                enabled BOOLEAN NOT NULL DEFAULT 1,
                email_alerts_enabled BOOLEAN DEFAULT 1,
                email_recipients TEXT,
                check_interval INTEGER DEFAULT 60,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(resource_type, drive_letter)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_resource_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resource_type TEXT NOT NULL,
                drive_letter TEXT,
                value_percent REAL NOT NULL,
                threshold_percent REAL,
                status TEXT NOT NULL,
                message TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sys_resource_logs_type ON system_resource_logs(resource_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sys_resource_logs_timestamp ON system_resource_logs(timestamp)')
        
        conn.commit()
    
    async def set_threshold(self, resource_type: str, threshold_percent: float,
                           drive_letter: Optional[str] = None,
                           email_alerts_enabled: bool = True,
                           email_recipients: List[str] = None,
                           check_interval: int = 60) -> bool:
        """Set a resource threshold"""
        try:
            if resource_type not in ['cpu', 'ram', 'disk']:
                self.logger.error(f"Invalid resource type: {resource_type}")
                return False
            
            if resource_type == 'disk' and not drive_letter:
                self.logger.error("Drive letter required for disk threshold")
                return False
            
            recipients = email_recipients or []
            threshold_id = f"{resource_type}_{drive_letter}" if drive_letter else resource_type
            
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            self._ensure_tables_exist(cursor, conn)
            
            cursor.execute('''
                INSERT OR REPLACE INTO system_resource_thresholds 
                (resource_type, threshold_percent, drive_letter, enabled,
                 email_alerts_enabled, email_recipients, check_interval, updated_at)
                VALUES (?, ?, ?, 1, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (resource_type, threshold_percent, drive_letter,
                  email_alerts_enabled, ','.join(recipients), check_interval))
            
            conn.commit()
            conn.close()
            
            self.thresholds[threshold_id] = ResourceThreshold(
                resource_type=resource_type,
                threshold_percent=threshold_percent,
                drive_letter=drive_letter,
                email_alerts_enabled=email_alerts_enabled,
                email_recipients=recipients,
                check_interval=check_interval
            )
            
            self.logger.info(f"Set threshold: {threshold_id} = {threshold_percent}%")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to set threshold: {e}")
            return False
    
    async def remove_threshold(self, resource_type: str, 
                               drive_letter: Optional[str] = None) -> bool:
        """Remove a resource threshold"""
        try:
            threshold_id = f"{resource_type}_{drive_letter}" if drive_letter else resource_type
            
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if drive_letter:
                cursor.execute('''
                    DELETE FROM system_resource_thresholds 
                    WHERE resource_type = ? AND drive_letter = ?
                ''', (resource_type, drive_letter))
            else:
                cursor.execute('''
                    DELETE FROM system_resource_thresholds 
                    WHERE resource_type = ? AND drive_letter IS NULL
                ''', (resource_type,))
            
            conn.commit()
            conn.close()
            
            if threshold_id in self.thresholds:
                del self.thresholds[threshold_id]
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to remove threshold: {e}")
            return False
    
    def get_cpu_usage(self) -> float:
        """Get current CPU usage percentage"""
        return psutil.cpu_percent(interval=1)
    
    def get_ram_usage(self) -> Dict:
        """Get current RAM usage"""
        memory = psutil.virtual_memory()
        return {
            'percent': memory.percent,
            'total_bytes': memory.total,
            'available_bytes': memory.available,
            'used_bytes': memory.used,
            'total_gb': round(memory.total / (1024**3), 2),
            'available_gb': round(memory.available / (1024**3), 2),
            'used_gb': round(memory.used / (1024**3), 2)
        }
    
    def get_disk_usage(self, drive_letter: str = None) -> List[Dict]:
        """Get disk usage for specified drive or all drives"""
        disks = []
        
        try:
            partitions = psutil.disk_partitions()
            
            for partition in partitions:
                # Skip removable/network drives unless specifically requested
                if 'removable' in partition.opts.lower() or 'cdrom' in partition.opts.lower():
                    continue
                
                mount_point = partition.mountpoint
                
                # Filter by drive letter if specified
                if drive_letter:
                    if not mount_point.upper().startswith(drive_letter.upper()):
                        continue
                
                try:
                    usage = psutil.disk_usage(mount_point)
                    disks.append({
                        'drive': mount_point,
                        'device': partition.device,
                        'fstype': partition.fstype,
                        'percent': usage.percent,
                        'total_bytes': usage.total,
                        'used_bytes': usage.used,
                        'free_bytes': usage.free,
                        'total_gb': round(usage.total / (1024**3), 2),
                        'used_gb': round(usage.used / (1024**3), 2),
                        'free_gb': round(usage.free / (1024**3), 2)
                    })
                except (PermissionError, OSError):
                    continue
            
        except Exception as e:
            self.logger.error(f"Failed to get disk usage: {e}")
        
        return disks
    
    def get_all_resources(self) -> Dict:
        """Get all system resource usage"""
        return {
            'cpu': {
                'percent': self.get_cpu_usage()
            },
            'ram': self.get_ram_usage(),
            'disks': self.get_disk_usage(),
            'timestamp': datetime.now().isoformat()
        }
    
    async def check_thresholds(self) -> List[Dict]:
        """Check all configured thresholds and return violations"""
        violations = []
        
        for threshold_id, threshold in self.thresholds.items():
            if not threshold.enabled:
                continue
            
            threshold.last_check = datetime.now()
            current_value = 0.0
            
            try:
                if threshold.resource_type == 'cpu':
                    current_value = self.get_cpu_usage()
                elif threshold.resource_type == 'ram':
                    current_value = self.get_ram_usage()['percent']
                elif threshold.resource_type == 'disk':
                    disks = self.get_disk_usage(threshold.drive_letter)
                    if disks:
                        current_value = disks[0]['percent']
                
                threshold.last_value = current_value
                
                # Check if threshold is exceeded
                if current_value >= threshold.threshold_percent:
                    status = 'exceeded'
                    
                    violation = {
                        'resource_type': threshold.resource_type,
                        'drive_letter': threshold.drive_letter,
                        'current_value': current_value,
                        'threshold': threshold.threshold_percent,
                        'timestamp': datetime.now().isoformat()
                    }
                    violations.append(violation)
                    
                    # Send alert if not already sent for this breach
                    if not threshold.alert_sent and threshold.email_alerts_enabled:
                        await self._send_threshold_alert(threshold, current_value)
                        threshold.alert_sent = True
                    
                    self._log_resource_check(threshold, current_value, 'exceeded',
                                            f'Threshold exceeded: {current_value:.1f}% >= {threshold.threshold_percent}%')
                else:
                    status = 'normal'
                    threshold.alert_sent = False  # Reset alert flag when back to normal
                    
                    self._log_resource_check(threshold, current_value, 'normal',
                                            f'Resource usage normal: {current_value:.1f}%')
                
            except Exception as e:
                self.logger.error(f"Error checking threshold {threshold_id}: {e}")
        
        return violations
    
    async def _send_threshold_alert(self, threshold: ResourceThreshold, current_value: float):
        """Send email alert for threshold violation"""
        if not threshold.email_recipients:
            return
        
        try:
            email_alert = self._get_email_alert()
            
            resource_name = threshold.resource_type.upper()
            if threshold.drive_letter:
                resource_name = f"Disk {threshold.drive_letter}"
            
            subject = f"WinSentry: {resource_name} Usage Alert - {current_value:.1f}%"
            
            body = f"""
            System Resource Alert
            
            Resource: {resource_name}
            Current Usage: {current_value:.1f}%
            Threshold: {threshold.threshold_percent}%
            Time: {datetime.now().isoformat()}
            
            The resource usage has exceeded the configured threshold.
            Please investigate and take appropriate action.
            """
            
            await email_alert.send_alert_email(
                port=0,
                recipients=threshold.email_recipients,
                template_name='resource_alert',
                custom_data={
                    'resource_type': threshold.resource_type,
                    'drive_letter': threshold.drive_letter,
                    'current_value': current_value,
                    'threshold': threshold.threshold_percent,
                    'subject': subject,
                    'body': body
                }
            )
            
            self.logger.info(f"Sent threshold alert for {resource_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to send threshold alert: {e}")
    
    def _log_resource_check(self, threshold: ResourceThreshold, value: float, 
                           status: str, message: str):
        """Log resource check to database"""
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO system_resource_logs 
                (resource_type, drive_letter, value_percent, threshold_percent, status, message)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (threshold.resource_type, threshold.drive_letter, value,
                  threshold.threshold_percent, status, message))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Failed to log resource check: {e}")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while self._running:
            try:
                await self.check_thresholds()
                
                # Use the minimum check interval from all thresholds
                min_interval = 60
                for threshold in self.thresholds.values():
                    if threshold.enabled:
                        min_interval = min(min_interval, threshold.check_interval)
                
                await asyncio.sleep(min_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in resource monitoring loop: {e}")
                await asyncio.sleep(30)
    
    async def start_monitoring(self):
        """Start resource monitoring"""
        self._running = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        self.logger.info("Started system resource monitoring")
    
    async def stop_monitoring(self):
        """Stop resource monitoring"""
        self._running = False
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Stopped system resource monitoring")
    
    def get_thresholds(self) -> List[Dict]:
        """Get all configured thresholds with live current values"""
        results = []
        
        for t in self.thresholds.values():
            # Fetch live current value for this threshold
            current_value = 0.0
            try:
                if t.resource_type == 'cpu':
                    current_value = self.get_cpu_usage()
                elif t.resource_type == 'ram':
                    current_value = self.get_ram_usage()['percent']
                elif t.resource_type == 'disk':
                    disks = self.get_disk_usage(t.drive_letter)
                    if disks:
                        current_value = disks[0]['percent']
                
                # Update the cached value
                t.last_value = current_value
            except Exception as e:
                self.logger.error(f"Error getting current value for {t.resource_type}: {e}")
                current_value = t.last_value  # Fall back to cached value
            
            results.append({
                'resource_type': t.resource_type,
                'threshold_percent': t.threshold_percent,
                'drive_letter': t.drive_letter,
                'enabled': t.enabled,
                'email_alerts_enabled': t.email_alerts_enabled,
                'email_recipients': t.email_recipients,
                'check_interval': t.check_interval,
                'last_value': current_value,
                'last_check': t.last_check.isoformat() if t.last_check else None
            })
        
        return results
    
    def get_resource_logs(self, resource_type: Optional[str] = None, 
                         limit: int = 100) -> List[Dict]:
        """Get resource monitoring logs"""
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if resource_type:
                cursor.execute('''
                    SELECT resource_type, drive_letter, value_percent, 
                           threshold_percent, status, message, timestamp
                    FROM system_resource_logs 
                    WHERE resource_type = ?
                    ORDER BY timestamp DESC LIMIT ?
                ''', (resource_type, limit))
            else:
                cursor.execute('''
                    SELECT resource_type, drive_letter, value_percent, 
                           threshold_percent, status, message, timestamp
                    FROM system_resource_logs 
                    ORDER BY timestamp DESC LIMIT ?
                ''', (limit,))
            
            logs = []
            for row in cursor.fetchall():
                logs.append({
                    'resource_type': row['resource_type'],
                    'drive_letter': row['drive_letter'],
                    'value_percent': row['value_percent'],
                    'threshold_percent': row['threshold_percent'],
                    'status': row['status'],
                    'message': row['message'],
                    'timestamp': row['timestamp']
                })
            
            conn.close()
            return logs
            
        except Exception as e:
            self.logger.error(f"Failed to get resource logs: {e}")
            return []
