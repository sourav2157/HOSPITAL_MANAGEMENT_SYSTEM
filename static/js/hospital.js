function getRoleColor(roleStr, nameStr) {
    const combined = (String(roleStr || '') + ' ' + String(nameStr || '')).toLowerCase();
    if (combined.includes('bedside') || combined.includes('bed side') || combined.includes('unit') || combined.includes('patient')) return '#000000'; // Normal black
    if (combined.includes('doctor')) return '#3b82f6'; // Blue
    if (combined.includes('nurse')) return '#eab308';  // Yellow
    if (combined.includes('helper')) return '#22c55e'; // Green
    if (combined.includes('admin')) return '#a855f7';  // Purple
    return '#64748b';
}

function getTaskCssClass(targetRoles) {
    const rolesArr = Array.isArray(targetRoles) ? targetRoles : [targetRoles];
    const roles = rolesArr.map(r => String(r || '').toLowerCase());
    
    const hasDoc = roles.some(r => r.includes('doctor'));
    const hasNurse = roles.some(r => r.includes('nurse'));
    const hasHelper = roles.some(r => r.includes('helper'));

    const count = (hasDoc ? 1 : 0) + (hasNurse ? 1 : 0) + (hasHelper ? 1 : 0);

    if (count >= 3) {
        return 'task-multi-3team';
    } else if (count === 2) {
        if (hasDoc && hasNurse) return 'task-multi-2team-doc-nurse';
        if (hasDoc && hasHelper) return 'task-multi-2team-doc-helper';
        if (hasNurse && hasHelper) return 'task-multi-2team-nurse-helper';
        return 'task-multi-2team';
    } else {
        if (hasDoc) return 'task-box-doctor';
        if (hasNurse) return 'task-box-nurse';
        if (hasHelper) return 'task-box-helper';
        return '';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const socket = io();

    const wsDot = document.getElementById('ws-dot');
    const wsStatus = document.getElementById('ws-status');
    const emergencyBanner = document.getElementById('emergency-banner');
    const alertMessage = document.getElementById('alert-message');
    const btnSilenceAudio = document.getElementById('btn-silence-audio');

    const currentUserRoleEl = document.getElementById('current-user-role');
    const currentUserNameEl = document.getElementById('current-user-name');
    const btnLogout = document.getElementById('btn-logout');

    const statDoctorCalls = document.getElementById('stat-doctor-calls');
    const statNurseCalls = document.getElementById('stat-nurse-calls');
    const statPinnedCount = document.getElementById('stat-pinned-count');
    const statTotalPatients = document.getElementById('stat-total-patients');

    const patientsContainer = document.getElementById('patients-container');
    
    // Extensive Controls & Filters Elements
    const searchInput = document.getElementById('search-input');
    const searchClearBtn = document.getElementById('search-clear-btn');
    const presetTabs = document.getElementById('preset-tabs');
    const filterWard = document.getElementById('filter-ward');
    const filterStatus = document.getElementById('filter-status');
    const filterAgeGroup = document.getElementById('filter-age-group');
    const sortBy = document.getElementById('sort-by');
    const resultsCountBadge = document.getElementById('results-count-badge');
    const btnResetFilters = document.getElementById('btn-reset-filters');

    // Modals
    const recordBookModal = document.getElementById('record-book-modal');
    const btnCloseModal = document.getElementById('btn-close-modal');
    const modalPatientInfo = document.getElementById('modal-patient-info');
    const timelineContainer = document.getElementById('timeline-container');
    const commentStaffRole = document.getElementById('comment-staff-role');
    const commentStaffName = document.getElementById('comment-staff-name');
    const commentText = document.getElementById('comment-text');
    const btnSubmitComment = document.getElementById('btn-submit-comment');

    const addPatientModal = document.getElementById('add-patient-modal');
    const btnAddPatient = document.getElementById('btn-add-patient');
    const btnCloseAddModal = document.getElementById('btn-close-add-modal');
    const btnSavePatient = document.getElementById('btn-save-patient');

    const transferModal = document.getElementById('transfer-modal');
    const btnCloseTransferModal = document.getElementById('btn-close-transfer-modal');
    const btnSaveTransfer = document.getElementById('btn-save-transfer');

    const statusModal = document.getElementById('status-modal');
    const btnCloseStatusModal = document.getElementById('btn-close-status-modal');
    const btnSaveStatus = document.getElementById('btn-save-status');

    const reportsModal = document.getElementById('reports-modal');
    const btnOpenReports = document.getElementById('btn-open-reports');
    const btnCloseReportsModal = document.getElementById('btn-close-reports-modal');
    const btnDownloadCsv = document.getElementById('btn-download-csv');

    // Prescription Modal
    const prescriptionModal = document.getElementById('prescription-modal');
    const btnCloseRxModal = document.getElementById('btn-close-rx-modal');
    const rxPatientInfo = document.getElementById('rx-patient-info');
    const rxHistoryContainer = document.getElementById('rx-history-container');
    const rxDoctorName = document.getElementById('rx-doctor-name');
    const rxMedication = document.getElementById('rx-medication');
    const rxDosage = document.getElementById('rx-dosage');
    const rxDuration = document.getElementById('rx-duration');
    const rxInstructions = document.getElementById('rx-instructions');
    const btnSaveRx = document.getElementById('btn-save-rx');

    let currentUser = null;
    let allPatients = [];
    let activeTab = 'MY_PATIENTS';
    let currentRecordBookPatientId = null;
    let currentTransferPatientId = null;
    let currentStatusPatientId = null;
    let currentRxPatientId = null;

    let audioMuted = false;
    let audioCtx = null;

    // Fetch Current Logged In User Profile
    fetch('/api/me')
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                currentUser = data.user;
                currentUserNameEl.textContent = currentUser.full_name;
                currentUserRoleEl.textContent = currentUser.role;
                currentUserRoleEl.className = `role-tag ${getRoleCssClass(currentUser.role)}`;
                
                if (commentStaffName) commentStaffName.value = currentUser.full_name;
                if (commentStaffRole) commentStaffRole.value = currentUser.role;
                if (rxDoctorName) rxDoctorName.value = currentUser.full_name;

                // Hide Add Patient button for non-receptionist / non-admin
                if (btnAddPatient && currentUser.role !== 'Receptionist' && currentUser.role !== 'Admin') {
                    btnAddPatient.style.display = 'none';
                }
            } else {
                window.location.href = '/login';
            }
        });

    function getRoleCssClass(role) {
        if (role.includes('Doctor')) return 'Doctor';
        if (role.includes('Nurse')) return 'Nurse';
        if (role === 'Receptionist') return 'Receptionist';
        return 'Doctor';
    }

    btnLogout.addEventListener('click', () => {
        fetch('/api/logout').then(() => window.location.href = '/login');
    });

    function initAudioContext() {
        if (!audioCtx) {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        }
        if (audioCtx.state === 'suspended') {
            audioCtx.resume();
        }
    }

    document.addEventListener('click', initAudioContext, { once: false });
    document.addEventListener('keydown', initAudioContext, { once: false });

    function playAlarmChime(isDoctorCall) {
        if (audioMuted) return;
        try {
            initAudioContext();
            if (!audioCtx) return;

            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();

            if (isDoctorCall) {
                osc.type = 'sawtooth';
                osc.frequency.setValueAtTime(880, audioCtx.currentTime);
                osc.frequency.setValueAtTime(440, audioCtx.currentTime + 0.2);
                osc.frequency.setValueAtTime(880, audioCtx.currentTime + 0.4);
                gain.gain.setValueAtTime(0.4, audioCtx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.9);
            } else {
                osc.type = 'sine';
                osc.frequency.setValueAtTime(587.33, audioCtx.currentTime);
                osc.frequency.setValueAtTime(880, audioCtx.currentTime + 0.15);
                gain.gain.setValueAtTime(0.3, audioCtx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.7);
            }

            osc.connect(gain);
            gain.connect(audioCtx.destination);
            osc.start();
            osc.stop(audioCtx.currentTime + 0.9);
        } catch (e) {
            console.log('Audio alert error:', e);
        }
    }

    btnSilenceAudio.addEventListener('click', () => {
        audioMuted = !audioMuted;
        btnSilenceAudio.textContent = audioMuted ? '🔇 Unmute Sound' : '🔊 Mute Sound';
        if (!audioMuted) playAlarmChime(false);
    });

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
    fetchPatients();

    socket.on('connect', () => {
        updateSocketUI(true);
        fetchPatients();
    });

    socket.on('disconnect', () => {
        updateSocketUI(false);
    });

    socket.on('connect_error', () => {
        updateSocketUI(false);
    });

    socket.on('nurse_call_alert', (callData) => {
        playAlarmChime(callData.call_type === 'DOCTOR_CALL' || callData.call_type === 'URGENT_EMERGENCY');
        fetchPatients();
    });

    socket.on('urgent_call_alert', (callData) => {
        playAlarmChime(true);
        if (emergencyBanner && alertMessage) {
            alertMessage.textContent = callData.message || `🚨 URGENT EMERGENCY ALERT FROM ROOM ${callData.room_no}, BED ${callData.bed_no}!`;
            emergencyBanner.classList.remove('hidden');
        }
        fetchPatients();
    });

    socket.on('call_updated', () => fetchPatients());
    socket.on('patient_updated', () => fetchPatients());
    socket.on('patient_added', () => fetchPatients());

    socket.on('new_action_log', (data) => {
        if (currentRecordBookPatientId === data.patient_id) {
            loadRecordBookTimeline(currentRecordBookPatientId);
        }
    });

    function fetchPatients() {
        const includeArchived = activeTab === 'ARCHIVED';
        fetch(`/api/patients?include_archived=${includeArchived}`)
            .then(res => res.json())
            .then(patients => {
                allPatients = patients;
                updateStats();
                renderPatientsGrid();
            });
    }

    function updateStats() {
        const docCalls = allPatients.filter(p => p.status === 'DOCTOR_CALL').length;
        const nurseCalls = allPatients.filter(p => p.status === 'NURSE_CALL').length;
        const pinned = allPatients.filter(p => p.is_pinned === 1).length;
        const activeCount = allPatients.filter(p => p.status !== 'DISCHARGED' && p.status !== 'DECEASED').length;

        statDoctorCalls.textContent = docCalls;
        statNurseCalls.textContent = nurseCalls;
        statPinnedCount.textContent = pinned;
        statTotalPatients.textContent = activeCount;

        if (docCalls > 0 || nurseCalls > 0) {
            emergencyBanner.classList.remove('hidden');
            if (docCalls > 0) {
                alertMessage.textContent = `🚨 EMERGENCY DOCTOR CALL ACTIVE (${docCalls} PATIENT(S))!`;
            } else {
                alertMessage.textContent = `🔔 NURSE CALL ACTIVE (${nurseCalls} PATIENT(S))!`;
            }
        } else {
            emergencyBanner.classList.add('hidden');
        }
    }

    function parseCustomFields(p) {
        if (!p || !p.custom_fields) return {};
        if (typeof p.custom_fields === 'object') return p.custom_fields;
        try {
            return JSON.parse(p.custom_fields);
        } catch (e) {
            return {};
        }
    }

    function renderPatientsGrid() {
        const query = searchInput.value.toLowerCase().trim();
        const wardVal = filterWard.value;
        const statusVal = filterStatus.value;
        const ageGroupVal = filterAgeGroup.value;
        const sortVal = sortBy.value;
        const role = currentUser ? currentUser.role : 'Doctor';

        // Toggle Search Clear Button visibility
        if (query) {
            searchClearBtn.classList.remove('hidden');
        } else {
            searchClearBtn.classList.add('hidden');
        }

        let filtered = allPatients.filter(p => {
            // 1. Extensive Search Matching (Name, Ward, Room, Bed, Doctor, Status, Age, Gender, Device, MAC, Custom Fields)
            if (query) {
                const customObj = parseCustomFields(p);
                const customTerms = Object.entries(customObj).map(([k, v]) => `${k} ${v}`).join(' ');

                const searchHaystack = [
                    p.patient_name || '',
                    p.ward || '',
                    p.room_no || '',
                    p.bed_no || '',
                    `room ${p.room_no}`,
                    `bed ${p.bed_no}`,
                    `${p.room_no}-${p.bed_no}`,
                    p.assigned_doctor_name || '',
                    p.status || '',
                    p.gender || '',
                    p.id_card_type || '',
                    p.id_card_no || '',
                    p.aadhar_no || '',
                    p.mobile_no || '',
                    p.alt_mobile_no || '',
                    p.emergency_contact_name || '',
                    p.cause_of_admission || '',
                    p.admitted_by || '',
                    p.referred_by || '',
                    p.admission_notes || '',
                    p.comments || '',
                    customTerms,
                    p.esp_device_id || '',
                    p.esp_mac || '',
                    String(p.age || '')
                ].join(' ').toLowerCase();

                if (!searchHaystack.includes(query)) return false;
            }

            // 2. Preset Tab Filtering
            if (activeTab === 'MY_PATIENTS' && p.is_selected !== 1) return false;
            if (activeTab === 'PINNED' && p.is_pinned !== 1) return false;
            if (activeTab === 'ACTIVE_CALLS' && (p.status !== 'NURSE_CALL' && p.status !== 'DOCTOR_CALL')) return false;
            if (activeTab === 'IN_TREATMENT' && p.status !== 'IN_TREATMENT') return false;
            if (activeTab === 'ARCHIVED' && (p.status !== 'DISCHARGED' && p.status !== 'DECEASED')) return false;

            // 3. Department / Ward Filtering
            if (wardVal !== 'ALL' && (p.ward || '').toLowerCase() !== wardVal.toLowerCase()) return false;

            // 4. Clinical Status Filtering
            if (statusVal !== 'ALL' && p.status !== statusVal) return false;

            // 5. Demographics Age Group Filtering
            if (ageGroupVal === 'PEDIATRIC' && (p.age || 0) >= 18) return false;
            if (ageGroupVal === 'ADULT' && ((p.age || 0) < 18 || (p.age || 0) > 60)) return false;
            if (ageGroupVal === 'SENIOR' && (p.age || 0) <= 60) return false;

            return true;
        });

        // Sorting Logic
        filtered.sort((a, b) => {
            if (sortVal === 'PRIORITY') {
                const priorityScore = (p) => {
                    if (p.status === 'DOCTOR_CALL') return 40;
                    if (p.status === 'NURSE_CALL') return 30;
                    if (p.is_pinned === 1) return 20;
                    if (p.status === 'IN_TREATMENT') return 10;
                    return 0;
                };
                return priorityScore(b) - priorityScore(a);
            }
            if (sortVal === 'ROOM_ASC') {
                return a.room_no.localeCompare(b.room_no, undefined, { numeric: true }) || a.bed_no.localeCompare(b.bed_no);
            }
            if (sortVal === 'ROOM_DESC') {
                return b.room_no.localeCompare(a.room_no, undefined, { numeric: true }) || b.bed_no.localeCompare(a.bed_no);
            }
            if (sortVal === 'NAME_ASC') {
                return a.patient_name.localeCompare(b.patient_name);
            }
            if (sortVal === 'NAME_DESC') {
                return b.patient_name.localeCompare(a.patient_name);
            }
            if (sortVal === 'DATE_DESC') {
                return (b.admitted_at || '').localeCompare(a.admitted_at || '');
            }
            if (sortVal === 'DATE_ASC') {
                return (a.admitted_at || '').localeCompare(b.admitted_at || '');
            }
            if (sortVal === 'AGE_ASC') {
                return (a.age || 0) - (b.age || 0);
            }
            if (sortVal === 'AGE_DESC') {
                return (b.age || 0) - (a.age || 0);
            }
            return 0;
        });

        // Update Results Match Counter Badge
        resultsCountBadge.textContent = `Showing ${filtered.length} of ${allPatients.length} patient records`;

        // Toggle Reset Button Visibility
        const isModifiedFilter = query !== '' || wardVal !== 'ALL' || statusVal !== 'ALL' || ageGroupVal !== 'ALL' || activeTab !== 'MY_PATIENTS';
        if (isModifiedFilter) {
            btnResetFilters.classList.remove('hidden');
        } else {
            btnResetFilters.classList.add('hidden');
        }

        if (filtered.length === 0) {
            patientsContainer.innerHTML = `
                <div style="grid-column: 1 / -1; text-align: center; color: var(--text-secondary); padding: 45px 20px; background: var(--card-bg); border-radius: 12px; border: 1px dashed var(--border-color);">
                    <div style="font-size: 2.5rem; margin-bottom: 10px;">🔍</div>
                    <div style="font-size: 1.1rem; font-weight: bold; color: var(--text-primary);">No matching patient records found</div>
                    <div style="font-size: 0.88rem; margin-top: 6px;">Try adjusting your search terms, switching preset tabs, or clearing your active filters.</div>
                    <button class="btn-reset-filters" style="margin-top: 15px; display: inline-block;" onclick="resetAllFilters()">🔄 Reset All Filters</button>
                </div>
            `;
            return;
        }

        filtered.sort((a, b) => {
            if ((b.is_pinned || 0) !== (a.is_pinned || 0)) {
                return (b.is_pinned || 0) - (a.is_pinned || 0);
            }
            const aSla = a.min_remaining_seconds !== undefined && a.min_remaining_seconds !== null ? a.min_remaining_seconds : 999999999;
            const bSla = b.min_remaining_seconds !== undefined && b.min_remaining_seconds !== null ? b.min_remaining_seconds : 999999999;
            if (aSla !== bSla) {
                return aSla - bSla;
            }
            return a.id - b.id;
        });

        patientsContainer.innerHTML = filtered.map(p => {
            const isPinned = p.is_pinned === 1;
            const isSelected = p.is_selected === 1;
            const statusClass = p.status || 'NORMAL';
            let statusLabel = 'NORMAL / RESTING';
            const countStr = (p.active_call_count && p.active_call_count > 1) ? ` [Requested ${p.active_call_count}x]` : '';
            const timeStr = p.active_call_time ? ` (at ${p.active_call_time})` : '';
            if (p.status === 'NURSE_CALL') statusLabel = `🔔 NURSE CALLED${timeStr}${countStr}`;
            if (p.status === 'DOCTOR_CALL') statusLabel = `🚨 EMERGENCY DOCTOR CALL${timeStr}${countStr}`;
            if (p.status === 'GENERAL_HELP') statusLabel = `🤝 GENERAL HELP CALLED${timeStr}${countStr}`;
            if (p.status === 'URGENT_EMERGENCY') statusLabel = `🚨 URGENT EMERGENCY CALL${timeStr}${countStr}`;
            if (p.status === 'IN_TREATMENT') statusLabel = `💊 IN TREATMENT${timeStr}`;
            if (p.status === 'DISCHARGED') statusLabel = '✅ DISCHARGED / TREATMENT OVER';
            if (p.status === 'DECEASED') statusLabel = '⚰️ DECEASED';

            // Role-based button visibility flags
            const canPrescribe = role.includes('Doctor') || role === 'Admin';
            const canCallActions = role.includes('Nurse') || role.includes('Doctor') || role === 'Admin';
            const canManagePatient = role === 'Receptionist' || role === 'Admin';
            const canEditHealth = role.includes('Doctor') || role.includes('Nurse') || role === 'Admin';

            const healthPct = (p.health_condition !== undefined && p.health_condition !== null) ? p.health_condition : 100;
            let healthBg = '#22c55e';
            let healthText = 'Stable';
            if (healthPct < 50) {
                healthBg = '#ef4444';
                healthText = 'Critical';
            } else if (healthPct < 80) {
                healthBg = '#eab308';
                healthText = 'Under Watch';
            }

            return `
                <div class="patient-card ${isPinned ? 'is-pinned' : ''} status-${statusClass}">
                    <div>
                        <div class="patient-card-header">
                            <span class="room-bed-badge">${escapeHtml(p.ward || 'General Ward')} | Rm ${escapeHtml(p.room_no)} Bed ${escapeHtml(p.bed_no)}</span>
                            <div style="display:flex; align-items:center; gap:8px;">
                                <label style="font-size:0.8rem; cursor:pointer; color:var(--text-secondary); display:flex; align-items:center; gap:4px;" title="Select/Unselect for My Patients view">
                                    <input type="checkbox" ${isSelected ? 'checked' : ''} onchange="toggleSelect(${p.id})">
                                    Track
                                </label>
                                <button class="pin-star ${isPinned ? 'pinned' : 'unpinned'}" title="${isPinned ? 'Unstar Patient (Pinned to top)' : 'Star Patient to Pin to top'}" onclick="togglePin(${p.id})">${isPinned ? '⭐' : '☆'}</button>
                            </div>
                        </div>
                        <div class="patient-name" style="display:flex; align-items:center; justify-space-between;">
                            <span>${escapeHtml(p.patient_name)}</span>
                            <span style="font-size:0.8rem; background:${healthBg}; color:#fff; font-weight:bold; padding:2px 8px; border-radius:6px; margin-left: auto;">❤️ ${healthPct}% (${healthText})</span>
                        </div>
                        <div class="patient-meta">
                            Age: ${p.age || 'N/A'} | Gender: ${escapeHtml(p.gender || 'N/A')} | Doctor: <strong style="color:var(--accent-blue);">${escapeHtml(p.assigned_doctor_name || 'Unassigned')}</strong>
                        </div>
                        <div class="patient-meta" style="font-size:0.8rem; color:var(--text-secondary); margin-top:2px;">
                            🆔 <strong>${escapeHtml(p.id_card_type || 'Aadhar Card')}:</strong> ${escapeHtml(p.id_card_no || p.aadhar_no || 'N/A')} | 📞 <strong>Mobile:</strong> ${escapeHtml(p.mobile_no || 'N/A')}${p.alt_mobile_no && p.alt_mobile_no !== 'N/A' ? ` (Alt: ${escapeHtml(p.alt_mobile_no)})` : ''}
                        </div>
                        ${p.emergency_contact_name && p.emergency_contact_name !== 'N/A' ? `<div class="patient-meta" style="font-size:0.8rem; color:var(--text-secondary); margin-top:2px;">🚨 <strong>Emergency Contact:</strong> ${escapeHtml(p.emergency_contact_name)}</div>` : ''}
                        <div class="patient-meta" style="font-size:0.8rem; color:var(--text-secondary); margin-top:2px;">
                            📋 <strong>Cause:</strong> ${escapeHtml(p.cause_of_admission || 'General Checkup')} | 🏥 <strong>Ref By:</strong> ${escapeHtml(p.referred_by || 'Self / Walk-in')}
                        </div>
                        ${p.comments && p.comments !== 'N/A' ? `<div class="patient-meta" style="font-size:0.8rem; color:var(--text-secondary); margin-top:2px;">💬 <strong>Comments:</strong> ${escapeHtml(p.comments)}</div>` : ''}
                        ${(() => {
                            const customObj = parseCustomFields(p);
                            const customEntries = Object.entries(customObj);
                            if (customEntries.length === 0) return '';
                            return `<div class="patient-meta" style="font-size:0.8rem; color:var(--accent-blue); margin-top:2px;">${customEntries.map(([k, v]) => `🏷️ <strong>${escapeHtml(k)}:</strong> ${escapeHtml(v)}`).join(' | ')}</div>`;
                        })()}
                        ${(() => {
                            if (!p.active_service_requests || p.active_service_requests.length === 0) return '';
                            return p.active_service_requests.map(req => {
                                const remainingMins = Math.max(0, Math.floor(Math.abs(req.remaining_seconds) / 60));
                                const remainingSecs = Math.max(0, Math.abs(req.remaining_seconds) % 60);
                                const isOverdue = req.remaining_seconds <= 0;
                                const rolesArr = Array.isArray(req.target_roles) ? req.target_roles : [req.target_roles];
                                const slaText = isOverdue ? `⚡ OVERDUE by ${remainingMins}m ${remainingSecs}s` : `⏱️ SLA: ${req.target_minutes}m (Due in ${remainingMins}m ${remainingSecs}s)`;
                                
                                const taskCssClass = typeof getTaskCssClass === 'function' ? getTaskCssClass(rolesArr) : '';
                                const reqRoleColor = typeof getRoleColor === 'function' ? getRoleColor(req.requested_role, req.requested_by) : '#38bdf8';
                                const requestedByStyle = reqRoleColor === '#000000' 
                                    ? `color: #000000; background: #e2e8f0; padding: 1px 5px; border-radius: 4px; font-weight: bold;`
                                    : `color: ${reqRoleColor}; font-weight: bold;`;
                                
                                let solvedRoles = req.solved_by_roles || [];
                                if (typeof solvedRoles === 'string') {
                                    try { solvedRoles = JSON.parse(solvedRoles); } catch(e) { solvedRoles = []; }
                                }
                                
                                const badgesHtml = rolesArr.map(r => {
                                    const isSolved = solvedRoles.includes(r);
                                    const col = typeof getRoleColor === 'function' ? getRoleColor(r) : '#38bdf8';
                                    const styleText = isSolved 
                                        ? `background:#334155; color:#94a3b8; border:1px dashed #64748b; text-decoration:line-through;`
                                        : `background:${col}22; color:${col}; border:1px solid ${col};`;
                                    
                                    return `<span style="padding:2px 8px; border-radius:12px; font-weight:bold; font-size:0.75rem; margin-right:4px; ${styleText}">${escapeHtml(r)}${isSolved ? ' ✓' : ''}</span>`;
                                }).join('');

                                const userRole = (currentUser ? currentUser.role : role) || '';
                                const isAdmin = userRole === 'Admin';
                                const isDoctor = userRole.includes('Doctor');
                                const isNurse = userRole.includes('Nurse');
                                const isHelper = userRole.includes('General Helper') || userRole.includes('Helper');

                                let canServeThisTask = false;
                                rolesArr.forEach(tr => {
                                    const trLower = String(tr || '').toLowerCase();
                                    const isSolved = solvedRoles.includes(tr);
                                    if (!isSolved) {
                                        if (trLower.includes('doctor') && isDoctor) canServeThisTask = true;
                                        if (trLower.includes('nurse') && isNurse) canServeThisTask = true;
                                        if (trLower.includes('helper') && isHelper) canServeThisTask = true;
                                    }
                                });
                                const isCreator = currentUser && req.requested_by === currentUser.full_name;
                                if ((isAdmin || isCreator) && solvedRoles.length < rolesArr.length) canServeThisTask = true;

                                return `
                                    <div class="${taskCssClass}" style="background: rgba(15, 23, 42, 0.6); border-radius: 8px; padding: 10px 12px; margin-top: 8px; text-align: left;">
                                        <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.82rem; font-weight:bold; flex-wrap:wrap; gap:4px;">
                                            <div style="display:flex; align-items:center; flex-wrap:wrap; gap:4px;">
                                                <span style="color:var(--text-secondary); margin-right:4px;">📢 Target <span style="font-size:0.7rem; color:var(--text-muted);">[${escapeHtml(req.sla_tracking_id || "ID-PENDING")}]</span>:</span>
                                                ${badgesHtml}
                                            </div>
                                            <span style="color:${isOverdue ? '#ef4444' : '#eab308'}; font-weight:800;">${slaText}</span>
                                        </div>
                                        <div style="font-size:0.88rem; color:var(--text-primary); margin-top:6px; font-weight:600;">
                                            📝 ${escapeHtml(req.instructions)}
                                        </div>
                                        <div style="font-size:0.76rem; color:var(--text-secondary); margin-top:6px; display:flex; justify-content:space-between; flex-wrap:wrap; gap:5px;">
                                            <span>📅 Requested: <strong>${escapeHtml(req.created_at)}</strong> by <strong style="${requestedByStyle}">${escapeHtml(req.requested_by)} (${escapeHtml(req.requested_role)})</strong></span>
                                            ${req.due_by_time ? `<span>⏱️ Due By: <strong style="color:${isOverdue ? '#ef4444' : '#eab308'}">${escapeHtml(req.due_by_time)}</strong></span>` : ''}
                                        </div>
                                        <div style="display:flex; justify-content:flex-end; align-items:center; margin-top:6px;">
                                            ${canServeThisTask ? `
                                                <button onclick="serveServiceRequestFromCard(${req.id})" style="background:#22c55e; color:#fff; border:none; border-radius:6px; padding:4px 10px; font-size:0.78rem; font-weight:bold; cursor:pointer;">✅ Mark Served</button>
                                            ` : `
                                                <span style="font-size:0.75rem; color:var(--text-secondary); font-style:italic;">🔒 Action Restricted to ${escapeHtml(rolesArr.join(', '))}</span>
                                            `}
                                        </div>
                                    </div>
                                `;
                            }).join('');
                        })()}
                        ${(() => {
                            if (!p.active_calls || p.active_calls.length === 0) {
                                return `
                                    <div class="call-status-box ${statusClass}">
                                        ${statusLabel}
                                    </div>
                                `;
                            }
                            return p.active_calls.map(ac => {
                                let boxBg = 'rgba(234, 179, 8, 0.12)';
                                let boxBorder = '#eab308';
                                let titleColor = '#eab308';
                                let pulseClass = 'task-box-nurse';
                                if (ac.category === 'Doctor') {
                                    boxBg = 'rgba(59, 130, 246, 0.12)';
                                    boxBorder = '#3b82f6';
                                    titleColor = '#60a5fa';
                                    pulseClass = 'task-box-doctor';
                                } else if (ac.category === 'General Helper') {
                                    boxBg = 'rgba(34, 197, 94, 0.12)';
                                    boxBorder = '#22c55e';
                                    titleColor = '#4ade80';
                                    pulseClass = 'task-box-helper';
                                }

                                const userRole = (currentUser ? currentUser.role : role) || '';
                                const isAdmin = userRole === 'Admin';
                                const isDoctor = userRole.includes('Doctor');
                                const isNurse = userRole.includes('Nurse');
                                const isHelper = userRole.includes('General Helper') || userRole.includes('Helper');

                                let canPerformThisCall = isAdmin;
                                if (ac.category === 'Doctor' && isDoctor) canPerformThisCall = true;
                                if (ac.category === 'Nurse' && isNurse) canPerformThisCall = true;
                                if (ac.category === 'General Helper' && isHelper) canPerformThisCall = true;

                                const countText = ac.press_count > 1 ? ` <span style="background:${boxBorder}; color:#0f172a; border-radius:4px; padding:1px 6px; font-weight:800; font-size:0.75rem;">Requested ${ac.press_count}x</span>` : '';
                                const tsList = Array.isArray(ac.timestamps) ? ac.timestamps.join(', ') : ac.first_called_at;
                                const statusStr = ac.status === 'ACKNOWLEDGED' ? `<span style="color:#4ade80; font-weight:bold;">ACKNOWLEDGED by ${escapeHtml(ac.acknowledged_by || 'Staff')}</span>` : `<span style="color:#ef4444; font-weight:bold;">ACTIVE / PENDING</span>`;

                                return `
                                    <div class="${pulseClass}" style="background: ${boxBg}; border-radius: 8px; padding: 10px 12px; margin-top: 8px; text-align: left;">
                                        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:4px;">
                                            <span style="color:${titleColor}; font-weight:bold; font-size:0.9rem;">${ac.title}${countText}</span>
                                            <span style="font-size:0.78rem;">${statusStr}</span>
                                        </div>
                                        <div style="font-size:0.76rem; color:var(--text-secondary); margin-top:4px;">
                                            📅 <strong>Serially Requested at:</strong> <span style="font-family:monospace; color:var(--text-primary); font-weight:bold;">${escapeHtml(tsList)}</span>
                                        </div>
                                        ${canPerformThisCall ? `
                                            <div style="display:flex; justify-content:flex-end; align-items:center; gap:6px; margin-top:8px;">
                                                ${ac.status === 'ACTIVE' ? `
                                                    <button onclick="acknowledgeCall(${p.id}, '${ac.call_type}')" style="background:#eab308; color:#0f172a; border:none; border-radius:6px; padding:4px 10px; font-size:0.78rem; font-weight:bold; cursor:pointer;">Ack ${ac.category} Call</button>
                                                ` : ''}
                                                <button onclick="resolveCall(${p.id}, '${ac.call_type}')" style="background:#ef4444; color:#fff; border:none; border-radius:6px; padding:4px 10px; font-size:0.78rem; font-weight:bold; cursor:pointer;">Clear ${ac.category} Call</button>
                                            </div>
                                        ` : ''}
                                    </div>
                                `;
                            }).join('');
                        })()}
                    </div>
                    <div class="card-actions">
                        <button class="btn-card" style="background: rgba(59, 130, 246, 0.2); color: var(--accent-blue); border: 1px solid var(--accent-blue);" onclick="openServiceRequestModal(${p.id})">📢 Service Request</button>
                        ${canEditHealth ? `
                            <button class="btn-card" style="background: rgba(34, 197, 94, 0.15); color: #4ade80; border: 1px solid #22c55e;" onclick="openHealthModal(${p.id})">❤️ Edit Health (${healthPct}%)</button>
                        ` : ''}
                        ${canPrescribe ? `
                            <button class="btn-card" style="background: var(--accent-blue); color:#0f172a; font-weight:bold;" onclick="openPrescriptionModal(${p.id})">💊 Prescribe Rx</button>
                        ` : ''}
                        ${canManagePatient ? `
                            <button class="btn-card" style="background: #f59e0b; color:#fff;" onclick="openEditPatientModal(${p.id})">✏️ Edit</button>
                            <button class="btn-card" style="background: var(--accent-purple); color:#fff;" onclick="openTransferModal(${p.id})">🔄 Transfer Ward</button>
                            <button class="btn-card" style="background: var(--border-color); color:#fff;" onclick="openStatusModal(${p.id})">🏁 Discharge / Status</button>
                        ` : ''}
                        <button class="btn-card btn-record-book" onclick="openRecordBook(${p.id})">📖 Patient Record Book</button>
                    </div>
                </div>
            `;
        }).join('');
    }

    // Event Handlers for Extensive Searching & Filtering Controls
    searchInput.addEventListener('input', renderPatientsGrid);
    filterWard.addEventListener('change', renderPatientsGrid);
    filterStatus.addEventListener('change', renderPatientsGrid);
    filterAgeGroup.addEventListener('change', renderPatientsGrid);
    sortBy.addEventListener('change', renderPatientsGrid);

    searchClearBtn.addEventListener('click', () => {
        searchInput.value = '';
        renderPatientsGrid();
    });

    if (presetTabs) {
        presetTabs.addEventListener('click', (e) => {
            const btn = e.target.closest('.tab-btn');
            if (!btn) return;
            const newTab = btn.dataset.tab;
            if (newTab === activeTab) return;

            presetTabs.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const wasArchived = activeTab === 'ARCHIVED';
            activeTab = newTab;
            const isArchived = activeTab === 'ARCHIVED';

            if (wasArchived !== isArchived) {
                fetchPatients();
            } else {
                renderPatientsGrid();
            }
        });
    }

    window.resetAllFilters = function() {
        searchInput.value = '';
        filterWard.value = 'ALL';
        filterStatus.value = 'ALL';
        filterAgeGroup.value = 'ALL';
        sortBy.value = 'PRIORITY';
        
        activeTab = 'MY_PATIENTS';
        if (presetTabs) {
            presetTabs.querySelectorAll('.tab-btn').forEach(b => {
                if (b.dataset.tab === 'MY_PATIENTS') b.classList.add('active');
                else b.classList.remove('active');
            });
        }

        fetchPatients();
    };

    if (btnResetFilters) {
        btnResetFilters.addEventListener('click', window.resetAllFilters);
    }

    window.toggleSelect = function(patientId) {
        fetch('/api/patient/select', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ patient_id: patientId })
        }).then(() => fetchPatients());
    };

    window.togglePin = function(patientId) {
        fetch('/api/patient/pin', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ patient_id: patientId })
        }).then(() => fetchPatients());
    };

    window.acknowledgeCall = function(patientId, callType = null) {
        const staffName = (currentUser ? currentUser.full_name : 'Staff');
        const role = (currentUser ? currentUser.role : 'Nurse');
        const payload = { patient_id: patientId, staff_name: staffName, staff_role: role };
        if (callType) payload.call_type = callType;
        fetch('/api/call/acknowledge', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(r => r.json().then(data => ({ status: r.status, body: data })))
        .then(res => {
            if (res.status === 200 && res.body.status === 'success') {
                fetchPatients();
            } else {
                alert(`⚠️ ${res.body.message || 'Authorization failed: Only authorized roles can acknowledge this call.'}`);
            }
        });
    };

    window.resolveCall = function(patientId, callType = null) {
        const staffName = (currentUser ? currentUser.full_name : 'Staff');
        const role = (currentUser ? currentUser.role : 'Nurse');
        const payload = { patient_id: patientId, staff_name: staffName, staff_role: role };
        if (callType) payload.call_type = callType;
        fetch('/api/call/resolve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(r => r.json().then(data => ({ status: r.status, body: data })))
        .then(res => {
            if (res.status === 200 && res.body.status === 'success') {
                fetchPatients();
            } else {
                alert(`⚠️ ${res.body.message || 'Authorization failed: Only authorized roles can clear this call.'}`);
            }
        });
    };

    // Prescription Handlers
    window.openPrescriptionModal = function(patientId) {
        currentRxPatientId = patientId;
        const patient = allPatients.find(p => p.id === patientId);
        if (patient) {
            rxPatientInfo.innerHTML = `<div><strong>Patient:</strong> ${escapeHtml(patient.patient_name)} | Ward: ${escapeHtml(patient.ward || 'General')} | Rm ${escapeHtml(patient.room_no)} Bed ${escapeHtml(patient.bed_no)}</div>`;
        }
        if (currentUser) rxDoctorName.value = currentUser.full_name;
        loadPrescriptionsHistory(patientId);
        prescriptionModal.classList.remove('hidden');
    };

    btnCloseRxModal.addEventListener('click', () => prescriptionModal.classList.add('hidden'));

    function loadPrescriptionsHistory(patientId) {
        fetch(`/api/prescriptions/${patientId}`)
            .then(res => res.json())
            .then(items => {
                if (items.length === 0) {
                    rxHistoryContainer.innerHTML = `<div class="empty-state">No digital prescriptions issued yet.</div>`;
                    return;
                }
                rxHistoryContainer.innerHTML = items.map(item => `
                    <div class="timeline-item role-Doctor">
                        <div class="timeline-header">
                            <div><span class="role-tag Doctor">Doctor</span> <strong>${escapeHtml(item.doctor_name)}</strong></div>
                            <span class="timeline-time">${escapeHtml(item.created_at)}</span>
                        </div>
                        <div class="timeline-comment" style="font-size:1rem; font-weight:bold; color:var(--accent-blue);">💊 ${escapeHtml(item.medication)} (${escapeHtml(item.dosage)})</div>
                        <div style="font-size:0.85rem; color:var(--text-secondary); margin-top:4px;">Duration: ${escapeHtml(item.duration)} | Note: ${escapeHtml(item.instructions || 'N/A')}</div>
                    </div>
                `).join('');
            });
    }

    btnSaveRx.addEventListener('click', () => {
        if (!currentRxPatientId) return;
        const docName = currentUser ? currentUser.full_name : 'Dr. Smith';
        const med = rxMedication.value.trim();
        const dosage = rxDosage.value.trim() || '1 tablet daily';
        const duration = rxDuration.value.trim() || '5 days';
        const instructions = rxInstructions.value.trim() || 'Take after meals';

        if (!med) {
            alert('Please enter Medication name.');
            return;
        }

        fetch('/api/prescription/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                patient_id: currentRxPatientId,
                doctor_name: docName,
                medication: med,
                dosage: dosage,
                duration: duration,
                instructions: instructions
            })
        })
        .then(res => res.json())
        .then(() => {
            rxMedication.value = '';
            rxDosage.value = '';
            rxDuration.value = '';
            rxInstructions.value = '';
            loadPrescriptionsHistory(currentRxPatientId);
        });
    });

    // Transfer Modal
    window.openTransferModal = function(patientId) {
        currentTransferPatientId = patientId;
        const patient = allPatients.find(p => p.id === patientId);
        if (patient) {
            document.getElementById('transfer-room-no').value = patient.room_no;
            document.getElementById('transfer-bed-no').value = patient.bed_no;
        }
        transferModal.classList.remove('hidden');
    };

    btnCloseTransferModal.addEventListener('click', () => transferModal.classList.add('hidden'));

    btnSaveTransfer.addEventListener('click', () => {
        if (!currentTransferPatientId) return;
        const ward = document.getElementById('transfer-ward').value;
        const room = document.getElementById('transfer-room-no').value.trim();
        const bed = document.getElementById('transfer-bed-no').value.trim();
        const staff = (currentUser ? currentUser.full_name : 'Nurse');
        const role = (currentUser ? currentUser.role : 'Nurse');

        if (!room || !bed) {
            alert('Please enter a new room and bed number.');
            return;
        }

        fetch('/api/patient/transfer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                patient_id: currentTransferPatientId,
                new_ward: ward,
                new_room_no: room,
                new_bed_no: bed,
                staff_name: staff,
                staff_role: role
            })
        })
        .then(res => res.json())
        .then(() => {
            transferModal.classList.add('hidden');
            fetchPatients();
        });
    });

    // Status / Discharge Modal
    window.openStatusModal = function(patientId) {
        currentStatusPatientId = patientId;
        statusModal.classList.remove('hidden');
    };

    btnCloseStatusModal.addEventListener('click', () => statusModal.classList.add('hidden'));

    btnSaveStatus.addEventListener('click', () => {
        if (!currentStatusPatientId) return;
        const newStatus = document.getElementById('status-select').value;
        const staffName = currentUser ? currentUser.full_name : 'Doctor';
        const role = currentUser ? currentUser.role : 'Doctor';

        fetch('/api/patient/status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                patient_id: currentStatusPatientId,
                new_status: newStatus,
                staff_name: staffName,
                staff_role: role
            })
        })
        .then(res => res.json())
        .then(() => {
            statusModal.classList.add('hidden');
            fetchPatients();
        });
    });

    // Reports & Service Analytics Portal Handlers
    const reportStartDate = document.getElementById('report-start-date');
    const reportEndDate = document.getElementById('report-end-date');
    const reportWard = document.getElementById('report-ward');
    const reportRoleFilter = document.getElementById('report-role-filter');
    const reportActionType = document.getElementById('report-action-type');
    const reportGroupBy = document.getElementById('report-group-by');
    const reportChronology = document.getElementById('report-chronology');
    const reportMaskPrivacy = document.getElementById('report-mask-privacy');
    
    const btnRunReport = document.getElementById('btn-run-report');
    const btnPrintReport = document.getElementById('btn-print-report');

    const repStatTotal = document.getElementById('rep-stat-total');
    const repStatCalls = document.getElementById('rep-stat-calls');
    const repStatRx = document.getElementById('rep-stat-rx');
    const repStatTransfers = document.getElementById('rep-stat-transfers');

    const reportTableHead = document.getElementById('report-table-head');
    const reportTableBody = document.getElementById('report-table-body');

    btnOpenReports.addEventListener('click', () => {
        reportsModal.classList.remove('hidden');
        runReportQuery();
    });

    btnCloseReportsModal.addEventListener('click', () => reportsModal.classList.add('hidden'));

    function buildReportQueryParams() {
        const params = new URLSearchParams();
        if (reportStartDate && reportStartDate.value) params.append('start_date', reportStartDate.value);
        if (reportEndDate && reportEndDate.value) params.append('end_date', reportEndDate.value);
        if (reportWard && reportWard.value) params.append('ward', reportWard.value);
        if (reportRoleFilter && reportRoleFilter.value) params.append('role', reportRoleFilter.value);
        if (reportActionType && reportActionType.value) params.append('action_type', reportActionType.value);
        if (reportGroupBy && reportGroupBy.value) params.append('group_by', reportGroupBy.value);
        if (reportChronology) params.append('chronology', reportChronology.checked ? 'ASC' : 'DESC');
        if (reportMaskPrivacy) params.append('mask_privacy', reportMaskPrivacy.checked ? 'true' : 'false');
        return params.toString();
    }

    function runReportQuery() {
        const queryString = buildReportQueryParams();
        reportTableBody.innerHTML = `<tr><td colspan="8" style="text-align:center; color: var(--text-secondary);">Querying hospital service logs...</td></tr>`;

        fetch(`/api/reports/query?${queryString}`)
            .then(res => res.json())
            .then(resData => {
                if (resData.status !== 'success') {
                    alert(resData.message || 'Failed to execute report query.');
                    return;
                }

                const data = resData.data;
                const summary = data.summary || {};
                const rows = data.rows || [];
                const groupBy = data.group_by || 'DETAILED';

                // Update Analytics Summary Cards
                if (repStatTotal) repStatTotal.textContent = summary.total_events || 0;
                if (repStatCalls) repStatCalls.textContent = summary.call_acks || 0;
                if (repStatRx) repStatRx.textContent = summary.prescriptions || 0;
                if (repStatTransfers) repStatTransfers.textContent = summary.transfers || 0;

                // Render Table Header & Rows based on Group By
                if (groupBy === 'BY_DATE') {
                    reportTableHead.innerHTML = `
                        <tr>
                            <th>Date</th>
                            <th>Total Service Events</th>
                            <th>Calls Acknowledged</th>
                            <th>Prescriptions Issued</th>
                            <th>Transfers & Discharges</th>
                        </tr>
                    `;
                    if (rows.length === 0) {
                        reportTableBody.innerHTML = `<tr><td colspan="5" style="text-align:center; color: var(--text-secondary);">No logs match the query parameters.</td></tr>`;
                    } else {
                        reportTableBody.innerHTML = rows.map(r => `
                            <tr>
                                <td><strong>${escapeHtml(r.group_key)}</strong></td>
                                <td style="font-weight:bold; color:var(--accent-blue);">${r.total_events}</td>
                                <td>${r.calls}</td>
                                <td>${r.prescriptions}</td>
                                <td>${r.transfers}</td>
                            </tr>
                        `).join('');
                    }
                } else if (groupBy === 'BY_PATIENT') {
                    reportTableHead.innerHTML = `
                        <tr>
                            <th>Patient Identifier</th>
                            <th>Ward / Dept</th>
                            <th>Total Service Events</th>
                            <th>Calls Cleared</th>
                            <th>Prescriptions Issued</th>
                        </tr>
                    `;
                    if (rows.length === 0) {
                        reportTableBody.innerHTML = `<tr><td colspan="5" style="text-align:center; color: var(--text-secondary);">No logs match the query parameters.</td></tr>`;
                    } else {
                        reportTableBody.innerHTML = rows.map(r => `
                            <tr>
                                <td><strong>${escapeHtml(r.group_key)}</strong></td>
                                <td><span class="role-tag Nurse">${escapeHtml(r.ward || 'N/A')}</span></td>
                                <td style="font-weight:bold; color:var(--accent-blue);">${r.total_events}</td>
                                <td>${r.calls}</td>
                                <td>${r.prescriptions}</td>
                            </tr>
                        `).join('');
                    }
                } else if (groupBy === 'BY_WARD') {
                    reportTableHead.innerHTML = `
                        <tr>
                            <th>Ward / Department</th>
                            <th>Total Service Events</th>
                            <th>Calls Cleared</th>
                            <th>Prescriptions Issued</th>
                            <th>Transfers & Discharges</th>
                        </tr>
                    `;
                    if (rows.length === 0) {
                        reportTableBody.innerHTML = `<tr><td colspan="5" style="text-align:center; color: var(--text-secondary);">No logs match the query parameters.</td></tr>`;
                    } else {
                        reportTableBody.innerHTML = rows.map(r => `
                            <tr>
                                <td><strong>${escapeHtml(r.group_key)}</strong></td>
                                <td style="font-weight:bold; color:var(--accent-blue);">${r.total_events}</td>
                                <td>${r.calls}</td>
                                <td>${r.prescriptions}</td>
                                <td>${r.transfers}</td>
                            </tr>
                        `).join('');
                    }
                } else if (groupBy === 'BY_STAFF') {
                    reportTableHead.innerHTML = `
                        <tr>
                            <th>Staff Member & Role</th>
                            <th>Staff Name</th>
                            <th>Staff Role</th>
                            <th>Total Service Actions</th>
                            <th>Calls Cleared</th>
                            <th>Prescriptions Issued</th>
                        </tr>
                    `;
                    if (rows.length === 0) {
                        reportTableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; color: var(--text-secondary);">No logs match the query parameters.</td></tr>`;
                    } else {
                        reportTableBody.innerHTML = rows.map(r => `
                            <tr>
                                <td><strong>${escapeHtml(r.group_key)}</strong></td>
                                <td>${escapeHtml(r.staff_name)}</td>
                                <td><span class="role-tag ${getRoleCssClass(r.staff_role)}">${escapeHtml(r.staff_role)}</span></td>
                                <td style="font-weight:bold; color:var(--accent-blue);">${r.total_events}</td>
                                <td>${r.calls}</td>
                                <td>${r.prescriptions}</td>
                            </tr>
                        `).join('');
                    }
                } else {
                    // Detailed Log
                    reportTableHead.innerHTML = `
                        <tr>
                            <th>Timestamp</th>
                            <th>Patient Name</th>
                            <th>Ward</th>
                            <th>Rm / Bed</th>
                            <th>Staff Name</th>
                            <th>Role</th>
                            <th>Action Type</th>
                            <th>Comment / Details</th>
                        </tr>
                    `;
                    if (rows.length === 0) {
                        reportTableBody.innerHTML = `<tr><td colspan="8" style="text-align:center; color: var(--text-secondary);">No logs match the query parameters.</td></tr>`;
                    } else {
                        reportTableBody.innerHTML = rows.map(r => `
                            <tr>
                                <td style="font-size:0.8rem; color:var(--text-secondary); white-space:nowrap;">${escapeHtml(r.timestamp)}</td>
                                <td><strong>${escapeHtml(r.patient_name)}</strong></td>
                                <td>${escapeHtml(r.ward)}</td>
                                <td>${escapeHtml(r.room_no)}-${escapeHtml(r.bed_no)}</td>
                                <td>${escapeHtml(r.staff_name)}</td>
                                <td><span class="role-tag ${getRoleCssClass(r.staff_role)}">${escapeHtml(r.staff_role)}</span></td>
                                <td><span style="font-size:0.8rem; font-weight:bold; color:var(--accent-blue);">${escapeHtml(r.action_type)}</span></td>
                                <td style="font-size:0.85rem;">${escapeHtml(r.comment)}</td>
                            </tr>
                        `).join('');
                    }
                }
            });
    }

    if (btnRunReport) btnRunReport.addEventListener('click', runReportQuery);

    if (btnDownloadCsv) {
        btnDownloadCsv.addEventListener('click', () => {
            const queryString = buildReportQueryParams();
            window.location.href = `/api/reports/download?${queryString}`;
        });
    }

    if (btnPrintReport) {
        btnPrintReport.addEventListener('click', () => window.print());
    }

    // Record Book Modal
    window.openRecordBook = function(patientId) {
        currentRecordBookPatientId = patientId;
        const patient = allPatients.find(p => p.id === patientId);

        if (patient) {
            modalPatientInfo.innerHTML = `
                <div><strong>Patient:</strong> ${escapeHtml(patient.patient_name)} | Age: ${patient.age || 'N/A'} | Gender: ${escapeHtml(patient.gender || 'N/A')}</div>
                <div><strong>Ward:</strong> ${escapeHtml(patient.ward || 'General Ward')} (Rm ${escapeHtml(patient.room_no)}, Bed ${escapeHtml(patient.bed_no)})</div>
                <div><strong>Attending Doctor:</strong> <strong style="color:var(--accent-blue);">${escapeHtml(patient.assigned_doctor_name || 'Unassigned')}</strong></div>
                <div>🆔 <strong>${escapeHtml(patient.id_card_type || 'Aadhar Card')}:</strong> ${escapeHtml(patient.id_card_no || patient.aadhar_no || 'N/A')} | 📞 <strong>Mobile:</strong> ${escapeHtml(patient.mobile_no || 'N/A')}${patient.alt_mobile_no && patient.alt_mobile_no !== 'N/A' ? ` (Alt: ${escapeHtml(patient.alt_mobile_no)})` : ''}</div>
                ${patient.emergency_contact_name && patient.emergency_contact_name !== 'N/A' ? `<div>🚨 <strong>Emergency Contact:</strong> ${escapeHtml(patient.emergency_contact_name)}</div>` : ''}
                <div>📋 <strong>Cause of Admission:</strong> ${escapeHtml(patient.cause_of_admission || 'General Checkup')}</div>
                <div>👤 <strong>Admitted By:</strong> ${escapeHtml(patient.admitted_by || 'Reception Desk')} | 🏥 <strong>Referred By:</strong> ${escapeHtml(patient.referred_by || 'Self / Walk-in')}</div>
                ${patient.admission_notes && patient.admission_notes !== 'N/A' ? `<div>📝 <strong>Admission Notes:</strong> ${escapeHtml(patient.admission_notes)}</div>` : ''}
                ${patient.comments && patient.comments !== 'N/A' ? `<div>💬 <strong>Remarks & Comments:</strong> ${escapeHtml(patient.comments)}</div>` : ''}
                ${(() => {
                    const customObj = parseCustomFields(patient);
                    const customEntries = Object.entries(customObj);
                    if (customEntries.length === 0) return '';
                    return `<div>🏷️ <strong>Custom Parameters:</strong> ${customEntries.map(([k, v]) => `<strong>${escapeHtml(k)}:</strong> ${escapeHtml(v)}`).join(' | ')}</div>`;
                })()}
            `;
        }

        loadRecordBookTimeline(patientId);
        recordBookModal.classList.remove('hidden');
    };

    function loadRecordBookTimeline(patientId) {
        fetch(`/api/action_log/${patientId}`)
            .then(res => res.json())
            .then(data => {
                const logs = data.record_book || [];
                if (logs.length === 0) {
                    timelineContainer.innerHTML = `<div class="empty-state">No recorded notes yet.</div>`;
                    return;
                }

                timelineContainer.innerHTML = logs.map(log => {
                    const role = log.staff_role || 'Nurse';
                    let roleClass = 'Nurse';
                    if (role.includes('Doctor')) roleClass = 'Doctor';
                    else if (role.includes('Helper')) roleClass = 'General-Helper';
                    else if (role.includes('Admin')) roleClass = 'Admin';
                    else if (role.includes('Lab')) roleClass = 'Lab';
                    else if (role.includes('Receptionist')) roleClass = 'Receptionist';

                    let commentHtml = escapeHtml(log.comment);
                    if (commentHtml.includes('[SLA MET]')) {
                        commentHtml = commentHtml.replace('[SLA MET]', '<span class="sla-badge-met">✅ SLA MET</span>');
                    }
                    if (commentHtml.includes('[SLA BREACHED]')) {
                        commentHtml = commentHtml.replace('[SLA BREACHED]', '<span class="sla-badge-breached">🚨 SLA BREACHED</span>');
                    }

                    return `
                        <div class="timeline-item role-${roleClass} type-${log.action_type}" style="border-left-width: 4px; margin-bottom: 12px; background: rgba(30, 41, 59, 0.6); padding: 12px; border-radius: 8px;">
                            <div class="timeline-header" style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 6px;">
                                <div>
                                    <span class="role-tag ${roleClass}">${escapeHtml(log.staff_role)}</span>
                                    <strong style="margin-left: 8px; color: var(--text-primary); font-size: 0.95rem;">${escapeHtml(log.staff_name)}</strong>
                                </div>
                                <span class="timeline-time" style="font-size: 0.8rem; color: var(--text-secondary);">${escapeHtml(log.timestamp)}</span>
                            </div>
                            <div class="timeline-comment" style="font-size: 0.92rem; color: var(--text-primary); line-height: 1.4;">${commentHtml}</div>
                        </div>
                    `;
                }).join('');
            });
    }

    btnSubmitComment.addEventListener('click', () => {
        if (!currentRecordBookPatientId) return;
        const role = currentUser ? currentUser.role : 'Nurse';
        const name = currentUser ? currentUser.full_name : 'Staff';
        const text = commentText.value.trim();

        if (!text) {
            alert('Please enter a clinical note or comment.');
            return;
        }

        fetch('/api/action_log/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                patient_id: currentRecordBookPatientId,
                staff_name: name,
                staff_role: role,
                comment: text
            })
        })
        .then(res => res.json())
        .then(() => {
            commentText.value = '';
            loadRecordBookTimeline(currentRecordBookPatientId);
        });
    });

    const btnSubmitServed = document.getElementById('btn-submit-served');
    if (btnSubmitServed) {
        btnSubmitServed.addEventListener('click', () => {
            if (!currentRecordBookPatientId) return;
            const role = currentUser ? currentUser.role : 'Nurse';
            const name = currentUser ? currentUser.full_name : 'Staff';
            const text = commentText.value.trim() || 'Patient attended and served at bedside.';

            fetch('/api/call/serve', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    patient_id: currentRecordBookPatientId,
                    staff_name: name,
                    staff_role: role,
                    notes: text
                })
            })
            .then(res => res.json())
            .then(() => {
                commentText.value = '';
                loadRecordBookTimeline(currentRecordBookPatientId);
                fetchPatients();
            });
        });
    }

    btnCloseModal.addEventListener('click', () => {
        recordBookModal.classList.add('hidden');
        currentRecordBookPatientId = null;
    });

    // Dynamic Custom Fields & Values Handler
    function addCustomFieldRow(key = '', val = '') {
        const container = document.getElementById('custom-fields-container');
        if (!container) return;

        const row = document.createElement('div');
        row.className = 'custom-field-row form-row';
        row.style.cssText = 'display: flex; gap: 8px; align-items: center;';

        row.innerHTML = `
            <input type="text" class="custom-key flex-1" placeholder="Field Name (e.g. Blood Group)" value="${escapeHtml(key)}" style="font-size: 0.85rem; padding: 6px 10px;">
            <input type="text" class="custom-val flex-1" placeholder="Value (e.g. B+ / Star Health)" value="${escapeHtml(val)}" style="font-size: 0.85rem; padding: 6px 10px;">
            <button type="button" class="btn-remove-custom" title="Remove Field" style="background: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid #ef4444; border-radius: 6px; padding: 4px 10px; cursor: pointer; font-weight: bold;">&times;</button>
        `;

        row.querySelector('.btn-remove-custom').addEventListener('click', () => row.remove());
        container.appendChild(row);
    }

    const btnAddCustomField = document.getElementById('btn-add-custom-field');
    if (btnAddCustomField) {
        btnAddCustomField.addEventListener('click', () => addCustomFieldRow());
    }

    // Add Patient Modal
    if (btnAddPatient) btnAddPatient.addEventListener('click', () => addPatientModal.classList.remove('hidden'));
    if (btnCloseAddModal) btnCloseAddModal.addEventListener('click', () => addPatientModal.classList.add('hidden'));

    if (btnSavePatient) {
        btnSavePatient.addEventListener('click', () => {
            const name = document.getElementById('new-patient-name').value.trim();
            const ward = document.getElementById('new-ward').value;
            const room = document.getElementById('new-room-no').value.trim();
            const bed = document.getElementById('new-bed-no').value.trim();
            const age = document.getElementById('new-age').value.trim();
            const gender = document.getElementById('new-gender').value;
            const idTypeEl = document.getElementById('new-id-type');
            const idCardNoEl = document.getElementById('new-id-card-no');
            const mobileNoEl = document.getElementById('new-mobile-no');
            const altMobileNoEl = document.getElementById('new-alt-mobile-no');
            const emergencyContactEl = document.getElementById('new-emergency-contact');
            const causeEl = document.getElementById('new-cause');
            const admittedByEl = document.getElementById('new-admitted-by');
            const referredByEl = document.getElementById('new-referred-by');
            const notesEl = document.getElementById('new-admission-notes');
            const commentsEl = document.getElementById('new-comments');
            const espId = document.getElementById('new-esp-id').value.trim();

            const idType = idTypeEl ? idTypeEl.value : 'Aadhar Card';
            const idCardNo = idCardNoEl ? idCardNoEl.value.trim() : 'N/A';
            const mobileNo = mobileNoEl ? mobileNoEl.value.trim() : 'N/A';
            const altMobileNo = altMobileNoEl ? altMobileNoEl.value.trim() : 'N/A';
            const emergencyContact = emergencyContactEl ? emergencyContactEl.value.trim() : 'N/A';
            const cause = causeEl ? causeEl.value.trim() : 'General Checkup';
            const admittedBy = admittedByEl && admittedByEl.value.trim() ? admittedByEl.value.trim() : (currentUser ? currentUser.full_name : 'Reception Desk');
            const referredBy = referredByEl ? referredByEl.value.trim() : 'Self / Walk-in';
            const notes = notesEl ? notesEl.value.trim() : 'N/A';
            const comments = commentsEl ? commentsEl.value.trim() : 'N/A';

            // Collect dynamic custom fields
            const customFieldsObj = {};
            const customContainer = document.getElementById('custom-fields-container');
            if (customContainer) {
                customContainer.querySelectorAll('.custom-field-row').forEach(row => {
                    const k = row.querySelector('.custom-key').value.trim();
                    const v = row.querySelector('.custom-val').value.trim();
                    if (k && v) {
                        customFieldsObj[k] = v;
                    }
                });
            }

            if (!name || !room || !bed) {
                alert('Please fill in Patient Name, Room Number, and Bed Number.');
                return;
            }

            fetch('/api/patient/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    patient_name: name,
                    ward: ward,
                    room_no: room,
                    bed_no: bed,
                    age: age ? parseInt(age) : 0,
                    gender: gender,
                    id_card_type: idType,
                    id_card_no: idCardNo,
                    aadhar_no: idCardNo,
                    mobile_no: mobileNo,
                    alt_mobile_no: altMobileNo,
                    emergency_contact_name: emergencyContact,
                    cause_of_admission: cause,
                    admitted_by: admittedBy,
                    referred_by: referredBy,
                    admission_notes: notes,
                    comments: comments,
                    custom_fields: customFieldsObj,
                    esp_device_id: espId
                })
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    addPatientModal.classList.add('hidden');
                    document.getElementById('new-patient-name').value = '';
                    document.getElementById('new-room-no').value = '';
                    document.getElementById('new-bed-no').value = '';
                    if (idCardNoEl) idCardNoEl.value = '';
                    if (mobileNoEl) mobileNoEl.value = '';
                    if (altMobileNoEl) altMobileNoEl.value = '';
                    if (emergencyContactEl) emergencyContactEl.value = '';
                    if (causeEl) causeEl.value = '';
                    if (referredByEl) referredByEl.value = '';
                    if (notesEl) notesEl.value = '';
                    if (commentsEl) commentsEl.value = '';
                    if (customContainer) customContainer.innerHTML = '';
                    fetchPatients();
                } else {
                    alert(data.message || 'Failed to add patient.');
                }
            });
        });
    }

    const btnOpenServiceDispatch = document.getElementById('btn-open-service-dispatch');
    const serviceWardFilter = document.getElementById('service-ward-filter');
    const servicePatientSelect = document.getElementById('service-patient-select');
    const serviceRoomNo = document.getElementById('service-room-no');
    const serviceBedNo = document.getElementById('service-bed-no');
    let allBedsList = [];

    function populateServicePatientSelect(selectedId = null) {
        fetch('/api/bedside/search_beds')
            .then(r => r.json())
            .then(beds => {
                allBedsList = beds;
                if (!servicePatientSelect) return;

                const currentWard = serviceWardFilter ? serviceWardFilter.value : '';
                const wards = Array.from(new Set(beds.map(b => b.ward).filter(Boolean)));
                if (serviceWardFilter) {
                    serviceWardFilter.innerHTML = '<option value="">🏢 All Wards</option>' +
                        wards.map(w => `<option value="${w}" ${w === currentWard ? 'selected' : ''}>🏥 ${w}</option>`).join('');
                }

                let filtered = beds;
                if (currentWard) {
                    filtered = beds.filter(b => b.ward === currentWard);
                }

                servicePatientSelect.innerHTML = '<option value="">-- Select Patient Bed --</option>' +
                    filtered.map(b => `<option value="${b.patient_id}" data-room="${b.room_no}" data-bed="${b.bed_no}" ${b.patient_id === selectedId ? 'selected' : ''}>[${b.ward || 'General'}] Room ${b.room_no} Bed ${b.bed_no} - ${b.patient_name} (Health: ${b.health_condition}%)</option>`).join('');

                if (selectedId) {
                    const selBed = beds.find(b => b.patient_id === selectedId);
                    if (selBed) {
                        if (serviceRoomNo) serviceRoomNo.value = selBed.room_no;
                        if (serviceBedNo) serviceBedNo.value = selBed.bed_no;
                    }
                }
            });
    }

    if (serviceWardFilter) {
        serviceWardFilter.addEventListener('change', () => populateServicePatientSelect(currentServicePatientId));
    }

    if (btnOpenServiceDispatch) {
        btnOpenServiceDispatch.addEventListener('click', () => {
            populateServicePatientSelect(currentServicePatientId);
            if (serviceRequestPatientInfo) serviceRequestPatientInfo.textContent = 'Select a target patient bed or enter Room & Bed number:';
            if (servicePresetSelect) servicePresetSelect.value = 'Custom Instruction';
            if (serviceInstructions) serviceInstructions.value = '';
            if (serviceTargetMinutes) serviceTargetMinutes.value = '15';
            if (serviceRequestModal) serviceRequestModal.classList.remove('hidden');
        });
    }

    if (servicePatientSelect) {
        servicePatientSelect.addEventListener('change', () => {
            const pId = parseInt(servicePatientSelect.value);
            if (pId) {
                currentServicePatientId = pId;
                const patient = (allPatients && allPatients.length ? allPatients : allBedsList).find(p => (p.id === pId || p.patient_id === pId));
                if (patient) {
                    serviceRequestPatientInfo.textContent = `Target Patient: ${patient.patient_name} | Ward: ${patient.ward || 'General Ward'} (Room ${patient.room_no}, Bed ${patient.bed_no})`;
                    if (serviceRoomNo) serviceRoomNo.value = patient.room_no;
                    if (serviceBedNo) serviceBedNo.value = patient.bed_no;
                }
            }
        });
    }

    // Service Request Modal Handlers
    const serviceRequestModal = document.getElementById('service-request-modal');
    const btnCloseServiceRequestModal = document.getElementById('btn-close-service-request-modal');
    const serviceRequestPatientInfo = document.getElementById('service-request-patient-info');
    const serviceTargetMinutes = document.getElementById('service-target-minutes');
    const servicePresetSelect = document.getElementById('service-preset-select');
    const serviceInstructions = document.getElementById('service-instructions');
    const btnSendServiceRequest = document.getElementById('btn-send-service-request');
    let currentServicePatientId = null;

    window.serveServiceRequestFromCard = function(reqId) {
        const userRole = (currentUser ? currentUser.role : role) || 'Staff';
        let customNotes = prompt("Optional: Add notes/comments for this task (leave empty for default):");
        if (customNotes === null) return; // User clicked Cancel
        if (!customNotes.trim()) customNotes = 'Service completed from patient card.';

        fetch('/api/service_request/serve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                request_id: reqId,
                served_by: currentUser ? currentUser.full_name : 'Staff',
                staff_role: userRole,
                notes: customNotes
            })
        })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'success') {
                fetchPatients();
            } else if (data.message) {
                alert(`Action Restricted: ${data.message}`);
            }
        });
    };

    window.openServiceRequestModal = function(patientId) {
        currentServicePatientId = patientId;
        populateServicePatientSelect(patientId);
        const patient = (allPatients && allPatients.length ? allPatients : allBedsList).find(p => (p.id === patientId || p.patient_id === patientId));
        if (patient) {
            serviceRequestPatientInfo.textContent = `Patient: ${patient.patient_name} | Ward: ${patient.ward || 'General Ward'} (Room ${patient.room_no}, Bed ${patient.bed_no})`;
            if (serviceRoomNo) serviceRoomNo.value = patient.room_no;
            if (serviceBedNo) serviceBedNo.value = patient.bed_no;
        }
        if (servicePresetSelect) servicePresetSelect.value = 'Custom Instruction';
        if (serviceInstructions) serviceInstructions.value = '';
        if (serviceTargetMinutes) serviceTargetMinutes.value = '15';
        if (serviceRequestModal) serviceRequestModal.classList.remove('hidden');
    };

    if (btnCloseServiceRequestModal) {
        btnCloseServiceRequestModal.addEventListener('click', () => {
            if (serviceRequestModal) serviceRequestModal.classList.add('hidden');
            currentServicePatientId = null;
        });
    }

    if (servicePresetSelect) {
        servicePresetSelect.addEventListener('change', () => {
            if (servicePresetSelect.value !== 'Custom Instruction') {
                serviceInstructions.value = servicePresetSelect.value;
            } else {
                serviceInstructions.value = '';
            }
        });
    }

    if (btnSendServiceRequest) {
        btnSendServiceRequest.addEventListener('click', () => {
            if (!currentServicePatientId) {
                alert('Please select a target patient bed.');
                return;
            }
            const patient = allPatients.find(p => p.id === currentServicePatientId);
            const text = serviceInstructions.value.trim() || servicePresetSelect.value;

            const selectedRoles = [];
            document.querySelectorAll('.target-role-cb:checked').forEach(cb => {
                selectedRoles.push(cb.value);
            });

            if (selectedRoles.length === 0) {
                alert('Please select at least one recipient role (Doctor, Nurse, or General Helper).');
                return;
            }

            if (!text) {
                alert('Please enter instructions for the request.');
                return;
            }

            const targetMins = parseInt(serviceTargetMinutes.value) || 15;
            const staffName = currentUser ? currentUser.full_name : 'Staff';
            const role = currentUser ? currentUser.role : 'Doctor';

            fetch('/api/service_request/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    patient_id: currentServicePatientId,
                    room_no: patient ? patient.room_no : '',
                    bed_no: patient ? patient.bed_no : '',
                    ward: patient ? patient.ward : 'General Ward',
                    target_roles: selectedRoles,
                    instructions: text,
                    target_minutes: targetMins,
                    requested_by: staffName,
                    requested_role: role
                })
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    if (serviceRequestModal) serviceRequestModal.classList.add('hidden');
                    alert(`✅ Service Request dispatched to [${selectedRoles.join(', ')}] with ${targetMins}m SLA!`);
                    fetchPatients();
                } else {
                    alert(data.message || 'Failed to create service request.');
                }
            });
        });
    }

    // Health Condition Rating Modal Handlers
    const healthModal = document.getElementById('health-modal');
    const btnCloseHealthModal = document.getElementById('btn-close-health-modal');
    const healthModalPatientInfo = document.getElementById('health-modal-patient-info');
    const healthRangeInput = document.getElementById('health-range-input');
    const healthNumInput = document.getElementById('health-num-input');
    const btnSaveHealth = document.getElementById('btn-save-health');
    let currentHealthPatientId = null;

    window.openHealthModal = function(patientId) {
        currentHealthPatientId = patientId;
        const patient = allPatients.find(p => p.id === patientId);
        if (patient) {
            healthModalPatientInfo.textContent = `Patient: ${patient.patient_name} (Room ${patient.room_no}, Bed ${patient.bed_no})`;
            const currentPct = (patient.health_condition !== undefined && patient.health_condition !== null) ? patient.health_condition : 100;
            healthRangeInput.value = currentPct;
            healthNumInput.value = currentPct;
        }
        if (healthModal) healthModal.classList.remove('hidden');
    };

    if (btnCloseHealthModal) {
        btnCloseHealthModal.addEventListener('click', () => {
            if (healthModal) healthModal.classList.add('hidden');
            currentHealthPatientId = null;
        });
    }

    if (healthRangeInput && healthNumInput) {
        healthRangeInput.addEventListener('input', () => {
            healthNumInput.value = healthRangeInput.value;
        });
        healthNumInput.addEventListener('input', () => {
            let val = parseInt(healthNumInput.value) || 0;
            val = Math.max(0, Math.min(100, val));
            healthRangeInput.value = val;
        });
    }

    window.setHealthPreset = function(val) {
        if (healthRangeInput) healthRangeInput.value = val;
        if (healthNumInput) healthNumInput.value = val;
    };

    if (btnSaveHealth) {
        btnSaveHealth.addEventListener('click', () => {
            if (!currentHealthPatientId) return;
            const healthPct = parseInt(healthNumInput.value) || 100;
            const staffName = currentUser ? currentUser.full_name : 'Staff';
            const role = currentUser ? currentUser.role : 'Doctor';

            fetch('/api/patient/health', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    patient_id: currentHealthPatientId,
                    health_condition: healthPct,
                    staff_name: staffName,
                    staff_role: role
                })
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    if (healthModal) healthModal.classList.add('hidden');
                    alert(`✅ Patient Health Condition updated to ${healthPct}%!`);
                    fetchPatients();
                } else {
                    alert(data.message || 'Failed to update health condition.');
                }
            });
        });
    }

    // Notice Board & Chat Box Handlers
    const noticeBoardModal = document.getElementById('notice-board-modal');
    const btnOpenNoticeBoard = document.getElementById('btn-open-notice-board');
    const btnCloseNoticeBoardModal = document.getElementById('btn-close-notice-board-modal');
    const chatTargetDept = document.getElementById('chat-target-dept');
    const chatPriority = document.getElementById('chat-priority');
    const chatMessageInput = document.getElementById('chat-message-input');
    const btnSendChatMsg = document.getElementById('btn-send-chat-msg');
    const chatFilterDept = document.getElementById('chat-filter-dept');
    const noticeMessagesContainer = document.getElementById('notice-messages-container');

    function loadNoticeBoardMessages() {
        const dept = chatFilterDept ? chatFilterDept.value : 'ALL';
        fetch(`/api/chat/messages?department=${encodeURIComponent(dept)}`)
            .then(r => r.json())
            .then(messages => {
                if (!noticeMessagesContainer) return;
                if (!messages || messages.length === 0) {
                    noticeMessagesContainer.innerHTML = '<div class="empty-state">No notice board messages posted yet.</div>';
                    return;
                }

                noticeMessagesContainer.innerHTML = messages.map(msg => renderChatMessageHtml(msg)).join('');
            });
    }

    function renderChatMessageHtml(msg) {
        const isUrgent = msg.priority === 'URGENT';
        const isAnnouncement = msg.priority === 'ANNOUNCEMENT';

        let badgeBg = 'rgba(59, 130, 246, 0.2)';
        let badgeColor = '#60a5fa';
        let badgeLabel = '💬 Chat';

        if (isUrgent) {
            badgeBg = 'rgba(239, 68, 68, 0.2)';
            badgeColor = '#f87171';
            badgeLabel = '⚡ URGENT';
        } else if (isAnnouncement) {
            badgeBg = 'rgba(168, 85, 247, 0.2)';
            badgeColor = '#c084fc';
            badgeLabel = '📢 ANNOUNCEMENT';
        }

        const deptStr = msg.target_department === 'ALL' ? '🌐 All Departments' : `🏥 ${msg.target_department}`;

        return `
            <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-left: 4px solid ${badgeColor}; padding: 12px; border-radius: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.82rem; margin-bottom: 6px;">
                    <div>
                        <span class="role-tag ${getRoleCssClass(msg.sender_role)}">${escapeHtml(msg.sender_role)}</span>
                        <strong style="margin-left: 6px; color: var(--text-primary);">${escapeHtml(msg.sender_name)}</strong>
                        <span style="color: var(--text-secondary); margin-left: 8px;">➔ ${escapeHtml(deptStr)}</span>
                    </div>
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span style="background: ${badgeBg}; color: ${badgeColor}; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 0.75rem;">${badgeLabel}</span>
                        <span style="color: var(--text-secondary);">${escapeHtml(msg.created_at)}</span>
                    </div>
                </div>
                <div style="font-size: 0.95rem; color: var(--text-primary); line-height: 1.4;">
                    ${escapeHtml(msg.message)}
                </div>
            </div>
        `;
    }

    if (btnOpenNoticeBoard) {
        btnOpenNoticeBoard.addEventListener('click', () => {
            loadNoticeBoardMessages();
            if (noticeBoardModal) noticeBoardModal.classList.remove('hidden');
        });
    }

    if (btnCloseNoticeBoardModal) {
        btnCloseNoticeBoardModal.addEventListener('click', () => {
            if (noticeBoardModal) noticeBoardModal.classList.add('hidden');
        });
    }

    if (chatFilterDept) {
        chatFilterDept.addEventListener('change', loadNoticeBoardMessages);
    }

    if (btnSendChatMsg) {
        btnSendChatMsg.addEventListener('click', () => {
            const text = chatMessageInput.value.trim();
            if (!text) {
                alert('Please enter a message to post.');
                return;
            }

            const dept = chatTargetDept.value;
            const priority = chatPriority.value;
            const staffName = currentUser ? currentUser.full_name : 'Staff';
            const role = currentUser ? currentUser.role : 'Doctor';

            fetch('/api/chat/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    sender_name: staffName,
                    sender_role: role,
                    target_department: dept,
                    message: text,
                    priority: priority
                })
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    chatMessageInput.value = '';
                    loadNoticeBoardMessages();
                } else {
                    alert(data.message || 'Failed to send message.');
                }
            });
        });
    }

    // Additional Socket Event Listeners for Realtime Updates
    socket.on('patient_health_updated', () => fetchPatients());
    socket.on('service_request_created', () => fetchPatients());
    socket.on('service_request_served', () => fetchPatients());
    socket.on('new_chat_message', (msg) => {
        if (msg.priority === 'URGENT') {
            playAlarmChime(false);
        }
        loadNoticeBoardMessages();
    });

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


// Edit Patient Logic
const editPatientModal = document.getElementById('edit-patient-modal');
const btnCloseEditModal = document.getElementById('btn-close-edit-modal');
const btnSubmitEditPatient = document.getElementById('btn-submit-edit-patient');

if (btnCloseEditModal) btnCloseEditModal.addEventListener('click', () => editPatientModal.classList.add('hidden'));

window.openEditPatientModal = function(patientId) {
    const patient = (typeof allPatients !== 'undefined' ? allPatients : []).find(p => p.id === patientId);
    if (!patient) return;
    
    document.getElementById('edit-patient-id').value = patient.id;
    document.getElementById('edit-patient-name').value = patient.patient_name || '';
    document.getElementById('edit-ward').value = patient.ward || 'General Ward A';
    document.getElementById('edit-room-no').value = patient.room_no || '';
    document.getElementById('edit-bed-no').value = patient.bed_no || '';
    document.getElementById('edit-age').value = patient.age || '';
    document.getElementById('edit-gender').value = patient.gender || 'Male';
    document.getElementById('edit-mobile-no').value = patient.mobile_no || '';
    document.getElementById('edit-cause').value = patient.cause_of_admission || '';
    
    editPatientModal.classList.remove('hidden');
};

if (btnSubmitEditPatient) {
    btnSubmitEditPatient.addEventListener('click', () => {
        const payload = {
            id: parseInt(document.getElementById('edit-patient-id').value),
            patient_name: document.getElementById('edit-patient-name').value,
            ward: document.getElementById('edit-ward').value,
            room_no: document.getElementById('edit-room-no').value,
            bed_no: document.getElementById('edit-bed-no').value,
            age: document.getElementById('edit-age').value,
            gender: document.getElementById('edit-gender').value,
            mobile_no: document.getElementById('edit-mobile-no').value,
            cause_of_admission: document.getElementById('edit-cause').value
        };
        
        fetch('/api/patient/edit', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        }).then(res => res.json()).then(data => {
            if (data.status === 'success') {
                editPatientModal.classList.add('hidden');
                // The socket 'patient_updated' will trigger a refresh
            } else {
                alert('Error: ' + data.message);
            }
        });
    });
}
