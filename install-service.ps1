#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Registers WinSentry as a Windows Service using pywin32

.DESCRIPTION
    This script installs WinSentry as a Windows service using Python's pywin32.
    It will automatically start with Windows and run in the background.

.PARAMETER Action
    Action to perform: install, uninstall, start, stop, restart, status

.PARAMETER Port
    Port to run WinSentry on (default: 8888)

.EXAMPLE
    .\install-service.ps1 -Action install
    .\install-service.ps1 -Action uninstall
    .\install-service.ps1 -Action start
    .\install-service.ps1 -Action stop
    .\install-service.ps1 -Action status
#>

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("install", "uninstall", "start", "stop", "restart", "status")]
    [string]$Action,
    
    [int]$Port = 8888
)

# Configuration
$ServiceName = "WinSentry"
$ProjectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServiceScript = Join-Path $ProjectPath "winsentry_service.py"
$LogPath = Join-Path $ProjectPath "logs"

# Ensure logs directory exists
if (-not (Test-Path $LogPath)) {
    New-Item -ItemType Directory -Path $LogPath -Force | Out-Null
}

# Find Python executable
function Get-PythonPath {
    # Try to find Python in PATH
    $pythonPaths = @(
        (Get-Command python -ErrorAction SilentlyContinue).Source,
        (Get-Command python3 -ErrorAction SilentlyContinue).Source,
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "$env:LOCALAPPDATA\Microsoft\WindowsApps\python.exe",
        "C:\Python312\python.exe",
        "C:\Python311\python.exe",
        "C:\Python310\python.exe"
    )
    
    foreach ($path in $pythonPaths) {
        if ($path -and (Test-Path $path)) {
            return $path
        }
    }
    
    throw "Python executable not found. Please install Python or add it to PATH."
}

# Check if pywin32 is installed
function Test-PyWin32 {
    $pythonPath = Get-PythonPath
    $result = & $pythonPath -c "import win32serviceutil; print('OK')" 2>&1
    return $result -eq "OK"
}

# Install pywin32 if needed
function Install-PyWin32 {
    $pythonPath = Get-PythonPath
    Write-Host "Installing pywin32..." -ForegroundColor Yellow
    & $pythonPath -m pip install pywin32 --quiet
    
    # Run post-install script
    $pythonDir = Split-Path -Parent $pythonPath
    $postInstall = Join-Path $pythonDir "Scripts\pywin32_postinstall.py"
    if (Test-Path $postInstall) {
        & $pythonPath $postInstall -install
    }
}

# Install the service
function Install-WinSentryService {
    Write-Host "Installing $ServiceName service..." -ForegroundColor Cyan
    
    # Check if service already exists
    $existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($existingService) {
        Write-Host "Service $ServiceName already exists. Uninstalling first..." -ForegroundColor Yellow
        Uninstall-WinSentryService
        Start-Sleep -Seconds 2
    }
    
    # Check for pywin32
    if (-not (Test-PyWin32)) {
        Write-Host "pywin32 not found. Installing..." -ForegroundColor Yellow
        Install-PyWin32
        
        if (-not (Test-PyWin32)) {
            Write-Host "Failed to install pywin32. Please install manually: pip install pywin32" -ForegroundColor Red
            return $false
        }
    }
    
    # Check if service script exists
    if (-not (Test-Path $ServiceScript)) {
        Write-Host "Service script not found: $ServiceScript" -ForegroundColor Red
        return $false
    }
    
    # Set environment variable for port
    [Environment]::SetEnvironmentVariable("WINSENTRY_PORT", $Port, "Machine")
    
    # Get Python path
    $pythonPath = Get-PythonPath
    Write-Host "Python: $pythonPath" -ForegroundColor Gray
    Write-Host "Service Script: $ServiceScript" -ForegroundColor Gray
    
    # Install service using pywin32
    $result = & $pythonPath $ServiceScript install 2>&1
    Write-Host $result
    
    if ($LASTEXITCODE -eq 0 -or $result -match "installed") {
        # Configure service to auto-start
        sc.exe config $ServiceName start= auto | Out-Null
        sc.exe description $ServiceName "WinSentry - Windows Port, Service, and Resource Monitoring Tool" | Out-Null
        sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/10000/restart/30000 | Out-Null
        
        Write-Host @"

$ServiceName service installed successfully!

Service Details:
  Name: $ServiceName
  Port: $Port
  Startup Type: Automatic
  Auto-Restart: Yes (on failure)
  Log Files: $LogPath

Commands:
  Start:      sc start $ServiceName
  Stop:       sc stop $ServiceName
  Query:      sc query $ServiceName
  Delete:     sc delete $ServiceName

PowerShell Commands:
  Start-Service $ServiceName
  Stop-Service $ServiceName
  Get-Service $ServiceName
  Restart-Service $ServiceName

Web Interface: http://localhost:$Port

"@ -ForegroundColor Green
        return $true
    }
    else {
        Write-Host "Failed to install service." -ForegroundColor Red
        return $false
    }
}

# Uninstall the service
function Uninstall-WinSentryService {
    Write-Host "Uninstalling $ServiceName service..." -ForegroundColor Cyan
    
    # Stop service first
    $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($service -and $service.Status -eq 'Running') {
        Write-Host "Stopping service..." -ForegroundColor Yellow
        sc.exe stop $ServiceName | Out-Null
        Start-Sleep -Seconds 3
    }
    
    # Remove service using pywin32
    $pythonPath = Get-PythonPath
    if (Test-Path $ServiceScript) {
        & $pythonPath $ServiceScript remove 2>&1 | Out-Null
    }
    
    # Fallback to sc.exe
    sc.exe delete $ServiceName 2>&1 | Out-Null
    
    # Remove environment variable
    [Environment]::SetEnvironmentVariable("WINSENTRY_PORT", $null, "Machine")
    
    Write-Host "$ServiceName service uninstalled successfully." -ForegroundColor Green
}

# Start the service
function Start-WinSentryService {
    $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if (-not $service) {
        Write-Host "Service $ServiceName is not installed. Run: .\install-service.ps1 -Action install" -ForegroundColor Red
        return
    }
    
    if ($service.Status -eq 'Running') {
        Write-Host "Service $ServiceName is already running." -ForegroundColor Yellow
        return
    }
    
    Write-Host "Starting $ServiceName service..." -ForegroundColor Cyan
    sc.exe start $ServiceName
    Start-Sleep -Seconds 3
    
    $service = Get-Service -Name $ServiceName
    if ($service.Status -eq 'Running') {
        Write-Host @"

$ServiceName service started successfully!

Web Interface: http://localhost:$Port

"@ -ForegroundColor Green
    }
    else {
        Write-Host "Failed to start service. Check logs at: $LogPath\winsentry-service.log" -ForegroundColor Red
    }
}

# Stop the service
function Stop-WinSentryService {
    $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if (-not $service) {
        Write-Host "Service $ServiceName is not installed." -ForegroundColor Red
        return
    }
    
    if ($service.Status -eq 'Stopped') {
        Write-Host "Service $ServiceName is already stopped." -ForegroundColor Yellow
        return
    }
    
    Write-Host "Stopping $ServiceName service..." -ForegroundColor Cyan
    sc.exe stop $ServiceName
    Write-Host "$ServiceName service stopped." -ForegroundColor Green
}

# Restart the service
function Restart-WinSentryService {
    Write-Host "Restarting $ServiceName service..." -ForegroundColor Cyan
    Stop-WinSentryService
    Start-Sleep -Seconds 2
    Start-WinSentryService
}

# Get service status
function Get-WinSentryServiceStatus {
    $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if (-not $service) {
        Write-Host "Service $ServiceName is not installed." -ForegroundColor Red
        return
    }
    
    $statusColor = switch ($service.Status) {
        'Running' { 'Green' }
        'Stopped' { 'Red' }
        'Paused' { 'Yellow' }
        default { 'Gray' }
    }
    
    # Also get detailed info from sc.exe
    $scQuery = sc.exe query $ServiceName
    
    Write-Host @"

$ServiceName Service Status
============================
Name:        $($service.Name)
Display:     $($service.DisplayName)
Status:      $($service.Status)
StartType:   $($service.StartType)

"@ -ForegroundColor $statusColor
    
    Write-Host "sc.exe query output:" -ForegroundColor Gray
    Write-Host $scQuery
    
    if ($service.Status -eq 'Running') {
        Write-Host "`nWeb Interface: http://localhost:$Port" -ForegroundColor Cyan
    }
}

# Main execution
switch ($Action) {
    "install"   { Install-WinSentryService }
    "uninstall" { Uninstall-WinSentryService }
    "start"     { Start-WinSentryService }
    "stop"      { Stop-WinSentryService }
    "restart"   { Restart-WinSentryService }
    "status"    { Get-WinSentryServiceStatus }
}
