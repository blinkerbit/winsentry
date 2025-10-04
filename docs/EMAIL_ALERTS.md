# WinSentry Email Alert System

## 📧 Comprehensive Email Alert Functionality

WinSentry now includes a complete email alert system with customizable templates, SMTP configuration, and intelligent failure handling.

## 🚀 Key Features

### ✅ **SMTP Configuration**
- **Flexible SMTP settings** for any email provider
- **TLS/SSL support** for secure email transmission
- **Connection testing** to verify SMTP settings
- **Secure password storage** with masked display

### ✅ **Customizable Email Templates**
- **Multiple templates** for different alert types
- **Variable substitution** with dynamic content
- **Template preview** with sample data
- **Easy template management** (add, edit, delete)

### ✅ **Port-Specific Email Configuration**
- **Individual email settings** per monitored port
- **Custom recipient lists** for each port
- **Template selection** per port
- **Configurable failure thresholds**

### ✅ **Intelligent Failure Handling**
- **PowerShell script execution** after N failures
- **Email alerts** after M failures
- **Spam prevention** with email cooldown periods
- **Automatic reset** when ports come back online

## 🔧 Configuration Workflow

### 1. **SMTP Server Setup**
```
SMTP Server: smtp.gmail.com
Port: 587
Username: your-email@gmail.com
Password: your-app-password
From Email: alerts@yourcompany.com
From Name: WinSentry Alert System
Use TLS: ✓
```

### 2. **Email Template Creation**
```html
Subject: WinSentry Alert - Port {port} is {status}

Body:
Dear Administrator,

Port {port} has been {status} for {failure_count} consecutive checks.

Details:
- Port: {port}
- Status: {status}
- Failure Count: {failure_count}
- Timestamp: {timestamp}
- Server: {server_name}

Please investigate immediately.

Best regards,
WinSentry Alert System
```

### 3. **Port Email Configuration**
```json
{
  "enabled": true,
  "recipients": ["admin@company.com", "support@company.com"],
  "template": "critical_alert",
  "powershell_script_failures": 3,
  "email_alert_failures": 5,
  "custom_data": {}
}
```

## 📊 Failure Handling Logic

### **Sequential Failure Processing:**
1. **Port goes offline** → Failure count increments
2. **After N failures** → PowerShell script executes
3. **After M failures** → Email alert sent
4. **Port comes online** → Reset all counters

### **Example Configuration:**
- **PowerShell Script**: Execute after 3 failures
- **Email Alert**: Send after 5 failures
- **Email Cooldown**: 5 minutes between alerts
- **Auto-reset**: When port comes back online

## 🎯 Template Variables

### **Available Variables:**
- `{port}` - Port number
- `{status}` - ONLINE/OFFLINE
- `{failure_count}` - Number of consecutive failures
- `{timestamp}` - Current date/time
- `{server_name}` - Server hostname
- `{message}` - Custom message

### **Template Examples:**

**Critical Alert Template:**
```
Subject: 🚨 CRITICAL: Port {port} is {status}

Port {port} has been {status} for {failure_count} consecutive checks.
Server: {server_name}
Time: {timestamp}

This requires immediate attention!
```

**Informational Template:**
```
Subject: WinSentry Alert - Port {port} Status

Port {port} is currently {status}.
Failure count: {failure_count}
Timestamp: {timestamp}

Please check the system when convenient.
```

## 🔧 API Endpoints

### **SMTP Configuration**
```http
GET /api/email/config          # Get SMTP settings
POST /api/email/config         # Update SMTP settings
```

### **Email Templates**
```http
GET /api/email/templates       # Get all templates
POST /api/email/templates      # Add/update template
DELETE /api/email/templates     # Delete template
```

### **Port Email Configuration**
```http
GET /api/email/port-config?port=8080    # Get port email settings
POST /api/email/port-config             # Save port email settings
DELETE /api/email/port-config            # Delete port email settings
```

### **Email Testing**
```http
POST /api/email/test           # Test SMTP connection or send test email
```

## 🎨 Web Interface

### **Email Configuration Page** (`/email-config`)
- **SMTP Configuration Tab**: Server settings and connection testing
- **Email Templates Tab**: Template management with preview
- **Port Email Settings Tab**: Per-port email configuration
- **Test Email Tab**: Send test emails to verify setup

### **Main Dashboard Integration**
- **Email Config Link**: Direct access to email configuration
- **Port Monitoring**: Shows email alert status
- **Real-time Updates**: Email settings reflected immediately

## 🔒 Security Features

### **Password Protection**
- **Masked passwords** in web interface
- **Secure storage** in configuration files
- **No password logging** in application logs

### **Email Validation**
- **Recipient validation** before sending
- **Template validation** with required variables
- **SMTP connection testing** before saving

## 📈 Monitoring & Logging

### **Email Activity Logging**
- **All email sends** logged with timestamps
- **Failure tracking** for email delivery
- **Template usage** statistics
- **SMTP connection** status monitoring

### **Database Integration**
- **Email configurations** stored in SQLite
- **Historical email logs** for analysis
- **Failure pattern** tracking
- **Performance metrics** collection

## 🚀 Getting Started

### **1. Configure SMTP Server**
1. Go to `/email-config`
2. Enter SMTP server details
3. Test connection
4. Save configuration

### **2. Create Email Templates**
1. Navigate to Email Templates tab
2. Click "Add Template"
3. Define subject and body with variables
4. Preview template
5. Save template

### **3. Configure Port Email Alerts**
1. Go to Port Email Settings tab
2. Select port to configure
3. Set recipients and template
4. Configure failure thresholds
5. Enable email alerts

### **4. Test Email System**
1. Go to Test Email tab
2. Enter test recipients
3. Send test email
4. Verify delivery

## 📋 Configuration Files

### **SMTP Configuration** (`smtp_config.json`)
```json
{
  "smtp_server": "smtp.gmail.com",
  "smtp_port": 587,
  "smtp_username": "your-email@gmail.com",
  "smtp_password": "your-app-password",
  "use_tls": true,
  "from_email": "alerts@yourcompany.com",
  "from_name": "WinSentry Alert System"
}
```

### **Email Templates** (`email_templates.json`)
```json
{
  "default": {
    "subject": "WinSentry Alert - Port {port} is {status}",
    "body": "Port {port} is {status}..."
  },
  "critical": {
    "subject": "🚨 CRITICAL: Port {port} is {status}",
    "body": "URGENT: Port {port} requires immediate attention..."
  }
}
```

### **Port Email Config** (`port_email_config_{port}.json`)
```json
{
  "enabled": true,
  "recipients": ["admin@company.com"],
  "template": "critical",
  "powershell_script_failures": 3,
  "email_alert_failures": 5,
  "custom_data": {}
}
```

## 🎯 Use Cases

### **Critical Infrastructure Monitoring**
- **Database ports** (3306, 5432) → Critical alerts
- **Web server ports** (80, 443) → High priority
- **Application ports** (8080, 3000) → Medium priority

### **Multi-Environment Setup**
- **Development** → Internal team alerts
- **Staging** → QA team notifications
- **Production** → On-call engineer alerts

### **Escalation Workflows**
- **Level 1**: PowerShell script recovery
- **Level 2**: Email alert to team
- **Level 3**: Escalation to management

The email alert system provides enterprise-grade notification capabilities with full customization and intelligent failure handling!
