"""
SQLite database module for WinSentry
"""

import sqlite3
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime
import os

logger = logging.getLogger(__name__)


class Database:
    """SQLite database manager for WinSentry"""
    
    def __init__(self, db_path: str = "winsentry.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the database with required tables"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Create port configurations table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS port_configs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        port INTEGER UNIQUE NOT NULL,
                        interval_seconds INTEGER NOT NULL DEFAULT 30,
                        powershell_script TEXT,
                        powershell_commands TEXT,
                        enabled BOOLEAN NOT NULL DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Create port monitoring logs table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS port_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        port INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        failure_count INTEGER DEFAULT 0,
                        message TEXT,
                        FOREIGN KEY (port) REFERENCES port_configs (port)
                    )
                ''')
                
                # Create service configurations table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS service_configs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        service_name TEXT UNIQUE NOT NULL,
                        interval_seconds INTEGER NOT NULL DEFAULT 30,
                        powershell_script TEXT,
                        powershell_commands TEXT,
                        enabled BOOLEAN NOT NULL DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Create service monitoring logs table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS service_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        service_name TEXT NOT NULL,
                        status TEXT NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        failure_count INTEGER DEFAULT 0,
                        message TEXT,
                        FOREIGN KEY (service_name) REFERENCES service_configs (service_name)
                    )
                ''')
                
                # Create port resource thresholds table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS port_thresholds (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        port INTEGER UNIQUE NOT NULL,
                        cpu_threshold REAL DEFAULT 0,
                        ram_threshold REAL DEFAULT 0,
                        email_alerts_enabled BOOLEAN DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (port) REFERENCES port_configs (port)
                    )
                ''')
                
                # Create process monitoring logs table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS process_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        port INTEGER NOT NULL,
                        pid INTEGER NOT NULL,
                        process_name TEXT NOT NULL,
                        cpu_percent REAL,
                        memory_percent REAL,
                        memory_rss_bytes INTEGER,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (port) REFERENCES port_configs (port)
                    )
                ''')
                
                # Create real-time port status table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS port_status (
                        port INTEGER PRIMARY KEY,
                        status TEXT NOT NULL,
                        last_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        failure_count INTEGER DEFAULT 0,
                        last_status_change TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        uptime_seconds INTEGER DEFAULT 0,
                        total_checks INTEGER DEFAULT 0,
                        successful_checks INTEGER DEFAULT 0,
                        FOREIGN KEY (port) REFERENCES port_configs (port)
                    )
                ''')
                
                # Create service resource thresholds table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS service_thresholds (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        service_name TEXT UNIQUE NOT NULL,
                        cpu_threshold REAL DEFAULT 0,
                        ram_threshold REAL DEFAULT 0,
                        email_alerts_enabled BOOLEAN DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (service_name) REFERENCES service_configs (service_name)
                    )
                ''')
                
                # Create service process monitoring logs table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS service_process_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        service_name TEXT NOT NULL,
                        pid INTEGER NOT NULL,
                        process_name TEXT NOT NULL,
                        cpu_percent REAL,
                        memory_percent REAL,
                        memory_rss_bytes INTEGER,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (service_name) REFERENCES service_configs (service_name)
                    )
                ''')
                
                # Create indexes for better performance
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_port_logs_port ON port_logs(port)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_port_logs_timestamp ON port_logs(timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_service_logs_service ON service_logs(service_name)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_service_logs_timestamp ON service_logs(timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_port_thresholds_port ON port_thresholds(port)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_process_logs_port ON process_logs(port)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_process_logs_timestamp ON process_logs(timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_service_thresholds_service ON service_thresholds(service_name)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_service_process_logs_service ON service_process_logs(service_name)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_service_process_logs_timestamp ON service_process_logs(timestamp)')
                
                # Add powershell_commands column if it doesn't exist (migration)
                try:
                    cursor.execute('ALTER TABLE port_configs ADD COLUMN powershell_commands TEXT')
                    logger.info("Added powershell_commands column to port_configs table")
                except sqlite3.OperationalError:
                    # Column already exists, ignore
                    pass
                
                # Add recovery_script_delay column to port_configs (migration)
                try:
                    cursor.execute('ALTER TABLE port_configs ADD COLUMN recovery_script_delay INTEGER DEFAULT 300')
                    logger.info("Added recovery_script_delay column to port_configs table")
                except sqlite3.OperationalError:
                    # Column already exists, ignore
                    pass
                
                # Add recovery_script_delay column to service_configs (migration)
                try:
                    cursor.execute('ALTER TABLE service_configs ADD COLUMN recovery_script_delay INTEGER DEFAULT 300')
                    logger.info("Added recovery_script_delay column to service_configs table")
                except sqlite3.OperationalError:
                    # Column already exists, ignore
                    pass
                
                conn.commit()
                logger.info("Database initialized successfully")
                
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def save_port_config(self, port: int, interval: int, powershell_script: Optional[str] = None, powershell_commands: Optional[str] = None, enabled: bool = True, recovery_script_delay: int = 20) -> bool:
        """Save or update port configuration"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT OR REPLACE INTO port_configs 
                    (port, interval_seconds, powershell_script, powershell_commands, enabled, recovery_script_delay, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (port, interval, powershell_script, powershell_commands, enabled, recovery_script_delay))
                
                conn.commit()
                logger.info(f"Port configuration saved: port={port}, interval={interval}s, recovery_delay={recovery_script_delay}s")
                return True
                
        except Exception as e:
            logger.error(f"Failed to save port configuration: {e}")
            return False
    
    def get_port_config(self, port: int) -> Optional[Dict]:
        """Get port configuration by port number"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT port, interval_seconds, powershell_script, powershell_commands, enabled, 
                           recovery_script_delay, created_at, updated_at
                    FROM port_configs WHERE port = ?
                ''', (port,))
                
                row = cursor.fetchone()
                if row:
                    return {
                        'port': row['port'],
                        'interval': row['interval_seconds'],
                        'powershell_script': row['powershell_script'],
                        'powershell_commands': row['powershell_commands'],
                        'enabled': bool(row['enabled']),
                        'recovery_script_delay': row['recovery_script_delay'] or 20,
                        'created_at': row['created_at'],
                        'updated_at': row['updated_at']
                    }
                return None
                
        except Exception as e:
            logger.error(f"Failed to get port configuration: {e}")
            return None
    
    def get_all_port_configs(self) -> List[Dict]:
        """Get all port configurations"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT port, interval_seconds, powershell_script, powershell_commands, enabled, 
                           recovery_script_delay, created_at, updated_at
                    FROM port_configs ORDER BY port
                ''')
                
                configs = []
                for row in cursor.fetchall():
                    configs.append({
                        'port': row['port'],
                        'interval': row['interval_seconds'],
                        'powershell_script': row['powershell_script'],
                        'powershell_commands': row['powershell_commands'],
                        'enabled': bool(row['enabled']),
                        'recovery_script_delay': row['recovery_script_delay'] or 20,
                        'created_at': row['created_at'],
                        'updated_at': row['updated_at']
                    })
                
                return configs
                
        except Exception as e:
            logger.error(f"Failed to get all port configurations: {e}")
            return []
    
    def delete_port_config(self, port: int) -> bool:
        """Delete port configuration"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('DELETE FROM port_configs WHERE port = ?', (port,))
                cursor.execute('DELETE FROM port_logs WHERE port = ?', (port,))
                
                conn.commit()
                logger.info(f"Port configuration deleted: port={port}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete port configuration: {e}")
            return False
    
    def log_port_check(self, port: int, status: str, failure_count: int = 0, message: str = None) -> bool:
        """Log a port check result"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO port_logs (port, status, failure_count, message)
                    VALUES (?, ?, ?, ?)
                ''', (port, status, failure_count, message))
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Failed to log port check: {e}")
            return False
    
    def update_port_status(self, port: int, status: str, failure_count: int = 0) -> bool:
        """Update real-time port status in database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if port status record exists
                cursor.execute('SELECT status, last_status_change FROM port_status WHERE port = ?', (port,))
                existing = cursor.fetchone()
                
                current_time = datetime.now().isoformat()
                status_changed = False
                
                if existing:
                    old_status = existing[0]
                    last_change = existing[1]
                    status_changed = (old_status != status)
                    
                    if status_changed:
                        # Update with status change
                        cursor.execute('''
                            UPDATE port_status 
                            SET status = ?, last_check = ?, failure_count = ?, 
                                last_status_change = ?, total_checks = total_checks + 1,
                                successful_checks = CASE WHEN ? = 'ONLINE' THEN successful_checks + 1 ELSE successful_checks END
                            WHERE port = ?
                        ''', (status, current_time, failure_count, current_time, status, port))
                    else:
                        # Update without status change
                        cursor.execute('''
                            UPDATE port_status 
                            SET last_check = ?, failure_count = ?, total_checks = total_checks + 1,
                                successful_checks = CASE WHEN ? = 'ONLINE' THEN successful_checks + 1 ELSE successful_checks END
                            WHERE port = ?
                        ''', (current_time, failure_count, status, port))
                else:
                    # Insert new port status record
                    cursor.execute('''
                        INSERT INTO port_status (port, status, last_check, failure_count, 
                                               last_status_change, total_checks, successful_checks)
                        VALUES (?, ?, ?, ?, ?, 1, ?)
                    ''', (port, status, current_time, failure_count, current_time, 1 if status == 'ONLINE' else 0))
                    status_changed = True
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Failed to update port status: {e}")
            return False
    
    def get_port_status(self, port: Optional[int] = None) -> List[Dict]:
        """Get real-time port status from database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                if port:
                    cursor.execute('''
                        SELECT ps.*, pc.interval_seconds, pc.enabled
                        FROM port_status ps
                        JOIN port_configs pc ON ps.port = pc.port
                        WHERE ps.port = ?
                    ''', (port,))
                else:
                    cursor.execute('''
                        SELECT ps.*, pc.interval_seconds, pc.enabled
                        FROM port_status ps
                        JOIN port_configs pc ON ps.port = pc.port
                        ORDER BY ps.port
                    ''')
                
                status_list = []
                for row in cursor.fetchall():
                    # Calculate uptime if port is online
                    uptime_seconds = 0
                    if row['status'] == 'ONLINE' and row['last_status_change']:
                        try:
                            last_change = datetime.fromisoformat(row['last_status_change'])
                            uptime_seconds = int((datetime.now() - last_change).total_seconds())
                        except:
                            uptime_seconds = 0
                    
                    # Calculate success rate
                    success_rate = 0
                    if row['total_checks'] > 0:
                        success_rate = (row['successful_checks'] / row['total_checks']) * 100
                    
                    status_list.append({
                        'port': row['port'],
                        'status': row['status'].lower(),
                        'last_check': row['last_check'],
                        'failure_count': row['failure_count'],
                        'last_status_change': row['last_status_change'],
                        'uptime_seconds': uptime_seconds,
                        'total_checks': row['total_checks'],
                        'successful_checks': row['successful_checks'],
                        'success_rate': round(success_rate, 2),
                        'interval': row['interval_seconds'],
                        'enabled': bool(row['enabled'])
                    })
                
                return status_list
                
        except Exception as e:
            logger.error(f"Failed to get port status: {e}")
            return []
    
    def get_port_logs(self, port: Optional[int] = None, limit: int = 100) -> List[Dict]:
        """Get port monitoring logs"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                if port:
                    cursor.execute('''
                        SELECT port, status, timestamp, failure_count, message
                        FROM port_logs WHERE port = ?
                        ORDER BY timestamp DESC LIMIT ?
                    ''', (port, limit))
                else:
                    cursor.execute('''
                        SELECT port, status, timestamp, failure_count, message
                        FROM port_logs
                        ORDER BY timestamp DESC LIMIT ?
                    ''', (limit,))
                
                logs = []
                for row in cursor.fetchall():
                    logs.append({
                        'port': row['port'],
                        'status': row['status'],
                        'timestamp': row['timestamp'],
                        'failure_count': row['failure_count'],
                        'message': row['message']
                    })
                
                return logs
                
        except Exception as e:
            logger.error(f"Failed to get port logs: {e}")
            return []
    
    def cleanup_old_logs(self, days: int = 30) -> int:
        """Clean up old logs older than specified days"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    DELETE FROM port_logs 
                    WHERE timestamp < datetime('now', '-{} days')
                '''.format(days))
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} old log entries")
                
                return deleted_count
                
        except Exception as e:
            logger.error(f"Failed to cleanup old logs: {e}")
            return 0
    
    def get_database_stats(self) -> Dict:
        """Get database statistics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get port config count
                cursor.execute('SELECT COUNT(*) FROM port_configs')
                port_config_count = cursor.fetchone()[0]
                
                # Get service config count
                cursor.execute('SELECT COUNT(*) FROM service_configs')
                service_config_count = cursor.fetchone()[0]
                
                # Get total log count
                cursor.execute('SELECT COUNT(*) FROM port_logs')
                port_log_count = cursor.fetchone()[0]
                
                # Get service log count
                cursor.execute('SELECT COUNT(*) FROM service_logs')
                service_log_count = cursor.fetchone()[0]
                
                # Get database size
                db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
                
                return {
                    'port_configs': port_config_count,
                    'service_configs': service_config_count,
                    'port_log_entries': port_log_count,
                    'service_log_entries': service_log_count,
                    'total_log_entries': port_log_count + service_log_count,
                    'database_size_bytes': db_size,
                    'database_size_mb': round(db_size / (1024 * 1024), 2)
                }
                
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            return {}
    
    # Service monitoring methods
    def save_service_config(self, service_name: str, interval: int, powershell_script: Optional[str] = None, powershell_commands: Optional[str] = None, enabled: bool = True, recovery_script_delay: int = 20) -> bool:
        """Save or update service configuration"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT OR REPLACE INTO service_configs 
                    (service_name, interval_seconds, powershell_script, powershell_commands, enabled, recovery_script_delay, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (service_name, interval, powershell_script, powershell_commands, enabled, recovery_script_delay))
                
                conn.commit()
                logger.info(f"Service configuration saved: service={service_name}, interval={interval}s, recovery_delay={recovery_script_delay}s")
                return True
                
        except Exception as e:
            logger.error(f"Failed to save service configuration: {e}")
            return False
    
    def get_service_config(self, service_name: str) -> Optional[Dict]:
        """Get service configuration by service name"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT service_name, interval_seconds, powershell_script, powershell_commands, enabled, 
                           recovery_script_delay, created_at, updated_at
                    FROM service_configs WHERE service_name = ?
                ''', (service_name,))
                
                row = cursor.fetchone()
                if row:
                    return {
                        'service_name': row['service_name'],
                        'interval': row['interval_seconds'],
                        'powershell_script': row['powershell_script'],
                        'powershell_commands': row['powershell_commands'],
                        'enabled': bool(row['enabled']),
                        'recovery_script_delay': row['recovery_script_delay'] or 20,
                        'created_at': row['created_at'],
                        'updated_at': row['updated_at']
                    }
                return None
                
        except Exception as e:
            logger.error(f"Failed to get service configuration: {e}")
            return None
    
    def get_all_service_configs(self) -> List[Dict]:
        """Get all service configurations"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT service_name, interval_seconds, powershell_script, powershell_commands, enabled, 
                           recovery_script_delay, created_at, updated_at
                    FROM service_configs ORDER BY service_name
                ''')
                
                configs = []
                for row in cursor.fetchall():
                    configs.append({
                        'service_name': row['service_name'],
                        'interval': row['interval_seconds'],
                        'powershell_script': row['powershell_script'],
                        'powershell_commands': row['powershell_commands'],
                        'enabled': bool(row['enabled']),
                        'recovery_script_delay': row['recovery_script_delay'] or 20,
                        'created_at': row['created_at'],
                        'updated_at': row['updated_at']
                    })
                
                return configs
                
        except Exception as e:
            logger.error(f"Failed to get all service configurations: {e}")
            return []
    
    def delete_service_config(self, service_name: str) -> bool:
        """Delete service configuration"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('DELETE FROM service_configs WHERE service_name = ?', (service_name,))
                cursor.execute('DELETE FROM service_logs WHERE service_name = ?', (service_name,))
                
                conn.commit()
                logger.info(f"Service configuration deleted: service={service_name}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete service configuration: {e}")
            return False
    
    def log_service_check(self, service_name: str, status: str, failure_count: int = 0, message: str = None) -> bool:
        """Log a service check result"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO service_logs (service_name, status, failure_count, message)
                    VALUES (?, ?, ?, ?)
                ''', (service_name, status, failure_count, message))
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Failed to log service check: {e}")
            return False
    
    def get_service_logs(self, service_name: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Get service monitoring logs"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                if service_name:
                    cursor.execute('''
                        SELECT service_name, status, timestamp, failure_count, message
                        FROM service_logs WHERE service_name = ?
                        ORDER BY timestamp DESC LIMIT ?
                    ''', (service_name, limit))
                else:
                    cursor.execute('''
                        SELECT service_name, status, timestamp, failure_count, message
                        FROM service_logs
                        ORDER BY timestamp DESC LIMIT ?
                    ''', (limit,))
                
                logs = []
                for row in cursor.fetchall():
                    logs.append({
                        'service_name': row['service_name'],
                        'status': row['status'],
                        'timestamp': row['timestamp'],
                        'failure_count': row['failure_count'],
                        'message': row['message']
                    })
                
                return logs
                
        except Exception as e:
            logger.error(f"Failed to get service logs: {e}")
            return []
    
    def cleanup_old_service_logs(self, days: int = 30) -> int:
        """Clean up old service logs older than specified days"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    DELETE FROM service_logs 
                    WHERE timestamp < datetime('now', '-{} days')
                '''.format(days))
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} old service log entries")
                
                return deleted_count
                
        except Exception as e:
            logger.error(f"Failed to cleanup old service logs: {e}")
            return 0
    
    # Port resource threshold methods
    def save_port_thresholds(self, port: int, cpu_threshold: float = 0, ram_threshold: float = 0, email_alerts_enabled: bool = False) -> bool:
        """Save or update port resource thresholds"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT OR REPLACE INTO port_thresholds 
                    (port, cpu_threshold, ram_threshold, email_alerts_enabled, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (port, cpu_threshold, ram_threshold, email_alerts_enabled))
                
                conn.commit()
                logger.info(f"Port thresholds saved: port={port}, cpu={cpu_threshold}%, ram={ram_threshold}%")
                return True
                
        except Exception as e:
            logger.error(f"Failed to save port thresholds: {e}")
            return False
    
    def get_port_thresholds(self, port: int) -> Optional[Dict]:
        """Get port resource thresholds"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT port, cpu_threshold, ram_threshold, email_alerts_enabled, created_at, updated_at
                    FROM port_thresholds WHERE port = ?
                ''', (port,))
                
                row = cursor.fetchone()
                if row:
                    return {
                        'port': row['port'],
                        'cpu_threshold': row['cpu_threshold'],
                        'ram_threshold': row['ram_threshold'],
                        'email_alerts_enabled': bool(row['email_alerts_enabled']),
                        'created_at': row['created_at'],
                        'updated_at': row['updated_at']
                    }
                return None
                
        except Exception as e:
            logger.error(f"Failed to get port thresholds: {e}")
            return None
    
    def delete_port_thresholds(self, port: int) -> bool:
        """Delete port resource thresholds"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('DELETE FROM port_thresholds WHERE port = ?', (port,))
                
                conn.commit()
                logger.info(f"Port thresholds deleted: port={port}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete port thresholds: {e}")
            return False
    
    def log_process_metrics(self, port: int, pid: int, process_name: str, cpu_percent: float, memory_percent: float, memory_rss_bytes: int) -> bool:
        """Log process resource metrics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO process_logs (port, pid, process_name, cpu_percent, memory_percent, memory_rss_bytes)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (port, pid, process_name, cpu_percent, memory_percent, memory_rss_bytes))
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Failed to log process metrics: {e}")
            return False
    
    def get_process_logs(self, port: Optional[int] = None, limit: int = 100) -> List[Dict]:
        """Get process monitoring logs"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                if port:
                    cursor.execute('''
                        SELECT port, pid, process_name, cpu_percent, memory_percent, memory_rss_bytes, timestamp
                        FROM process_logs WHERE port = ?
                        ORDER BY timestamp DESC LIMIT ?
                    ''', (port, limit))
                else:
                    cursor.execute('''
                        SELECT port, pid, process_name, cpu_percent, memory_percent, memory_rss_bytes, timestamp
                        FROM process_logs
                        ORDER BY timestamp DESC LIMIT ?
                    ''', (limit,))
                
                logs = []
                for row in cursor.fetchall():
                    logs.append({
                        'port': row['port'],
                        'pid': row['pid'],
                        'process_name': row['process_name'],
                        'cpu_percent': row['cpu_percent'],
                        'memory_percent': row['memory_percent'],
                        'memory_rss_bytes': row['memory_rss_bytes'],
                        'memory_rss_mb': round(row['memory_rss_bytes'] / (1024 * 1024), 2),
                        'timestamp': row['timestamp']
                    })
                
                return logs
                
        except Exception as e:
            logger.error(f"Failed to get process logs: {e}")
            return []
    
    def cleanup_old_process_logs(self, days: int = 30) -> int:
        """Clean up old process logs older than specified days"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    DELETE FROM process_logs 
                    WHERE timestamp < datetime('now', '-{} days')
                '''.format(days))
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} old process log entries")
                
                return deleted_count
                
        except Exception as e:
            logger.error(f"Failed to cleanup old process logs: {e}")
            return 0
    
    # Service resource threshold methods
    def save_service_thresholds(self, service_name: str, cpu_threshold: float = 0, ram_threshold: float = 0, email_alerts_enabled: bool = False) -> bool:
        """Save or update service resource thresholds"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT OR REPLACE INTO service_thresholds 
                    (service_name, cpu_threshold, ram_threshold, email_alerts_enabled, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (service_name, cpu_threshold, ram_threshold, email_alerts_enabled))
                
                conn.commit()
                logger.info(f"Service thresholds saved: service={service_name}, cpu={cpu_threshold}%, ram={ram_threshold}%")
                return True
                
        except Exception as e:
            logger.error(f"Failed to save service thresholds: {e}")
            return False
    
    def get_service_thresholds(self, service_name: str) -> Optional[Dict]:
        """Get service resource thresholds"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT service_name, cpu_threshold, ram_threshold, email_alerts_enabled, created_at, updated_at
                    FROM service_thresholds WHERE service_name = ?
                ''', (service_name,))
                
                row = cursor.fetchone()
                if row:
                    return {
                        'service_name': row['service_name'],
                        'cpu_threshold': row['cpu_threshold'],
                        'ram_threshold': row['ram_threshold'],
                        'email_alerts_enabled': bool(row['email_alerts_enabled']),
                        'created_at': row['created_at'],
                        'updated_at': row['updated_at']
                    }
                return None
                
        except Exception as e:
            logger.error(f"Failed to get service thresholds: {e}")
            return None
    
    def get_all_service_thresholds(self) -> List[Dict]:
        """Get all service resource thresholds with current resource usage"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT service_name, cpu_threshold, ram_threshold, email_alerts_enabled, created_at, updated_at
                    FROM service_thresholds
                    ORDER BY service_name
                ''')
                
                thresholds = []
                for row in cursor.fetchall():
                    # Get current resource usage for this service
                    # This is a simplified version - in a real implementation, you'd get actual current usage
                    thresholds.append({
                        'service_name': row['service_name'],
                        'cpu_threshold': row['cpu_threshold'],
                        'ram_threshold': row['ram_threshold'],
                        'email_alerts_enabled': bool(row['email_alerts_enabled']),
                        'current_cpu': 0.0,  # Placeholder - would be populated with actual current usage
                        'current_ram': 0.0,  # Placeholder - would be populated with actual current usage
                        'created_at': row['created_at'],
                        'updated_at': row['updated_at'],
                        'last_updated': row['updated_at']
                    })
                
                return thresholds
                
        except Exception as e:
            logger.error(f"Failed to get all service thresholds: {e}")
            return []
    
    def delete_service_thresholds(self, service_name: str) -> bool:
        """Delete service resource thresholds"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('DELETE FROM service_thresholds WHERE service_name = ?', (service_name,))
                
                conn.commit()
                logger.info(f"Service thresholds deleted: service={service_name}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete service thresholds: {e}")
            return False
    
    def log_service_process_metrics(self, service_name: str, pid: int, process_name: str, cpu_percent: float, memory_percent: float, memory_rss_bytes: int) -> bool:
        """Log service process resource metrics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO service_process_logs (service_name, pid, process_name, cpu_percent, memory_percent, memory_rss_bytes)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (service_name, pid, process_name, cpu_percent, memory_percent, memory_rss_bytes))
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Failed to log service process metrics: {e}")
            return False
    
    def get_service_process_logs(self, service_name: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Get service process monitoring logs"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                if service_name:
                    cursor.execute('''
                        SELECT service_name, pid, process_name, cpu_percent, memory_percent, memory_rss_bytes, timestamp
                        FROM service_process_logs WHERE service_name = ?
                        ORDER BY timestamp DESC LIMIT ?
                    ''', (service_name, limit))
                else:
                    cursor.execute('''
                        SELECT service_name, pid, process_name, cpu_percent, memory_percent, memory_rss_bytes, timestamp
                        FROM service_process_logs
                        ORDER BY timestamp DESC LIMIT ?
                    ''', (limit,))
                
                logs = []
                for row in cursor.fetchall():
                    logs.append({
                        'service_name': row['service_name'],
                        'pid': row['pid'],
                        'process_name': row['process_name'],
                        'cpu_percent': row['cpu_percent'],
                        'memory_percent': row['memory_percent'],
                        'memory_rss_bytes': row['memory_rss_bytes'],
                        'memory_rss_mb': round(row['memory_rss_bytes'] / (1024 * 1024), 2),
                        'timestamp': row['timestamp']
                    })
                
                return logs
                
        except Exception as e:
            logger.error(f"Failed to get service process logs: {e}")
            return []
    
    def cleanup_old_service_process_logs(self, days: int = 30) -> int:
        """Clean up old service process logs older than specified days"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    DELETE FROM service_process_logs 
                    WHERE timestamp < datetime('now', '-{} days')
                '''.format(days))
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} old service process log entries")
                
                return deleted_count
                
        except Exception as e:
            logger.error(f"Failed to cleanup old service process logs: {e}")
            return 0
