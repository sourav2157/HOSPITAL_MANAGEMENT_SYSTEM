document.addEventListener('DOMContentLoaded', () => {
    const socket = io();

    const wsDot = document.getElementById('ws-dot');
    const wsStatus = document.getElementById('ws-status');
    const devicesContainer = document.getElementById('devices-container');
    const logsTbody = document.getElementById('logs-tbody');
    const noLogsRow = document.getElementById('no-logs-row');

    const statActiveCount = document.getElementById('stat-active-count');
    const statHwCount = document.getElementById('stat-hw-count');
    const statBrowserCount = document.getElementById('stat-browser-count');
    const statMsgCount = document.getElementById('stat-msg-count');

    let devicesMap = {};
    let totalMessagesReceived = 0;

    socket.on('connect', () => {
        wsDot.classList.add('connected');
        wsStatus.textContent = 'Connected to Server';
    });

    socket.on('disconnect', () => {
        wsDot.classList.remove('connected');
        wsStatus.textContent = 'Disconnected';
    });

    socket.on('init_state', (devicesList) => {
        devicesMap = {};
        if (Array.isArray(devicesList)) {
            devicesList.forEach(dev => {
                devicesMap[dev.device_id] = dev;
            });
        }
        renderDevicesGrid();
    });

    socket.on('new_data', (deviceInfo) => {
        totalMessagesReceived++;
        statMsgCount.textContent = totalMessagesReceived;

        devicesMap[deviceInfo.device_id] = deviceInfo;
        renderDevicesGrid();
        addLogEntry(deviceInfo);
    });

    function renderDevicesGrid() {
        const devicesList = Object.values(devicesMap);
        const total = devicesList.length;
        const hwCount = devicesList.filter(d => d.device_type === 'hardware').length;
        const browserCount = devicesList.filter(d => d.device_type === 'browser').length;

        statActiveCount.textContent = total;
        statHwCount.textContent = hwCount;
        statBrowserCount.textContent = browserCount;

        if (total === 0) {
            devicesContainer.innerHTML = `
                <div style="color: var(--text-secondary); grid-column: 1 / -1; text-align: center; padding: 40px; background: var(--card-bg); border-radius: 12px;">
                    Waiting for data from ESP8266, Mobile devices, or Data Pusher...
                </div>`;
            return;
        }

        devicesContainer.innerHTML = devicesList.map(dev => {
            const isHw = dev.device_type === 'hardware';
            const tagClass = isHw ? 'hardware' : 'browser';
            const payloadFormatted = typeof dev.payload === 'object' 
                ? JSON.stringify(dev.payload, null, 2) 
                : dev.payload;

            return `
                <div class="device-card">
                    <div class="device-header">
                        <div class="device-id">${escapeHtml(dev.device_id)}</div>
                        <span class="type-tag ${tagClass}">${escapeHtml(dev.device_type)}</span>
                    </div>
                    <div class="device-meta">
                        <div class="meta-row">
                            <span class="meta-key">${isHw ? 'MAC Address' : 'LocalStorage ID'}:</span>
                            <span class="meta-val">${escapeHtml(dev.hardware_id || 'N/A')}</span>
                        </div>
                        <div class="meta-row">
                            <span class="meta-key">Source IP:</span>
                            <span class="meta-val">${escapeHtml(dev.source_ip || 'N/A')}</span>
                        </div>
                        <div class="meta-row">
                            <span class="meta-key">Last Update:</span>
                            <span class="meta-val">${escapeHtml(dev.timestamp)}</span>
                        </div>
                    </div>
                    <div class="payload-box">${escapeHtml(payloadFormatted)}</div>
                </div>
            `;
        }).join('');
    }

    function addLogEntry(dev) {
        if (noLogsRow) {
            noLogsRow.remove();
        }

        const tr = document.createElement('tr');
        const isHw = dev.device_type === 'hardware';
        const tagClass = isHw ? 'hardware' : 'browser';
        const payloadStr = typeof dev.payload === 'object' ? JSON.stringify(dev.payload) : dev.payload;

        tr.innerHTML = `
            <td style="font-family: monospace; font-size: 0.8rem; color: var(--text-secondary);">${escapeHtml(dev.timestamp)}</td>
            <td style="font-weight: 600; color: var(--accent-blue);">${escapeHtml(dev.device_id)}</td>
            <td><span class="type-tag ${tagClass}">${escapeHtml(dev.device_type)}</span></td>
            <td style="font-family: monospace; font-size: 0.82rem;">${escapeHtml(dev.hardware_id || 'N/A')}</td>
            <td style="font-family: monospace; font-size: 0.82rem;">${escapeHtml(dev.source_ip || 'N/A')}</td>
            <td style="font-family: monospace; font-size: 0.85rem; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(payloadStr)}</td>
        `;

        logsTbody.insertBefore(tr, logsTbody.firstChild);

        // Keep max 50 log rows
        while (logsTbody.children.length > 50) {
            logsTbody.removeChild(logsTbody.lastChild);
        }
    }

    function escapeHtml(str) {
        if (str === null || str === undefined) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }
});
