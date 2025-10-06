# WinSentry

A comprehensive Windows Service and Port Monitoring Tool built with Tornado, featuring async/await architecture for high performance.

## Features

### 🔧 Service Management & Monitoring
- **List all Windows services** with real-time status
- **Start, stop, and restart services** with one-click actions
- **Service status monitoring** with email alerts when a service stops
- **Configurable check intervals per service** (5s–1h)
- **Bulk service operations** support
- **Service process visibility**: PIDs, CPU%, RAM%, RSS/VMS, username, status, full command line arguments
- **Service resource thresholds**: Define CPU%/RAM% limits per service with alerting
- **Service process logs**: Historical CPU/RAM usage (per PID) persisted in SQLite

### 🌐 Port Monitoring
- **Real-time port monitoring** with configurable intervals
- **Automatic failure detection** and logging
- **PowerShell script execution** on port failures
- **Custom recovery actions** per port
- **Failure count tracking** and statistics
- **Per-port process visibility**: See processes bound to a port with CPU%, RAM%, cmdline, user
- **Port resource thresholds**: CPU%/RAM% thresholds with email alerts
- **Process metrics history**: Rolling logs of process CPU/RAM for ports

### 📊 Web Interface
- **Modern, responsive web UI** built with Bootstrap 5
- **Real-time updates** without page refresh
- **Service management dashboard** (Services tab)
- **Port monitoring configuration** (Port Monitor tab)
- **Service Monitor tab**: Add/remove service monitors, see status, interval, failures, recovery script; bulk start/stop; test
- **Resource Monitor tab**: Configure CPU/RAM thresholds per service, view current usage and summaries, see existing threshold configs with status (Normal/Warning/Critical), check-all/test-all
- **Enhanced process views**: Per-service processes table with CPU/RAM and clickable command lines; details modal
- **Comprehensive logging viewer**

### 🔍 Advanced Features
- **Async/await architecture** for optimal performance
- **Configurable monitoring intervals** (5 seconds to 1 hour)
- **PowerShell script integration** for automated recovery
- **Comprehensive logging** with rotation
- **RESTful API** for integration
- **Windows-specific optimizations**
- **SQLite database** for configs, logs, thresholds (auto-migrations)
- **psutil-powered process insights** (CPU, memory, cmdline, user)
- **Email templates** with service/port-specific content

## Installation

### Prerequisites
- **Windows 10/11** (required for Windows service management)
- **Python 3.8+**
- **Administrator privileges** (for service management operations)

### Install from PyPI
```bash
pip install winsentry
```

### Install from Source
```bash
git clone https://github.com/yourusername/winsentry.git
cd winsentry
pip install -e .
```

## Usage

### Basic Usage

#### Option 1: Using the installed command (after pip install)
```bash
# Start WinSentry (requires administrator privileges)
winsentry

# Start with custom port
winsentry --port=9999

# Start in debug mode
winsentry --debug
```

#### Option 2: Running directly from source
```bash
# Run the entry point script
python run_winsentry.py

# Or use the Windows batch file
run_winsentry.bat

# With custom options
python run_winsentry.py --port=9999 --debug
```

#### Option 3: Run as Python module
```bash
# Run the package as a module
python -m winsentry

# With custom options
python -m winsentry --port=9999 --debug
```

#### Option 4: Run main.py directly
```bash
# Run main.py directly (now works with import fallback)
python winsentry\main.py

# With custom options
python winsentry\main.py --port=9999 --debug
```

#### Option 5: Test imports first
```bash
# Test that all modules can be imported
python test_imports.py
```

### Web Interface
1. Open your browser to `http://localhost:8888`
2. Navigate between tabs:
   - **Services**: Manage Windows services
   - **Port Monitor**: Configure port monitoring and thresholds
   - **Service Monitor**: Configure monitoring of service state; manage monitored services
   - **Resource Monitor**: Configure CPU/RAM thresholds for services; view summaries and current status
   - **Logs**: View monitoring logs

### Service Management
- View all Windows services with their current status
- Start, stop, or restart services with one click
- Real-time status updates
 - Add services to continuous monitoring with custom intervals and optional PowerShell recovery
 - See per-service processes with CPU/RAM and command line; open details modal

### Port Monitoring Setup
1. Go to the **Port Monitor** tab
2. Add ports to monitor with:
   - **Port number** (1-65535)
   - **Check interval** (5-3600 seconds)
   - **PowerShell recovery script** (optional)
3. Monitor real-time status and failure counts
4. View processes bound to a port (CPU%, RAM%, username, cmdline)
5. Configure CPU/RAM thresholds and enable email alerts

### PowerShell Recovery Scripts
Create custom PowerShell scripts for automated recovery:

```powershell
# Example: restart-service.ps1
param([int]$Port)

# Restart a specific service when port goes offline
Restart-Service -Name "YourServiceName" -Force
Write-Host "Service restarted for port $Port"
```

## Configuration

### Command Line Options
```bash
winsentry --help
```

Available options:
- `--port`: Web server port (default: 8888)
- `--debug`: Enable debug mode
- `--help`: Show help message

### PowerShell Script Requirements
- Scripts must be `.ps1` files
- Use `param([int]$Port)` to receive port number
- Scripts run with `-ExecutionPolicy Bypass`
- Maximum execution time: 30 seconds
- Logs are captured and displayed in the UI

### Email Alerts
- Configure SMTP and templates via the Email Config UI
- Enable alerts per service/port threshold configuration
- Built-in templates include service state changes and resource threshold exceedances

## API Reference

### Services API
```http
GET /api/services                    # List all services
POST /api/services/{name}/start       # Start service
POST /api/services/{name}/stop        # Stop service
POST /api/services/{name}/restart     # Restart service
```

### Service Monitor API
```http
GET    /api/service-monitor                           # List monitored services/status
POST   /api/service-monitor/config                    # Add/update service monitor (service_name, interval, powershell_script, enabled)
DELETE /api/service-monitor/config                    # Remove service monitor (JSON: service_name)

GET    /api/service-monitor/processes?service_name=X  # Processes for a service (CPU/RAM/cmdline)
GET    /api/service-monitor/resource-summary?service_name=X  # Aggregated CPU/RAM summary

GET    /api/service-monitor/thresholds?service_name=X # Get thresholds (CPU/RAM, email)
POST   /api/service-monitor/thresholds                # Set thresholds (service_name, cpu_threshold, ram_threshold, email_alerts_enabled)
DELETE /api/service-monitor/thresholds?service_name=X # Delete thresholds

GET    /api/service-monitor/threshold-check?service_name=X   # Check thresholds now
GET    /api/service-process-logs[?service_name=X][&limit=N]  # Historical process metrics
```

### Port Monitoring API
```http
GET /api/ports                       # List monitored ports
POST /api/ports                      # Add port monitor
DELETE /api/ports                    # Remove port monitor
PUT /api/ports/config                # Update port configuration
GET /api/ports/processes?port=NN     # Processes on port (CPU/RAM/cmdline)
GET /api/ports/resource-summary?port=NN           # Aggregated CPU/RAM summary
GET /api/ports/thresholds?port=NN                # Get thresholds
POST /api/ports/thresholds                       # Set thresholds (port, cpu_threshold, ram_threshold, email_alerts_enabled)
DELETE /api/ports/thresholds?port=NN             # Delete thresholds
GET /api/ports/threshold-check?port=NN           # Check thresholds now
GET /api/process-logs[?port=NN][&limit=N]        # Historical process metrics for ports
```

### Logs API
```http
GET /api/logs                        # Get monitoring logs
GET /api/logs?port=8080              # Get logs for specific port
```

## Examples

### Basic Port Monitoring
```bash
# Monitor port 8080 every 30 seconds
curl -X POST http://localhost:8888/api/ports \
  -H "Content-Type: application/json" \
  -d '{"port": 8080, "interval": 30}'
```

### Port with Recovery Script
```bash
# Monitor port 3306 with MySQL restart script
curl -X POST http://localhost:8888/api/ports \
  -H "Content-Type: application/json" \
  -d '{
    "port": 3306,
    "interval": 60,
    "powershell_script": "C:\\scripts\\restart-mysql.ps1"
  }'
```

### Service Management
```bash
# Start a Windows service
curl -X POST http://localhost:8888/api/services/MyService/start

# Stop a Windows service
curl -X POST http://localhost:8888/api/services/MyService/stop
```

## Logging

WinSentry creates detailed logs in the `logs/` directory:
- `winsentry.log`: General application logs
- `port_monitor.log`: Port monitoring events
- `service_manager.log`: Service management operations
- `service_monitor.log`: Service monitor and threshold events
- `process_logs` (SQLite): Historical process CPU/RAM metrics (ports & services)

Log files are automatically rotated when they reach 10MB (5MB for specialized logs).

## Security Considerations

- **Run as Administrator**: Required for service management
- **PowerShell Execution**: Scripts run with bypassed execution policy
- **Network Access**: Web interface accessible on all interfaces
- **File Permissions**: Ensure script files have appropriate permissions

## Troubleshooting

### Common Issues

**"Access Denied" errors:**
- Run WinSentry as Administrator
- Check service permissions

**PowerShell scripts not executing:**
- Verify script file exists and is accessible
- Check PowerShell execution policy
- Review logs for error messages

**Port monitoring not working:**
- Ensure ports are not already in use
- Check firewall settings
- Verify monitoring intervals are reasonable

### Debug Mode
```bash
winsentry --debug
```
Enables detailed logging and error reporting.

## Development

### Project Structure
```
winsentry/
├── __init__.py
├── main.py              # Entry point
├── app.py               # Tornado application
├── service_manager.py   # Windows service management
├── service_monitor.py   # Service monitoring and thresholds
├── port_monitor.py      # Port monitoring logic
├── handlers.py          # API handlers
├── logger.py            # Logging configuration
├── templates/           # HTML templates
├── static/              # CSS/JS assets
└── examples/            # PowerShell script examples
```

### Contributing
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Support

For issues and questions:
- Create an issue on GitHub
- Check the troubleshooting section
- Review the logs for error details
