document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const loginOverlay = document.getElementById('login-overlay');
    const loginForm = document.getElementById('login-form');
    const loginUsername = document.getElementById('login-username');
    const loginPassword = document.getElementById('login-password');
    const loginError = document.getElementById('login-error');
    
    const userDisplayName = document.getElementById('user-display-name');
    const btnLogout = document.getElementById('btn-logout');
    
    // Config form
    const configForm = document.getElementById('test-config-form');
    const testSubjectSelect = document.getElementById('test-subject');
    const configPanelCard = document.getElementById('config-panel-card');
    
    // Dashboard stats
    const statsPct = document.getElementById('stats-pct');
    const statsTotal = document.getElementById('stats-total');
    const subjectProgressList = document.getElementById('subject-progress-list');
    
    // Welcome / Active / Finished states
    const welcomeState = document.getElementById('test-welcome-state');
    const activeState = document.getElementById('test-active-state');
    const finishedState = document.getElementById('test-finished-state');
    
    // Active question elements
    const progressText = document.getElementById('test-progress-text');
    const progressFill = document.getElementById('test-progress-fill');
    const questionSubject = document.getElementById('active-question-subject');
    const questionText = document.getElementById('active-question-text');
    const optionsList = document.getElementById('active-options-list');
    
    // Explanation block
    const explanationCard = document.getElementById('active-explanation-card');
    const explanationText = document.getElementById('active-explanation-text');
    const explanationSource = document.getElementById('active-explanation-source');
    
    const btnNextQuestion = document.getElementById('btn-next-question');
    const btnRestartSimulator = document.getElementById('btn-restart-simulator');

    // State Variables
    let currentUser = null;
    let availableSubjects = [];
    
    let testSessionId = null;
    let testSubject = 'All';
    let testTotalQuestions = 5;
    let testCurrentIndex = 0;
    let testScore = 0;
    let currentQuestion = null;
    let hasAnsweredCurrent = false;

    // Initialize Page
    checkAuth();

    // Check Authentication Status
    async function checkAuth() {
        try {
            const res = await fetch('/api/auth/me');
            if (res.ok) {
                currentUser = await res.json();
                userDisplayName.textContent = currentUser.username;
                loginOverlay.style.display = 'none';
                
                // Load available manuals and performance stats
                await loadAvailableManuals();
                await loadPerformanceStats();
            } else {
                loginOverlay.style.display = 'flex';
            }
        } catch (e) {
            console.error("Auth check failed:", e);
            loginOverlay.style.display = 'flex';
        }
    }

    // Handle Login Form Submission
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        loginError.style.display = 'none';
        
        const username = loginUsername.value;
        const password = loginPassword.value;
        
        const formData = new FormData();
        formData.append('username', username);
        formData.append('password', password);
        
        try {
            const res = await fetch('/api/auth/login', {
                method: 'POST',
                body: formData
            });
            
            if (res.ok) {
                await checkAuth();
            } else {
                const data = await res.json();
                loginError.textContent = data.detail || "Error al iniciar sesión.";
                loginError.style.display = 'block';
            }
        } catch (err) {
            console.error("Login request failed:", err);
            loginError.textContent = "Error de conexión con el servidor.";
            loginError.style.display = 'block';
        }
    });

    // Handle Logout
    btnLogout.addEventListener('click', async () => {
        try {
            const res = await fetch('/api/auth/logout', { method: 'POST' });
            if (res.ok) {
                window.location.href = '/test';
            }
        } catch (e) {
            console.error("Logout request failed:", e);
        }
    });

    // Load available manuals into subject select dropdown
    async function loadAvailableManuals() {
        try {
            const res = await fetch('/api/status');
            if (res.ok) {
                const data = await res.json();
                availableSubjects = data.files || [];
                
                // Clear dropdown except first "All" option
                testSubjectSelect.innerHTML = '<option value="All">Aleatorio (Todas las materias)</option>';
                
                availableSubjects.forEach(file => {
                    const opt = document.createElement('option');
                    opt.value = file.name;
                    opt.textContent = file.readable_name;
                    testSubjectSelect.appendChild(opt);
                });
            }
        } catch (e) {
            console.error("Error loading manuals list:", e);
        }
    }

    // Load user test performance stats
    async function loadPerformanceStats() {
        try {
            const res = await fetch('/api/tests/stats');
            if (res.ok) {
                const data = await res.json();
                statsPct.textContent = `${data.success_rate}%`;
                statsTotal.textContent = data.total_answers;
                
                subjectProgressList.innerHTML = '';
                if (!data.subjects || data.subjects.length === 0) {
                    subjectProgressList.innerHTML = '<p class="empty-list" style="font-size:11px;">Aún no has respondido preguntas de test.</p>';
                    return;
                }
                
                // Sort subjects by total answers descending
                const sortedSubjects = [...data.subjects].sort((a, b) => b.total - a.total);
                
                sortedSubjects.forEach(sub => {
                    const pct = sub.percent;
                    let progressColorClass = 'red';
                    if (pct >= 70) progressColorClass = 'green';
                    else if (pct >= 50) progressColorClass = 'yellow';
                    
                    const progressItem = document.createElement('div');
                    progressItem.className = 'subject-progress-item';
                    progressItem.innerHTML = `
                        <div class="subject-info" style="display:flex; justify-content:space-between; font-size:11px; margin-bottom:4px;">
                            <span class="subject-name" style="font-weight:500; color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:160px;" title="${sub.name}">${sub.name}</span>
                            <span class="subject-ratio" style="color:var(--text-muted);">${sub.correct}/${sub.total} (${pct}%)</span>
                        </div>
                        <div class="progress-bar-bg" style="height:6px; background:rgba(255,255,255,0.05); border-radius:3px; overflow:hidden;">
                            <div class="progress-bar-fill ${progressColorClass}" style="width:${pct}%; height:100%; border-radius:3px;"></div>
                        </div>
                    `;
                    subjectProgressList.appendChild(progressItem);
                });
            }
        } catch (e) {
            console.error("Error loading performance stats:", e);
        }
    }

    // Handle Start Test Form Submit
    configForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        testSubject = testSubjectSelect.value;
        const selectedSize = document.querySelector('input[name="test-size"]:checked');
        testTotalQuestions = parseInt(selectedSize ? selectedSize.value : 5);
        
        testSessionId = Date.now().toString();
        testCurrentIndex = 1;
        testScore = 0;
        
        // Log new test session to server
        const sessionFormData = new FormData();
        sessionFormData.append('test_id', testSessionId);
        sessionFormData.append('subject', testSubject);
        sessionFormData.append('total_questions', testTotalQuestions);
        
        try {
            const startRes = await fetch('/api/tests/session', {
                method: 'POST',
                body: sessionFormData
            });
            
            if (startRes.ok) {
                // Switch states
                welcomeState.style.display = 'none';
                finishedState.style.display = 'none';
                activeState.style.display = 'block';
                configPanelCard.style.pointerEvents = 'none';
                configPanelCard.style.opacity = '0.5';
                
                await fetchQuestion();
            } else {
                alert("Error al iniciar sesión de test.");
            }
        } catch (err) {
            console.error("Error initiating test session:", err);
            alert("Error de conexión al iniciar el examen.");
        }
    });

    // Fetch question from server RAG Vector Store & LLM
    async function fetchQuestion() {
        hasAnsweredCurrent = false;
        explanationCard.style.display = 'none';
        
        // Render Loading State (Skeleton or spinner)
        questionSubject.textContent = "Cargando...";
        questionText.innerHTML = '<span class="loading-pulse">Generando pregunta tipo MIR con la IA a partir de los apuntes... <i class="fa-solid fa-spinner fa-spin"></i></span>';
        optionsList.innerHTML = '';
        
        // Update Progress Bar UI
        progressText.textContent = `Pregunta ${testCurrentIndex} de ${testTotalQuestions}`;
        const pctPercent = (testCurrentIndex / testTotalQuestions) * 100;
        progressFill.style.width = `${pctPercent}%`;
        
        // Fetch Question API
        const questionFormData = new FormData();
        questionFormData.append('subject', testSubject);
        
        try {
            const res = await fetch('/api/tests/generate-question', {
                method: 'POST',
                body: questionFormData
            });
            
            if (res.ok) {
                currentQuestion = await res.json();
                renderQuestion();
            } else {
                const data = await res.json();
                questionText.textContent = `Error: ${data.detail || "No se pudo generar la pregunta. Verifica que el tema seleccionado contenga documentos indexados."}`;
                questionSubject.textContent = "Error";
            }
        } catch (err) {
            console.error("Error fetching question:", err);
            questionText.textContent = "Error de red al conectar con el servidor.";
            questionSubject.textContent = "Error de red";
        }
    }

    // Render loaded question structure
    function renderQuestion() {
        const docNameRaw = currentQuestion.source_doc;
        const readableSubj = getReadableSubjectName(docNameRaw);
        
        questionSubject.textContent = readableSubj;
        questionText.textContent = currentQuestion.question;
        
        optionsList.innerHTML = '';
        currentQuestion.options.forEach((opt, idx) => {
            const btn = document.createElement('button');
            btn.className = 'option-btn';
            btn.innerHTML = `
                <span class="option-num">${idx + 1}</span>
                <span class="option-content">${opt}</span>
            `;
            btn.addEventListener('click', () => selectOption(idx, btn));
            optionsList.appendChild(btn);
        });
    }

    // Helper: Map raw filename to readable subject
    function getReadableSubjectName(filename) {
        if (!availableSubjects || availableSubjects.length === 0) return filename.replace('.pdf', '');
        const matched = availableSubjects.find(f => f.name === filename);
        return matched ? matched.readable_name : filename.replace('.pdf', '');
    }

    // User chooses a multiple-choice option
    async function selectOption(selectedIndex, btnElement) {
        if (hasAnsweredCurrent) return;
        hasAnsweredCurrent = true;
        
        const isCorrect = (selectedIndex === currentQuestion.correct_index);
        
        // Highlight correct option in green, user selection in red if incorrect
        const optionBtns = optionsList.querySelectorAll('.option-btn');
        optionBtns.forEach((btn, idx) => {
            if (idx === currentQuestion.correct_index) {
                btn.classList.add('correct');
                const numSpan = btn.querySelector('.option-num');
                numSpan.innerHTML = '<i class="fa-solid fa-circle-check"></i>';
            } else if (idx === selectedIndex && !isCorrect) {
                btn.classList.add('incorrect');
                const numSpan = btn.querySelector('.option-num');
                numSpan.innerHTML = '<i class="fa-solid fa-circle-xmark"></i>';
            }
            btn.style.cursor = 'default';
        });

        // Save answer results to SQLite database
        const answerFormData = new FormData();
        answerFormData.append('test_session_id', testSessionId);
        answerFormData.append('question', currentQuestion.question);
        answerFormData.append('subject', currentQuestion.source_doc);
        answerFormData.append('is_correct', isCorrect ? 1 : 0);
        
        if (isCorrect) testScore++;
        
        try {
            await fetch('/api/tests/answer', {
                method: 'POST',
                body: answerFormData
            });
        } catch (e) {
            console.error("Error logging answer response:", e);
        }

        // Show Explanation Details Card
        explanationText.textContent = currentQuestion.explanation;
        explanationSource.textContent = `Manual: ${getReadableSubjectName(currentQuestion.source_doc)} | ${currentQuestion.source_page || 'Sin Pág.'}`;
        explanationCard.style.display = 'block';
        
        // Scroll explanation into view
        activeState.scrollTop = activeState.scrollHeight;
        
        // Update Next Question button text
        if (testCurrentIndex >= testTotalQuestions) {
            btnNextQuestion.innerHTML = 'Ver Resultados <i class="fa-solid fa-square-poll-vertical"></i>';
        } else {
            btnNextQuestion.innerHTML = 'Siguiente Pregunta <i class="fa-solid fa-arrow-right"></i>';
        }
    }

    // Handle Click Next Question / End test
    btnNextQuestion.addEventListener('click', async () => {
        if (testCurrentIndex < testTotalQuestions) {
            testCurrentIndex++;
            await fetchQuestion();
        } else {
            endTest();
        }
    });

    // Handle Finish Test Session
    async function endTest() {
        activeState.style.display = 'none';
        finishedState.style.display = 'block';
        
        configPanelCard.style.pointerEvents = 'auto';
        configPanelCard.style.opacity = '1';
        
        const successRate = Math.round((testScore / testTotalQuestions) * 100);
        document.getElementById('finished-score-text').textContent = `Has respondido correctamente ${testScore} de ${testTotalQuestions} preguntas (${successRate}% de aciertos).`;
        
        // Reload Stats Scoreboard
        await loadPerformanceStats();
    }

    // Restart Test Simulator button
    btnRestartSimulator.addEventListener('click', () => {
        finishedState.style.display = 'none';
        welcomeState.style.display = 'flex';
    });
});
