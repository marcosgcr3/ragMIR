document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements - Auth & Stats
    const loginOverlay = document.getElementById('login-overlay');
    const loginForm = document.getElementById('login-form');
    const loginUsername = document.getElementById('login-username');
    const loginPassword = document.getElementById('login-password');
    const loginError = document.getElementById('login-error');
    
    const userProfile = document.getElementById('user-profile');
    const userDisplayName = document.getElementById('user-display-name');
    const btnLogout = document.getElementById('btn-logout');
    const btnShowStats = document.getElementById('btn-show-stats');
    
    const statsModal = document.getElementById('stats-modal');
    const btnCloseStats = document.getElementById('btn-close-stats');
    const kpiQueries = document.getElementById('kpi-queries');
    const kpiTokens = document.getElementById('kpi-tokens');
    const kpiDays = document.getElementById('kpi-days');
    const statsChartBars = document.getElementById('stats-chart-bars');

    // DOM Elements - Core Chat
    const chatMessages = document.getElementById('chat-messages');
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const fileInput = document.getElementById('file-input');
    const imageInput = document.getElementById('image-input');
    const dropZone = document.getElementById('drop-zone');
    const btnAttach = document.getElementById('btn-attach');
    const btnSend = document.getElementById('btn-send');
    const btnRemoveImage = document.getElementById('btn-remove-image');
    
    const imagePreviewArea = document.getElementById('image-preview-area');
    const imagePreviewSrc = document.getElementById('image-preview-src');
    const welcomeBanner = document.getElementById('welcome-banner');
    
    // Sidebar elements
    const statCollection = document.getElementById('stat-collection');
    const statChunks = document.getElementById('stat-chunks');
    const statLlm = document.getElementById('stat-llm');
    const indexedFilesList = document.getElementById('indexed-files-list');
    const dbIndicator = document.getElementById('db-indicator');
    const chatSessionsList = document.getElementById('chat-sessions-list');
    const btnNewChat = document.getElementById('btn-new-chat');
    
    // Upload Progress
    const uploadProgressContainer = document.getElementById('upload-progress-container');
    const uploadProgress = document.getElementById('upload-progress');
    const uploadStatusText = document.getElementById('upload-status-text');

    // Global Chat State
    let sessions = [];
    let currentSessionId = null;
    let currentUser = null;
    let attachedImageFile = null;
    let attachedImageBase64 = null;

    // Helper: Simple Markdown Formatter
    function formatResponseText(text) {
        let html = text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");

        // Bold formatting (**text**)
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

        // Lists (converts lines starting with * or - into list items)
        let inList = false;
        const lines = html.split('\n');
        const formattedLines = lines.map(line => {
            const listMatch = line.match(/^(\s*[\*\-]\s+)(.*)$/);
            if (listMatch) {
                let content = listMatch[2];
                if (!inList) {
                    inList = true;
                    return '<ul><li>' + content + '</li>';
                }
                return '<li>' + content + '</li>';
            } else {
                if (inList) {
                    inList = false;
                    return '</ul>' + line;
                }
                return line;
            }
        });
        if (inList) {
            formattedLines.push('</ul>');
        }
        
        return formattedLines.join('<br>').replace(/<\/ul><br>/g, '</ul>');
    }

    // Check session on load
    async function checkAuthStatus() {
        try {
            const res = await fetch('/api/auth/me');
            if (res.ok) {
                currentUser = await res.json();
                showAuthenticatedUI(currentUser.username);
            } else {
                showLoginUI();
            }
        } catch (err) {
            console.error("Auth check failed:", err);
            showLoginUI();
        }
    }

    function showLoginUI() {
        loginOverlay.style.display = 'flex';
        userProfile.style.display = 'none';
    }

    function showAuthenticatedUI(username) {
        loginOverlay.style.display = 'none';
        userDisplayName.textContent = username;
        userProfile.style.display = 'flex';
        
        // Initialize App data
        loadSessions();
        checkDatabaseStatus();
    }

    // Login Form handler
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
                const data = await res.json();
                loginPassword.value = '';
                showAuthenticatedUI(data.username);
            } else {
                const errorData = await res.json();
                loginError.textContent = errorData.detail || "Error al iniciar sesión.";
                loginError.style.display = 'block';
            }
        } catch (err) {
            console.error("Login request failed:", err);
            loginError.textContent = "Error de red al conectar con el servidor.";
            loginError.style.display = 'block';
        }
    });

    // Logout Handler
    btnLogout.addEventListener('click', async () => {
        try {
            await fetch('/api/auth/logout', { method: 'POST' });
            currentUser = null;
            sessions = [];
            currentSessionId = null;
            showLoginUI();
        } catch (err) {
            console.error("Logout failed:", err);
        }
    });

    // Statistics Modal Handlers
    btnShowStats.addEventListener('click', async () => {
        try {
            const res = await fetch('/api/stats');
            if (!res.ok) throw new Error("Could not retrieve stats.");
            
            const stats = await res.json();
            
            // Populate metrics
            kpiQueries.textContent = stats.total_queries;
            kpiTokens.textContent = stats.total_tokens.toLocaleString();
            kpiDays.textContent = stats.active_days;
            
            // Render chart
            statsChartBars.innerHTML = '';
            const dayData = stats.queries_by_day || [];
            
            if (dayData.length === 0) {
                statsChartBars.innerHTML = '<p class="empty-chart">Aún no hay actividad registrada.</p>';
            } else {
                const maxCount = Math.max(...dayData.map(d => d.count), 1);
                
                dayData.forEach(d => {
                    // Date formatting (e.g. "2026-07-02" -> "02/07")
                    let label = d.date;
                    try {
                        const parts = d.date.split('-');
                        if (parts.length === 3) {
                            label = `${parts[2]}/${parts[1]}`;
                        }
                    } catch (e) {}
                    
                    const heightPercent = (d.count / maxCount) * 100;
                    
                    const barWrapper = document.createElement('div');
                    barWrapper.className = 'bar-wrapper';
                    barWrapper.innerHTML = `
                        <span class="bar-count">${d.count}</span>
                        <div class="bar-fill" style="height: ${heightPercent}%"></div>
                        <span class="bar-label">${label}</span>
                    `;
                    statsChartBars.appendChild(barWrapper);
                });
            }
            
            statsModal.style.display = 'flex';
        } catch (err) {
            alert("Error al cargar las estadísticas: " + err.message);
        }
    });

    btnCloseStats.addEventListener('click', () => {
        statsModal.style.display = 'none';
    });

    // Close modal on background click
    statsModal.addEventListener('click', (e) => {
        if (e.target === statsModal) {
            statsModal.style.display = 'none';
        }
    });

    // Server-side Session Management
    async function loadSessions() {
        try {
            const res = await fetch('/api/sessions');
            if (!res.ok) throw new Error();
            sessions = await res.json();
            
            if (sessions.length === 0) {
                await createNewSession();
            } else {
                currentSessionId = sessions[0].id;
                renderSessionsList();
                await loadCurrentSessionMessages();
            }
        } catch (e) {
            console.error("Error loading sessions from server:", e);
        }
    }

    async function createNewSession() {
        const newId = Date.now().toString();
        const newSession = {
            id: newId,
            title: "Nueva Consulta",
            messages: []
        };
        
        const formData = new FormData();
        formData.append('session_id', newId);
        formData.append('title', newSession.title);
        
        try {
            const res = await fetch('/api/sessions', {
                method: 'POST',
                body: formData
            });
            if (res.ok) {
                sessions.unshift(newSession);
                currentSessionId = newId;
                renderSessionsList();
                renderChatMessages();
            }
        } catch (err) {
            console.error("Error creating session on server:", err);
        }
    }

    async function deleteSession(id, event) {
        if (event) event.stopPropagation();
        
        const confirmDelete = confirm("¿Estás seguro de que deseas eliminar esta consulta?");
        if (!confirmDelete) return;

        try {
            const res = await fetch(`/api/sessions/${id}`, {
                method: 'DELETE'
            });
            
            if (res.ok) {
                sessions = sessions.filter(s => s.id !== id);
                renderSessionsList();
                if (sessions.length === 0) {
                    await createNewSession();
                } else {
                    if (currentSessionId === id) {
                        currentSessionId = sessions[0].id;
                        await loadCurrentSessionMessages();
                    }
                }
            }
        } catch (e) {
            console.error("Error deleting session:", e);
        }
    }

    async function selectSession(id) {
        currentSessionId = id;
        btnRemoveImage.click(); // Reset attached images
        renderSessionsList();
        await loadCurrentSessionMessages();
    }

    async function loadCurrentSessionMessages() {
        const currentSession = sessions.find(s => s.id === currentSessionId);
        if (!currentSession) return;
        
        try {
            const res = await fetch(`/api/sessions/${currentSessionId}/messages`);
            if (res.ok) {
                currentSession.messages = await res.json();
                renderChatMessages();
            }
        } catch (e) {
            console.error("Error fetching messages for session:", e);
        }
    }

    function renderSessionsList() {
        chatSessionsList.innerHTML = '';
        sessions.forEach(session => {
            const li = document.createElement('li');
            li.className = session.id === currentSessionId ? 'active' : '';
            li.addEventListener('click', () => selectSession(session.id));
            
            const titleSpan = document.createElement('span');
            titleSpan.className = 'session-title';
            titleSpan.innerHTML = `<i class="fa-regular fa-comment-medical"></i> ${session.title}`;
            
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'btn-delete-session';
            deleteBtn.title = 'Eliminar consulta';
            deleteBtn.innerHTML = '<i class="fa-solid fa-trash-can"></i>';
            deleteBtn.addEventListener('click', (e) => deleteSession(session.id, e));
            
            li.appendChild(titleSpan);
            li.appendChild(deleteBtn);
            chatSessionsList.appendChild(li);
        });
    }

    // Render Chat Message History for current active session
    function renderChatMessages() {
        chatMessages.innerHTML = '';
        const currentSession = sessions.find(s => s.id === currentSessionId);
        if (!currentSession || !currentSession.messages || currentSession.messages.length === 0) {
            chatMessages.appendChild(welcomeBanner);
            welcomeBanner.style.display = 'flex';
            return;
        }

        welcomeBanner.style.display = 'none';

        currentSession.messages.forEach(msg => {
            const msgDiv = document.createElement('div');
            msgDiv.className = `message message-${msg.role === 'user' ? 'user' : 'bot'}`;
            
            let avatarIcon = msg.role === 'user' ? 'fa-user' : 'fa-notes-medical';
            let bubbleHtml = `
                <div class="message-avatar"><i class="fa-solid ${avatarIcon}"></i></div>
                <div class="message-content-wrapper">
                    <div class="message-bubble">${msg.role === 'user' ? msg.content.replace(/\n/g, '<br>') : formatResponseText(msg.content)}</div>
            `;

            // If user attached image (which is stored in database as image_base64)
            if (msg.role === 'user' && (msg.image_base64 || msg.imageBase64)) {
                const imgUrl = msg.image_base64 || msg.imageBase64;
                bubbleHtml += `<img class="message-image" src="${imgUrl}" alt="Imagen enviada">`;
            }

            // If bot cites sources
            if (msg.role === 'model' && msg.sources && msg.sources.length > 0) {
                bubbleHtml += `
                    <div class="sources-container">
                        <div class="sources-header">Fuentes consultadas:</div>
                        <div class="sources-list">
                `;
                msg.sources.forEach(src => {
                    const cleanName = src.source.replace('.pdf', '');
                    bubbleHtml += `
                        <div class="source-item" title="${src.source} (Similitud: ${(src.similarity * 100).toFixed(1)}%)">
                            <i class="fa-solid fa-file-pdf"></i>
                            <span class="source-name">${cleanName}</span>
                            <span class="source-page">${src.location}</span>
                        </div>
                    `;
                });
                bubbleHtml += `
                        </div>
                    </div>
                `;
            }

            bubbleHtml += `</div>`; // Close message-content-wrapper
            msgDiv.innerHTML = bubbleHtml;
            chatMessages.appendChild(msgDiv);
        });
        
        scrollToBottom();
    }

    // Scroll chat area to bottom
    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // DB Status and Metadata Check
    async function checkDatabaseStatus() {
        try {
            const response = await fetch('/api/status');
            const data = await response.json();
            
            if (data.exists) {
                dbIndicator.className = 'pulse-dot active';
                dbIndicator.style.backgroundColor = 'var(--system-green)';
                statCollection.textContent = data.collection;
                statChunks.textContent = data.total_chunks;
                statLlm.textContent = data.model;
                
                renderIndexedFiles(data.files || []);
            } else {
                dbIndicator.className = 'pulse-dot inactive';
                dbIndicator.style.backgroundColor = 'var(--text-muted)';
                statCollection.textContent = '-';
                statChunks.textContent = '-';
                statLlm.textContent = '-';
                indexedFilesList.innerHTML = '<li class="empty-list">No hay colección de base de datos activa.</li>';
            }
        } catch (e) {
            console.error("Error checking database status:", e);
            dbIndicator.className = 'pulse-dot inactive';
            dbIndicator.style.backgroundColor = 'var(--system-red)';
        }
    }

    function renderIndexedFiles(files) {
        indexedFilesList.innerHTML = '';
        if (files.length === 0) {
            indexedFilesList.innerHTML = '<li class="empty-list">No hay documentos indexados.</li>';
            return;
        }

        files.forEach(file => {
            const li = document.createElement('li');
            li.innerHTML = `
                <div class="doc-info">
                    <i class="fa-solid fa-file-pdf"></i>
                    <span class="doc-name" title="${file.name}">${file.name}</span>
                </div>
                <span class="doc-badge">${file.chunks} chunks</span>
            `;
            indexedFilesList.appendChild(li);
        });
    }

    // Check Database Status every 30 seconds
    setInterval(checkDatabaseStatus, 30000);

    // Event Listeners for file attachment triggers
    btnAttach.addEventListener('click', () => {
        imageInput.click();
    });

    // Handle Image Attachment Preview
    function handleImageAttachment(file) {
        if (!file.type.startsWith('image/')) {
            alert('Por favor, selecciona solo archivos de imagen (PNG, JPG, etc.)');
            return;
        }
        
        attachedImageFile = file;
        
        const reader = new FileReader();
        reader.onload = (event) => {
            imagePreviewSrc.src = event.target.result;
            attachedImageBase64 = event.target.result;
            imagePreviewArea.style.display = 'block';
            scrollToBottom();
        };
        reader.readAsDataURL(file);
    }

    // Image selection change
    imageInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) handleImageAttachment(file);
    });

    // Remove image preview
    btnRemoveImage.addEventListener('click', () => {
        attachedImageFile = null;
        attachedImageBase64 = null;
        imageInput.value = '';
        imagePreviewSrc.src = '';
        imagePreviewArea.style.display = 'none';
    });

    // Create a new chat session
    btnNewChat.addEventListener('click', () => {
        createNewSession();
    });

    // Auto-grow textarea height dynamically
    chatInput.addEventListener('input', () => {
        chatInput.style.height = 'auto';
        chatInput.style.height = (chatInput.scrollHeight) + 'px';
    });

    // Handle shift+enter vs enter key
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event('submit'));
        }
    });

    // Handle Query Form Submit
    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const questionText = chatInput.value.trim();
        if (!questionText && !attachedImageFile) return;

        const currentSession = sessions.find(s => s.id === currentSessionId);
        if (!currentSession) return;

        // Update session title on the first user message
        if (currentSession.messages.length === 0 && questionText) {
            const shortTitle = questionText.length > 22 ? questionText.slice(0, 22) + '...' : questionText;
            currentSession.title = shortTitle;
            
            // Optionally update title in DB
            const formTitle = new FormData();
            formTitle.append('session_id', currentSessionId);
            formTitle.append('title', shortTitle);
            fetch('/api/sessions', { method: 'POST', body: formTitle }).then(() => renderSessionsList());
        }

        // 1. Add User Message to State
        const userMsg = {
            role: 'user',
            content: questionText,
            imageBase64: attachedImageBase64
        };
        currentSession.messages.push(userMsg);
        renderChatMessages();

        // 2. Clear inputs and preview area
        chatInput.value = '';
        chatInput.style.height = 'auto';
        const currentImageFile = attachedImageFile;
        btnRemoveImage.click(); // Reset preview UI

        // 3. Render Bot Loading Bubble
        const botLoadingDiv = document.createElement('div');
        botLoadingDiv.className = 'message message-bot';
        botLoadingDiv.id = 'bot-loading-bubble';
        botLoadingDiv.innerHTML = `
            <div class="message-avatar"><i class="fa-solid fa-notes-medical"></i></div>
            <div class="message-content-wrapper">
                <div class="message-bubble">
                    <div class="typing-dots">
                        <span></span>
                        <span></span>
                        <span></span>
                    </div>
                </div>
            </div>
        `;
        chatMessages.appendChild(botLoadingDiv);
        scrollToBottom();

        // 4. Construct Request Body with Memory/History
        const formData = new FormData();
        formData.append('question', questionText);
        formData.append('session_id', currentSessionId);
        if (currentImageFile) {
            formData.append('image', currentImageFile);
        }

        // Build history excluding images (to keep request lightweight)
        // Only take the last 6 messages to prevent hitting context limits
        const historyContext = currentSession.messages
            .slice(0, -1) // exclude current user question we just appended
            .slice(-6)   // only take last 6 messages (3 turns)
            .map(msg => ({
                role: msg.role,
                content: msg.content
            }));
            
        formData.append('history', JSON.stringify(historyContext));

        try {
            // Fetch API Response
            const res = await fetch('/api/query', {
                method: 'POST',
                body: formData
            });

            // Remove loading indicator
            const loadingBubble = document.getElementById('bot-loading-bubble');
            if (loadingBubble) loadingBubble.remove();

            if (!res.ok) {
                const errorData = await res.json();
                throw new Error(errorData.error || "Ocurrió un error en el servidor.");
            }

            const data = await res.json();

            // 5. Add Bot Message to State
            const botMsg = {
                role: 'model',
                content: data.answer,
                sources: data.sources,
                usage: data.usage
            };
            currentSession.messages.push(botMsg);
            renderChatMessages();

        } catch (err) {
            // Remove loading indicator on failure
            const loadingBubble = document.getElementById('bot-loading-bubble');
            if (loadingBubble) loadingBubble.remove();

            const botErrorDiv = document.createElement('div');
            botErrorDiv.className = 'message message-bot';
            botErrorDiv.innerHTML = `
                <div class="message-avatar"><i class="fa-solid fa-notes-medical"></i></div>
                <div class="message-content-wrapper">
                    <div class="message-bubble error-bubble">
                        <i class="fa-solid fa-circle-exclamation"></i> Error: ${err.message}
                    </div>
                </div>
            `;
            chatMessages.appendChild(botErrorDiv);
            scrollToBottom();
        }
    });

    // PDF upload drag-and-drop
    dropZone.addEventListener('click', () => {
        fileInput.click();
    });

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFileUpload(files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        const files = e.target.files;
        if (files.length > 0) {
            handleFileUpload(files[0]);
        }
    });

    async function handleFileUpload(file) {
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            alert('Solo se permiten archivos PDF.');
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        uploadProgressContainer.style.display = 'block';
        uploadProgress.style.width = '10%';
        uploadStatusText.textContent = 'Subiendo...';

        try {
            const xhr = new XMLHttpRequest();
            xhr.open('POST', '/api/upload', true);

            xhr.upload.onprogress = (e) => {
                if (e.lengthComputable) {
                    const percentComplete = (e.loaded / e.total) * 100;
                    uploadProgress.style.width = percentComplete + '%';
                    if (percentComplete === 100) {
                        uploadStatusText.textContent = 'Procesando e Indexando...';
                    }
                }
            };

            xhr.onload = async () => {
                if (xhr.status === 200) {
                    uploadProgress.style.width = '100%';
                    uploadStatusText.textContent = 'Indexando en segundo plano...';
                    setTimeout(() => {
                        uploadProgressContainer.style.display = 'none';
                        checkDatabaseStatus();
                    }, 3000);
                } else {
                    const errResponse = JSON.parse(xhr.responseText);
                    alert('Error: ' + (errResponse.detail || 'Fallo al subir el archivo'));
                    uploadProgressContainer.style.display = 'none';
                }
            };

            xhr.onerror = () => {
                alert('Error de red al subir el archivo.');
                uploadProgressContainer.style.display = 'none';
            };

            xhr.send(formData);

        } catch (err) {
            console.error(err);
            uploadProgressContainer.style.display = 'none';
        }
    }

    // Check auth status on DOM load
    checkAuthStatus();
});
