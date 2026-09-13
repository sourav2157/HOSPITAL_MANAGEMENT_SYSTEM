document.addEventListener('DOMContentLoaded', () => {
    const socket = io();

    const wsDot = document.getElementById('ws-dot');
    const wsStatus = document.getElementById('ws-status');
    const helperBanner = document.getElementById('helper-banner');
    const helperAlertMessage = document.getElementById('helper-alert-message');
    const btnSilenceAudio = document.getElementById('btn-silence-audio');

    const currentUserRoleEl = document.getElementById('current-user-role');
    const currentUserNameEl = document.getElementById('current-user-name');
    const btnLogout = document.getElementById('btn-logout');

    const statActiveHelp = document.getElementById('stat-active-help');
    const statBedsideHelp = document.getElementById('stat-bedside-help');
    const statStaffDispatches = document.getElementById('stat-staff-dispatches');
    const statResolvedToday = document.getElementById('stat-resolved-today');

    const cardsContainer = document.getElementById('helper-cards-container');

    const searchInput = document.getElementById('search-input');
    const searchClearBtn = document.getElementById('search-clear-btn');
    const filterWard = document.getElementById('filter-ward');
    const filterStatus = document.getElementById('filter-status');

    // Modals
    const resolveTaskModal = document.getElementById('resolve-task-modal');
    const btnCloseResolveModal = document.getElementById('btn-close-resolve-modal');
    const resolveTaskInfo = document.getElementById('resolve-task-info');
    const resolveNotes = document.getElementById('resolve-notes');
    const btnSubmitResolve = document.getElementById('btn-submit-resolve');

    const helperReportsModal = document.getElementById('helper-reports-modal');
    const btnOpenHelperReports = document.getElementById('btn-open-helper-reports');
    const btnCloseHelperReportsModal = document.getElementById('btn-close-helper-reports-modal');
    const btnRunHelperReport = document.getElementById('btn-run-helper-report');
    const btnDownloadHelperCsv = document.getElementById('btn-download-helper-csv');
    const helperReportBody = document.getElementById('helper-report-body');

    let currentUser = null;
    let allCalls = [];
    let currentResolveCallId = null;
    let audioMuted = false;
    let audioCtx = null;

    // Check logged in user profile
    fetch('/api/me')
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                currentUser = data.user;
                if (currentUserNameEl) currentUserNameEl.textContent = currentUser.full_name;
                if (currentUserRoleEl) currentUserRoleEl.textContent = currentUser.role;
            } else {
                window.location.href = '/login';
            }
        });

    if (btnLogout) {
        btnLogout.addEventListener('click', () => {
            fetch('/api/logout').then(() => window.location.href = '/login');
        });
    }

    function updateSocketUI(isConnected) {
        if (wsDot && wsStatus) {
            if (isConnected) {
                wsDot.classList.add('connected');
                wsStatus.textContent = 'Connected to Network';
            } else {
                wsDot.classList.remove('connected');
                wsStatus.textContent = 'Connecting...';
            }
        }
    }

    updateSocketUI(socket.connected);
    fetchHelperCalls();

    socket.on('connect', () => {
        updateSocketUI(true);
        fetchHelperCalls();
    });

    socket.on('disconnect', () => {
        updateSocketUI(false);
    });

    socket.on('connect_error', () => {
        updateSocketUI(false);
    });

    function initAudioContext() {
        if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        if (audioCtx.state === 'suspended') audioCtx.resume();
    }

    document.addEventListener('click', initAudioContext);

    function playHelpChime() {
        if (audioMuted) return;
        try {
            initAudioContext();
            if (!audioCtx) return;
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();

            osc.type = 'triangle';
            osc.frequency.setValueAtTime(523.25, audioCtx.currentTime); // C5
            osc.frequency.setValueAtTime(659.25, audioCtx.currentTime + 0.15); // E5
            osc.frequency.setValueAtTime(783.99, audioCtx.currentTime + 0.3); // G5

            gain.gain.setValueAtTime(0.3, audioCtx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.8);

            osc.connect(gain);
            gain.connect(audioCtx.destination);
            osc.start();
            osc.stop(audioCtx.currentTime + 0.8);
        } catch (e) {
            console.log('Audio alert error:', e);
        }
    }

    if (btnSilenceAudio) {
        btnSilenceAudio.addEventListener('click', () => {
            audioMuted = !audioMuted;
            btnSilenceAudio.textContent = audioMuted ? '🔇 Unmute Sound' : '🔊 Mute Sound';
            if (!audioMuted) playHelpChime();
        });
    }

    socket.on('general_help_alert', (callData) => {
        playHelpChime();
        fetchHelperCalls();
    });

    socket.on('general_help_urgent_alert', (callData) => {
        playHelpChime();
        if (helperBanner && helperAlertMessage) {
            helperAlertMessage.textContent = callData.message || `🚨 URGENT ATTENDEE ALERT FROM ROOM ${callData.room_no}, BED ${callData.bed_no}!`;
            helperBanner.classList.remove('hidden');
        }
        fetchHelperCalls();
    });

    socket.on('general_help_updated', () => fetchHelperCalls());

    function fetchHelperCalls() {
        const includeResolved = filterStatus ? filterStatus.value === 'ALL' : true;
        fetch(`/api/helper/calls?include_resolved=${includeResolved}`)
            .then(res => res.json())
            .then(calls => {
                allCalls = calls;
                updateStats();
                renderHelperCards();
            });
    }

    function updateStats() {
        const activeCount = allCalls.filter(c => c.status === 'ACTIVE' || c.status === 'ACKNOWLEDGED').length;
        const bedsideCount = allCalls.filter(c => c.call_type === 'BEDSIDE_CALL' && c.status !== 'RESOLVED').length;
        const staffCount = allCalls.filter(c => c.call_type === 'STAFF_DISPATCH' && c.status !== 'RESOLVED').length;
        const resolvedCount = allCalls.filter(c => c.status === 'RESOLVED').length;

        if (statActiveHelp) statActiveHelp.textContent = activeCount;
        if (statBedsideHelp) statBedsideHelp.textContent = bedsideCount;
        if (statStaffDispatches) statStaffDispatches.textContent = staffCount;
        if (statResolvedToday) statResolvedToday.textContent = resolvedCount;

        if (activeCount > 0) {
            if (helperBanner) helperBanner.classList.remove('hidden');
            if (helperAlertMessage) helperAlertMessage.textContent = `🤝 ${activeCount} GENERAL HELP REQUEST(S) ACTIVE!`;
        } else {
            if (helperBanner) helperBanner.classList.add('hidden');
        }
    }

    function renderHelperCards() {
        const query = searchInput ? searchInput.value.toLowerCase().trim() : '';
        const wardVal = filterWard ? filterWard.value : 'ALL';
        const statusVal = filterStatus ? filterStatus.value : 'ACTIVE_ALL';

        if (searchClearBtn) {
            if (query) searchClearBtn.classList.remove('hidden');
            else searchClearBtn.classList.add('hidden');
        }

        let filtered = allCalls.filter(c => {
            if (query) {
                const searchHaystack = [
                    c.patient_name || '',
                    c.ward || '',
                    c.room_no || '',
                    c.bed_no || '',
                    c.assigned_by || '',
                    c.assigned_role || '',
                    c.notes || '',
                    c.status || ''
                ].join(' ').toLowerCase();

                if (!searchHaystack.includes(query)) return false;
            }

            if (wardVal !== 'ALL' && (c.ward || '').toLowerCase() !== wardVal.toLowerCase()) return false;

            if (statusVal === 'ACTIVE_ALL' && c.status === 'RESOLVED') return false;
            if (statusVal === 'ACTIVE' && c.status !== 'ACTIVE') return false;
            if (statusVal === 'ACKNOWLEDGED' && c.status !== 'ACKNOWLEDGED') return false;

            return true;
        });

        if (filtered.length === 0) {
            cardsContainer.innerHTML = `
                <div style="grid-column: 1 / -1; text-align: center; color: var(--text-secondary); padding: 45px 20px; background: var(--card-bg); border-radius: 12px; border: 1px dashed var(--border-color);">
                    <div style="font-size: 2.5rem; margin-bottom: 10px;">🤝</div>
                    <div style="font-size: 1.1rem; font-weight: bold; color: var(--text-primary);">No active general help tasks</div>
                    <div style="font-size: 0.88rem; margin-top: 6px;">All attendee requests have been attended to or cleared.</div>
                </div>
            `;
            return;
        }

        // Group active calls by patient / room / bed to keep EXACTLY ONE card per patient
        const patientGroupsMap = {};
        filtered.forEach(c => {
            const key = c.patient_id ? `pid_${c.patient_id}` : `rb_${c.room_no}_${c.bed_no}`;
            if (!patientGroupsMap[key]) {
                patientGroupsMap[key] = {
                    patient_id: c.patient_id,
                    patient_name: c.patient_name || `Patient (Room ${c.room_no}-${c.bed_no})`,
                    room_no: c.room_no,
                    bed_no: c.bed_no,
                    ward: c.ward || 'General Ward',
                    calls: []
                };
            }
            patientGroupsMap[key].calls.push(c);
        });

        const groups = Object.values(patientGroupsMap);

        cardsContainer.innerHTML = groups.map(g => {
            const hasActive = g.calls.some(c => c.status === 'ACTIVE');
            const hasAck = g.calls.some(c => c.status === 'ACKNOWLEDGED');
            const cardStatus = hasActive ? 'ACTIVE' : (hasAck ? 'ACKNOWLEDGED' : 'RESOLVED');

            return `
                <div class="helper-card status-${cardStatus}" style="background: var(--card-bg); border: 1.5px solid var(--border-color); border-radius: 12px; padding: 16px; margin-bottom: 15px;">
                    <div>
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 10px; flex-wrap: wrap; gap: 4px;">
                            <span class="room-bed-badge">${escapeHtml(g.ward)} | Rm ${escapeHtml(g.room_no)} Bed ${escapeHtml(g.bed_no)}</span>
                            <span style="font-size:0.78rem; background:rgba(59,130,246,0.18); color:#60a5fa; border:1px solid rgba(59,130,246,0.3); padding:2px 8px; border-radius:12px; font-weight:bold;">
                                📋 ${g.calls.length} Active SLA Request(s)
                            </span>
                        </div>

                        <h3 style="margin: 0 0 12px 0; font-size: 1.15rem; color: var(--text-primary);">👤 ${escapeHtml(g.patient_name)}</h3>

                        <!-- List of multiple SLA requests in this single patient card -->
                        <div style="display:flex; flex-direction:column; gap:10px;">
                            ${g.calls.map(c => {
                                const isBedside = c.call_type === 'BEDSIDE_CALL';
                                const originClass = isBedside ? 'origin-BEDSIDE_CALL' : 'origin-STAFF_DISPATCH';
                                const originLabel = isBedside ? '🛏️ Bedside Unit Call' : `🩺 Dispatched by ${escapeHtml(c.assigned_by)} [${escapeHtml(c.assigned_role)}]`;

                                let slaTag = '';
                                if (c.notes && c.notes.includes('[SLA:')) {
                                    const match = c.notes.match(/\[SLA:\s*(\d+)m\]/);
                                    if (match) {
                                        slaTag = `<span style="background: rgba(234, 179, 8, 0.2); color: #facc15; border: 1px solid rgba(234, 179, 8, 0.4); padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; font-weight: bold; margin-left: 6px;">⏱️ SLA Target: ${match[1]} mins</span>`;
                                    }
                                } else if (!isBedside) {
                                    slaTag = `<span style="background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.4); padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; font-weight: bold; margin-left: 6px;">⏱️ SLA Target: 15 mins</span>`;
                                }

                                let statusLabel = 'ACTIVE / UNATTENDED';
                                let statusColor = '#ef4444';
                                if (c.status === 'ACKNOWLEDGED') {
                                    statusLabel = `⏳ In Progress (${escapeHtml(c.acknowledged_by || 'Helper')})`;
                                    statusColor = '#eab308';
                                }
                                if (c.status === 'RESOLVED') {
                                    statusLabel = '✅ Task Completed';
                                    statusColor = '#22c55e';
                                }

                                return `
                                    <div style="background: rgba(15, 23, 42, 0.5); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px 12px;">
                                        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:4px;">
                                            <span class="origin-badge ${originClass}">${originLabel}</span>
                                            ${slaTag}
                                        </div>
                                        <div style="color: var(--accent-blue); margin-top: 6px; font-weight: 600; font-size: 0.88rem;">
                                            📝 "${escapeHtml(c.notes || 'General assistance requested.')}"
                                        </div>
                                        <div style="font-size: 0.78rem; color: var(--text-secondary); margin-top: 6px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:4px;">
                                            <span>🕒 Called: ${escapeHtml(c.called_at)}</span>
                                            <span>Status: <strong style="color:${statusColor}">${statusLabel}</strong></span>
                                        </div>
                                        <div style="display:flex; gap: 8px; margin-top: 8px; justify-content:flex-end;">
                                            ${c.status === 'ACTIVE' ? `
                                                <button class="btn" style="background: var(--accent-yellow); color: #0f172a; font-weight: bold; padding: 4px 10px; font-size: 0.78rem;" onclick="acknowledgeHelperCall(${c.id})">⏳ Acknowledge Task</button>
                                            ` : ''}
                                            ${c.status !== 'RESOLVED' ? `
                                                <button class="btn" style="background: var(--accent-green); color: #0f172a; font-weight: bold; padding: 4px 10px; font-size: 0.78rem;" onclick="openResolveModal(${c.id})">✅ Complete & Clear</button>
                                            ` : ''}
                                        </div>
                                    </div>
                                `;
                            }).join('')}
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }

    if (searchInput) searchInput.addEventListener('input', renderHelperCards);
    if (filterWard) filterWard.addEventListener('change', renderHelperCards);
    if (filterStatus) filterStatus.addEventListener('change', renderHelperCards);

    if (searchClearBtn) {
        searchClearBtn.addEventListener('click', () => {
            searchInput.value = '';
            renderHelperCards();
        });
    }

    window.acknowledgeHelperCall = function(callId) {
        const staffName = currentUser ? currentUser.full_name : 'Helper Mark';
        const staffRole = currentUser ? currentUser.role : 'General Helper';
        fetch('/api/helper/call/acknowledge', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ call_id: callId, staff_name: staffName, staff_role: staffRole })
        }).then(() => fetchHelperCalls());
    };

    window.openResolveModal = function(callId) {
        currentResolveCallId = callId;
        const call = allCalls.find(c => c.id === callId);
        if (call && resolveTaskInfo) {
            resolveTaskInfo.textContent = `Patient: ${call.patient_name} (Rm ${call.room_no}, Bed ${call.bed_no}) | Task: ${call.notes || 'General assistance'}`;
        }
        if (resolveNotes) resolveNotes.value = '';
        if (resolveTaskModal) resolveTaskModal.classList.remove('hidden');
    };

    if (btnCloseResolveModal) {
        btnCloseResolveModal.addEventListener('click', () => {
            if (resolveTaskModal) resolveTaskModal.classList.add('hidden');
            currentResolveCallId = null;
        });
    }

    if (btnSubmitResolve) {
        btnSubmitResolve.addEventListener('click', () => {
            if (!currentResolveCallId) return;
            const text = resolveNotes.value.trim() || 'Task completed cleanly.';

            const staffName = currentUser ? currentUser.full_name : 'Helper Mark';
            const staffRole = currentUser ? currentUser.role : 'General Helper';
            fetch('/api/helper/call/resolve', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ call_id: currentResolveCallId, resolution_notes: text, staff_name: staffName, staff_role: staffRole })
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    if (resolveTaskModal) resolveTaskModal.classList.add('hidden');
                    fetchHelperCalls();
                } else {
                    alert(data.message || 'Failed to resolve task.');
                }
            });
        });
    }

    // Reports Handlers
    if (btnOpenHelperReports) {
        btnOpenHelperReports.addEventListener('click', () => {
            if (helperReportsModal) helperReportsModal.classList.remove('hidden');
            runHelperReportQuery();
        });
    }

    if (btnCloseHelperReportsModal) {
        btnCloseHelperReportsModal.addEventListener('click', () => {
            if (helperReportsModal) helperReportsModal.classList.add('hidden');
        });
    }

    function buildHelperReportQueryParams() {
        const params = new URLSearchParams();
        const start = document.getElementById('rep-start-date');
        const end = document.getElementById('rep-end-date');
        const ward = document.getElementById('rep-ward');

        if (start && start.value) params.append('start_date', start.value);
        if (end && end.value) params.append('end_date', end.value);
        if (ward && ward.value) params.append('ward', ward.value);
        return params.toString();
    }

    function runHelperReportQuery() {
        const queryStr = buildHelperReportQueryParams();
        if (helperReportBody) helperReportBody.innerHTML = `<tr><td colspan="9" style="text-align:center; color: var(--text-secondary);">Querying helper service logs...</td></tr>`;

        fetch(`/api/helper/reports/query?${queryStr}`)
            .then(res => res.json())
            .then(resData => {
                if (resData.status !== 'success') return;
                const rows = resData.data.rows || [];
                if (rows.length === 0) {
                    helperReportBody.innerHTML = `<tr><td colspan="9" style="text-align:center; color: var(--text-secondary);">No helper logs match query.</td></tr>`;
                    return;
                }

                helperReportBody.innerHTML = rows.map(r => `
                    <tr>
                        <td style="font-size:0.8rem; color:var(--text-secondary); white-space:nowrap;">${escapeHtml(r.called_at)}</td>
                        <td><strong>${escapeHtml(r.patient_name)}</strong></td>
                        <td>${escapeHtml(r.ward)}</td>
                        <td>${escapeHtml(r.room_no)}-${escapeHtml(r.bed_no)}</td>
                        <td><span class="origin-badge ${r.call_type === 'BEDSIDE_CALL' ? 'origin-BEDSIDE_CALL' : 'origin-STAFF_DISPATCH'}">${r.call_type === 'BEDSIDE_CALL' ? 'Bedside' : 'Staff Dispatch'}</span></td>
                        <td>${escapeHtml(r.assigned_by || 'N/A')}</td>
                        <td>${escapeHtml(r.notes || 'N/A')}</td>
                        <td><strong>${escapeHtml(r.status)}</strong></td>
                        <td>${escapeHtml(r.acknowledged_by || 'N/A')}</td>
                    </tr>
                `).join('');
            });
    }

    if (btnRunHelperReport) btnRunHelperReport.addEventListener('click', runHelperReportQuery);

    if (btnDownloadHelperCsv) {
        btnDownloadHelperCsv.addEventListener('click', () => {
            const queryStr = buildHelperReportQueryParams();
            window.location.href = `/api/helper/reports/download?${queryStr}`;
        });
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
