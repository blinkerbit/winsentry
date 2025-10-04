# PowerShell Recovery Script Template for WinSentry
# Copy this file and customize it for your specific needs
# The port number is automatically passed as a parameter

param(
    [Parameter(Mandatory=$true)]
    [int]$Port
)

# =============================================================================
# CUSTOMIZE THIS SECTION FOR YOUR SPECIFIC NEEDS
# =============================================================================

# Define the service name that should be restarted for this port
$ServiceName = "YourServiceName"  # Change this to your actual service name

# Define the log file path
$LogPath = "C:\temp\winsentry_recovery_$Port.log"

# =============================================================================
# RECOVERY LOGIC - CUSTOMIZE AS NEEDED
# =============================================================================

# Function to write log entries
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$timestamp] [$Level] Port $Port - $Message"
    Write-Host $logEntry
    Add-Content -Path $LogPath -Value $logEntry
}

Write-Log "Starting recovery script for port $Port"

# Example 1: Restart a Windows service
if ($ServiceName) {
    Write-Log "Attempting to restart service: $ServiceName"
    try {
        $service = Get-Service -Name $ServiceName -ErrorAction Stop
        if ($service.Status -ne "Running") {
            Start-Service -Name $ServiceName
            Start-Sleep -Seconds 5
            $service = Get-Service -Name $ServiceName
            if ($service.Status -eq "Running") {
                Write-Log "Service $ServiceName restarted successfully"
            } else {
                Write-Log "Service $ServiceName failed to start" "ERROR"
            }
        } else {
            Write-Log "Service $ServiceName is already running"
        }
    }
    catch {
        Write-Log "Failed to restart service $ServiceName : $($_.Exception.Message)" "ERROR"
    }
}

# Example 2: Send notification
try {
    Add-Type -AssemblyName System.Windows.Forms
    $title = "WinSentry Alert - Port $Port Offline"
    $message = "Port $Port is offline. Recovery script executed at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    [System.Windows.Forms.MessageBox]::Show($message, $title, [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Warning)
    Write-Log "Windows notification sent"
}
catch {
    Write-Log "Failed to send Windows notification: $($_.Exception.Message)" "ERROR"
}

# Example 3: Create event log entry
try {
    $source = "WinSentry"
    if (![System.Diagnostics.EventLog]::SourceExists($source)) {
        New-EventLog -LogName Application -Source $source
    }
    Write-EventLog -LogName Application -Source $source -EventId 1001 -EntryType Warning -Message "Port $Port monitoring alert - Recovery script executed"
    Write-Log "Event log entry created"
}
catch {
    Write-Log "Failed to create event log entry: $($_.Exception.Message)" "ERROR"
}

# Example 4: Custom recovery actions
# Add your own recovery logic here, such as:
# - Restart specific applications
# - Send emails
# - Execute other scripts
# - Modify configuration files
# - etc.

Write-Log "Recovery script completed for port $Port"
