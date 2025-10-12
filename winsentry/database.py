"""SQLite database manager for WinSentry configuration storage"""

import sqlite3
import os
import json
from typing import Dict, Any, List, Optional
from pathlib import Path


class DatabaseManager:
    """Manages SQLite database for all configuration storage"""
    
    def __init__(self, db_path: str = "data/monitoring.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_database()
    
    def _run_migrations(self, conn):
        """Run database migrations for schema updates"""
        cursor = conn.cursor()
        
        # Add max_script_executions to monitored_ports if missing
        try:
            cursor.execute("SELECT max_script_executions FROM monitored_ports LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE monitored_ports ADD COLUMN max_script_executions INTEGER DEFAULT 5")
            print("✅ Added max_script_executions column to monitored_ports")
        
        # Add retry_interval_multiplier to monitored_ports if missing
        try:
            cursor.execute("SELECT retry_interval_multiplier FROM monitored_ports LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE monitored_ports ADD COLUMN retry_interval_multiplier INTEGER DEFAULT 10")
            print("✅ Added retry_interval_multiplier column to monitored_ports")
        
        # Add trigger_on_status to monitored_ports if missing
        try:
            cursor.execute("SELECT trigger_on_status FROM monitored_ports LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE monitored_ports ADD COLUMN trigger_on_status TEXT DEFAULT 'stopped'")
            print("✅ Added trigger_on_status column to monitored_ports")
        
        # Add max_script_executions to monitored_processes if missing
        try:
            cursor.execute("SELECT max_script_executions FROM monitored_processes LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE monitored_processes ADD COLUMN max_script_executions INTEGER DEFAULT 5")
            print("✅ Added max_script_executions column to monitored_processes")
        
        # Add retry_interval_multiplier to monitored_processes if missing
        try:
            cursor.execute("SELECT retry_interval_multiplier FROM monitored_processes LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE monitored_processes ADD COLUMN retry_interval_multiplier INTEGER DEFAULT 10")
            print("✅ Added retry_interval_multiplier column to monitored_processes")
        
        # Add trigger_on_status to monitored_processes if missing
        try:
            cursor.execute("SELECT trigger_on_status FROM monitored_processes LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE monitored_processes ADD COLUMN trigger_on_status TEXT DEFAULT 'stopped'")
            print("✅ Added trigger_on_status column to monitored_processes")
        
        # Add separate script fields for running status to monitored_ports
        try:
            cursor.execute("SELECT script_type_running FROM monitored_ports LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE monitored_ports ADD COLUMN script_type_running TEXT DEFAULT 'inline'")
            cursor.execute("ALTER TABLE monitored_ports ADD COLUMN script_content_running TEXT")
            cursor.execute("ALTER TABLE monitored_ports ADD COLUMN script_path_running TEXT")
            # Rename existing columns for clarity
            print("✅ Added script_*_running columns to monitored_ports")
        
        # Rename existing script columns to script_*_stopped for ports (if not already done)
        try:
            cursor.execute("SELECT script_type_stopped FROM monitored_ports LIMIT 1")
        except sqlite3.OperationalError:
            # Columns don't exist, need to migrate
            cursor.execute("ALTER TABLE monitored_ports RENAME COLUMN script_type TO script_type_stopped")
            cursor.execute("ALTER TABLE monitored_ports RENAME COLUMN script_content TO script_content_stopped")
            cursor.execute("ALTER TABLE monitored_ports RENAME COLUMN script_path TO script_path_stopped")
            print("✅ Renamed script columns to script_*_stopped in monitored_ports")
        
        # Same for processes
        try:
            cursor.execute("SELECT script_type_running FROM monitored_processes LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE monitored_processes ADD COLUMN script_type_running TEXT DEFAULT 'inline'")
            cursor.execute("ALTER TABLE monitored_processes ADD COLUMN script_content_running TEXT")
            cursor.execute("ALTER TABLE monitored_processes ADD COLUMN script_path_running TEXT")
            print("✅ Added script_*_running columns to monitored_processes")
        
        try:
            cursor.execute("SELECT script_type_stopped FROM monitored_processes LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE monitored_processes RENAME COLUMN script_type TO script_type_stopped")
            cursor.execute("ALTER TABLE monitored_processes RENAME COLUMN script_content TO script_content_stopped")
            cursor.execute("ALTER TABLE monitored_processes RENAME COLUMN script_path TO script_path_stopped")
            print("✅ Renamed script columns to script_*_stopped in monitored_processes")
        
        conn.commit()
    
    def _init_database(self):
        """Initialize database with all required tables"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            
            # Monitored ports table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS monitored_ports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    port_number INTEGER NOT NULL,
                    monitoring_interval INTEGER DEFAULT 5,
                    script_type_stopped TEXT CHECK(script_type_stopped IN ('inline', 'file')) DEFAULT 'inline',
                    script_content_stopped TEXT,
                    script_path_stopped TEXT,
                    script_type_running TEXT CHECK(script_type_running IN ('inline', 'file')) DEFAULT 'inline',
                    script_content_running TEXT,
                    script_path_running TEXT,
                    duration_threshold INTEGER DEFAULT 1,
                    max_script_executions INTEGER DEFAULT 5,
                    retry_interval_multiplier INTEGER DEFAULT 10,
                    trigger_on_status TEXT CHECK(trigger_on_status IN ('stopped', 'running', 'both')) DEFAULT 'stopped',
                    enabled BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Monitored processes table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS monitored_processes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    process_id INTEGER,
                    process_name TEXT,
                    monitoring_interval INTEGER DEFAULT 5,
                    script_type_stopped TEXT CHECK(script_type_stopped IN ('inline', 'file')) DEFAULT 'inline',
                    script_content_stopped TEXT,
                    script_path_stopped TEXT,
                    script_type_running TEXT CHECK(script_type_running IN ('inline', 'file')) DEFAULT 'inline',
                    script_content_running TEXT,
                    script_path_running TEXT,
                    duration_threshold INTEGER DEFAULT 1,
                    max_script_executions INTEGER DEFAULT 5,
                    retry_interval_multiplier INTEGER DEFAULT 10,
                    trigger_on_status TEXT CHECK(trigger_on_status IN ('stopped', 'running', 'both')) DEFAULT 'stopped',
                    enabled BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Monitored services table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS monitored_services (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_name TEXT NOT NULL,
                    display_name TEXT,
                    monitoring_interval INTEGER DEFAULT 5,
                    restart_config TEXT,
                    state_duration_threshold INTEGER DEFAULT 1,
                    enabled BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Supervised processes table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS supervised_processes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    command TEXT NOT NULL,
                    working_directory TEXT,
                    monitoring_interval INTEGER DEFAULT 5,
                    restart_delay INTEGER DEFAULT 3,
                    max_restarts INTEGER DEFAULT 0,
                    current_pid INTEGER,
                    restart_count INTEGER DEFAULT 0,
                    last_started_at TIMESTAMP,
                    enabled BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # System monitoring table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS system_monitoring (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    monitor_type TEXT CHECK(monitor_type IN ('cpu', 'ram', 'disk', 'process_cpu', 'process_ram')) NOT NULL,
                    threshold_value REAL,
                    monitoring_interval INTEGER DEFAULT 5,
                    process_reference TEXT,
                    drive_letter TEXT,
                    enabled BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Alert rules table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alert_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    monitored_item_id INTEGER NOT NULL,
                    monitored_item_type TEXT CHECK(monitored_item_type IN ('port', 'process', 'service', 'system')) NOT NULL,
                    alert_condition TEXT CHECK(alert_condition IN ('status_change', 'duration', 'recurring', 'threshold')) NOT NULL,
                    condition_value TEXT,
                    recurring_schedule TEXT,
                    template_id INTEGER,
                    enabled BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (template_id) REFERENCES email_templates(id)
                )
            """)
            
            # Alert recipients junction table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alert_recipients (
                    alert_id INTEGER NOT NULL,
                    recipient_id INTEGER NOT NULL,
                    PRIMARY KEY (alert_id, recipient_id),
                    FOREIGN KEY (alert_id) REFERENCES alert_rules(id) ON DELETE CASCADE,
                    FOREIGN KEY (recipient_id) REFERENCES recipients(id) ON DELETE CASCADE
                )
            """)
            
            # Email templates table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS email_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_name TEXT NOT NULL UNIQUE,
                    subject_template TEXT NOT NULL,
                    body_template TEXT NOT NULL,
                    variables TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Email servers table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS email_servers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    smtp_host TEXT NOT NULL,
                    smtp_port INTEGER DEFAULT 587,
                    use_ssl BOOLEAN DEFAULT TRUE,
                    use_tls BOOLEAN DEFAULT TRUE,
                    username TEXT,
                    password TEXT,
                    from_address TEXT NOT NULL,
                    default_template_id INTEGER,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (default_template_id) REFERENCES email_templates(id)
                )
            """)
            
            # Script configurations table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS script_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    script_name TEXT NOT NULL,
                    script_type TEXT CHECK(script_type IN ('inline', 'file')) DEFAULT 'inline',
                    content TEXT,
                    file_path TEXT,
                    timeout_seconds INTEGER DEFAULT 300,
                    success_handling TEXT,
                    failure_handling TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Recipients table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS recipients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email_address TEXT NOT NULL UNIQUE,
                    name TEXT,
                    alert_types TEXT,
                    enabled BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Status history table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS status_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    monitor_type TEXT CHECK(monitor_type IN ('port', 'process', 'service')) NOT NULL,
                    monitor_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    metadata TEXT,
                    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create index for efficient lookups
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status_history_lookup 
                ON status_history(monitor_type, monitor_id, changed_at DESC)
            """)
            
            # Run migrations for existing databases
            self._run_migrations(conn)
            
            # Insert default email template
            conn.execute("""
                INSERT OR IGNORE INTO email_templates (template_name, subject_template, body_template, variables)
                VALUES (?, ?, ?, ?)
            """, (
                "default_alert",
                "Alert: {monitored_item_type} {monitored_item_id} - {status}",
                "The {monitored_item_type} {monitored_item_id} has changed status to {status}.\n\nTrigger reason: {trigger_reason}\nTimestamp: {timestamp}",
                json.dumps(["monitored_item_type", "monitored_item_id", "status", "trigger_reason", "timestamp"])
            ))
            
            conn.commit()
    
    def get_connection(self):
        """Get a database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def execute_query(self, query: str, params: tuple = ()):
        """Execute a query and return results"""
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchall()
    
    def execute_update(self, query: str, params: tuple = ()):
        """Execute an update query and return row count"""
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor.rowcount
    
    def execute_insert(self, query: str, params: tuple = ()):
        """Execute an insert query and return the last row id"""
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor.lastrowid
    
    def record_status_change(self, monitor_type: str, monitor_id: int, status: str, metadata: dict = None):
        """Record a status change in the history table"""
        metadata_json = json.dumps(metadata) if metadata else None
        query = """
            INSERT INTO status_history (monitor_type, monitor_id, status, metadata)
            VALUES (?, ?, ?, ?)
        """
        return self.execute_insert(query, (monitor_type, monitor_id, status, metadata_json))
    
    def get_last_status_change(self, monitor_type: str, monitor_id: int):
        """Get the most recent status change for a monitor"""
        query = """
            SELECT status, changed_at, metadata
            FROM status_history
            WHERE monitor_type = ? AND monitor_id = ?
            ORDER BY changed_at DESC
            LIMIT 1
        """
        results = self.execute_query(query, (monitor_type, monitor_id))
        return dict(results[0]) if results else None
    
    def get_previous_status(self, monitor_type: str, monitor_id: int):
        """Get the previous status (second most recent) for a monitor"""
        query = """
            SELECT status, changed_at
            FROM status_history
            WHERE monitor_type = ? AND monitor_id = ?
            ORDER BY changed_at DESC
            LIMIT 2
        """
        results = self.execute_query(query, (monitor_type, monitor_id))
        if len(results) >= 2:
            return dict(results[1])
        return None


# Global database instance (will be initialized in __main__.py)
db: Optional[DatabaseManager] = None

