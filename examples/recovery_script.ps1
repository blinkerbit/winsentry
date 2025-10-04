# Example PowerShell recovery script for WinSentry
# This script will be executed when a monitored port goes offline
# The port number is automatically passed as a parameter

param(
    [Parameter(Mandatory=$true)]
    [int]$Port
)

# Log the port failure
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host "[$timestamp] Port $Port is offline - executing recovery script"

# Example recovery actions:
# 1. Try to restart a specific service
if ($ServiceName) {
    Write-Host "Attempting to restart service: $ServiceName"
    try {
        Restart-Service -Name $ServiceName -Force
        Write-Host "Service $ServiceName restarted successfully"
    }
    catch {
        Write-Host "Failed to restart service $ServiceName : $($_.Exception.Message)"
    }
}

# 2. Send notification (example with Windows notification)
$title = "WinSentry Alert"
$message = "Port $Port is offline and recovery script executed"
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.MessageBox]::Show($message, $title, [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Warning)

# 3. Log to file
$logFile = "C:\temp\winsentry_recovery.log"
$logEntry = "[$timestamp] Port $Port offline - Recovery script executed"
Add-Content -Path $logFile -Value $logEntry

Write-Host "Recovery script completed for port $Port"
