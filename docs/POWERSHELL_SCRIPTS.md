# PowerShell Script Integration Guide

WinSentry allows you to specify PowerShell scripts that will be automatically executed when a monitored port goes offline. This provides powerful automated recovery capabilities.

## How It Works

1. **Port Monitoring**: WinSentry continuously monitors specified ports
2. **Failure Detection**: When a port becomes unavailable, the failure is logged
3. **Script Execution**: If a PowerShell script is configured, it's automatically executed
4. **Recovery Actions**: The script can perform any recovery actions you define

## Script Requirements

### File Format
- **Extension**: Must be `.ps1` (PowerShell script)
- **Location**: Full path must be provided (e.g., `C:\scripts\recovery.ps1`)
- **Permissions**: Script must be readable by the WinSentry process

### Parameter Handling
Your PowerShell script **must** accept a `-Port` parameter:

```powershell
param(
    [Parameter(Mandatory=$true)]
    [int]$Port
)
```

The port number is automatically passed to your script when executed.

## Example Scripts

### Basic Service Restart
```powershell
param([int]$Port)

# Restart a specific service when port goes offline
Restart-Service -Name "YourServiceName" -Force
Write-Host "Service restarted for port $Port"
```

### Advanced Recovery with Logging
```powershell
param([int]$Port)

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host "[$timestamp] Port $Port is offline - executing recovery"

# Restart service
Restart-Service -Name "YourServiceName" -Force

# Send notification
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.MessageBox]::Show("Port $Port recovered", "WinSentry Alert")

# Log to file
Add-Content -Path "C:\logs\recovery.log" -Value "[$timestamp] Port $Port recovered"
```

## Configuration

### Via Web Interface
1. Go to the **Port Monitor** tab
2. Add a new port monitor
3. Enter the **full path** to your PowerShell script
4. Example: `C:\scripts\my-recovery.ps1`

### Via API
```bash
curl -X POST http://localhost:8888/api/ports \
  -H "Content-Type: application/json" \
  -d '{
    "port": 8080,
    "interval": 30,
    "powershell_script": "C:\\scripts\\restart-service.ps1"
  }'
```

## Script Execution Details

### Execution Environment
- **Execution Policy**: Scripts run with `-ExecutionPolicy Bypass`
- **Timeout**: Maximum 30 seconds execution time
- **Working Directory**: Same as WinSentry process
- **User Context**: Same as WinSentry process (requires appropriate permissions)

### Error Handling
- Script execution errors are logged
- Script output (stdout/stderr) is captured and logged
- Failed scripts don't prevent port monitoring from continuing

### Logging
All script executions are logged in:
- `logs/port_monitor.log` - Port monitoring events
- `logs/winsentry.log` - General application logs

## Best Practices

### 1. Script Design
- Keep scripts focused and fast
- Include proper error handling
- Use meaningful log messages
- Test scripts manually before using with WinSentry

### 2. Security
- Store scripts in secure locations
- Use appropriate file permissions
- Avoid hardcoded credentials
- Consider using Windows authentication

### 3. Performance
- Keep execution time under 30 seconds
- Avoid blocking operations
- Use async operations when possible
- Monitor script performance

### 4. Reliability
- Include validation checks
- Handle edge cases
- Provide fallback actions
- Test with different scenarios

## Common Use Cases

### Service Management
```powershell
param([int]$Port)

# Restart service based on port
switch ($Port) {
    80 { Restart-Service -Name "IIS" -Force }
    3306 { Restart-Service -Name "MySQL" -Force }
    5432 { Restart-Service -Name "PostgreSQL" -Force }
    default { Write-Host "No specific service for port $Port" }
}
```

### Application Restart
```powershell
param([int]$Port)

# Kill and restart application
$processes = Get-Process | Where-Object { $_.ProcessName -eq "MyApp" }
if ($processes) {
    $processes | Stop-Process -Force
    Start-Sleep -Seconds 5
    Start-Process "C:\MyApp\MyApp.exe"
    Write-Host "Application restarted for port $Port"
}
```

### Notification and Alerting
```powershell
param([int]$Port)

# Send email notification
$smtpServer = "smtp.gmail.com"
$smtpPort = 587
$smtpUser = "your-email@gmail.com"
$smtpPass = "your-app-password"

$mail = New-Object System.Net.Mail.MailMessage
$mail.From = $smtpUser
$mail.To.Add("admin@yourcompany.com")
$mail.Subject = "Port $Port Offline Alert"
$mail.Body = "Port $Port is offline. Recovery script executed at $(Get-Date)"

$smtp = New-Object System.Net.Mail.SmtpClient($smtpServer, $smtpPort)
$smtp.EnableSsl = $true
$smtp.Credentials = New-Object System.Net.NetworkCredential($smtpUser, $smtpPass)
$smtp.Send($mail)
```

## Troubleshooting

### Script Not Executing
1. Check file path is correct and accessible
2. Verify file has `.ps1` extension
3. Ensure file is readable by WinSentry process
4. Check PowerShell execution policy
5. Review logs for error messages

### Script Execution Failing
1. Test script manually with: `powershell.exe -File "C:\path\to\script.ps1" -Port 8080`
2. Check script syntax and logic
3. Verify all dependencies are available
4. Review error messages in logs

### Performance Issues
1. Monitor script execution time
2. Optimize script logic
3. Consider async operations
4. Check system resources

## Security Considerations

- **Run as Administrator**: WinSentry requires admin privileges for service management
- **Script Permissions**: Ensure scripts have appropriate permissions
- **Network Access**: Scripts can access network resources
- **File System**: Scripts can read/write files
- **System Access**: Scripts can modify system settings

Always review and test PowerShell scripts before deploying them in production environments.
