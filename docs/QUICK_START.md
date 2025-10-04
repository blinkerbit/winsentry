# WinSentry Quick Start Guide

## 🚀 Quick Installation & Setup

### 1. Install Dependencies
```bash
pip install tornado psutil pywin32 WMI
```

### 2. Test Installation
```bash
python test_imports.py
python test_installation.py
```

### 3. Run WinSentry

#### Option A: Direct Python execution
```bash
python run_winsentry.py
```

#### Option B: Windows batch file
```bash
run_winsentry.bat
```

#### Option C: Run as Python module
```bash
python -m winsentry
```

#### Option D: Run main.py directly
```bash
python winsentry\main.py
```

#### Option E: After pip install (if installed)
```bash
winsentry
```

### 4. Access Web Interface
Open your browser to: **http://localhost:8888**

## 🔧 Key Features

### Service Management
- View all Windows services
- Start, stop, restart services
- Real-time status monitoring

### Port Monitoring
- Monitor any port (1-65535)
- Configurable check intervals (5-3600 seconds)
- PowerShell script execution on failures
- Failure count tracking

### PowerShell Integration
- Automatic script execution when ports go offline
- Port number passed as parameter
- Full path validation
- Comprehensive logging

## 📝 Example Usage

### Add Port Monitor via Web UI
1. Go to **Port Monitor** tab
2. Enter port number (e.g., 8080)
3. Set check interval (e.g., 30 seconds)
4. Add PowerShell script path (optional):
   ```
   C:\scripts\restart-service.ps1
   ```

### PowerShell Script Template
```powershell
param([int]$Port)

# Your recovery logic here
Restart-Service -Name "YourService" -Force
Write-Host "Service restarted for port $Port"
```

### API Usage
```bash
# Add port monitor
curl -X POST http://localhost:8888/api/ports \
  -H "Content-Type: application/json" \
  -d '{"port": 8080, "interval": 30, "powershell_script": "C:\\scripts\\restart.ps1"}'

# List services
curl http://localhost:8888/api/services

# Start service
curl -X POST http://localhost:8888/api/services/MyService/start
```

## 🛠 Troubleshooting

### Import Errors
- Run `python test_imports.py` to verify imports
- Ensure all dependencies are installed
- Check Python path and working directory

### PowerShell Script Issues
- Verify script path is correct and accessible
- Ensure script has `.ps1` extension
- Test script manually: `powershell.exe -File "C:\path\to\script.ps1" -Port 8080`
- Check logs in `logs/` directory

### Service Management Issues
- Run WinSentry as Administrator
- Check service permissions
- Verify Windows service access

## 📁 Project Structure
```
winsentry/
├── run_winsentry.py          # Main entry point
├── run_winsentry.bat          # Windows batch file
├── test_imports.py             # Import testing
├── test_installation.py       # Installation testing
├── winsentry/                 # Main package
│   ├── main.py               # Application entry
│   ├── app.py                # Tornado app
│   ├── service_manager.py    # Service management
│   ├── port_monitor.py      # Port monitoring
│   ├── handlers.py          # API handlers
│   ├── logger.py            # Logging setup
│   ├── templates/           # Web UI
│   └── static/              # CSS/JS
├── examples/                 # PowerShell examples
└── logs/                     # Log files
```

## 🔐 Security Notes
- **Administrator privileges required** for service management
- PowerShell scripts run with bypassed execution policy
- Scripts have full system access
- Review and test scripts before production use

## 📊 Logging
- `logs/winsentry.log` - General application logs
- `logs/port_monitor.log` - Port monitoring events
- `logs/service_manager.log` - Service management operations

## 🆘 Support
- Check logs for error details
- Run test scripts to verify installation
- Ensure all dependencies are installed
- Verify PowerShell script paths and permissions
