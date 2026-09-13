document.addEventListener('DOMContentLoaded', () => {
    const socket = io();

    const wsDot = document.getElementById('ws-dot');
    const wsStatus = document.getElementById('ws-status');

    const deviceIdInput = document.getElementById('device-id');
    const localStorageIdInput = document.getElementById('local-storage-id');
    const payloadInput = document.getElementById('payload-input');
    const btnSend = document.getElementById('btn-send');
    const btnAuto = document.getElementById('btn-auto');
    const statusLog = document.getElementById('status-log');

    // 1. Get or Create Browser LocalStorage ID
    let localStorageId = localStorage.getItem('browser_device_id');
    if (!localStorageId) {
        localStorageId = 'LS_ID_' + Math.random().toString(36).substring(2, 10).toUpperCase();
        localStorage.setItem('browser_device_id', localStorageId);
    }
    localStorageIdInput.value = localStorageId;

    // Socket Connection Status
    socket.on('connect', () => {
        wsDot.classList.add('connected');
        wsStatus.textContent = 'Connected';
        statusLog.textContent = 'WebSocket connected ready to send data.';
    });

    socket.on('disconnect', () => {
        wsDot.classList.remove('connected');
        wsStatus.textContent = 'Disconnected';
        statusLog.textContent = 'Connection lost.';
    });

    // Send Single Packet
    btnSend.addEventListener('click', () => {
        sendTelemetry();
    });

    // Auto-Push Timer Toggle
    let autoInterval = null;
    btnAuto.addEventListener('click', () => {
        if (autoInterval) {
            clearInterval(autoInterval);
            autoInterval = null;
            btnAuto.textContent = '⚡ Start Auto-Push (Every 3s)';
            btnAuto.classList.remove('btn-secondary');
            statusLog.textContent = 'Auto-push stopped.';
        } else {
            sendTelemetry(); // send first immediately
            autoInterval = setInterval(() => {
                // Update simulated readings
                const simulatedPayload = {
                    sensor: "mobile_motion",
                    accel_x: (Math.random() * 2 - 1).toFixed(2),
                    accel_y: (Math.random() * 2 - 1).toFixed(2),
                    accel_z: (9.81 + (Math.random() - 0.5)).toFixed(2),
                    battery: Math.floor(60 + Math.random() * 40)
                };
                payloadInput.value = JSON.stringify(simulatedPayload, null, 2);
                sendTelemetry();
            }, 3000);
            btnAuto.textContent = '⏹️ Stop Auto-Push';
            btnAuto.classList.add('btn-secondary');
            statusLog.textContent = 'Auto-pushing telemetry every 3 seconds...';
        }
    });

    function sendTelemetry() {
        const deviceId = deviceIdInput.value.trim() || 'MOBILE_001';
        let payload = payloadInput.value.trim();

        try {
            payload = JSON.parse(payload);
        } catch (e) {
            // Keep as string if not valid JSON
        }

        const dataPacket = {
            device_id: deviceId,
            device_type: "browser",
            hardware_id: localStorageId,
            payload: payload,
            timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19)
        };

        socket.emit('push_data', dataPacket);
        statusLog.textContent = `Sent payload at ${new Date().toLocaleTimeString()}`;
    }
});
