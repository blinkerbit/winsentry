"""Database migration script to add new columns"""

import sqlite3
import sys
import os

def migrate_database(db_path):
    """Add missing columns to existing database"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    migrations = []
    
    # Check and add max_script_executions to monitored_ports
    try:
        cursor.execute("SELECT max_script_executions FROM monitored_ports LIMIT 1")
    except sqlite3.OperationalError:
        migrations.append(
            "ALTER TABLE monitored_ports ADD COLUMN max_script_executions INTEGER DEFAULT 5"
        )
    
    # Check and add retry_interval_multiplier to monitored_ports
    try:
        cursor.execute("SELECT retry_interval_multiplier FROM monitored_ports LIMIT 1")
    except sqlite3.OperationalError:
        migrations.append(
            "ALTER TABLE monitored_ports ADD COLUMN retry_interval_multiplier INTEGER DEFAULT 10"
        )
    
    # Check and add max_script_executions to monitored_processes
    try:
        cursor.execute("SELECT max_script_executions FROM monitored_processes LIMIT 1")
    except sqlite3.OperationalError:
        migrations.append(
            "ALTER TABLE monitored_processes ADD COLUMN max_script_executions INTEGER DEFAULT 5"
        )
    
    # Check and add retry_interval_multiplier to monitored_processes
    try:
        cursor.execute("SELECT retry_interval_multiplier FROM monitored_processes LIMIT 1")
    except sqlite3.OperationalError:
        migrations.append(
            "ALTER TABLE monitored_processes ADD COLUMN retry_interval_multiplier INTEGER DEFAULT 10"
        )
    
    if migrations:
        print(f"Running {len(migrations)} migration(s)...")
        for migration in migrations:
            print(f"  - {migration}")
            cursor.execute(migration)
        conn.commit()
        print("✅ Migration completed successfully!")
    else:
        print("✅ Database is already up to date!")
    
    conn.close()

if __name__ == "__main__":
    # Default database path
    db_path = "data/winsentry.db"
    
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found at: {db_path}")
        print("Usage: python -m winsentry.migrate_db [path_to_db]")
        sys.exit(1)
    
    print(f"Migrating database: {db_path}")
    migrate_database(db_path)

