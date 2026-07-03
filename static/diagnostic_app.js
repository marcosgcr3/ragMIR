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
    let sessionId = null;
    let questions = [];
    let currentIdx = 0;
    let answered = false;
    let radarChart = null;
    let historyChart = null;

    // ── Screen management ─────────────────────────────────────────────────
    function showScreen(id) {
        document.querySelectorAll('.diag-screen').forEach(s => s.classList.remove('active'));
        const el = document.getElementById(id);
        if (el) {
            el.classList.add('active');
            // Scroll to top
            const content = el.closest('.diag-content') || document.querySelector('.diag-content');
            if (content) content.scrollTop = 0;
        }
    }

    function showWelcome(useCache = false) {
        showScreen('screen-welcome');
        document.getElementById('header-subtitle').textContent = '50 preguntas adaptativas · Sistema de puntuación MIR (+3 / -1)';
        loadSidebarHistory(useCache);
    }

    // ── Auth & init ───────────────────────────────────────────────────────
    async function init() {
        // Setup logout button
        const logoutBtn = document.getElementById('btn-logout');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', async () => {
                sessionStorage.clear(); // Clear cache on logout
                await fetch('/api/auth/logout', { method: 'POST' });
                window.location.href = '/';
            });
        }

        // Setup login form
        const loginForm = document.getElementById('login-form');
        if (loginForm) {
            loginForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const username = document.getElementById('login-username').value;
                const password = document.getElementById('login-password').value;
                const fd = new FormData();
                fd.append('username', username);
                fd.append('password', password);
                const res = await fetch('/api/auth/login', { method: 'POST', body: fd });
                if (res.ok) {
                    document.getElementById('login-overlay').style.display = 'none';
                    await afterLogin();
                } else {
                    document.getElementById('login-error').style.display = 'block';
                }
            });
        }

        // SWR: Load cached user instantly
        const cachedUser = sessionStorage.getItem('currentUser');
        if (cachedUser) {
            try {
                const user = JSON.parse(cachedUser);
                document.getElementById('user-display-name').textContent = user.username || '—';
                document.getElementById('user-profile').style.display = 'flex';
                showWelcome(true); // Load history from cache instantly
            } catch (e) {
                sessionStorage.removeItem('currentUser');
            }
        }

        // Background authentication check
        let authenticatedUser = null;
        try {
            const res = await fetch('/api/auth/me');
            if (!res.ok) {
                sessionStorage.clear();
                document.getElementById('login-overlay').style.display = 'flex';
                return;
            }
            authenticatedUser = await res.json();
            sessionStorage.setItem('currentUser', JSON.stringify(authenticatedUser));
            document.getElementById('user-display-name').textContent = authenticatedUser.username || '—';
            document.getElementById('user-profile').style.display = 'flex';
        } catch {
            if (!cachedUser) {
                document.getElementById('login-overlay').style.display = 'flex';
                return;
            }
        }

        if (!cachedUser) {
            await afterLogin();
        } else {
            // Revalidate history in background
            loadSidebarHistory(false);
        }
    }

    async function afterLogin() {
        try {
            const res = await fetch('/api/auth/me');
            if (res.ok) {
                const user = await res.json();
                sessionStorage.setItem('currentUser', JSON.stringify(user));
                document.getElementById('user-display-name').textContent = user.username || '—';
                document.getElementById('user-profile').style.display = 'flex';
            }
        } catch {}
        showWelcome(false);
    }

    // ── Sidebar history ───────────────────────────────────────────────────
    async function loadSidebarHistory(useCache = false) {
        const el = document.getElementById('sidebar-history-list');
        if (!el) return;

        if (useCache) {
            const cachedHistory = sessionStorage.getItem('diagnosticHistory');
            if (cachedHistory) {
                try {
                    const history = JSON.parse(cachedHistory);
                    renderHistoryList(history, el);
                } catch (e) {
                    sessionStorage.removeItem('diagnosticHistory');
                }
            }
        }

        try {
            const res = await fetch('/api/diagnostic/history');
            const data = await res.json();
            const history = data.history || [];
            sessionStorage.setItem('diagnosticHistory', JSON.stringify(history));
            renderHistoryList(history, el);
        } catch (e) {
            console.warn('Error loading sidebar history:', e);
        }
    }

    function renderHistoryList(history, el) {
        if (history.length === 0) {
            el.innerHTML = '<p class="empty-list" style="font-size:11px;">Aún no has hecho ningún diagnóstico.</p>';
            return;
        }

        el.innerHTML = history.slice(0, 10).map((h, idx) => {
            const score = parseFloat(h.mir_score);
            const cls = score >= 7 ? 'score-good' : score >= 5 ? 'score-mid' : 'score-bad';
            const date = new Date(h.created_at).toLocaleDateString('es-ES', { day: '2-digit', month: 'short' });
            const pct = h.total_questions > 0 ? Math.round(h.correct_answers / h.total_questions * 100) : 0;
            return `
                <div class="diag-hist-item" onclick="DiagApp.viewResults('${h.id}')">
                    <div>
                        <div class="diag-hist-date">Test ${history.length - idx} · ${date}</div>
                        <div style="font-size:0.75rem;color:#475569;margin-top:2px">${pct}% aciertos</div>
                    </div>
                    <div class="diag-hist-score ${cls}">${score.toFixed(1)}<span style="font-size:0.7rem;color:#64748b"> /10</span></div>
                </div>`;
        }).join('');
    }

    // ── Start new diagnostic ──────────────────────────────────────────────
    async function start() {
        showScreen('screen-loading');
        document.getElementById('loading-msg').textContent = 'Preparando tu test personalizado…';
        document.getElementById('header-subtitle').textContent = 'Cargando preguntas…';
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
        } catch {
            alert('Error de conexión. Inténtalo de nuevo.');
            showWelcome();
        }
    }

    // ── Render question ───────────────────────────────────────────────────
    function renderQuestion() {
        if (currentIdx >= questions.length) { finishExam(); return; }
        answered = false;

        const q = questions[currentIdx];
        const total = questions.length;
        const subjectName = q.name || MANUAL_NAMES[q.subject] || q.subject?.replace('.pdf', '') || '—';

        document.getElementById('header-subtitle').textContent = `Pregunta ${currentIdx + 1} de ${total} · ${subjectName}`;
        document.getElementById('q-count-label').textContent = `Pregunta ${currentIdx + 1} de ${total}`;
        document.getElementById('q-subject-label').textContent = subjectName;
        document.getElementById('progress-fill').style.width = `${(currentIdx / total) * 100}%`;
        document.getElementById('q-text').textContent = q.question;
        document.getElementById('q-explanation').classList.remove('visible');
        document.getElementById('q-explanation').innerHTML = '';

        const letters = ['A', 'B', 'C', 'D'];
        document.getElementById('options-grid').innerHTML = q.options.map((opt, i) => `
            <button class="opt-btn" id="opt-${i}" onclick="DiagApp.answer(${i})">
                <span class="opt-letter">${letters[i]}</span>
                <span>${opt}</span>
            </button>`).join('');

        document.getElementById('btn-skip').style.display = 'block';
        document.getElementById('btn-skip').disabled = false;
        const btnNext = document.getElementById('btn-next');
        btnNext.disabled = true;
        btnNext.innerHTML = currentIdx === total - 1
            ? '<i class="fa-solid fa-chart-bar"></i> Ver resultados'
            : 'Siguiente <i class="fa-solid fa-arrow-right"></i>';
    }

    // ── Answer ────────────────────────────────────────────────────────────
    async function answer(selectedIdx) {
        if (answered) return;
        answered = true;

        const q = questions[currentIdx];
        const isCorrect = selectedIdx === q.correct_index ? 1 : 0;

        document.querySelectorAll('.opt-btn').forEach(b => b.disabled = true);
        document.getElementById(`opt-${selectedIdx}`).classList.add(isCorrect ? 'selected-correct' : 'selected-wrong');
        if (!isCorrect) document.getElementById(`opt-${q.correct_index}`)?.classList.add('show-correct');

        const expEl = document.getElementById('q-explanation');
        expEl.innerHTML = `<strong>Explicación:</strong> ${q.explanation || 'Sin explicación disponible.'}`;
        expEl.classList.add('visible');
        document.getElementById('btn-skip').style.display = 'none';
        document.getElementById('btn-next').disabled = false;

        const fd = new FormData();
        fd.append('session_id', sessionId);
        fd.append('question_id', q.id);
        fd.append('selected_index', selectedIdx);
        fd.append('is_correct', isCorrect);
        fetch('/api/diagnostic/answer', { method: 'POST', body: fd })
            .catch(e => console.warn('Error saving answer:', e));
    }

    // ── Skip ──────────────────────────────────────────────────────────────
    async function skip() {
        if (answered) return;
        answered = true;

        document.querySelectorAll('.opt-btn').forEach(b => b.disabled = true);
        document.getElementById(`opt-${questions[currentIdx].correct_index}`)?.classList.add('show-correct');

        const expEl = document.getElementById('q-explanation');
        expEl.innerHTML = `<strong>Respuesta correcta:</strong> Opción ${['A','B','C','D'][questions[currentIdx].correct_index]}`;
        expEl.classList.add('visible');
        document.getElementById('btn-skip').style.display = 'none';
        document.getElementById('btn-next').disabled = false;

        const fd = new FormData();
        fd.append('session_id', sessionId);
        fd.append('question_id', questions[currentIdx].id);
        fd.append('selected_index', -1);
        fd.append('is_correct', 0);
        fetch('/api/diagnostic/answer', { method: 'POST', body: fd })
            .catch(e => console.warn('Error saving skip:', e));
    }

    // ── Next ──────────────────────────────────────────────────────────────
    function next() {
        currentIdx++;
        if (currentIdx >= questions.length) { finishExam(); return; }
        renderQuestion();
    }

    // ── Finish ────────────────────────────────────────────────────────────
    async function finishExam() {
        showScreen('screen-loading');
        document.getElementById('loading-msg').textContent = 'Calculando tu puntuación…';
        try {
            const fd = new FormData();
            fd.append('session_id', sessionId);
            await fetch('/api/diagnostic/complete', { method: 'POST', body: fd });
            await viewResults(sessionId);
        } catch {
            alert('Error al calcular resultados.');
            showWelcome();
        }
    }

    // ── View results ──────────────────────────────────────────────────────
    async function viewResults(sid) {
        showScreen('screen-loading');
        try {
            const res = await fetch(`/api/diagnostic/results/${sid}`);
            if (!res.ok) { showWelcome(); return; }
            const data = await res.json();

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
            document.getElementById('header-subtitle').textContent = `Nota MIR: ${score.toFixed(1)} / 10 · ${pct}% aciertos`;

            // Calculate MIR Net Questions out of 200 expected questions
            const expectedCorrect = 200 * (correct / total);
            const expectedIncorrect = 200 * (incorrect / total);
            const netScore = Math.max(0, expectedCorrect - (expectedIncorrect / 3));
            document.getElementById('estim-netas').textContent = netScore.toFixed(1) + ' netas';

            // Calculate National Ranking order prediction
            let rankingText = "# 10.000+";
            let rankColor = "#ef4444";
            let pctText = "Percentil estimado: < 15%";
            if (netScore >= 165) {
                rankingText = "# 1 - 250";
                rankColor = "#00e676";
                pctText = "Percentil estimado: ~99% (Excelente, plaza asegurada de tu elección)";
            } else if (netScore >= 150) {
                rankingText = "# 250 - 900";
                rankColor = "#00f2fe";
                pctText = "Percentil estimado: ~95% (Sobresaliente, acceso a especialidades altamente cotizadas)";
            } else if (netScore >= 135) {
                rankingText = "# 900 - 2.000";
                rankColor = "#8c52ff";
                pctText = "Percentil estimado: ~88% (Muy bueno, alta probabilidad para la mayoría de especialidades)";
            } else if (netScore >= 120) {
                rankingText = "# 2.000 - 3.500";
                rankColor = "#eab308";
                pctText = "Percentil estimado: ~75% (Bueno, opciones competitivas en múltiples hospitales)";
            } else if (netScore >= 105) {
                rankingText = "# 3.500 - 5.500";
                rankColor = "#ff9100";
                pctText = "Percentil estimado: ~60% (Media nacional, múltiples opciones disponibles)";
            } else if (netScore >= 90) {
                rankingText = "# 5.500 - 8.000";
                rankColor = "#ff3d00";
                pctText = "Percentil estimado: ~40% (Acceso a plazas de medicina familiar y comunitarias)";
            } else {
                rankingText = "# 8.000+";
                rankColor = "#ef4444";
                pctText = "Percentil estimado: < 25% (Riesgo de no obtener plaza. ¡Es hora de intensificar el estudio!)";
            }

            const rankingEl = document.getElementById('estim-ranking');
            rankingEl.textContent = rankingText;
            rankingEl.style.color = rankColor;
            document.getElementById('estim-ranking-desc').textContent = pctText;

            // Score ring
            const ringEl = document.getElementById('score-ring');
            const color = score >= 7 ? '#22c55e' : score >= 5 ? '#eab308' : '#ef4444';
            ringEl.style.setProperty('--ring-pct', `${(score / 10) * 100}%`);
            ringEl.style.setProperty('--ring-color', color);
            const numEl = document.getElementById('score-num');
            numEl.textContent = score.toFixed(1);
            numEl.style.color = color;

            const percentile = estimatePercentile(score);
            document.getElementById('percentile-badge').textContent = `Top ${100 - percentile}% de estudiantes MIR`;

            const subjects = (data.subjects || []).sort((a, b) => b.percent - a.percent);
            renderSubjectBars(subjects);
            renderRadarChart(subjects);
            renderStrengthsWeaknesses(subjects);
            renderPriorityMatrix(subjects);
            renderTutorRecommendations(subjects, correct, incorrect, skipped);
            await renderHistoryChart();

            showScreen('screen-results');
            loadSidebarHistory(); // refresh sidebar after new result
        } catch (e) {
            console.error('Error loading results:', e);
            showWelcome();
        }
    }

    function estimatePercentile(score) {
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
        if (!subjects.length) { el.innerHTML = '<p style="color:#64748b;font-size:0.82rem">Sin datos suficientes.</p>'; return; }
        el.innerHTML = subjects.map(s => {
            const name = s.name || MANUAL_NAMES[s.subject] || s.subject?.replace('.pdf', '');
            const pct = s.percent || 0;
            const cls = pct >= 70 ? 'fill-green' : pct >= 50 ? 'fill-yellow' : 'fill-red';
            const clr = pct >= 70 ? '#22c55e' : pct >= 50 ? '#eab308' : '#ef4444';
            return `<div class="subject-bar-row">
                <div class="subject-bar-top"><span class="s-name">${name}</span><span class="s-pct" style="color:${clr}">${pct}%</span></div>
                <div class="subject-bar-bg"><div class="subject-bar-fill ${cls}" style="width:${pct}%"></div></div>
            </div>`;
        }).join('');
    }

    function renderRadarChart(subjects) {
        const ctx = document.getElementById('radar-chart').getContext('2d');
        if (radarChart) radarChart.destroy();
        const top = subjects.slice(0, 12);
        radarChart = new Chart(ctx, {
            type: 'radar',
            data: {
                labels: top.map(s => s.name || MANUAL_NAMES[s.subject] || s.subject?.replace('.pdf','')),
                datasets: [{
                    label: '% Aciertos',
                    data: top.map(s => s.percent || 0),
                    backgroundColor: 'rgba(124,58,237,0.18)',
                    borderColor: '#a855f7',
                    pointBackgroundColor: '#a855f7',
                    pointBorderColor: '#fff',
                    borderWidth: 2, pointRadius: 4,
                }]
            },
            options: {
                responsive: true,
                scales: { r: { min:0, max:100, ticks:{color:'#64748b',font:{size:9},stepSize:25}, grid:{color:'rgba(255,255,255,0.06)'}, angleLines:{color:'rgba(255,255,255,0.06)'}, pointLabels:{color:'#94a3b8',font:{size:9,family:'Inter'}} } },
                plugins: { legend:{display:false}, tooltip:{callbacks:{label: c => ` ${c.raw}% aciertos`}} }
            }
        });
    }

    function renderStrengthsWeaknesses(subjects) {
        const sorted = [...subjects].sort((a,b) => b.percent - a.percent);
        const toHtml = (list, colorFn) => list.map((s,i) => {
            const name = s.name || MANUAL_NAMES[s.subject] || s.subject?.replace('.pdf','');
            const pct = s.percent || 0;
            return `<div class="sw-item"><span class="sw-rank">#${i+1}</span><span class="sw-name">${name}</span><span class="sw-pct-val" style="color:${colorFn(pct)}">${pct}%</span></div>`;
        }).join('');

        document.getElementById('strengths-list').innerHTML = toHtml(sorted.slice(0,3), p => p>=70?'#22c55e':'#eab308');
        document.getElementById('weaknesses-list').innerHTML = toHtml([...sorted].reverse().slice(0,3), p => p<50?'#ef4444':'#eab308');
    }

    function renderPriorityMatrix(subjects) {
        const highWeightFiles = [
            "CD.pdf", "NR.pdf", "DG.pdf", "PD.pdf", "GC.pdf",
            "ED.pdf", "TM.pdf", "IF.pdf", "NF.pdf", "NM.pdf", "HM.pdf"
        ];
        
        const criticalEl = document.getElementById('priority-critical');
        const maintenanceEl = document.getElementById('priority-maintenance');
        
        let criticalHtml = "";
        let maintenanceHtml = "";
        
        let criticalCount = 0;
        let maintenanceCount = 0;
        
        subjects.forEach(s => {
            const isHighWeight = highWeightFiles.includes(s.subject);
            if (isHighWeight) {
                const name = s.name || MANUAL_NAMES[s.subject] || s.subject?.replace('.pdf', '');
                const pct = s.percent || 0;
                
                if (pct < 65) {
                    criticalCount++;
                    criticalHtml += `
                        <div style="display:flex; justify-content:space-between; align-items:center; background: rgba(239,68,68,0.06); border: 1px solid rgba(239,68,68,0.15); padding: 8px 12px; border-radius: 8px; margin-bottom: 4px;">
                            <span style="font-size:0.85rem; color:#cbd5e1; font-weight:500;">${name}</span>
                            <span style="font-size:0.75rem; background:var(--diag-red); color:#fff; padding: 2px 8px; border-radius: 100px; font-weight: 600;">${pct}%</span>
                        </div>`;
                } else {
                    maintenanceCount++;
                    maintenanceHtml += `
                        <div style="display:flex; justify-content:space-between; align-items:center; background: rgba(34,197,94,0.06); border: 1px solid rgba(34,197,94,0.15); padding: 8px 12px; border-radius: 8px; margin-bottom: 4px;">
                            <span style="font-size:0.85rem; color:#cbd5e1; font-weight:500;">${name}</span>
                            <span style="font-size:0.75rem; background:var(--diag-green); color:#fff; padding: 2px 8px; border-radius: 100px; font-weight: 600;">${pct}%</span>
                        </div>`;
                }
            }
        });
        
        if (criticalCount === 0) {
            criticalEl.innerHTML = '<p style="color:#64748b; font-size:0.82rem; font-style:italic; padding: 8px;">¡Excelente! No tienes materias de alto peso en zona crítica.</p>';
        } else {
            criticalEl.innerHTML = criticalHtml;
        }
        
        if (maintenanceCount === 0) {
            maintenanceEl.innerHTML = '<p style="color:#64748b; font-size:0.82rem; font-style:italic; padding: 8px;">No hay materias en mantenimiento de alto peso todavía.</p>';
        } else {
            maintenanceEl.innerHTML = maintenanceHtml;
        }
    }

    function renderTutorRecommendations(subjects, correct, incorrect, skipped) {
        const recEl = document.getElementById('tutor-recommendations');
        const recs = [];
        
        const highWeightFiles = [
            "CD.pdf", "NR.pdf", "DG.pdf", "PD.pdf", "GC.pdf",
            "ED.pdf", "TM.pdf", "IF.pdf", "NF.pdf", "NM.pdf", "HM.pdf"
        ];
        
        // Find weakest and strongest high weight subjects
        const criticalSubjects = subjects.filter(s => highWeightFiles.includes(s.subject) && (s.percent || 0) < 65);
        const strongSubjects = subjects.filter(s => highWeightFiles.includes(s.subject) && (s.percent || 0) >= 80);
        
        if (criticalSubjects.length > 0) {
            criticalSubjects.sort((a,b) => a.percent - b.percent); // ASCENDING (lowest first)
            const worst = criticalSubjects[0];
            const name = worst.name || MANUAL_NAMES[worst.subject] || worst.subject?.replace('.pdf', '');
            recs.push(`<strong>Prioridad de Estudio Urgente:</strong> Se ha detectado un rendimiento bajo (${worst.percent}%) en <strong>${name}</strong>. Esta materia tiene un peso crítico en el examen real. Concéntrate en leer sus manuales CTO en la biblioteca RAG.`);
        }
        
        if (strongSubjects.length > 0) {
            strongSubjects.sort((a,b) => b.percent - a.percent); // DESCENDING (highest first)
            const best = strongSubjects[0];
            const name = best.name || MANUAL_NAMES[best.subject] || best.subject?.replace('.pdf', '');
            recs.push(`<strong>Dominio Destacado:</strong> ¡Excelente trabajo en <strong>${name}</strong>! Tienes una precisión de ${best.percent}%. Puedes programar repasos más espaciados para esta materia y optimizar tu tiempo.`);
        }
        
        if (skipped > 8) {
            recs.push(`<strong>Estrategia de Examen (Omitidas):</strong> Has dejado en blanco ${skipped} preguntas. En el examen MIR, la penalización de un error (-1) frente a una correcta (+3) hace que estadísticamente convenga arriesgarse si consigues descartar 2 de las 4 opciones.`);
        } else if (incorrect > correct) {
            recs.push(`<strong>Estrategia de Precisión (Errores):</strong> Tienes más fallos que aciertos. Intenta leer con mayor atención los enunciados (especialmente las preguntas en negativo "Señala la INCORRECTA") y no te precipites al responder.`);
        }
        
        recs.push(`<strong>Recomendación General:</strong> Dirígete al <strong>Simulador de Tests</strong> para crear un examen personalizado enfocado exclusivamente en las asignaturas donde tu rendimiento fue menor al 65%.`);
        
        recEl.innerHTML = recs.map(r => `<li style="margin-bottom: 8px;">${r}</li>`).join('');
    }

    async function renderHistoryChart() {
        // SWR: Load from cache instantly
        const cachedHistory = sessionStorage.getItem('diagnosticHistory');
        if (cachedHistory) {
            try {
                const history = JSON.parse(cachedHistory).reverse();
                renderChartWithData(history);
            } catch (e) {
                sessionStorage.removeItem('diagnosticHistory');
            }
        }

        try {
            const res = await fetch('/api/diagnostic/history');
            const data = await res.json();
            const history = (data.history || []).reverse();
            sessionStorage.setItem('diagnosticHistory', JSON.stringify(data.history || []));
            renderChartWithData(history);
        } catch (e) { console.warn('History chart error:', e); }
    }

    function renderChartWithData(history) {
        if (history.length < 2) { document.getElementById('progress-section').style.display = 'none'; return; }
        document.getElementById('progress-section').style.display = 'block';
        const ctx = document.getElementById('history-chart').getContext('2d');
        if (historyChart) historyChart.destroy();
        historyChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: history.map((_,i) => `Test ${i+1}`),
                datasets: [{
                    label: 'Nota MIR', data: history.map(h => parseFloat(h.mir_score||0)),
                    borderColor:'#a855f7', backgroundColor:'rgba(168,85,247,0.12)',
                    fill:true, tension:0.4, pointBackgroundColor:'#a855f7', pointRadius:5, pointHoverRadius:7,
                }]
            },
            options: {
                responsive: true,
                scales: {
                    y:{ min:0, max:10, ticks:{color:'#64748b',font:{size:11}}, grid:{color:'rgba(255,255,255,0.06)'}},
                    x:{ ticks:{color:'#64748b',font:{size:11}}, grid:{color:'rgba(255,255,255,0.04)'}}
                },
                plugins: { legend:{display:false}, tooltip:{callbacks:{label: c => ` ${c.raw.toFixed(1)} / 10`}} }
            }
        });
    }

    return { init, start, answer, skip, next, showWelcome, viewResults };
})();

document.addEventListener('DOMContentLoaded', () => DiagApp.init());
