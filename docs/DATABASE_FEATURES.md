# WinSentry Database Features

## 🗄️ SQLite Database Integration

WinSentry now includes comprehensive SQLite database persistence for port configurations and monitoring logs.

## 📊 Database Schema

### Port Configurations Table (`port_configs`)
```sql
CREATE TABLE port_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    port INTEGER UNIQUE NOT NULL,
    interval_seconds INTEGER NOT NULL DEFAULT 30,
    powershell_script TEXT,
    enabled BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Port Monitoring Logs Table (`port_logs`)
```sql
CREATE TABLE port_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    port INTEGER NOT NULL,
    status TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    failure_count INTEGER DEFAULT 0,
    message TEXT,
    FOREIGN KEY (port) REFERENCES port_configs (port)
);
```

## 🔧 Key Features

### ✅ **Persistent Configuration**
- **Port configurations** are automatically saved to SQLite database
- **Settings persist** across application restarts
- **Automatic loading** of saved configurations on startup

### ✅ **Comprehensive Logging**
- **All port checks** are logged to database
- **Status changes** (ONLINE/OFFLINE) are tracked
- **Failure counts** and timestamps are recorded
- **PowerShell script execution** events are logged

### ✅ **Database Management**
- **Automatic cleanup** of old logs (configurable retention period)
- **Database statistics** and health monitoring
- **Optimized queries** with proper indexing
- **Transaction safety** for data integrity

## 🚀 Usage Examples

### Port Configuration Persistence
```python
# Adding a port automatically saves to database
await port_monitor.add_port(8080, 30, "C:\\scripts\\restart.ps1")

# Configuration persists across restarts
# No need to reconfigure ports after restart
```

### Database Statistics
```python
# Get database statistics
stats = port_monitor.get_database_stats()
# Returns: {
#     'port_configs': 5,
#     'log_entries': 1250,
#     'database_size_bytes': 245760,
#     'database_size_mb': 0.24
# }
```

### Log Cleanup
```python
# Clean up logs older than 30 days
cleaned_count = port_monitor.cleanup_old_logs(30)
print(f"Cleaned up {cleaned_count} old log entries")
```

## 📈 API Endpoints

### Database Statistics
```http
GET /api/database/stats
```
Returns database statistics including:
- Number of port configurations
- Total log entries
- Database size

### Log Cleanup
```http
POST /api/database/stats
Content-Type: application/json

{
    "days": 30
}
```
Cleans up logs older than specified days.

## 🔍 Database Benefits

### **Data Persistence**
- Port configurations survive application restarts
- Historical monitoring data is preserved
- No data loss during system reboots

### **Performance**
- **Indexed queries** for fast log retrieval
- **Efficient storage** with SQLite optimization
- **Batch operations** for bulk data handling

### **Reliability**
- **ACID compliance** ensures data integrity
- **Transaction safety** prevents data corruption
- **Automatic recovery** from database issues

### **Monitoring & Analytics**
- **Historical trend analysis** of port status
- **Failure pattern detection** over time
- **Performance metrics** and statistics

## 🛠️ Database Management

### **Automatic Operations**
- **Startup loading** of saved configurations
- **Real-time logging** of all port checks
- **Automatic cleanup** of old logs
- **Statistics collection** for monitoring

### **Manual Operations**
- **Database stats** via API
- **Log cleanup** with configurable retention
- **Configuration backup** and restore
- **Health monitoring** and diagnostics

## 📁 File Structure

```
winsentry/
├── database.py          # SQLite database manager
├── port_monitor.py      # Updated with database integration
├── handlers.py          # Database stats API endpoints
└── winsentry.db         # SQLite database file (created automatically)
```

## 🔧 Configuration

### **Database Location**
- Default: `winsentry.db` in application directory
- Configurable via `PortMonitor(db_path="custom.db")`

### **Log Retention**
- Default: 30 days retention
- Configurable via `cleanup_old_logs(days=60)`
- Automatic cleanup on startup

### **Performance Tuning**
- **Indexed columns** for fast queries
- **Batch operations** for bulk inserts
- **Connection pooling** for efficiency

## 📊 Monitoring Dashboard

The web interface now shows:
- **Persistent port configurations** across restarts
- **Historical monitoring logs** with timestamps
- **Database statistics** and health metrics
- **Log cleanup** functionality

## 🚀 Getting Started

1. **Start WinSentry** - Database is created automatically
2. **Add port monitors** - Configurations are saved to database
3. **View logs** - Historical data is available immediately
4. **Restart application** - All configurations are restored automatically

The database integration is **completely transparent** - all existing functionality works the same, but now with full persistence and comprehensive logging!
