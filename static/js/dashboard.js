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
