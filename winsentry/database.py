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
                
                # Create indexes for better performance
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_port_logs_port ON port_logs(port)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_port_logs_timestamp ON port_logs(timestamp)')
                
                # Add powershell_commands column if it doesn't exist (migration)
                try:
                    cursor.execute('ALTER TABLE port_configs ADD COLUMN powershell_commands TEXT')
                    logger.info("Added powershell_commands column to port_configs table")
                except sqlite3.OperationalError:
                    # Column already exists, ignore
                    pass
                
                conn.commit()
                logger.info("Database initialized successfully")
                
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def save_port_config(self, port: int, interval: int, powershell_script: Optional[str] = None, powershell_commands: Optional[str] = None, enabled: bool = True) -> bool:
        """Save or update port configuration"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT OR REPLACE INTO port_configs 
                    (port, interval_seconds, powershell_script, powershell_commands, enabled, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (port, interval, powershell_script, powershell_commands, enabled))
                
                conn.commit()
                logger.info(f"Port configuration saved: port={port}, interval={interval}s")
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
                    SELECT port, interval_seconds, powershell_script, powershell_commands, enabled, created_at, updated_at
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
                    SELECT port, interval_seconds, powershell_script, powershell_commands, enabled, created_at, updated_at
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
                config_count = cursor.fetchone()[0]
                
                # Get total log count
                cursor.execute('SELECT COUNT(*) FROM port_logs')
                log_count = cursor.fetchone()[0]
                
                # Get database size
                db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
                
                return {
                    'port_configs': config_count,
                    'log_entries': log_count,
                    'database_size_bytes': db_size,
                    'database_size_mb': round(db_size / (1024 * 1024), 2)
                }
                
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            return {}
