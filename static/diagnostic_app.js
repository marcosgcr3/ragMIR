/**
 * diagnostic_app.js
 * Client-side logic for the Adaptive MIR Diagnostic Test.
 */

const MANUAL_NAMES = {
    "CD.pdf": "Cardiología", "NR.pdf": "Neurología", "DG.pdf": "Digestivo",
    "PD.pdf": "Pediatría", "GC.pdf": "Ginecología", "ED.pdf": "Endocrinología",
    "TM.pdf": "Traumatología", "IF.pdf": "Infecciosas", "NF.pdf": "Nefrología",
    "NM.pdf": "Neumología", "HM.pdf": "Hematología", "RH.pdf": "Reumatología",
    "CG.pdf": "Cirugía General", "DM.pdf": "Dermatología", "PQ.pdf": "Psiquiatría",
    "ON.pdf": "Oncología", "AN.pdf": "Anestesiología", "OF.pdf": "Oftalmología",
    "OR.pdf": "ORL", "FC.pdf": "Farmacología", "AP.pdf": "Anatomía Patológica",
    "UG.pdf": "Urología", "EP.pdf": "Epidemiología", "AL.pdf": "Alergología",
    "IG.pdf": "Inmunología", "GT.pdf": "Genética", "AT.pdf": "Atención Primaria",
    "UR.pdf": "Urgencias", "BL.pdf": "Bioestadística", "GR.pdf": "Geriatría",
    "RX.pdf": "Radiología", "NQ.pdf": "Neurocirugía", "MF.pdf": "Med. Forense",
    "CI.pdf": "Cirugía Plástica", "RE.pdf": "Rehabilitación",
};

const DiagApp = (() => {
    // ── State ─────────────────────────────────────────────────────────────
    let sessionId = null;
    let questions = [];
    let currentIdx = 0;
    let answered = false;
    let scores = { correct: 0, incorrect: 0, skipped: 0 };
    let radarChart = null;
    let historyChart = null;

    // ── Screens ───────────────────────────────────────────────────────────
    function showScreen(id) {
        document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
        document.getElementById(id).classList.add('active');
    }

    function showWelcome() {
        showScreen('screen-welcome');
        loadHistory();
    }

    // ── Auth check + nav username ─────────────────────────────────────────
    async function init() {
        try {
            const res = await fetch('/api/auth/me');
            if (!res.ok) { window.location.href = '/'; return; }
            const user = await res.json();
            document.getElementById('nav-username').textContent = user.username || '—';
        } catch { window.location.href = '/'; }
        showWelcome();
    }

    // ── Load history on welcome screen ────────────────────────────────────
    async function loadHistory() {
        try {
            const res = await fetch('/api/diagnostic/history');
            const data = await res.json();
            const history = data.history || [];
            if (history.length === 0) return;

            document.getElementById('history-section').style.display = 'block';
            const list = document.getElementById('history-list');
            list.innerHTML = history.slice(0, 5).map(h => {
                const score = parseFloat(h.mir_score);
                const cls = score >= 7 ? 'score-good' : score >= 5 ? 'score-mid' : 'score-bad';
                const date = new Date(h.created_at).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' });
                const pct = h.total_questions > 0 ? Math.round(h.correct_answers / h.total_questions * 100) : 0;
                return `
                    <div class="history-item" onclick="DiagApp.viewResults('${h.id}')">
                        <div>
                            <div class="history-date">${date}</div>
                            <div class="history-meta">${h.correct_answers} correctas · ${h.incorrect_answers} errores · ${pct}% acierto</div>
                        </div>
                        <div class="history-score ${cls}">${score.toFixed(1)} <span style="font-size:1rem;color:#64748b">/ 10</span></div>
                    </div>`;
            }).join('');
        } catch (e) { console.warn('Error loading history:', e); }
    }

    // ── Start new diagnostic ──────────────────────────────────────────────
    async function start() {
        showScreen('screen-loading');
        document.getElementById('loading-msg').textContent = 'Preparando tu test personalizado…';
        scores = { correct: 0, incorrect: 0, skipped: 0 };
        currentIdx = 0;
        answered = false;

        try {
            const res = await fetch('/api/diagnostic/start', { method: 'POST' });
            if (!res.ok) { const e = await res.json(); alert(e.detail || 'Error al iniciar'); showWelcome(); return; }
            const data = await res.json();
            sessionId = data.session_id;
            questions = data.questions;
            renderQuestion();
            showScreen('screen-exam');
        } catch (e) {
            alert('Error de conexión. Inténtalo de nuevo.');
            showWelcome();
        }
    }

    // ── Render current question ───────────────────────────────────────────
    function renderQuestion() {
        if (currentIdx >= questions.length) { finishExam(); return; }
        answered = false;

        const q = questions[currentIdx];
        const total = questions.length;
        const subjectName = q.name || MANUAL_NAMES[q.subject] || q.subject?.replace('.pdf', '') || '—';

        document.getElementById('q-count-label').textContent = `Pregunta ${currentIdx + 1} de ${total}`;
        document.getElementById('q-subject-label').textContent = subjectName;
        document.getElementById('progress-fill').style.width = `${(currentIdx / total) * 100}%`;
        document.getElementById('q-text').textContent = q.question;
        document.getElementById('q-explanation').classList.remove('visible');
        document.getElementById('q-explanation').innerHTML = '';

        const letters = ['A', 'B', 'C', 'D'];
        const grid = document.getElementById('options-grid');
        grid.innerHTML = q.options.map((opt, i) => `
            <button class="opt-btn" id="opt-${i}" onclick="DiagApp.answer(${i})">
                <span class="opt-letter">${letters[i]}</span>
                <span>${opt}</span>
            </button>`).join('');

        // Buttons state
        document.getElementById('btn-skip').style.display = 'block';
        document.getElementById('btn-skip').disabled = false;
        const btnNext = document.getElementById('btn-next');
        btnNext.disabled = true;
        btnNext.textContent = currentIdx === total - 1 ? 'Ver resultados' : 'Siguiente';
        btnNext.innerHTML = currentIdx === total - 1
            ? '<i class="fa-solid fa-chart-bar"></i> Ver resultados'
            : 'Siguiente <i class="fa-solid fa-arrow-right"></i>';
    }

    // ── Answer a question ─────────────────────────────────────────────────
    async function answer(selectedIdx) {
        if (answered) return;
        answered = true;

        const q = questions[currentIdx];
        const isCorrect = selectedIdx === q.correct_index ? 1 : 0;

        if (isCorrect) scores.correct++;
        else scores.incorrect++;

        // Visual feedback
        const allBtns = document.querySelectorAll('.opt-btn');
        allBtns.forEach(b => b.disabled = true);

        const selectedBtn = document.getElementById(`opt-${selectedIdx}`);
        const correctBtn = document.getElementById(`opt-${q.correct_index}`);

        if (isCorrect) {
            selectedBtn.classList.add('selected-correct');
        } else {
            selectedBtn.classList.add('selected-wrong');
            correctBtn.classList.add('show-correct');
        }

        // Show explanation
        const expEl = document.getElementById('q-explanation');
        expEl.innerHTML = `<strong>Explicación:</strong> ${q.explanation || 'Sin explicación disponible.'}`;
        expEl.classList.add('visible');

        document.getElementById('btn-skip').style.display = 'none';
        document.getElementById('btn-next').disabled = false;

        // Save answer silently
        try {
            const fd = new FormData();
            fd.append('session_id', sessionId);
            fd.append('question_id', q.id);
            fd.append('selected_index', selectedIdx);
            fd.append('is_correct', isCorrect);
            await fetch('/api/diagnostic/answer', { method: 'POST', body: fd });
        } catch (e) { console.warn('Error saving answer:', e); }
    }

    // ── Skip a question ───────────────────────────────────────────────────
    async function skip() {
        if (answered) return;
        answered = true;
        scores.skipped++;

        document.querySelectorAll('.opt-btn').forEach(b => b.disabled = true);
        const correctBtn = document.getElementById(`opt-${questions[currentIdx].correct_index}`);
        if (correctBtn) correctBtn.classList.add('show-correct');

        const expEl = document.getElementById('q-explanation');
        expEl.innerHTML = `<strong>Respuesta correcta:</strong> Opción ${['A','B','C','D'][questions[currentIdx].correct_index]}`;
        expEl.classList.add('visible');

        document.getElementById('btn-skip').style.display = 'none';
        document.getElementById('btn-next').disabled = false;

        try {
            const fd = new FormData();
            fd.append('session_id', sessionId);
            fd.append('question_id', questions[currentIdx].id);
            fd.append('selected_index', -1);
            fd.append('is_correct', 0);
            await fetch('/api/diagnostic/answer', { method: 'POST', body: fd });
        } catch (e) { console.warn('Error saving skip:', e); }
    }

    // ── Next question ─────────────────────────────────────────────────────
    function next() {
        currentIdx++;
        if (currentIdx >= questions.length) { finishExam(); return; }
        renderQuestion();
    }

    // ── Finish exam ───────────────────────────────────────────────────────
    async function finishExam() {
        showScreen('screen-loading');
        document.getElementById('loading-msg').textContent = 'Calculando tu puntuación…';

        try {
            // Complete session
            const fd = new FormData();
            fd.append('session_id', sessionId);
            await fetch('/api/diagnostic/complete', { method: 'POST', body: fd });

            // Load full results
            await viewResults(sessionId);
        } catch (e) {
            console.error('Error finishing exam:', e);
            alert('Error al calcular resultados. Inténtalo de nuevo.');
            showWelcome();
        }
    }

    // ── View results for a session ────────────────────────────────────────
    async function viewResults(sid) {
        showScreen('screen-loading');
        try {
            const res = await fetch(`/api/diagnostic/results/${sid}`);
            if (!res.ok) { showWelcome(); return; }
            const data = await res.json();

            // Summary cards
            const total = data.total_questions || 1;
            const correct = data.correct_answers || 0;
            const incorrect = data.incorrect_answers || 0;
            const skipped = data.skipped_answers || 0;
            const pct = Math.round(correct / total * 100);
            const score = parseFloat(data.mir_score || 0);

            document.getElementById('res-correct').textContent = correct;
            document.getElementById('res-incorrect').textContent = incorrect;
            document.getElementById('res-skipped').textContent = skipped;
            document.getElementById('res-pct').textContent = pct + '%';

            // Score ring
            const ringEl = document.getElementById('score-ring');
            const ringPct = (score / 10) * 100;
            const color = score >= 7 ? '#22c55e' : score >= 5 ? '#eab308' : '#ef4444';
            ringEl.style.setProperty('--ring-pct', ringPct + '%');
            ringEl.style.setProperty('--ring-color', color);
            document.getElementById('score-num').textContent = score.toFixed(1);
            document.getElementById('score-num').style.color = color;

            // Percentile estimate (rough)
            const percentile = estimatePercentile(score);
            document.getElementById('percentile-badge').textContent = `Top ${100 - percentile}% de estudiantes MIR`;

            // Subject bars & radar
            const subjects = (data.subjects || []).sort((a, b) => b.percent - a.percent);
            renderSubjectBars(subjects);
            renderRadarChart(subjects);
            renderStrengthsWeaknesses(subjects);

            // Progress history chart
            await renderHistoryChart();

            showScreen('screen-results');
        } catch (e) {
            console.error('Error loading results:', e);
            showWelcome();
        }
    }

    function estimatePercentile(score) {
        // Rough bell curve estimate for MIR scoring
        if (score >= 9) return 95;
        if (score >= 8) return 85;
        if (score >= 7) return 72;
        if (score >= 6) return 57;
        if (score >= 5) return 42;
        if (score >= 4) return 28;
        return 15;
    }

    function renderSubjectBars(subjects) {
        const el = document.getElementById('subject-bars');
        if (!subjects.length) { el.innerHTML = '<p style="color:#64748b;font-size:0.85rem">Sin datos suficientes.</p>'; return; }
        el.innerHTML = subjects.map(s => {
            const name = s.name || MANUAL_NAMES[s.subject] || s.subject?.replace('.pdf', '');
            const pct = s.percent || 0;
            const cls = pct >= 70 ? 'fill-green' : pct >= 50 ? 'fill-yellow' : 'fill-red';
            const colorStyle = pct >= 70 ? 'color:#22c55e' : pct >= 50 ? 'color:#eab308' : 'color:#ef4444';
            return `
                <div class="subject-bar-row">
                    <div class="subject-bar-top">
                        <span class="s-name">${name}</span>
                        <span class="s-pct" style="${colorStyle}">${pct}%</span>
                    </div>
                    <div class="subject-bar-bg">
                        <div class="subject-bar-fill ${cls}" style="width:${pct}%"></div>
                    </div>
                </div>`;
        }).join('');
    }

    function renderRadarChart(subjects) {
        const ctx = document.getElementById('radar-chart').getContext('2d');
        if (radarChart) radarChart.destroy();

        const top12 = subjects.slice(0, 12);
        const labels = top12.map(s => s.name || MANUAL_NAMES[s.subject] || s.subject?.replace('.pdf', ''));
        const data = top12.map(s => s.percent || 0);

        radarChart = new Chart(ctx, {
            type: 'radar',
            data: {
                labels,
                datasets: [{
                    label: '% Aciertos',
                    data,
                    backgroundColor: 'rgba(124,58,237,0.2)',
                    borderColor: '#a855f7',
                    pointBackgroundColor: '#a855f7',
                    pointBorderColor: '#fff',
                    borderWidth: 2,
                    pointRadius: 4,
                }]
            },
            options: {
                responsive: true,
                scales: {
                    r: {
                        min: 0, max: 100,
                        ticks: { color: '#64748b', font: { size: 10 }, stepSize: 25 },
                        grid: { color: 'rgba(255,255,255,0.06)' },
                        angleLines: { color: 'rgba(255,255,255,0.06)' },
                        pointLabels: { color: '#94a3b8', font: { size: 10, family: 'Inter' } }
                    }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: { label: ctx => ` ${ctx.raw}% aciertos` }
                    }
                }
            }
        });
    }

    function renderStrengthsWeaknesses(subjects) {
        const sorted = [...subjects].sort((a, b) => b.percent - a.percent);
        const strengths = sorted.slice(0, 3);
        const weaknesses = sorted.slice(-3).reverse();

        const toHtml = (list, colorFn) => list.map((s, i) => {
            const name = s.name || MANUAL_NAMES[s.subject] || s.subject?.replace('.pdf', '');
            const pct = s.percent || 0;
            const clr = colorFn(pct);
            return `<div class="sw-item">
                <span class="sw-rank">#${i+1}</span>
                <span class="sw-name">${name}</span>
                <span class="sw-pct" style="color:${clr}">${pct}%</span>
            </div>`;
        }).join('');

        document.getElementById('strengths-list').innerHTML = toHtml(strengths, p => p >= 70 ? '#22c55e' : '#eab308');
        document.getElementById('weaknesses-list').innerHTML = toHtml(weaknesses, p => p < 50 ? '#ef4444' : '#eab308');
    }

    async function renderHistoryChart() {
        try {
            const res = await fetch('/api/diagnostic/history');
            const data = await res.json();
            const history = (data.history || []).reverse(); // oldest first
            if (history.length < 2) { document.getElementById('progress-section').style.display = 'none'; return; }

            document.getElementById('progress-section').style.display = 'block';
            const ctx = document.getElementById('history-chart').getContext('2d');
            if (historyChart) historyChart.destroy();

            const labels = history.map((h, i) => `Test ${i+1}`);
            const scores = history.map(h => parseFloat(h.mir_score || 0));

            historyChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels,
                    datasets: [{
                        label: 'Nota MIR',
                        data: scores,
                        borderColor: '#a855f7',
                        backgroundColor: 'rgba(168,85,247,0.15)',
                        fill: true,
                        tension: 0.4,
                        pointBackgroundColor: '#a855f7',
                        pointRadius: 5,
                        pointHoverRadius: 7,
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        y: {
                            min: 0, max: 10,
                            ticks: { color: '#64748b', font: { size: 11 } },
                            grid: { color: 'rgba(255,255,255,0.06)' }
                        },
                        x: {
                            ticks: { color: '#64748b', font: { size: 11 } },
                            grid: { color: 'rgba(255,255,255,0.04)' }
                        }
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: { label: ctx => ` ${ctx.raw.toFixed(1)} / 10` }
                        }
                    }
                }
            });
        } catch (e) { console.warn('Error rendering history chart:', e); }
    }

    // Public API
    return { init, start, answer, skip, next, showWelcome, viewResults };
})();

document.addEventListener('DOMContentLoaded', () => DiagApp.init());
