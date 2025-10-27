// WinSentry Frontend JavaScript
const API_BASE = '/api';

// Initialize application
document.addEventListener('DOMContentLoaded', () => {
    setupTabs();
    
    const savedTab = localStorage.getItem('activeTab') || 'dashboard';
    const tabButton = document.querySelector(`.tab-btn[data-tab="${savedTab}"]`);
    if (tabButton) {
        tabButton.click();
    } else {
        document.querySelector('.tab-btn[data-tab="dashboard"]').click();
    }

    checkHealth();

    const portForm = document.getElementById('portForm');
    portForm.addEventListener('submit', handlePortFormSubmit);

    const processForm = document.getElementById('processForm');
    processForm.addEventListener('submit', handleProcessFormSubmit);

    const alertForm = document.getElementById('alertForm');
    alertForm.addEventListener('submit', addAlertRule);
});

function handlePortFormSubmit(event) {
    event.preventDefault();
    const form = document.getElementById('portForm');
    const editingId = form.dataset.editingId;

    if (editingId) {
        updatePortMonitor(parseInt(editingId, 10));
    } else {
        addPortMonitor(event);
    }
}

function handleProcessFormSubmit(event) {
    event.preventDefault();
    const form = event.target;
    const editingId = form.dataset.editingId;

    if (editingId) {
        updateProcessMonitor(parseInt(editingId, 10));
    } else {
        addProcessMonitor();
    }
}

// Tab navigation
function setupTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');
    
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.dataset.tab;
            localStorage.setItem('activeTab', tabId);
            
            // Remove active class from all tabs
            tabBtns.forEach(b => b.classList.remove('active'));
            tabPanes.forEach(p => p.classList.remove('active'));
            
            // Add active class to clicked tab
            btn.classList.add('active');
            document.getElementById(tabId).classList.add('active');
            
            // Load data for the tab
            loadTabData(tabId);
        });
    });
}

function loadTabData(tabId) {
    switch(tabId) {
        case 'dashboard':
            loadDashboard();
            break;
        case 'ports':
            loadPortMonitors();
            break;
        case 'processes':
            loadProcessMonitors();
            break;
        case 'services':
            loadServiceMonitors();
            break;
        case 'supervise':
            loadSupervisedProcesses();
            break;
        case 'system':
            loadSystemMonitors();
            loadSystemStats();
            break;
        case 'alerts':
            loadAlerts();
            break;
        case 'settings':
            loadRecipients();
            loadSMTPServers();
            break;
        case 'logs':
            loadLogs();
            break;
    }
}

// Health check
async function checkHealth() {
    try {
        const response = await fetch(`${API_BASE}/health`);
        if (response.ok) {
            const statusDot = document.querySelector('.status-dot');
            statusDot.style.backgroundColor = '#5cb85c';
        }
    } catch (error) {
        const statusDot = document.querySelector('.status-dot');
        statusDot.style.backgroundColor = '#d9534f';
    }
}

// Dashboard
async function loadDashboard() {
    try {
        // Load system stats
        const statsResponse = await fetch(`${API_BASE}/system/stats`);
        const stats = await statsResponse.json();
        
        document.getElementById('cpuGauge').textContent = `${stats.cpu_percent.toFixed(1)}%`;
        document.getElementById('memoryGauge').textContent = `${stats.memory.percent.toFixed(1)}%`;
        
        // Load monitor counts
        const portsResponse = await fetch(`${API_BASE}/ports`);
        const ports = await portsResponse.json();
        document.getElementById('activePortMonitors').textContent = ports.length;
        
        const processesResponse = await fetch(`${API_BASE}/processes`);
        const processes = await processesResponse.json();
        document.getElementById('activeProcessMonitors').textContent = processes.length;
        
    } catch (error) {
        console.error('Error loading dashboard:', error);
        showNotification('Error loading dashboard', 'error');
    }
}

function closeAllModals() {
    document.body.classList.remove('modal-open');
    document.querySelectorAll('.modal').forEach(modal => {
        modal.classList.remove('show');
    });
}

// --- Port Monitoring ---

function openPortModal(port = null) {
    const modal = document.getElementById('portMonitorModal');
    const form = document.getElementById('portForm');
    const title = document.getElementById('portModalTitle');
    const submitButton = document.getElementById('portFormSubmit');

    form.reset();
    form.removeAttribute('data-editing-id');
    togglePortScriptFields('stopped');
    togglePortScriptFields('running');
    togglePortScriptSections();

    if (port) {
        title.textContent = 'Edit Port Monitor';
        submitButton.textContent = 'Update Monitor';
        form.dataset.editingId = port.id;
        
        document.getElementById('portNumber').value = port.port;
        document.getElementById('portDescription').value = port.description;
        document.getElementById('portInterval').value = port.check_interval;
        document.getElementById('portDurationThreshold').value = port.duration_threshold;
        document.getElementById('portMaxExecutions').value = port.max_executions;
        document.getElementById('portRetryMultiplier').value = port.retry_interval_multiplier;
        document.getElementById('portTriggerStatus').value = port.trigger_on_status;

        // Populate stopped script fields
        document.getElementById('portScriptTypeStopped').value = port.script_type_stopped || 'inline';
        document.getElementById('portScriptContentStopped').value = port.script_content_stopped || '';
        document.getElementById('portScriptPathStopped').value = port.script_path_stopped || '';

        // Populate running script fields
        document.getElementById('portScriptTypeRunning').value = port.script_type_running || 'inline';
        document.getElementById('portScriptContentRunning').value = port.script_content_running || '';
        document.getElementById('portScriptPathRunning').value = port.script_path_running || '';

        togglePortScriptFields('stopped');
        togglePortScriptFields('running');
        togglePortScriptSections();
    } else {
        title.textContent = 'Add Port Monitor';
        submitButton.textContent = 'Add Port Monitor';
    }

    modal.setAttribute('aria-hidden', 'false');
    modal.classList.add('show');
    document.body.classList.add('modal-open');
}

function closePortModal() {
    const modal = document.getElementById('portMonitorModal');
    modal.setAttribute('aria-hidden', 'true');
    modal.classList.remove('show');
    document.body.classList.remove('modal-open');
}

async function loadPortMonitors() {
    try {
        const response = await fetch(`${API_BASE}/ports`);
        const ports = await response.json();
        
        const listEl = document.getElementById('portsList');
        if (ports.length === 0) {
            listEl.innerHTML = '<div class="empty-state">No port monitors configured</div>';
            return;
        }
        
        // Fetch status for each port
        const portsWithStatus = await Promise.all(
            ports.map(async (port) => {
                try {
                    const statusResponse = await fetch(`${API_BASE}/ports/${port.id}/status`);
                    const status = await statusResponse.json();
                    return { ...port, status };
                } catch (error) {
                    return { ...port, status: null };
                }
            })
        );
        
        listEl.innerHTML = portsWithStatus.map(createPortCard).join('');
        
    } catch (error) {
        console.error('Error loading port monitors:', error);
        showNotification('Error loading port monitors', 'error');
    }
}

function createPortCard(port) {
    const status = port.status?.status || 'unknown';
    const statusClass = `status-${status}`;

    const statusBadge = port.status 
        ? `<span class="badge ${port.status.status === 'running' ? 'badge-success' : 'badge-danger'}">${port.status.status.toUpperCase()}</span>`
        : '<span class="badge badge-info">UNKNOWN</span>';
    
    const lastChecked = port.status && port.status.timestamp
        ? `<small class="timestamp">🕐 Last checked: ${new Date(port.status.timestamp).toLocaleString()}</small>`
        : '<small class="timestamp">🕐 Not checked yet</small>';
    
    const lastStatusChange = port.status && port.status.last_status_change
        ? `<small class="status-change-time">🔄 Last status change: ${new Date(port.status.last_status_change).toLocaleString()}</small>`
        : '<small class="status-change-time">🔄 No status changes yet</small>';
    
    const processInfo = port.status && port.status.process_name
        ? `<small>📊 Process: <strong>${port.status.process_name}</strong> (PID: ${port.status.pid})</small>`
        : port.status && port.status.status === 'stopped' 
        ? '<small>⚠️ No process listening on this port</small>'
        : '';
    
    const scriptInfo = port.trigger_on_status === 'both'
        ? `<small>📝 Scripts for Running & Stopped</small>`
        : `<small>📝 Script for ${port.trigger_on_status.charAt(0).toUpperCase() + port.trigger_on_status.slice(1)}</small>`;

    const stoppedDisabled = port.trigger_on_status === 'running';
    const runningDisabled = port.trigger_on_status === 'stopped';

    return `
        <div class="monitor-card ${statusClass}" data-port-id="${port.id}">
            <button class="monitor-summary" onclick="togglePortDetails(${port.id})">
                <div class="summary-left">
                    <strong>Port ${port.port_number} ${statusBadge}</strong>
                    <div class="summary-meta">
                        <span>Interval: ${port.monitoring_interval}s</span>
                        <span>Duration Threshold: ${port.duration_threshold}</span>
                        ${scriptInfo}
                    </div>
                    <div class="summary-meta">
                        ${lastChecked}
                        ${lastStatusChange}
                    </div>
                </div>
                <div class="summary-right">
                    ${processInfo}
                    <span class="summary-caret">⌄</span>
                </div>
            </button>
            <div class="monitor-details" id="port-details-${port.id}">
                <div class="details-grid">
                    <div class="details-block">
                        <h4>Script Triggers</h4>
                        <div class="script-actions">
                            <button class="script-trigger stopped" ${stoppedDisabled ? 'disabled' : ''} onclick="executePortScript(${port.id}, 'stopped')">
                                <span>▶️ Trigger Stopped Script</span>
                                ${stoppedDisabled ? '<small>Disabled for this monitor</small>' : ''}
                            </button>
                            <button class="script-trigger running" ${runningDisabled ? 'disabled' : ''} onclick="executePortScript(${port.id}, 'running')">
                                <span>▶️ Trigger Running Script</span>
                                ${runningDisabled ? '<small>Disabled for this monitor</small>' : ''}
                            </button>
                        </div>
                    </div>
                    <div class="details-block details-info">
                        <h4>Configuration</h4>
                        <small>Max executions: ${port.max_script_executions}</small>
                        <small>Retry multiplier: ${port.retry_interval_multiplier}</small>
                        ${port.script_path_stopped ? `<small>Stopped script: <code>${port.script_path_stopped}</code></small>` : ''}
                        ${port.script_path_running ? `<small>Running script: <code>${port.script_path_running}</code></small>` : ''}
                    </div>
                </div>
                <div class="details-actions">
                    <button class="btn-info" onclick="checkPortStatus(${port.id})">🔍 Check Now</button>
                    <button class="btn-toggle ${port.enabled ? 'enabled' : ''}" onclick="togglePortAutoExecute(${port.id}, ${!port.enabled})">${port.enabled ? '🟢 Auto ON' : '⭕ Auto OFF'}</button>
                    <button class="btn-warning" onclick="startPortEdit(${port.id})">✏️ Edit</button>
                    <button class="btn-danger" onclick="deletePortMonitor(${port.id})">🗑️ Delete</button>
                    <button class="btn-kill" onclick="killPortProcess(${port.id}, false)">⏹️ Kill</button>
                    <button class="btn-kill" onclick="killPortProcess(${port.id}, true)">🛑 Force Kill</button>
                </div>
            </div>
        </div>
    `;
}

function togglePortDetails(portId) {
    const card = document.querySelector(`.monitor-card[data-port-id="${portId}"]`);
    const details = document.getElementById(`port-details-${portId}`);
    const isOpen = card.classList.toggle('open');
    details.classList.toggle('open', isOpen);
}

async function startPortEdit(portId) {
    try {
        const response = await fetch(`${API_BASE}/ports/${portId}`);
        if (!response.ok) {
            throw new Error('Failed to fetch port details for editing.');
        }
        const port = await response.json();
        openPortModal(port);
    } catch (error) {
        showNotification(`Error: ${error.message}`, 'error');
        console.error('Error starting port edit:', error);
    }
}

async function addPortMonitor(event) {
    event.preventDefault();
    
    const portNumber = parseInt(document.getElementById('portNumber').value);
    const monitoringInterval = parseInt(document.getElementById('portInterval').value);
    const triggerStatus = document.getElementById('portTriggerStatus').value;

    // Script details for STOPPED status
    const scriptTypeStopped = document.getElementById('portScriptTypeStopped').value;
    const scriptContentStopped = document.getElementById('portScriptContentStopped').value;
    const scriptPathStopped = document.getElementById('portScriptPathStopped').value;

    // Script details for RUNNING status
    const scriptTypeRunning = document.getElementById('portScriptTypeRunning').value;
    const scriptContentRunning = document.getElementById('portScriptContentRunning').value;
    const scriptPathRunning = document.getElementById('portScriptPathRunning').value;

    const durationThreshold = parseInt(document.getElementById('portDurationThreshold').value);
    const maxExecutions = parseInt(document.getElementById('portMaxExecutions').value);
    const retryMultiplier = parseInt(document.getElementById('portRetryMultiplier').value);
    
    const data = {
        port_number: portNumber,
        monitoring_interval: monitoringInterval,
        trigger_on_status: triggerStatus,
        script_type_stopped: scriptTypeStopped,
        script_content_stopped: scriptTypeStopped === 'inline' ? scriptContentStopped : null,
        script_path_stopped: scriptTypeStopped === 'file' ? scriptPathStopped : null,
        script_type_running: scriptTypeRunning,
        script_content_running: scriptTypeRunning === 'inline' ? scriptContentRunning : null,
        script_path_running: scriptTypeRunning === 'file' ? scriptPathRunning : null,
        duration_threshold: durationThreshold,
        max_script_executions: maxExecutions,
        retry_interval_multiplier: retryMultiplier,
        enabled: true
    };
    
    try {
        const response = await fetch(`${API_BASE}/ports`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            showNotification('Port monitor added successfully');
            event.target.reset();
            closePortModal();
            loadPortMonitors();
        } else {
            throw new Error('Failed to add port monitor');
        }
    } catch (error) {
        console.error('Error adding port monitor:', error);
        showNotification('Error adding port monitor', 'error');
    }
}

async function updatePortMonitor(portId) {
    const portNumber = parseInt(document.getElementById('portNumber').value);
    const monitoringInterval = parseInt(document.getElementById('portInterval').value);
    const triggerStatus = document.getElementById('portTriggerStatus').value;

    // Script details for STOPPED status
    const scriptTypeStopped = document.getElementById('portScriptTypeStopped').value;
    const scriptContentStopped = document.getElementById('portScriptContentStopped').value;
    const scriptPathStopped = document.getElementById('portScriptPathStopped').value;

    // Script details for RUNNING status
    const scriptTypeRunning = document.getElementById('portScriptTypeRunning').value;
    const scriptContentRunning = document.getElementById('portScriptContentRunning').value;
    const scriptPathRunning = document.getElementById('portScriptPathRunning').value;

    const durationThreshold = parseInt(document.getElementById('portDurationThreshold').value);
    const maxExecutions = parseInt(document.getElementById('portMaxExecutions').value);
    const retryMultiplier = parseInt(document.getElementById('portRetryMultiplier').value);
    
    const data = {
        port_number: portNumber,
        monitoring_interval: monitoringInterval,
        trigger_on_status: triggerStatus,
        script_type_stopped: scriptTypeStopped,
        script_content_stopped: scriptTypeStopped === 'inline' ? scriptContentStopped : null,
        script_path_stopped: scriptTypeStopped === 'file' ? scriptPathStopped : null,
        script_type_running: scriptTypeRunning,
        script_content_running: scriptTypeRunning === 'inline' ? scriptContentRunning : null,
        script_path_running: scriptTypeRunning === 'file' ? scriptPathRunning : null,
        duration_threshold: durationThreshold,
        max_script_executions: maxExecutions,
        retry_interval_multiplier: retryMultiplier,
        enabled: true
    };
    
    try {
        const response = await fetch(`${API_BASE}/ports/${portId}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            showNotification('Port monitor updated successfully');
            closePortModal();
            loadPortMonitors();
        } else {
            throw new Error('Failed to update port monitor');
        }
    } catch (error) {
        console.error('Error updating port monitor:', error);
        showNotification('Error updating port monitor', 'error');
    }
}

async function deletePortMonitor(id) {
    if (!confirm('Delete this port monitor?')) return;
    
    try {
        const response = await fetch(`${API_BASE}/ports/${id}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showNotification('Port monitor deleted');
            loadPortMonitors();
        }
    } catch (error) {
        console.error('Error deleting port monitor:', error);
        showNotification('Error deleting port monitor', 'error');
    }
}

// --- Process Monitoring ---

function openProcessModal(process = null) {
    const modal = document.getElementById('processMonitorModal');
    const form = document.getElementById('processForm');
    const title = document.getElementById('processModalTitle');
    const submitButton = document.getElementById('processFormSubmit');

    form.reset();
    form.removeAttribute('data-editing-id');
    toggleProcessScriptFields('stopped');
    toggleProcessScriptFields('running');
    toggleProcessScriptSections();

    if (process) {
        title.textContent = 'Edit Process Monitor';
        submitButton.textContent = 'Update Monitor';
        form.dataset.editingId = process.id;
        
        document.getElementById('processId').value = process.pid;
        document.getElementById('processName').value = process.name || '';
        document.getElementById('processInterval').value = process.check_interval;
        document.getElementById('processDurationThreshold').value = process.duration_threshold;
        document.getElementById('processMaxExecutions').value = process.max_executions;
        document.getElementById('processRetryMultiplier').value = process.retry_interval_multiplier;
        document.getElementById('processTriggerStatus').value = process.trigger_on_status;

        document.getElementById('processScriptTypeStopped').value = process.script_type_stopped || 'inline';
        document.getElementById('processScriptContentStopped').value = process.script_content_stopped || '';
        document.getElementById('processScriptPathStopped').value = process.script_path_stopped || '';

        document.getElementById('processScriptTypeRunning').value = process.script_type_running || 'inline';
        document.getElementById('processScriptContentRunning').value = process.script_content_running || '';
        document.getElementById('processScriptPathRunning').value = process.script_path_running || '';

        toggleProcessScriptFields('stopped');
        toggleProcessScriptFields('running');
        toggleProcessScriptSections();
    } else {
        title.textContent = 'Add Process Monitor';
        submitButton.textContent = 'Add Process Monitor';
    }

    modal.setAttribute('aria-hidden', 'false');
    modal.classList.add('show');
    document.body.classList.add('modal-open');
}

function closeProcessModal() {
    const modal = document.getElementById('processMonitorModal');
    modal.setAttribute('aria-hidden', 'true');
    modal.classList.remove('show');
    document.body.classList.remove('modal-open');
}

async function loadProcessMonitors() {
    try {
        const response = await fetch('/api/processes');
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        
        const processes = await response.json();
        const processesList = document.getElementById('processesList');
        processesList.innerHTML = '';

        if (processes.length === 0) {
            processesList.innerHTML = '<div class="empty-state">No process monitors configured.</div>';
            return;
        }
        
        for (const process of processes) {
            const card = await createProcessCard(process);
            processesList.appendChild(card);
        }

    } catch (error) {
        console.error('Error loading process data:', error);
        document.getElementById('processesList').innerHTML = '<div class="error-state">Error loading process data.</div>';
    }
}

async function createProcessCard(process) {
    const card = document.createElement('div');
    card.className = 'monitor-card';
    card.id = `process-card-${process.id}`;

    let statusData;
    try {
        const statusResponse = await fetch(`/api/processes/${process.id}/status`);
        if (statusResponse.ok) {
            statusData = await statusResponse.json();
        }
    } catch (e) {
        console.error(`Could not fetch status for process ${process.pid}`, e);
    }
    
    const statusClass = statusData?.status === 'running' ? 'running' : 'stopped';
    const statusText = statusData?.status === 'running' ? 'Running' : 'Stopped';

    const scriptTriggerStopped = (process.trigger_on_status === 'stopped' || process.trigger_on_status === 'both')
        ? `<button class="script-trigger stopped" onclick="executeProcessScript(${process.id}, 'stopped')">Trigger 'Stopped' Script</button>` : '';
    const scriptTriggerRunning = (process.trigger_on_status === 'running' || process.trigger_on_status === 'both')
        ? `<button class="script-trigger running" onclick="executeProcessScript(${process.id}, 'running')">Trigger 'Running' Script</button>` : '';

    card.innerHTML = `
        <div class="monitor-summary" onclick="toggleProcessDetails(${process.id})">
            <div class="summary-left">
                <span class="badge-state ${statusClass}"><span class="dot"></span>${statusText}</span>
                <span class="summary-meta">PID: <strong>${process.pid}</strong></span>
                <span class="summary-meta">${process.name || 'N/A'}</span>
            </div>
            <div class="summary-right">
                <span class="summary-meta">CPU: ${statusData?.cpu_percent?.toFixed(1) ?? 'N/A'}%</span>
                <span class="summary-meta">RAM: ${statusData?.memory_mb?.toFixed(1) ?? 'N/A'} MB</span>
                <span id="process-caret-${process.id}" class="summary-caret">▼</span>
            </div>
        </div>
        <div class="monitor-details" id="process-details-${process.id}" style="display: none;">
            <div class="details-grid">
                <div class="details-block">
                    <h4>Configuration</h4>
                    <div class="details-info"><strong>Interval:</strong> ${process.check_interval}s</div>
                    <div class="details-info"><strong>Threshold:</strong> ${process.duration_threshold} checks</div>
                    <div class="details-info"><strong>Max Executes:</strong> ${process.max_executions}</div>
                    <div class="details-info"><strong>Retry Multiplier:</strong> ${process.retry_interval_multiplier}x</div>
                </div>
                <div class="details-block">
                    <h4>Script Actions</h4>
                    <div class="script-actions">
                        ${scriptTriggerStopped}
                        ${scriptTriggerRunning}
                    </div>
                </div>
            </div>
            <div class="details-actions">
                <span>Last checked: ${statusData?.timestamp ? new Date(statusData.timestamp).toLocaleString() : 'Never'}</span>
            </div>
        </div>
        <div class="monitor-actions">
            <button class="btn-ghost" onclick="startProcessEdit(${process.id})">Edit</button>
            <button class="btn-ghost" onclick="deleteProcessMonitor(${process.id})">Delete</button>
        </div>
    `;

    return card;
}

function toggleProcessDetails(processId) {
    const details = document.getElementById(`process-details-${processId}`);
    const caret = document.getElementById(`process-caret-${processId}`);
    const card = details.closest('.monitor-card');
    
    const isVisible = details.style.display === 'grid';
    details.style.display = isVisible ? 'none' : 'grid';
    caret.style.transform = isVisible ? 'rotate(0deg)' : 'rotate(180deg)';
    card.classList.toggle('is-open', !isVisible);
}

async function startProcessEdit(processId) {
    try {
        const response = await fetch(`/api/processes/${processId}`);
        if (!response.ok) {
            throw new Error('Failed to fetch process details for editing.');
        }
        const process = await response.json();
        openProcessModal(process);
    } catch (error) {
        showNotification(`Error: ${error.message}`, 'error');
        console.error('Error starting process edit:', error);
    }
}

async function addProcessMonitor() {
    const processData = {
        process_id: parseInt(document.getElementById('processId').value),
        process_name: document.getElementById('processName').value || null,
        monitoring_interval: parseInt(document.getElementById('processInterval').value),
        duration_threshold: parseInt(document.getElementById('processDurationThreshold').value),
        max_script_executions: parseInt(document.getElementById('processMaxExecutions').value),
        retry_interval_multiplier: parseInt(document.getElementById('processRetryMultiplier').value),
        trigger_on_status: document.getElementById('processTriggerStatus').value,
        enabled: true,
        
        script_type_stopped: document.getElementById('processScriptTypeStopped').value,
        script_content_stopped: document.getElementById('processScriptContentStopped').value,
        script_path_stopped: document.getElementById('processScriptPathStopped').value,
        
        script_type_running: document.getElementById('processScriptTypeRunning').value,
        script_content_running: document.getElementById('processScriptContentRunning').value,
        script_path_running: document.getElementById('processScriptPathRunning').value
    };

    try {
        const response = await fetch('/api/processes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(processData)
        });

        if (response.ok) {
            showNotification('Process monitor added successfully!', 'success');
            closeProcessModal();
            loadProcessMonitors();
        } else {
            const errorData = await response.json();
            showNotification(`Error: ${errorData.detail}`, 'error');
        }
    } catch (error) {
        console.error('Error adding process monitor:', error);
        showNotification('An error occurred while adding the process monitor.', 'error');
    }
}

async function updateProcessMonitor(processId) {
    const processData = {
        process_id: parseInt(document.getElementById('processId').value),
        process_name: document.getElementById('processName').value || null,
        monitoring_interval: parseInt(document.getElementById('processInterval').value),
        duration_threshold: parseInt(document.getElementById('processDurationThreshold').value),
        max_script_executions: parseInt(document.getElementById('processMaxExecutions').value),
        retry_interval_multiplier: parseInt(document.getElementById('processRetryMultiplier').value),
        trigger_on_status: document.getElementById('processTriggerStatus').value,
        enabled: true,

        script_type_stopped: document.getElementById('processScriptTypeStopped').value,
        script_content_stopped: document.getElementById('processScriptContentStopped').value,
        script_path_stopped: document.getElementById('processScriptPathStopped').value,
        
        script_type_running: document.getElementById('processScriptTypeRunning').value,
        script_content_running: document.getElementById('processScriptContentRunning').value,
        script_path_running: document.getElementById('processScriptPathRunning').value
    };

    try {
        const response = await fetch(`/api/processes/${processId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(processData)
        });

        if (response.ok) {
            showNotification('Process monitor updated successfully!', 'success');
            closeProcessModal();
            loadProcessMonitors();
        } else {
            const errorData = await response.json();
            showNotification(`Error: ${errorData.detail}`, 'error');
        }
    } catch (error) {
        console.error('Error updating process monitor:', error);
        showNotification('An error occurred while updating the process monitor.', 'error');
    }
}

async function deleteProcessMonitor(processId) {
    if (confirm('Are you sure you want to delete this process monitor?')) {
        try {
            const response = await fetch(`/api/processes/${processId}`, { method: 'DELETE' });
            if (response.ok) {
                showNotification('Process monitor deleted successfully!', 'success');
                loadProcessMonitors();
            } else {
                const errorData = await response.json();
                showNotification(`Error: ${errorData.detail}`, 'error');
            }
        } catch (error) {
            console.error('Error deleting process monitor:', error);
            showNotification('An error occurred while deleting the process monitor.', 'error');
        }
    }
}

async function executeProcessScript(processId, status) {
    try {
        const response = await fetch(`/api/processes/${processId}/execute-script?status=${status}`, {
            method: 'POST'
        });
        const result = await response.json();
        if (response.ok) {
            showNotification(`Script execution for process ${processId} (${status}) started.`, 'success');
        } else {
            showNotification(`Error: ${result.detail}`, 'error');
        }
    } catch (error) {
        console.error('Error executing script:', error);
        showNotification('An error occurred while executing the script.', 'error');
    }
}

function toggleProcessScriptFields(status) {
    const scriptType = document.getElementById(`processScriptType${status.charAt(0).toUpperCase() + status.slice(1)}`).value;
    const contentGroup = document.getElementById(`processScriptContentGroup${status.charAt(0).toUpperCase() + status.slice(1)}`);
    const pathGroup = document.getElementById(`processScriptPathGroup${status.charAt(0).toUpperCase() + status.slice(1)}`);

    if (scriptType === 'inline') {
        contentGroup.style.display = 'block';
        pathGroup.style.display = 'none';
    } else {
        contentGroup.style.display = 'none';
        pathGroup.style.display = 'block';
    }
}

function toggleProcessScriptSections() {
    const triggerStatus = document.getElementById('processTriggerStatus').value;
    const stoppedSection = document.getElementById('processScriptSectionStopped');
    const runningSection = document.getElementById('processScriptSectionRunning');

    stoppedSection.style.display = (triggerStatus === 'stopped' || triggerStatus === 'both') ? 'block' : 'none';
    runningSection.style.display = (triggerStatus === 'running' || triggerStatus === 'both') ? 'block' : 'none';
}


// --- Service Monitoring ---
async function loadServiceMonitors() {
    try {
        const response = await fetch(`${API_BASE}/services`);
        const services = await response.json();
        
        const listEl = document.getElementById('servicesList');
        if (services.length === 0) {
            listEl.innerHTML = '<div class="empty-state">No service monitors configured</div>';
            return;
        }
        
        // Fetch status for each service
        const servicesWithStatus = await Promise.all(
            services.map(async (svc) => {
                try {
                    const statusResponse = await fetch(`${API_BASE}/services/${svc.id}/status`);
                    const status = await statusResponse.json();
                    return { ...svc, status };
                } catch (error) {
                    return { ...svc, status: null };
                }
            })
        );
        
        listEl.innerHTML = servicesWithStatus.map(svc => {
            const status = svc.status?.status || 'unknown';
            const statusClass = `status-${status}`;
            
            let statusBadge = '<span class="badge badge-info">UNKNOWN</span>';
            if (svc.status) {
                if (svc.status.status === 'running') {
                    statusBadge = '<span class="badge badge-success">RUNNING</span>';
                } else if (svc.status.status === 'stopped') {
                    statusBadge = '<span class="badge badge-danger">STOPPED</span>';
                } else if (svc.status.status === 'not_found') {
                    statusBadge = '<span class="badge badge-warning">NOT FOUND</span>';
                } else {
                    statusBadge = `<span class="badge badge-info">${svc.status.status.toUpperCase()}</span>`;
                }
            }
            
            const lastChecked = svc.status && svc.status.timestamp
                ? `<small class="timestamp">🕐 Last checked: ${new Date(svc.status.timestamp).toLocaleString()}</small>`
                : '<small class="timestamp">🕐 Not checked yet</small>';
            
            const lastStatusChange = svc.status && svc.status.last_status_change
                ? `<small class="status-change-time">🔄 Last status change: ${new Date(svc.status.last_status_change).toLocaleString()}</small>`
                : '<small class="status-change-time">🔄 No status changes yet</small>';
            
            return `
            <div class="monitor-item ${statusClass}">
                <div class="monitor-info">
                    <strong>
                        ${svc.service_name}
                        ${statusBadge}
                    </strong>
                    ${lastChecked}
                    ${lastStatusChange}
                    ${svc.display_name ? `<small>📝 ${svc.display_name}</small>` : ''}
                    <small>⏱️ Interval: ${svc.monitoring_interval}s | 🔄 State Duration: ${svc.state_duration_threshold} intervals</small>
                </div>
                <div class="monitor-actions">
                    <button class="btn-info" onclick="checkServiceStatus(${svc.id})">🔍 Check Now</button>
                    <button class="btn-execute" onclick="executeServiceScript(${svc.id})">▶️ Execute Script</button>
                    <button class="btn-toggle ${svc.enabled ? 'enabled' : ''}" onclick="toggleServiceAutoExecute(${svc.id}, ${!svc.enabled})">${svc.enabled ? '🟢 Auto ON' : '⭕ Auto OFF'}</button>
                    <button class="btn-warning" onclick="editServiceMonitor(${svc.id})">✏️ Edit</button>
                    <button class="btn-danger" onclick="deleteServiceMonitor(${svc.id})">🗑️ Delete</button>
                </div>
            </div>
        `;
        }).join('');
        
    } catch (error) {
        console.error('Error loading service monitors:', error);
        showNotification('Error loading service monitors', 'error');
    }
}

async function checkServiceStatus(serviceId) {
    try {
        const response = await fetch(`${API_BASE}/services/${serviceId}/status`);
        const status = await response.json();
        
        const statusText = `Service Status: ${status.status.toUpperCase()}\n` +
            `Service: ${status.service_name}\n` +
            `Timestamp: ${new Date(status.timestamp).toLocaleString()}`;
        
        alert(statusText);
        loadServiceMonitors(); // Refresh the list
    } catch (error) {
        console.error('Error checking service status:', error);
        showNotification('Error checking service status', 'error');
    }
}

async function addServiceMonitor(event) {
    event.preventDefault();
    
    const serviceName = document.getElementById('serviceName').value;
    const displayName = document.getElementById('serviceDisplayName').value || null;
    const monitoringInterval = parseInt(document.getElementById('serviceInterval').value);
    const stateDurationThreshold = parseInt(document.getElementById('serviceStateDuration').value);
    
    const data = {
        service_name: serviceName,
        display_name: displayName,
        monitoring_interval: monitoringInterval,
        restart_config: null,
        state_duration_threshold: stateDurationThreshold,
        enabled: true
    };
    
    try {
        const response = await fetch(`${API_BASE}/services`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            showNotification('Service monitor added successfully');
            document.getElementById('serviceForm').reset();
            loadServiceMonitors();
        } else {
            throw new Error('Failed to add service monitor');
        }
    } catch (error) {
        console.error('Error adding service monitor:', error);
        showNotification('Error adding service monitor', 'error');
    }
}

async function editServiceMonitor(id) {
    try {
        const response = await fetch(`${API_BASE}/services`);
        const services = await response.json();
        const svc = services.find(s => s.id === id);
        
        if (!svc) {
            showNotification('Service not found', 'error');
            return;
        }
        
        // Populate form
        document.getElementById('serviceName').value = svc.service_name;
        document.getElementById('serviceDisplayName').value = svc.display_name || '';
        document.getElementById('serviceInterval').value = svc.monitoring_interval;
        document.getElementById('serviceStateDuration').value = svc.state_duration_threshold;
        
        document.querySelector('#services .config-section').scrollIntoView({ behavior: 'smooth' });
        
        const form = document.getElementById('serviceForm');
        form.onsubmit = async (e) => {
            e.preventDefault();
            await updateServiceMonitor(id);
        };
        
        const submitBtn = form.querySelector('button[type="submit"]');
        submitBtn.textContent = 'Update Service Monitor';
        submitBtn.classList.add('btn-warning');
        
        if (!document.getElementById('cancelServiceEdit')) {
            const cancelBtn = document.createElement('button');
            cancelBtn.type = 'button';
            cancelBtn.id = 'cancelServiceEdit';
            cancelBtn.textContent = 'Cancel';
            cancelBtn.className = 'btn-secondary';
            cancelBtn.onclick = cancelServiceEdit;
            submitBtn.parentNode.insertBefore(cancelBtn, submitBtn.nextSibling);
        }
        
        showNotification('Edit mode activated - modify and click Update');
        
    } catch (error) {
        console.error('Error loading service for edit:', error);
        showNotification('Error loading service data', 'error');
    }
}

async function updateServiceMonitor(id) {
    const serviceName = document.getElementById('serviceName').value;
    const displayName = document.getElementById('serviceDisplayName').value || null;
    const monitoringInterval = parseInt(document.getElementById('serviceInterval').value);
    const stateDurationThreshold = parseInt(document.getElementById('serviceStateDuration').value);
    
    const data = {
        service_name: serviceName,
        display_name: displayName,
        monitoring_interval: monitoringInterval,
        restart_config: null,
        state_duration_threshold: stateDurationThreshold,
        enabled: true
    };
    
    try {
        const response = await fetch(`${API_BASE}/services/${id}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            showNotification('Service monitor updated successfully');
            cancelServiceEdit();
            loadServiceMonitors();
        } else {
            throw new Error('Failed to update service monitor');
        }
    } catch (error) {
        console.error('Error updating service monitor:', error);
        showNotification('Error updating service monitor', 'error');
    }
}

function cancelServiceEdit() {
    const form = document.getElementById('serviceForm');
    form.reset();
    form.onsubmit = addServiceMonitor;
    
    const submitBtn = form.querySelector('button[type="submit"]');
    submitBtn.textContent = 'Add Service Monitor';
    submitBtn.classList.remove('btn-warning');
    
    const cancelBtn = document.getElementById('cancelServiceEdit');
    if (cancelBtn) {
        cancelBtn.remove();
    }
}

async function deleteServiceMonitor(id) {
    if (!confirm('Delete this service monitor?')) return;
    
    try {
        const response = await fetch(`${API_BASE}/services/${id}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showNotification('Service monitor deleted');
            loadServiceMonitors();
        }
    } catch (error) {
        console.error('Error deleting service monitor:', error);
        showNotification('Error deleting service monitor', 'error');
    }
}

// Supervised Processes
async function loadSupervisedProcesses() {
    try {
        const response = await fetch(`${API_BASE}/supervised`);
        const processes = await response.json();
        
        const list = document.getElementById('supervisedProcessesList');
        if (processes.length === 0) {
            list.innerHTML = '<p class="empty-state">No supervised processes configured</p>';
            return;
        }
        
        list.innerHTML = `
            <h3>Supervised Processes</h3>
            <table class="monitors-table">
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Command</th>
                        <th>Status</th>
                        <th>PID</th>
                        <th>Restarts</th>
                        <th>Last Started</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${processes.map(proc => `
                        <tr>
                            <td><strong>${proc.name}</strong></td>
                            <td><code>${proc.command}</code></td>
                            <td><span class="status-badge ${proc.current_pid ? 'status-running' : 'status-stopped'}">
                                ${proc.current_pid ? 'Running' : 'Stopped'}
                            </span></td>
                            <td>${proc.current_pid || '-'}</td>
                            <td>${proc.restart_count}</td>
                            <td>${proc.last_started_at ? new Date(proc.last_started_at).toLocaleString() : 'Never'}</td>
                            <td>
                                <button class="btn btn-sm btn-execute" onclick="stopSupervisedProcess(${proc.id})" ${!proc.current_pid ? 'disabled' : ''}>
                                    Stop
                                </button>
                                <button class="btn btn-sm btn-danger" onclick="deleteSupervisedProcess(${proc.id})">
                                    Delete
                                </button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (error) {
        console.error('Error loading supervised processes:', error);
        showNotification('Error loading supervised processes', 'error');
    }
}

// Set up supervised process form
document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('supervisedProcessForm');
    if (form) {
        form.addEventListener('submit', addSupervisedProcess);
    }
});

async function addSupervisedProcess(e) {
    e.preventDefault();
    
    const data = {
        name: document.getElementById('supervisedName').value,
        command: document.getElementById('supervisedCommand').value,
        working_directory: document.getElementById('supervisedWorkingDir').value || null,
        monitoring_interval: parseInt(document.getElementById('supervisedInterval').value),
        restart_delay: parseInt(document.getElementById('supervisedRestartDelay').value),
        max_restarts: parseInt(document.getElementById('supervisedMaxRestarts').value),
        enabled: true
    };
    
    try {
        const response = await fetch(`${API_BASE}/supervised`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            showNotification('Supervised process added successfully!', 'success');
            e.target.reset();
            loadSupervisedProcesses();
        } else {
            const error = await response.json();
            showNotification(`Error: ${error.detail}`, 'error');
        }
    } catch (error) {
        console.error('Error adding supervised process:', error);
        showNotification('Error adding supervised process', 'error');
    }
}

async function stopSupervisedProcess(procId) {
    if (!confirm('Are you sure you want to stop this supervised process?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/supervised/${procId}/stop`, {
            method: 'POST'
        });
        
        if (response.ok) {
            showNotification('Process stopped successfully', 'success');
            loadSupervisedProcesses();
        } else {
            showNotification('Error stopping process', 'error');
        }
    } catch (error) {
        console.error('Error stopping process:', error);
        showNotification('Error stopping process', 'error');
    }
}

async function deleteSupervisedProcess(procId) {
    if (!confirm('Are you sure you want to delete this supervised process?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/supervised/${procId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showNotification('Supervised process deleted successfully', 'success');
            loadSupervisedProcesses();
        } else {
            showNotification('Error deleting supervised process', 'error');
        }
    } catch (error) {
        console.error('Error deleting supervised process:', error);
        showNotification('Error deleting supervised process', 'error');
    }
}

function createSystemMonitorCard(monitor, stats) {
    const card = document.createElement('div');
    card.className = 'monitor-item system-monitor-item';

    let currentValue = 'N/A';
    if (stats) {
        switch (monitor.monitor_type) {
            case 'ram':
                currentValue = `${stats.memory.percent.toFixed(1)}%`;
                break;
            case 'cpu':
                currentValue = `${stats.cpu_percent.toFixed(1)}%`;
                break;
            case 'disk':
                if (monitor.drive_letter && stats.disk[monitor.drive_letter] && !stats.disk[monitor.drive_letter].error) {
                    currentValue = `${stats.disk[monitor.drive_letter].percent.toFixed(1)}%`;
                } else if (monitor.drive_letter) {
                    currentValue = `Error`;
                }
                break;
        }
    }

    card.innerHTML = `
        <div class="monitor-info">
            <div>
                <strong>${monitor.monitor_type.toUpperCase().replace('_', ' ')} ${monitor.drive_letter ? `(${monitor.drive_letter})` : ''}</strong>
                <small>Threshold: ${monitor.threshold_value}% | Interval: ${monitor.monitoring_interval}s</small>
            </div>
            <div class="current-value">
                <small>Current</small>
                <strong>${currentValue}</strong>
            </div>
        </div>
        <div class="monitor-actions">
            <button class="btn-ghost" onclick="deleteSystemMonitor(${monitor.id})">Delete</button>
        </div>
    `;
    return card;
}

// System Monitoring
async function loadSystemMonitors() {
    try {
        const statsResponse = await fetch(`${API_BASE}/system/stats`);
        if (!statsResponse.ok) throw new Error('Failed to load system stats');
        const stats = await statsResponse.json();

        const monitorsResponse = await fetch(`${API_BASE}/system`);
        if (!monitorsResponse.ok) throw new Error('Failed to load system monitors');
        const monitors = await monitorsResponse.json();

        const list = document.getElementById('systemMonitorsList');
        list.innerHTML = '';

        if (monitors.length === 0) {
            list.innerHTML = '<p>No system monitors configured.</p>';
        } else {
            monitors.forEach(monitor => {
                const card = createSystemMonitorCard(monitor, stats);
                list.appendChild(card);
            });
        }
        
        // Also load the stats overview when monitors are loaded
        loadSystemStats();

    } catch (error) {
        console.error('Error loading system monitors:', error);
        const list = document.getElementById('systemMonitorsList');
        if (list) {
            list.innerHTML = '<div class="error-state">Error loading system monitors.</div>';
        }
    }
}

async function addSystemMonitor(event) {
    event.preventDefault();
    
    const monitorType = document.getElementById('systemMonitorType').value;
    const thresholdValue = parseFloat(document.getElementById('systemThreshold').value);
    const monitoringInterval = parseInt(document.getElementById('systemMonitorInterval').value);
    const processRef = document.getElementById('systemProcessRef').value || null;
    const driveLetter = document.getElementById('systemDriveLetter').value || null;
    
    const data = {
        monitor_type: monitorType,
        threshold_value: thresholdValue,
        monitoring_interval: monitoringInterval,
        process_reference: processRef,
        drive_letter: driveLetter,
        enabled: true
    };
    
    try {
        const response = await fetch(`${API_BASE}/system`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            showNotification('System monitor added successfully');
            document.getElementById('systemForm').reset();
            loadSystemMonitors();
        } else {
            throw new Error('Failed to add system monitor');
        }
    } catch (error) {
        console.error('Error adding system monitor:', error);
        showNotification('Error adding system monitor', 'error');
    }
}

async function deleteSystemMonitor(id) {
    if (!confirm('Delete this system monitor?')) return;
    
    try {
        const response = await fetch(`${API_BASE}/system/${id}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showNotification('System monitor deleted');
            loadSystemMonitors();
        }
    } catch (error) {
        console.error('Error deleting system monitor:', error);
        showNotification('Error deleting system monitor', 'error');
    }
}

async function loadSystemStats() {
    try {
        const response = await fetch(`${API_BASE}/system/stats`);
        const stats = await response.json();
        
        let statsHtml = `CPU: ${stats.cpu_percent.toFixed(1)}% | Memory: ${stats.memory.percent.toFixed(1)}% (${(stats.memory.used_mb / 1024).toFixed(2)} GB / ${(stats.memory.total_mb / 1024).toFixed(2)} GB)\n\n`;
        statsHtml += 'Disk Usage:\n';
        
        for (const [drive, info] of Object.entries(stats.disk)) {
            if (!info.error) {
                statsHtml += `  ${drive}: ${info.percent.toFixed(1)}% used (${info.free_gb.toFixed(1)} GB free of ${info.total_gb.toFixed(1)} GB)\n`;
            } else {
                statsHtml += `  ${drive}: Error - ${info.error}\n`;
            }
        }
        
        document.getElementById('currentStats').textContent = statsHtml;
        
    } catch (error) {
        console.error('Error loading system stats:', error);
        document.getElementById('currentStats').textContent = 'Error loading system stats.';
    }
}

// Alerts
async function loadAlerts() {
    try {
        const response = await fetch(`${API_BASE}/alerts`);
        const alerts = await response.json();
        
        const listEl = document.getElementById('alertsList');
        if (alerts.length === 0) {
            listEl.innerHTML = '<div class="empty-state">No alert rules configured</div>';
            return;
        }
        
        listEl.innerHTML = alerts.map(alert => `
            <div class="monitor-item">
                <div class="monitor-info">
                    <strong>${alert.monitored_item_type.toUpperCase()} #${alert.monitored_item_id}</strong>
                    <small>Condition: ${alert.alert_condition.replace('_', ' ').toUpperCase()}</small>
                    ${alert.condition_value ? `<small>Value: ${alert.condition_value}</small>` : ''}
                    <small>Status: ${alert.enabled ? '🟢 Enabled' : '⭕ Disabled'}</small>
                </div>
                <div class="monitor-actions">
                    <button class="btn-warning" onclick="toggleAlert(${alert.id}, ${!alert.enabled})">${alert.enabled ? 'Disable' : 'Enable'}</button>
                    <button class="btn-danger" onclick="deleteAlert(${alert.id})">Delete</button>
                </div>
            </div>
        `).join('');
        
    } catch (error) {
        console.error('Error loading alerts:', error);
        showNotification('Error loading alerts', 'error');
    }
}

function openAlertModal() {
    const modal = document.getElementById('alertModal');
    const form = document.getElementById('alertForm');
    
    form.reset();
    loadAlertRecipients();
    
    modal.setAttribute('aria-hidden', 'false');
    modal.classList.add('show');
    document.body.classList.add('modal-open');
}

function closeAlertModal() {
    const modal = document.getElementById('alertModal');
    modal.setAttribute('aria-hidden', 'true');
    modal.classList.remove('show');
    document.body.classList.remove('modal-open');
}

async function updateAlertMonitorOptions() {
    const monitorType = document.getElementById('alertMonitorType').value;
    const monitorIdSelect = document.getElementById('alertMonitorId');
    
    monitorIdSelect.innerHTML = '<option value="">Select monitor...</option>';
    
    if (!monitorType) return;
    
    try {
        let response;
        switch (monitorType) {
            case 'port':
                response = await fetch(`${API_BASE}/ports`);
                break;
            case 'process':
                response = await fetch(`${API_BASE}/processes`);
                break;
            case 'service':
                response = await fetch(`${API_BASE}/services`);
                break;
            case 'system':
                response = await fetch(`${API_BASE}/system`);
                break;
        }
        
        if (response && response.ok) {
            const monitors = await response.json();
            monitors.forEach(monitor => {
                const option = document.createElement('option');
                option.value = monitor.id;
                option.textContent = `${monitorType.toUpperCase()} #${monitor.id}${monitor.name ? ` - ${monitor.name}` : ''}`;
                monitorIdSelect.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading monitors:', error);
    }
}

function updateAlertConditionFields() {
    const condition = document.getElementById('alertCondition').value;
    const conditionValueGroup = document.getElementById('alertConditionValueGroup');
    const conditionValueInput = document.getElementById('alertConditionValue');
    
    if (condition === 'status_change') {
        conditionValueGroup.style.display = 'block';
        conditionValueInput.placeholder = '{"from_status": "running", "to_status": "stopped"}';
    } else if (condition === 'duration') {
        conditionValueGroup.style.display = 'block';
        conditionValueInput.placeholder = '{"status": "stopped", "interval_count": 3}';
    } else if (condition === 'threshold') {
        conditionValueGroup.style.display = 'block';
        conditionValueInput.placeholder = '{"threshold": 80, "metric": "cpu"}';
    } else if (condition === 'recurring') {
        conditionValueGroup.style.display = 'block';
        conditionValueInput.placeholder = '{"schedule": "0 9 * * *"}';
    } else {
        conditionValueGroup.style.display = 'none';
    }
}

async function loadAlertRecipients() {
    try {
        const response = await fetch(`${API_BASE}/recipients`);
        const recipients = await response.json();
        
        const select = document.getElementById('alertRecipients');
        select.innerHTML = '';
        
        recipients.forEach(recipient => {
            const option = document.createElement('option');
            option.value = recipient.id;
            option.textContent = `${recipient.email_address}${recipient.name ? ` (${recipient.name})` : ''}`;
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading recipients:', error);
    }
}

async function addAlertRule(event) {
    event.preventDefault();
    
    const formData = new FormData(event.target);
    const recipientIds = Array.from(document.getElementById('alertRecipients').selectedOptions).map(opt => parseInt(opt.value));
    
    const alertData = {
        monitored_item_id: parseInt(document.getElementById('alertMonitorId').value),
        monitored_item_type: document.getElementById('alertMonitorType').value,
        alert_condition: document.getElementById('alertCondition').value,
        condition_value: document.getElementById('alertConditionValue').value || null,
        recurring_schedule: null,
        template_id: null,
        enabled: true,
        recipient_ids: recipientIds
    };
    
    try {
        const response = await fetch(`${API_BASE}/alerts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(alertData)
        });
        
        if (response.ok) {
            showNotification('Alert rule added successfully!', 'success');
            closeAlertModal();
            loadAlerts();
        } else {
            const errorData = await response.json();
            showNotification(`Error: ${errorData.detail}`, 'error');
        }
    } catch (error) {
        console.error('Error adding alert rule:', error);
        showNotification('Error adding alert rule', 'error');
    }
}

async function toggleAlert(alertId, enabled) {
    try {
        const response = await fetch(`${API_BASE}/alerts/${alertId}/toggle?enabled=${enabled}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            showNotification(`Alert rule ${enabled ? 'enabled' : 'disabled'} successfully!`, 'success');
            loadAlerts();
        } else {
            showNotification('Error toggling alert rule', 'error');
        }
    } catch (error) {
        console.error('Error toggling alert:', error);
        showNotification('Error toggling alert rule', 'error');
    }
}

async function autoCreateAlerts() {
    if (!confirm('This will create alert rules for all existing monitors. Continue?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/alerts/auto-create`, {
            method: 'POST'
        });
        
        if (response.ok) {
            const result = await response.json();
            showNotification(result.message, 'success');
            loadAlerts();
        } else {
            const errorData = await response.json();
            showNotification(`Error: ${errorData.detail}`, 'error');
        }
    } catch (error) {
        console.error('Error auto-creating alerts:', error);
        showNotification('Error auto-creating alert rules', 'error');
    }
}

async function deleteAlert(id) {
    if (!confirm('Delete this alert rule?')) return;
    
    try {
        const response = await fetch(`${API_BASE}/alerts/${id}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showNotification('Alert deleted');
            loadAlerts();
        }
    } catch (error) {
        console.error('Error deleting alert:', error);
        showNotification('Error deleting alert', 'error');
    }
}

// Settings
async function loadSMTPServers() {
    try {
        const response = await fetch(`${API_BASE}/smtp`);
        const servers = await response.json();
        
        const listEl = document.getElementById('smtpServersList');
        if (servers.length === 0) {
            listEl.innerHTML = '<div class="empty-state">No SMTP servers configured</div>';
            return;
        }
        
        listEl.innerHTML = servers.map(server => `
            <div class="config-item">
                <div class="config-info">
                    <h5>${server.smtp_host}:${server.smtp_port}</h5>
                    <p>From: ${server.from_address}${server.username ? ` | User: ${server.username}` : ''}</p>
                    <div class="config-status">
                        <span class="status-badge ${server.is_active ? 'active' : 'inactive'}">
                            ${server.is_active ? 'Active' : 'Inactive'}
                        </span>
                        <span class="status-badge ${server.use_ssl ? 'active' : 'inactive'}">
                            ${server.use_ssl ? 'SSL' : 'No SSL'}
                        </span>
                        <span class="status-badge ${server.use_tls ? 'active' : 'inactive'}">
                            ${server.use_tls ? 'TLS' : 'No TLS'}
                        </span>
                    </div>
                </div>
                <div class="config-actions">
                    <button onclick="editSMTPServer(${server.id})" class="btn-secondary">Edit</button>
                    <button onclick="testSMTPServer(${server.id})" class="btn-info">📧 Test</button>
                    <button onclick="deleteSMTPServer(${server.id})" class="btn-danger">Delete</button>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading SMTP servers:', error);
        showNotification('Error loading SMTP servers', 'error');
    }
}

async function saveSMTPServer(event) {
    event.preventDefault();
    
    const serverId = document.getElementById('smtpServerId').value;
    const isEdit = serverId !== '';
    
    const data = {
        smtp_host: document.getElementById('smtpHost').value,
        smtp_port: parseInt(document.getElementById('smtpPort').value),
        username: document.getElementById('smtpUsername').value || null,
        password: document.getElementById('smtpPassword').value || null,
        from_address: document.getElementById('smtpFromAddress').value,
        use_ssl: document.getElementById('smtpUseSSL').checked,
        use_tls: document.getElementById('smtpUseTLS').checked,
        is_active: document.getElementById('smtpIsActive').checked,
        default_template_id: null
    };
    
    try {
        const url = isEdit ? `${API_BASE}/smtp/${serverId}` : `${API_BASE}/smtp`;
        const method = isEdit ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method: method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            showNotification(`SMTP server ${isEdit ? 'updated' : 'created'} successfully`);
            document.getElementById('smtpForm').reset();
            document.getElementById('smtpServerId').value = '';
            document.getElementById('smtpFormTitle').textContent = 'Add New SMTP Server';
            document.getElementById('smtpSubmitBtn').textContent = 'Save SMTP Configuration';
            document.getElementById('cancelEditBtn').style.display = 'none';
            loadSMTPServers();
        } else {
            throw new Error(`Failed to ${isEdit ? 'update' : 'create'} SMTP configuration`);
        }
    } catch (error) {
        console.error(`Error ${isEdit ? 'updating' : 'creating'} SMTP configuration:`, error);
        showNotification(`Error ${isEdit ? 'updating' : 'creating'} SMTP configuration`, 'error');
    }
}

async function editSMTPServer(serverId) {
    try {
        const response = await fetch(`${API_BASE}/smtp`);
        const servers = await response.json();
        const server = servers.find(s => s.id === serverId);
        
        if (!server) {
            showNotification('SMTP server not found', 'error');
            return;
        }
        
        // Populate form with server data
        document.getElementById('smtpServerId').value = server.id;
        document.getElementById('smtpHost').value = server.smtp_host;
        document.getElementById('smtpPort').value = server.smtp_port;
        document.getElementById('smtpUsername').value = server.username || '';
        document.getElementById('smtpPassword').value = ''; // Don't show password
        document.getElementById('smtpFromAddress').value = server.from_address;
        document.getElementById('smtpUseSSL').checked = server.use_ssl;
        document.getElementById('smtpUseTLS').checked = server.use_tls;
        document.getElementById('smtpIsActive').checked = server.is_active;
        
        // Update form title and button
        document.getElementById('smtpFormTitle').textContent = `Edit SMTP Server: ${server.smtp_host}`;
        document.getElementById('smtpSubmitBtn').textContent = 'Update SMTP Configuration';
        document.getElementById('cancelEditBtn').style.display = 'inline-block';
        
        // Scroll to form
        document.getElementById('smtpForm').scrollIntoView({ behavior: 'smooth' });
        
    } catch (error) {
        console.error('Error loading SMTP server for edit:', error);
        showNotification('Error loading SMTP server', 'error');
    }
}

function cancelSMTPServerEdit() {
    document.getElementById('smtpForm').reset();
    document.getElementById('smtpServerId').value = '';
    document.getElementById('smtpFormTitle').textContent = 'Add New SMTP Server';
    document.getElementById('smtpSubmitBtn').textContent = 'Save SMTP Configuration';
    document.getElementById('cancelEditBtn').style.display = 'none';
}

async function deleteSMTPServer(serverId) {
    if (!confirm('Are you sure you want to delete this SMTP server configuration?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/smtp/${serverId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showNotification('SMTP server deleted successfully');
            loadSMTPServers();
        } else {
            throw new Error('Failed to delete SMTP server');
        }
    } catch (error) {
        console.error('Error deleting SMTP server:', error);
        showNotification('Error deleting SMTP server', 'error');
    }
}

async function testSMTPServer(serverId) {
    const testBtn = event.target;
    const originalText = testBtn.innerHTML;
    
    // Disable button and show loading state
    testBtn.disabled = true;
    testBtn.innerHTML = '⏳ Testing...';
    
    try {
        // Get recipient email from dropdown
        const recipientEmail = document.getElementById('testRecipient').value;
        
        // Prepare test parameters
        const params = new URLSearchParams();
        params.append('smtp_server_id', serverId);
        if (recipientEmail && recipientEmail.trim()) {
            params.append('recipient_email', recipientEmail.trim());
        }
        
        // Send test email request
        const response = await fetch(`${API_BASE}/email/test?${params}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification(
                `✅ Test email sent successfully to ${result.recipient_email}! ` +
                `Execution time: ${result.execution_time.toFixed(2)}s`, 
                'success'
            );
        } else {
            showNotification(
                `❌ Test email failed: ${result.error}`, 
                'error'
            );
        }
        
        // Log detailed result to console for debugging
        console.log('Test email result:', result);
        
    } catch (error) {
        console.error('Error testing SMTP server:', error);
        showNotification('Error testing SMTP server: ' + error.message, 'error');
    } finally {
        // Re-enable button
        testBtn.disabled = false;
        testBtn.innerHTML = originalText;
    }
}

// Auto-configure SSL/TLS based on port
function configureSSLTLSSettings() {
    const port = parseInt(document.getElementById('smtpPort').value);
    const sslCheckbox = document.getElementById('smtpUseSSL');
    const tlsCheckbox = document.getElementById('smtpUseTLS');
    
    if (port === 465) {
        // Port 465 uses SSL
        sslCheckbox.checked = true;
        tlsCheckbox.checked = false;
    } else if (port === 587) {
        // Port 587 uses TLS/STARTTLS
        sslCheckbox.checked = false;
        tlsCheckbox.checked = true;
    } else if (port === 25) {
        // Port 25 usually no encryption
        sslCheckbox.checked = false;
        tlsCheckbox.checked = false;
    }
}

// Add event listener to port field
document.addEventListener('DOMContentLoaded', function() {
    const portField = document.getElementById('smtpPort');
    if (portField) {
        portField.addEventListener('change', configureSSLTLSSettings);
        portField.addEventListener('input', configureSSLTLSSettings);
    }
});

async function testSMTPConfiguration() {
    const testBtn = document.getElementById('testEmailBtn');
    const originalText = testBtn.innerHTML;
    
    // Disable button and show loading state
    testBtn.disabled = true;
    testBtn.innerHTML = '⏳ Testing...';
    
    try {
        // Get recipient email from dropdown
        const recipientEmail = document.getElementById('testRecipient').value;
        
        // Prepare test parameters
        const params = new URLSearchParams();
        if (recipientEmail && recipientEmail.trim()) {
            params.append('recipient_email', recipientEmail.trim());
        }
        
        // Send test email request
        const response = await fetch(`${API_BASE}/email/test?${params}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification(
                `✅ Test email sent successfully to ${result.recipient_email}! ` +
                `Execution time: ${result.execution_time.toFixed(2)}s`, 
                'success'
            );
        } else {
            showNotification(
                `❌ Test email failed: ${result.error}`, 
                'error'
            );
        }
        
        // Log detailed result to console for debugging
        console.log('Test email result:', result);
        
    } catch (error) {
        console.error('Error testing SMTP configuration:', error);
        showNotification('Error testing SMTP configuration: ' + error.message, 'error');
    } finally {
        // Re-enable button
        testBtn.disabled = false;
        testBtn.innerHTML = originalText;
    }
}

async function loadRecipients() {
    try {
        const response = await fetch(`${API_BASE}/recipients`);
        const recipients = await response.json();
        
        const listEl = document.getElementById('recipientsList');
        if (recipients.length === 0) {
            listEl.innerHTML = '<div class="empty-state">No recipients configured</div>';
            return;
        }
        
        listEl.innerHTML = recipients.map(rec => `
            <div class="monitor-item">
                <div class="monitor-info">
                    <strong>${rec.email_address}</strong>
                    ${rec.name ? `<small>${rec.name}</small>` : ''}
                </div>
                <div class="monitor-actions">
                    <button class="btn-danger" onclick="deleteRecipient(${rec.id})">Delete</button>
                </div>
            </div>
        `).join('');
        
        // Also populate the test recipient dropdown
        populateTestRecipientDropdown(recipients);
        
    } catch (error) {
        console.error('Error loading recipients:', error);
        showNotification('Error loading recipients', 'error');
    }
}

function populateTestRecipientDropdown(recipients) {
    const dropdown = document.getElementById('testRecipient');
    if (!dropdown) return;
    
    // Clear existing options except the first one
    dropdown.innerHTML = '<option value="">Use first enabled recipient</option>';
    
    // Add enabled recipients to dropdown
    recipients
        .filter(rec => rec.enabled)
        .forEach(rec => {
            const option = document.createElement('option');
            option.value = rec.email_address;
            option.textContent = `${rec.email_address}${rec.name ? ` (${rec.name})` : ''}`;
            dropdown.appendChild(option);
        });
}

async function addRecipient(event) {
    event.preventDefault();
    
    const data = {
        email_address: document.getElementById('recipientEmail').value,
        name: document.getElementById('recipientName').value || null,
        alert_types: [],
        enabled: true
    };
    
    try {
        const response = await fetch(`${API_BASE}/recipients`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            showNotification('Recipient added successfully');
            document.getElementById('recipientForm').reset();
            loadRecipients(); // This will also update the test recipient dropdown
        } else {
            throw new Error('Failed to add recipient');
        }
    } catch (error) {
        console.error('Error adding recipient:', error);
        showNotification('Error adding recipient', 'error');
    }
}

async function deleteRecipient(id) {
    if (!confirm('Delete this recipient?')) return;
    
    try {
        const response = await fetch(`${API_BASE}/recipients/${id}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showNotification('Recipient deleted');
            loadRecipients();
        }
    } catch (error) {
        console.error('Error deleting recipient:', error);
        showNotification('Error deleting recipient', 'error');
    }
}

// Logs
async function loadLogs() {
    try {
        const response = await fetch(`${API_BASE}/logs/scripts?limit=50`);
        const data = await response.json();
        const logs = data.logs || [];
        
        const viewer = document.getElementById('logViewer');
        if (logs.length === 0) {
            viewer.innerHTML = '<div class="empty-state">No script execution logs available</div>';
            return;
        }
        
        viewer.innerHTML = `
            <div class="logs-container">
                <h3>Recent Script Execution Logs</h3>
                <div class="logs-list">
                    ${logs.map(log => `
                        <div class="log-entry">
                            <div class="log-header">
                                <span class="log-timestamp">${new Date(log.timestamp).toLocaleString()}</span>
                                <span class="log-status badge ${getLogStatusClass(log.status)}">${log.status || log.event}</span>
                            </div>
                            <div class="log-details">
                                ${log.job_id ? `<div class="log-detail"><strong>Job ID:</strong> ${log.job_id}</div>` : ''}
                                ${log.exit_code !== undefined ? `<div class="log-detail"><strong>Exit Code:</strong> ${log.exit_code}</div>` : ''}
                                ${log.execution_time ? `<div class="log-detail"><strong>Execution Time:</strong> ${log.execution_time}s</div>` : ''}
                                ${log.retry_count ? `<div class="log-detail"><strong>Retry Count:</strong> ${log.retry_count}</div>` : ''}
                                ${log.error_message ? `<div class="log-detail error"><strong>Error:</strong> ${log.error_message}</div>` : ''}
                                ${log.stdout_size ? `<div class="log-detail"><strong>Output Size:</strong> ${log.stdout_size} bytes</div>` : ''}
                                ${log.stderr_size ? `<div class="log-detail"><strong>Error Output Size:</strong> ${log.stderr_size} bytes</div>` : ''}
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
        
    } catch (error) {
        console.error('Error loading logs:', error);
        showNotification('Error loading logs', 'error');
    }
}

async function loadLogFiles() {
    try {
        const response = await fetch(`${API_BASE}/logs/files`);
        const data = await response.json();
        
        const logViewer = document.getElementById('logViewer');
        
        if (data.all && data.all.length > 0) {
            logViewer.innerHTML = `
                <div class="log-files-container">
                    <h3>Available Log Files</h3>
                    <div class="log-files-grid">
                        ${data.script_execution.map(file => `
                            <div class="log-file-card">
                                <div class="log-file-header">
                                    <h4>📄 ${file.name}</h4>
                                    <span class="log-file-type">Script Execution</span>
                                </div>
                                <div class="log-file-actions">
                                    <button class="btn-primary" onclick="viewLogFile('${file.name}', 'script_execution')">View Content</button>
                                    <button class="btn-ghost" onclick="downloadLogFile('${file.path}')">Download</button>
                                </div>
                            </div>
                        `).join('')}
                        ${data.monitoring.map(file => `
                            <div class="log-file-card">
                                <div class="log-file-header">
                                    <h4>📊 ${file.name}</h4>
                                    <span class="log-file-type">Monitoring</span>
                                </div>
                                <div class="log-file-actions">
                                    <button class="btn-primary" onclick="viewLogFile('${file.name}', 'monitoring')">View Content</button>
                                    <button class="btn-ghost" onclick="downloadLogFile('${file.path}')">Download</button>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        } else {
            logViewer.innerHTML = '<div class="empty-state">No log files available</div>';
        }
    } catch (error) {
        console.error('Error loading log files:', error);
        showNotification('Error loading log files', 'error');
    }
}

async function viewLogFile(filename, type) {
    try {
        const response = await fetch(`${API_BASE}/logs/file/${type}/${filename}`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        
        const logViewer = document.getElementById('logViewer');
        logViewer.innerHTML = `
            <div class="log-file-viewer">
                <div class="log-file-header">
                    <h3>📄 ${filename}</h3>
                    <div class="log-file-controls">
                        <button class="btn-ghost" onclick="loadLogFiles()">← Back to Files</button>
                        <button class="btn-primary" onclick="downloadLogFile('${data.path}')">Download</button>
                    </div>
                </div>
                <div class="log-content">
                    <pre class="log-content-text">${data.content}</pre>
                </div>
            </div>
        `;
    } catch (error) {
        console.error('Error viewing log file:', error);
        showNotification('Error loading log file content', 'error');
    }
}

function downloadLogFile(filePath) {
    // Create a temporary link to download the file
    const link = document.createElement('a');
    link.href = `${API_BASE}/logs/download?path=${encodeURIComponent(filePath)}`;
    link.download = filePath.split('/').pop();
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function getLogStatusClass(status) {
    switch (status) {
        case 'completed':
        case 'queued':
            return 'badge-success';
        case 'failed':
        case 'error':
            return 'badge-danger';
        case 'timeout':
            return 'badge-warning';
        default:
            return 'badge-info';
    }
}

// Helper functions
function toggleScriptFields(type) {
    const scriptType = document.getElementById(`${type}ScriptType`).value;
    const contentGroup = document.getElementById(`${type}ScriptContentGroup`);
    const pathGroup = document.getElementById(`${type}ScriptPathGroup`);
    
    if (scriptType === 'inline') {
        contentGroup.style.display = 'flex';
        pathGroup.style.display = 'none';
    } else {
        contentGroup.style.display = 'none';
        pathGroup.style.display = 'flex';
    }
}

function toggleSystemFields() {
    const monitorType = document.getElementById('systemMonitorType').value;
    const processRefGroup = document.getElementById('systemProcessRefGroup');
    const driveLetterGroup = document.getElementById('systemDriveLetterGroup');
    
    processRefGroup.style.display = (monitorType === 'process_cpu' || monitorType === 'process_ram') ? 'flex' : 'none';
    driveLetterGroup.style.display = (monitorType === 'disk') ? 'flex' : 'none';
}

// Toggle port script sections based on trigger status
function togglePortScriptSections() {
    const trigger = document.getElementById('portTriggerStatus').value;
    const stoppedSection = document.getElementById('portScriptSectionStopped');
    const runningSection = document.getElementById('portScriptSectionRunning');
    
    if (trigger === 'stopped') {
        stoppedSection.style.display = 'block';
        runningSection.style.display = 'none';
    } else if (trigger === 'running') {
        stoppedSection.style.display = 'none';
        runningSection.style.display = 'block';
    } else { // 'both'
        stoppedSection.style.display = 'block';
        runningSection.style.display = 'block';
    }
}

// Toggle port script fields (inline vs file) for specific status
function togglePortScriptFields(status) {
    const scriptType = document.getElementById(`portScriptType${status.charAt(0).toUpperCase() + status.slice(1)}`).value;
    const contentGroup = document.getElementById(`portScriptContentGroup${status.charAt(0).toUpperCase() + status.slice(1)}`);
    const pathGroup = document.getElementById(`portScriptPathGroup${status.charAt(0).toUpperCase() + status.slice(1)}`);
    
    if (scriptType === 'inline') {
        contentGroup.style.display = 'block';
        pathGroup.style.display = 'none';
    } else {
        contentGroup.style.display = 'none';
        pathGroup.style.display = 'block';
    }
}

// Toggle process script sections based on trigger status
function toggleProcessScriptSections() {
    const trigger = document.getElementById('processTriggerStatus').value;
    const stoppedSection = document.getElementById('processScriptSectionStopped');
    const runningSection = document.getElementById('processScriptSectionRunning');
    
    if (trigger === 'stopped') {
        stoppedSection.style.display = 'block';
        runningSection.style.display = 'none';
    } else if (trigger === 'running') {
        stoppedSection.style.display = 'none';
        runningSection.style.display = 'block';
    } else { // 'both'
        stoppedSection.style.display = 'block';
        runningSection.style.display = 'block';
    }
}

// Toggle process script fields (inline vs file) for specific status
function toggleProcessScriptFields(status) {
    const scriptType = document.getElementById(`processScriptType${status.charAt(0).toUpperCase() + status.slice(1)}`).value;
    const contentGroup = document.getElementById(`processScriptContentGroup${status.charAt(0).toUpperCase() + status.slice(1)}`);
    const pathGroup = document.getElementById(`processScriptPathGroup${status.charAt(0).toUpperCase() + status.slice(1)}`);
    
    if (scriptType === 'inline') {
        contentGroup.style.display = 'block';
        pathGroup.style.display = 'none';
    } else {
        contentGroup.style.display = 'none';
        pathGroup.style.display = 'block';
    }
}

function showNotification(message, type = 'success') {
    const notification = document.getElementById('notification');
    notification.textContent = message;
    notification.className = `notification ${type} show`;
    
    setTimeout(() => {
        notification.classList.remove('show');
    }, 3000);
}

// Port Monitor Action Functions
async function executePortScript(portId, status) {
    const label = status ? status.toUpperCase() : 'configured';
    if (!confirm(`Execute the ${label} script for this port?`)) return;
    
    const query = status ? `?status=${encodeURIComponent(status)}` : '';
    
    try {
        const response = await fetch(`${API_BASE}/ports/${portId}/execute-script${query}`, {
            method: 'POST'
        });
        const result = await response.json();
        
        if (response.ok) {
            showNotification(`Script queued: ${result.message}`, 'success');
        } else {
            showNotification(result.detail || 'Failed to execute script', 'error');
        }
    } catch (error) {
        console.error('Error executing port script:', error);
        showNotification('Error executing script', 'error');
    }
}

async function togglePortAutoExecute(portId, enabled) {
    try {
        const response = await fetch(`${API_BASE}/ports/${portId}/toggle-auto-execute?enabled=${enabled}`, {
            method: 'POST'
        });
        const result = await response.json();
        
        if (response.ok) {
            showNotification(result.message, 'success');
            loadPortMonitors(); // Refresh the list
        } else {
            showNotification(result.detail || 'Failed to toggle auto-execute', 'error');
        }
    } catch (error) {
        console.error('Error toggling auto-execute:', error);
        showNotification('Error toggling auto-execute', 'error');
    }
}

async function killPortProcess(portId, force) {
    const action = force ? 'force kill' : 'kill';
    if (!confirm(`Are you sure you want to ${action} the process on this port?`)) return;
    
    try {
        const response = await fetch(`${API_BASE}/ports/${portId}/kill-process?force=${force}`, {
            method: 'POST'
        });
        const result = await response.json();
        
        if (response.ok) {
            showNotification(result.message, 'success');
            setTimeout(() => checkPortStatus(portId), 1000); // Refresh status after 1s
        } else {
            showNotification(result.detail || `Failed to ${action} process`, 'error');
        }
    } catch (error) {
        console.error(`Error ${action}ing process:`, error);
        showNotification(`Error ${action}ing process`, 'error');
    }
}

// Process Monitor Action Functions
async function executeProcessScript(processId) {
    if (!confirm('Execute recovery script for this process?')) return;
    
    try {
        const response = await fetch(`${API_BASE}/processes/${processId}/execute-script`, {
            method: 'POST'
        });
        const result = await response.json();
        
        if (response.ok) {
            showNotification(`Script queued: ${result.message}`, 'success');
        } else {
            showNotification(result.detail || 'Failed to execute script', 'error');
        }
    } catch (error) {
        console.error('Error executing process script:', error);
        showNotification('Error executing script', 'error');
    }
}

async function toggleProcessAutoExecute(processId, enabled) {
    try {
        const response = await fetch(`${API_BASE}/processes/${processId}/toggle-auto-execute?enabled=${enabled}`, {
            method: 'POST'
        });
        const result = await response.json();
        
        if (response.ok) {
            showNotification(result.message, 'success');
            loadProcessMonitors(); // Refresh the list
        } else {
            showNotification(result.detail || 'Failed to toggle auto-execute', 'error');
        }
    } catch (error) {
        console.error('Error toggling auto-execute:', error);
        showNotification('Error toggling auto-execute', 'error');
    }
}

async function killProcess(processId, force) {
    const action = force ? 'force kill' : 'kill';
    if (!confirm(`Are you sure you want to ${action} this process?`)) return;
    
    try {
        const response = await fetch(`${API_BASE}/processes/${processId}/kill-process?force=${force}`, {
            method: 'POST'
        });
        const result = await response.json();
        
        if (response.ok) {
            showNotification(result.message, 'success');
            setTimeout(() => checkProcessStatus(processId), 1000); // Refresh status after 1s
        } else {
            showNotification(result.detail || `Failed to ${action} process`, 'error');
        }
    } catch (error) {
        console.error(`Error ${action}ing process:`, error);
        showNotification(`Error ${action}ing process`, 'error');
    }
}

// Service Monitor Action Functions
async function executeServiceScript(serviceId) {
    if (!confirm('Execute script for this service?')) return;
    
    try {
        const response = await fetch(`${API_BASE}/services/${serviceId}/execute-script`, {
            method: 'POST'
        });
        const result = await response.json();
        
        if (response.ok) {
            showNotification(`Script queued: ${result.message}`, 'success');
        } else {
            showNotification(result.detail || 'Failed to execute script', 'error');
        }
    } catch (error) {
        console.error('Error executing service script:', error);
        showNotification('Error executing script', 'error');
    }
}

async function toggleServiceAutoExecute(serviceId, enabled) {
    try {
        const response = await fetch(`${API_BASE}/services/${serviceId}/toggle-auto-execute?enabled=${enabled}`, {
            method: 'POST'
        });
        const result = await response.json();
        
        if (response.ok) {
            showNotification(result.message, 'success');
            loadServiceMonitors(); // Refresh the list
        } else {
            showNotification(result.detail || 'Failed to toggle auto-execute', 'error');
        }
    } catch (error) {
        console.error('Error toggling auto-execute:', error);
        showNotification('Error toggling auto-execute', 'error');
    }
}

