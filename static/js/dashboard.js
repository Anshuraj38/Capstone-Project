/* jshint esversion: 6 */

// ── State ─────────────────────────────────────────────────────────
let currentSuggestions = [];

// ── Section switching ─────────────────────────────────────────────
function showSection(name) {
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    event.currentTarget.classList.add('active');
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
    input.value = '';  // reset so same file can be re-uploaded
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
            renderDashboard(data.filename, data.profile, data.suggestions);
        })
        .catch(err => { hideLoading(); showToast('Upload failed. Try again.', 'error'); });
}

// ── Render Dashboard ──────────────────────────────────────────────
function renderDashboard(filename, profile, suggestions) {
    currentSuggestions = suggestions;

    // Switch sections
    document.getElementById('uploadSection').style.display = 'none';
    document.getElementById('dashboardSection').style.display = 'block';

    // Enable export
    document.getElementById('exportBtn').disabled = false;

    // Filename
    document.getElementById('datasetName').textContent = filename;

    // Quality
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

    // Column table
    renderColumnTable(profile.columns);

    // Preview table
    if (profile.sample && profile.sample.length > 0) {
        renderPreviewTable(profile.sample);
    }

    // Suggestions
    renderSuggestions(suggestions);

    // Update stepper
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

// ── AI Suggestions ────────────────────────────────────────────────
function renderSuggestions(suggestions) {
    const container = document.getElementById('suggestionsContainer');
    const none = document.getElementById('noSuggestions');
    container.innerHTML = '';

    if (!suggestions || suggestions.length === 0) {
        none.style.display = 'flex';
        return;
    }
    none.style.display = 'none';

    const icons = {
        missing:   '🔍',
        duplicate: '📋',
        normalize: '🔤',
        outlier:   '📊'
    };

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

// ── Apply Suggestion ──────────────────────────────────────────────
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
        showToast('Cleaning applied successfully!', 'success');
        currentSuggestions = data.suggestions;
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
    const statuses = ['Complete', 'In Progress', '', ''];
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
    toast.style.background = type === 'error' ? '#ef4444' : type === 'info' ? '#4F8EF7' : '#22c55e';
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

// ── Global search filter ──────────────────────────────────────────
document.getElementById('globalSearch').addEventListener('input', function () {
    const q = this.value.toLowerCase();
    document.querySelectorAll('.suggestion-item').forEach(el => {
        const text = el.textContent.toLowerCase();
        el.style.display = text.includes(q) ? 'block' : 'none';
    });
});
