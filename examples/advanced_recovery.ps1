# Advanced PowerShell recovery script for WinSentry
# This script demonstrates more sophisticated recovery actions
# The port number is automatically passed as a parameter

param(
    [Parameter(Mandatory=$true)]
    [int]$Port,
    [string]$ServiceName = "",
    [string]$LogPath = "C:\temp\winsentry_recovery.log"
)

# Create log directory if it doesn't exist
$logDir = Split-Path $LogPath -Parent
if (!(Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force
}

# Function to write log entries
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$timestamp] [$Level] $Message"
    Write-Host $logEntry
    Add-Content -Path $LogPath -Value $logEntry
}

# Function to send email notification (requires SMTP configuration)
function Send-EmailNotification {
    param([string]$Subject, [string]$Body)
    
    # Example email configuration - customize as needed
    $smtpServer = "smtp.gmail.com"
    $smtpPort = 587
    $smtpUser = "your-email@gmail.com"
    $smtpPass = "your-app-password"
    $toEmail = "admin@yourcompany.com"
    
    try {
        $smtp = New-Object System.Net.Mail.SmtpClient($smtpServer, $smtpPort)
        $smtp.EnableSsl = $true
        $smtp.Credentials = New-Object System.Net.NetworkCredential($smtpUser, $smtpPass)
        
        $mail = New-Object System.Net.Mail.MailMessage
        $mail.From = $smtpUser
        $mail.To.Add($toEmail)
        $mail.Subject = $Subject
        $mail.Body = $Body
        
        $smtp.Send($mail)
        Write-Log "Email notification sent successfully" "INFO"
    }
    catch {
        Write-Log "Failed to send email notification: $($_.Exception.Message)" "ERROR"
    }
}

# Main recovery logic
Write-Log "Starting recovery script for port $Port"

# 1. Check if the port is actually in use by any process
$netstatOutput = netstat -an | Select-String ":$Port "
if ($netstatOutput) {
    Write-Log "Port $Port appears to be in use according to netstat" "WARN"
} else {
    Write-Log "Port $Port confirmed offline" "INFO"
}

# 2. Try to restart associated service
if ($ServiceName) {
    Write-Log "Attempting to restart service: $ServiceName"
    try {
        $service = Get-Service -Name $ServiceName -ErrorAction Stop
        if ($service.Status -ne "Running") {
            Start-Service -Name $ServiceName
            Start-Sleep -Seconds 5
            $service = Get-Service -Name $ServiceName
            if ($service.Status -eq "Running") {
                Write-Log "Service $ServiceName restarted successfully" "INFO"
            } else {
                Write-Log "Service $ServiceName failed to start" "ERROR"
            }
        } else {
            Write-Log "Service $ServiceName is already running" "INFO"
        }
    }
    catch {
        Write-Log "Failed to restart service $ServiceName : $($_.Exception.Message)" "ERROR"
    }
}

# 3. Check for specific processes that might be using the port
$processes = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($processes) {
    foreach ($proc in $processes) {
        $processInfo = Get-Process -Id $proc.OwningProcess -ErrorAction SilentlyContinue
        if ($processInfo) {
            Write-Log "Process $($processInfo.ProcessName) (PID: $($processInfo.Id)) is using port $Port" "INFO"
        }
    }
}

# 4. Send notifications
$subject = "WinSentry Alert - Port $Port Offline"
$body = @"
Port Monitoring Alert

Port: $Port
Time: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
Service: $ServiceName
Recovery Script: Executed

Please check the system status.
"@

# Send email notification (uncomment and configure if needed)
# Send-EmailNotification -Subject $subject -Body $body

# Send Windows notification
try {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($body, $subject, [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Warning)
    Write-Log "Windows notification sent" "INFO"
}
catch {
    Write-Log "Failed to send Windows notification: $($_.Exception.Message)" "ERROR"
}

# 5. Create a system event log entry
try {
    $source = "WinSentry"
    if (![System.Diagnostics.EventLog]::SourceExists($source)) {
        New-EventLog -LogName Application -Source $source
    }
    Write-EventLog -LogName Application -Source $source -EventId 1001 -EntryType Warning -Message "Port $Port monitoring alert - Recovery script executed"
    Write-Log "Event log entry created" "INFO"
}
catch {
    Write-Log "Failed to create event log entry: $($_.Exception.Message)" "ERROR"
}

Write-Log "Recovery script completed for port $Port" "INFO"
