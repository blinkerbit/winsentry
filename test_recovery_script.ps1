# Test Recovery Script for WinSentry
# This script demonstrates how to create a recovery script for a stopped port/process

param(
    [string]$Action = "restart"
)

# Log the execution
$logFile = "C:\temp\winsentry_recovery.log"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# Create log directory if it doesn't exist
$logDir = Split-Path $logFile -Parent
if (!(Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

# Write log entry
Add-Content -Path $logFile -Value "[$timestamp] Recovery script executed - Action: $Action"

# Example: Restart a service
if ($Action -eq "restart_service") {
    try {
        # Replace 'YourServiceName' with actual service name
        $serviceName = "YourServiceName"
        Add-Content -Path $logFile -Value "[$timestamp] Attempting to restart service: $serviceName"
        
        Restart-Service -Name $serviceName -Force
        
        Add-Content -Path $logFile -Value "[$timestamp] Service $serviceName restarted successfully"
        Write-Output "Service $serviceName restarted successfully"
    }
    catch {
        Add-Content -Path $logFile -Value "[$timestamp] ERROR: Failed to restart service - $($_.Exception.Message)"
        Write-Error "Failed to restart service: $($_.Exception.Message)"
    }
}

# Example: Start a process
elseif ($Action -eq "start_process") {
    try {
        # Replace with your application path
        $appPath = "C:\Path\To\Your\Application.exe"
        Add-Content -Path $logFile -Value "[$timestamp] Attempting to start process: $appPath"
        
        Start-Process -FilePath $appPath
        
        Add-Content -Path $logFile -Value "[$timestamp] Process started successfully"
        Write-Output "Process started successfully"
    }
    catch {
        Add-Content -Path $logFile -Value "[$timestamp] ERROR: Failed to start process - $($_.Exception.Message)"
        Write-Error "Failed to start process: $($_.Exception.Message)"
    }
}

# Example: Send notification
elseif ($Action -eq "notify") {
    Add-Content -Path $logFile -Value "[$timestamp] Notification action triggered"
    Write-Output "Notification sent - check log at $logFile"
}

# Default action
else {
    Add-Content -Path $logFile -Value "[$timestamp] Default action executed"
    Write-Output "Recovery script executed successfully - check log at $logFile"
}

exit 0

