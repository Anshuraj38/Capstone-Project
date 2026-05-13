/* jshint esversion: 6 */
'use strict';

// ── State ─────────────────────────────────────────────────────────
let currentSuggestions = [];
let fileLoaded = false;

// ── Section switching ─────────────────────────────────────────────
function showSection(name, el) {
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    if (el) el.classList.add('active');
}

// ── File Upload ────────────────────────────────────────────────────
function handleDrop(e) {
    e.preventDefault();
    document.getElementById('uploadZone').classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
}

function handleFileUpload(input) {
    const file = input.files[0];
    if (file) uploadFile(file);
    input.value = '';
}

function uploadFile(file) {
    showLoading('Uploading and profiling dataset…');
    const formData = new FormData();
    formData.append('file', file);

    fetch('/upload', { method: 'POST', body: formData })
        .then(res => res.json())
        .then(data => {
            hideLoading();
            if (data.error) { showToast(data.error, 'error'); return; }
            fileLoaded = true;
            renderDashboard(data.filename, data.profile, data.suggestions);
            enableAiFeatures();
            // Auto-fetch AI summary after upload
            setTimeout(() => fetchAiSummary(true), 800);
        })
        .catch(() => { hideLoading(); showToast('Upload failed. Try again.', 'error'); });
}

// ── Enable AI buttons once a file is loaded ───────────────────────
function enableAiFeatures() {
    document.getElementById('exportBtn').disabled = false;
    document.getElementById('aiSummaryBtn').disabled = false;
    document.getElementById('chatSendBtn').disabled = false;
    document.getElementById('aiCleanBtn').disabled = false;
    document.getElementById('aiCleanInput').disabled = false;
    document.getElementById('chatInput').disabled = false;
}

// ── Render Dashboard ──────────────────────────────────────────────
function renderDashboard(filename, profile, suggestions) {
    currentSuggestions = suggestions;

    document.getElementById('uploadSection').style.display = 'none';
    document.getElementById('dashboardSection').style.display = 'block';
    document.getElementById('datasetName').textContent = filename;

    // Quality score
    const q = profile.quality_score;
    const qEl = document.getElementById('qualityScore');
    qEl.textContent = q + '%';
    qEl.style.color = q >= 85 ? '#22c55e' : q >= 60 ? '#eab308' : '#ef4444';

    // Stats
    document.getElementById('totalRows').textContent = profile.rows.toLocaleString();
    document.getElementById('totalCols').textContent = profile.cols;
    document.getElementById('missingCount').textContent = profile.missing.toLocaleString();
    document.getElementById('missingPct').textContent = `(${profile.missing_pct}%)`;
    document.getElementById('dupCount').textContent = profile.duplicates.toLocaleString();
    document.getElementById('schemaCount').textContent = profile.schema_issues;

    renderColumnTable(profile.columns);
    if (profile.sample && profile.sample.length > 0) renderPreviewTable(profile.sample);
    renderSuggestions(suggestions);
    updateStepper('profiling');
}

// ── Column Table ──────────────────────────────────────────────────
function renderColumnTable(columns) {
    const tbody = document.getElementById('colTableBody');
    tbody.innerHTML = '';
    columns.forEach(col => {
        const tr = document.createElement('tr');
        const typeBadge = col.dtype.includes('int') || col.dtype.includes('float')
            ? `<span class="badge badge-num">${col.dtype}</span>`
            : col.dtype === 'object'
            ? `<span class="badge badge-str">string</span>`
            : `<span class="badge badge-other">${col.dtype}</span>`;

        tr.innerHTML = `
            <td>${escapeHtml(col.name)}</td>
            <td>${typeBadge}</td>
            <td style="color:${col.missing > 0 ? '#ef4444' : '#22c55e'}">${col.missing_pct}%</td>
            <td>${col.unique.toLocaleString()}</td>
        `;
        tbody.appendChild(tr);
    });
}

// ── Preview Table ─────────────────────────────────────────────────
function renderPreviewTable(rows) {
    if (!rows.length) return;
    const head = document.getElementById('previewHead');
    const body = document.getElementById('previewBody');
    const cols = Object.keys(rows[0]);
    head.innerHTML = '<tr>' + cols.map(c => `<th>${escapeHtml(c)}</th>`).join('') + '</tr>';
    body.innerHTML = rows.map(row =>
        '<tr>' + cols.map(c => `<td>${escapeHtml(String(row[c] ?? ''))}</td>`).join('') + '</tr>'
    ).join('');
}

// ── Suggestions ───────────────────────────────────────────────────
function renderSuggestions(suggestions) {
    const container = document.getElementById('suggestionsContainer');
    const none = document.getElementById('noSuggestions');
    container.innerHTML = '';

    if (!suggestions || suggestions.length === 0) {
        none.style.display = 'flex';
        return;
    }
    none.style.display = 'none';

    const icons = { missing: '🔍', duplicate: '📋', normalize: '🔤', outlier: '📊' };

    suggestions.forEach((s, i) => {
        const div = document.createElement('div');
        div.className = 'suggestion-item';
        div.id = `sug-${i}`;

        const viewBtn = s.type !== 'duplicate'
            ? `<button class="sug-btn outline" onclick="viewSuggestion(${i})">View</button>`
            : '';
        const applyBtn = `<button class="sug-btn apply" onclick="applySuggestion(${i})">Apply</button>`;

        div.innerHTML = `
            <div class="sug-title">${icons[s.type] || '💡'} ${escapeHtml(s.title)}</div>
            <div class="sug-desc">${escapeHtml(s.description)}</div>
            <div class="sug-actions">${viewBtn}${applyBtn}</div>
        `;
        container.appendChild(div);
    });
}

function applySuggestion(index) {
    const s = currentSuggestions[index];
    if (!s) return;
    const el = document.getElementById(`sug-${index}`);
    if (el) el.style.opacity = '0.5';
    showLoading(`Applying: ${s.title}…`);

    fetch('/clean', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: s.action, column: s.column })
    })
    .then(r => r.json())
    .then(data => {
        hideLoading();
        if (data.error) { showToast(data.error, 'error'); return; }
        showToast('Cleaning applied!', 'success');
        const filename = document.getElementById('datasetName').textContent;
        renderDashboard(filename, data.profile, data.suggestions);
        updateStepper('clean');
    })
    .catch(() => { hideLoading(); showToast('Failed to apply cleaning.', 'error'); });
}

function viewSuggestion(index) {
    const s = currentSuggestions[index];
    showToast(`Column: "${s.column}" — ${s.description}`);
}

// ── NEW: Natural Language AI Cleaning ────────────────────────────
function setAiInstruction(text) {
    document.getElementById('aiCleanInput').value = text;
    document.getElementById('aiCleanInput').focus();
}

function runAiClean() {
    const input = document.getElementById('aiCleanInput');
    const instruction = input.value.trim();
    if (!instruction) { showToast('Please enter a cleaning instruction.', 'error'); return; }
    if (!fileLoaded) { showToast('Upload a file first.', 'error'); return; }

    const resultBox = document.getElementById('aiCleanResult');
    resultBox.style.display = 'none';

    const btn = document.getElementById('aiCleanBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="btn-spinner"></span> Thinking…';

    fetch('/ai_clean', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instruction })
    })
    .then(r => r.json())
    .then(data => {
        btn.disabled = false;
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg> Apply';

        if (data.error) {
            resultBox.className = 'ai-clean-result error';
            resultBox.innerHTML = `<strong>⚠ Error:</strong> ${escapeHtml(data.error)}`;
            resultBox.style.display = 'block';
            return;
        }

        const rowMsg = data.rows_affected > 0
            ? ` <span class="rows-badge">-${data.rows_affected} rows</span>` : '';

        resultBox.className = 'ai-clean-result success';
        resultBox.innerHTML = `
            <strong>✅ Done!</strong>${rowMsg}<br>
            <span class="ai-explanation">${escapeHtml(data.message)}</span>
            ${data.code_applied ? `<details class="code-details"><summary>View generated code</summary><pre>${escapeHtml(data.code_applied)}</pre></details>` : ''}
        `;
        resultBox.style.display = 'block';

        input.value = '';
        const filename = document.getElementById('datasetName').textContent;
        renderDashboard(filename, data.profile, data.suggestions);
        updateStepper('clean');
        showToast('AI cleaning applied!', 'success');
    })
    .catch(() => {
        btn.disabled = false;
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg> Apply';
        showToast('AI request failed. Check your connection.', 'error');
    });
}

// Allow Enter key to submit AI clean
document.addEventListener('DOMContentLoaded', () => {
    const aiInput = document.getElementById('aiCleanInput');
    if (aiInput) {
        aiInput.addEventListener('keydown', e => { if (e.key === 'Enter') runAiClean(); });
        aiInput.disabled = true;
    }
    const chatInput = document.getElementById('chatInput');
    if (chatInput) chatInput.disabled = true;
    const aiCleanBtn = document.getElementById('aiCleanBtn');
    if (aiCleanBtn) aiCleanBtn.disabled = true;

    // Search filter
    const search = document.getElementById('globalSearch');
    if (search) {
        search.addEventListener('input', function () {
            const q = this.value.toLowerCase();
            document.querySelectorAll('.suggestion-item').forEach(el => {
                el.style.display = el.textContent.toLowerCase().includes(q) ? 'block' : 'none';
            });
        });
    }
});

// ── NEW: Chat with your data ──────────────────────────────────────
function sendChatMessage() {
    const input = document.getElementById('chatInput');
    const question = input.value.trim();
    if (!question) return;
    if (!fileLoaded) { showToast('Upload a file first.', 'error'); return; }

    appendChatMsg('user', question);
    input.value = '';

    const typingId = appendChatTyping();

    fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question })
    })
    .then(r => r.json())
    .then(data => {
        removeTyping(typingId);
        if (data.error) {
            appendChatMsg('assistant', `⚠ ${data.error}`);
        } else {
            appendChatMsg('assistant', data.answer);
        }
    })
    .catch(() => {
        removeTyping(typingId);
        appendChatMsg('assistant', '⚠ Could not reach the AI. Check your connection.');
    });
}

function appendChatMsg(role, text) {
    const container = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = `chat-msg ${role}`;
    div.innerHTML = `<div class="chat-bubble">${escapeHtml(text)}</div>`;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return div;
}

function appendChatTyping() {
    const container = document.getElementById('chatMessages');
    const id = 'typing-' + Date.now();
    const div = document.createElement('div');
    div.className = 'chat-msg assistant';
    div.id = id;
    div.innerHTML = '<div class="chat-bubble typing-bubble"><span></span><span></span><span></span></div>';
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return id;
}

function removeTyping(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

// ── NEW: AI Summary ───────────────────────────────────────────────
function fetchAiSummary(asBanner = false) {
    if (!fileLoaded) { showToast('Upload a file first.', 'error'); return; }

    if (!asBanner) {
        // Show modal
        const modal = document.getElementById('aiSummaryModal');
        const body = document.getElementById('aiSummaryModalBody');
        modal.style.display = 'flex';
        body.innerHTML = '<div class="modal-spinner"></div>';
    } else {
        const banner = document.getElementById('aiSummaryBanner');
        const text = document.getElementById('aiSummaryText');
        banner.style.display = 'flex';
        text.textContent = 'Generating AI health report…';
    }

    fetch('/ai_summary')
        .then(r => r.json())
        .then(data => {
            if (asBanner) {
                document.getElementById('aiSummaryText').textContent =
                    data.error ? `⚠ ${data.error}` : data.summary;
            } else {
                const body = document.getElementById('aiSummaryModalBody');
                body.innerHTML = data.error
                    ? `<p class="modal-error">⚠ ${escapeHtml(data.error)}</p>`
                    : `<p class="modal-summary">${escapeHtml(data.summary)}</p>`;
            }
        })
        .catch(() => {
            if (asBanner) {
                document.getElementById('aiSummaryText').textContent = '⚠ Could not load AI summary.';
            } else {
                document.getElementById('aiSummaryModalBody').innerHTML =
                    '<p class="modal-error">⚠ Could not reach the AI.</p>';
            }
        });
}

function closeAiSummaryModal(e) {
    if (e.target === document.getElementById('aiSummaryModal')) {
        document.getElementById('aiSummaryModal').style.display = 'none';
    }
}

// ── Export ────────────────────────────────────────────────────────
function exportFile() {
    showToast('Preparing export…', 'info');
    window.location.href = '/export';
    updateStepper('export');
}

// ── Stepper ───────────────────────────────────────────────────────
function updateStepper(phase) {
    const phases = ['upload', 'profiling', 'clean', 'export'];
    const ids = ['step1', 'step2', 'step3', 'step4'];
    const phaseIdx = phases.indexOf(phase);

    ids.forEach((id, i) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.className = 'step';
        el.querySelector('.step-status').textContent = '';
        if (i < phaseIdx) {
            el.classList.add('done');
            el.querySelector('.step-status').textContent = '(Complete)';
        } else if (i === phaseIdx) {
            el.classList.add('active');
            el.querySelector('.step-status').textContent = '(In Progress)';
        }
    });
}

// ── Toast ─────────────────────────────────────────────────────────
function showToast(msg, type = 'success') {
    const toast = document.getElementById('toast');
    const toastMsg = document.getElementById('toastMsg');
    toastMsg.textContent = msg;
    toast.style.background = type === 'error' ? '#ef4444'
        : type === 'info' ? '#4F8EF7' : '#22c55e';
    toast.style.display = 'block';
    clearTimeout(window._toastTimer);
    window._toastTimer = setTimeout(() => { toast.style.display = 'none'; }, 3500);
}

// ── Loading ───────────────────────────────────────────────────────
function showLoading(text) {
    document.getElementById('loadingText').textContent = text || 'Processing…';
    document.getElementById('loadingOverlay').style.display = 'flex';
}
function hideLoading() {
    document.getElementById('loadingOverlay').style.display = 'none';
}

// ── Utils ─────────────────────────────────────────────────────────
function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
