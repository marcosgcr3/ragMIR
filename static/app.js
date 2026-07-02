document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
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
    let attachedImageFile = null;
    let attachedImageBase64 = null; // For localStorage persistence

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
        
        // Re-join with line breaks
        return formattedLines.join('<br>').replace(/<\/ul><br>/g, '</ul>');
    }

    // LocalStorage Session Management
    function loadSessions() {
        const stored = localStorage.getItem('rag_mir_sessions');
        if (stored) {
            try {
                sessions = JSON.parse(stored);
            } catch (e) {
                console.error("Error parsing stored sessions:", e);
                sessions = [];
            }
        }
        
        if (sessions.length === 0) {
            createNewSession();
        } else {
            currentSessionId = sessions[0].id;
            renderSessionsList();
            renderChatMessages();
        }
    }

    function saveSessions() {
        localStorage.setItem('rag_mir_sessions', JSON.stringify(sessions));
    }

    function createNewSession() {
        const newId = Date.now();
        const newSession = {
            id: newId,
            title: "Nueva Consulta",
            messages: []
        };
        sessions.unshift(newSession);
        currentSessionId = newId;
        saveSessions();
        renderSessionsList();
        renderChatMessages();
    }

    function deleteSession(id, event) {
        if (event) event.stopPropagation();
        
        const confirmDelete = confirm("¿Estás seguro de que deseas eliminar esta consulta?");
        if (!confirmDelete) return;

        sessions = sessions.filter(s => s.id !== id);
        
        if (sessions.length === 0) {
            createNewSession();
        } else {
            if (currentSessionId === id) {
                currentSessionId = sessions[0].id;
            }
            saveSessions();
            renderSessionsList();
            renderChatMessages();
        }
    }

    function selectSession(id) {
        currentSessionId = id;
        btnRemoveImage.click(); // Reset attached images
        renderSessionsList();
        renderChatMessages();
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
        if (!currentSession || currentSession.messages.length === 0) {
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

            // If user attached image
            if (msg.role === 'user' && msg.imageBase64) {
                bubbleHtml += `<img class="message-image" src="${msg.imageBase64}" alt="Imagen enviada">`;
            }

            // If bot cites sources
            if (msg.role === 'model' && msg.sources && msg.sources.length > 0) {
                bubbleHtml += `
                    <div class="sources-container">
                        <div class="sources-header">Fuentes consultadas:</div>
                        <div class="sources-list">
                `;
                msg.sources.forEach(src => {
                    bubbleHtml += `
                        <span class="source-badge" title="Coincidencia semántica: ${(src.similarity * 100).toFixed(1)}%">
                            <i class="fa-solid fa-file-invoice"></i> ${src.source} (${src.location})
                            <span class="source-similarity">${(src.similarity * 100).toFixed(0)}%</span>
                        </span>
                    `;
                });
                bubbleHtml += `</div></div>`;
            }

            // If bot reported tokens
            if (msg.role === 'model' && msg.usage) {
                bubbleHtml += `
                    <div class="token-usage-card" title="Métricas de consumo de tokens en Gemini">
                        <i class="fa-solid fa-microchip"></i> 
                        <span>Tokens: ${msg.usage.total_tokens} (Pregunta: ${msg.usage.prompt_tokens} \| Respuesta: ${msg.usage.completion_tokens})</span>
                    </div>
                `;
            }

            bubbleHtml += `</div>`;
            msgDiv.innerHTML = bubbleHtml;
            chatMessages.appendChild(msgDiv);
        });
        
        scrollToBottom();
    }

    // Fetch Database Status
    async function fetchStatus() {
        try {
            const res = await fetch('/api/status');
            if (!res.ok) throw new Error("Status endpoint error");
            const data = await res.json();
            
            // Render Stats
            statCollection.textContent = data.collection || '-';
            statChunks.textContent = data.total_chunks !== undefined ? data.total_chunks : '-';
            
            // Format LLM Display
            if (data.provider) {
                const providerName = data.provider === 'gemini' ? 'Gemini' : 'DeepSeek';
                statLlm.textContent = `${providerName} (${data.model})`;
            } else {
                statLlm.textContent = '-';
            }

            // Update pulse dot
            if (data.exists && data.total_chunks > 0) {
                dbIndicator.className = 'pulse-dot active';
                dbIndicator.title = 'Conectado. Base inicializada.';
            } else {
                dbIndicator.className = 'pulse-dot';
                dbIndicator.title = 'Base de datos vacía.';
            }

            // Render Indexed Files List
            if (data.files && data.files.length > 0) {
                indexedFilesList.innerHTML = '';
                data.files.forEach(file => {
                    const li = document.createElement('li');
                    li.innerHTML = `
                        <span class="doc-name"><i class="fa-solid fa-file-pdf"></i> ${file.name}</span>
                        <span class="doc-chunks">${file.chunks} chunks</span>
                    `;
                    indexedFilesList.appendChild(li);
                });
            } else {
                indexedFilesList.innerHTML = '<li class="empty-list">No hay documentos indexados.</li>';
            }
        } catch (err) {
            console.error("Error fetching status:", err);
            dbIndicator.className = 'pulse-dot';
            dbIndicator.title = 'Error de conexión.';
        }
    }

    // Auto-scroll chat area
    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // Helper: Handle Image Attachment & Previews
    function handleImageAttachment(file) {
        if (file && file.type.startsWith('image/')) {
            attachedImageFile = file;
            const reader = new FileReader();
            reader.onload = (event) => {
                imagePreviewSrc.src = event.target.result;
                attachedImageBase64 = event.target.result; // For saving in chat history
                imagePreviewArea.style.display = 'flex';
            };
            reader.readAsDataURL(file);
        }
    }

    // Attach button click
    btnAttach.addEventListener('click', () => imageInput.click());
    
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

    // Submit Query Form
    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const questionText = chatInput.value.trim();
        if (!questionText && !attachedImageFile) return;

        const currentSession = sessions.find(s => s.id === currentSessionId);
        if (!currentSession) return;

        // Auto-rename session if it has default title
        if (currentSession.title === "Nueva Consulta") {
            const rawTitle = questionText || "Consulta con Imagen";
            currentSession.title = rawTitle.length > 22 ? rawTitle.substring(0, 20) + "..." : rawTitle;
            renderSessionsList();
        }

        // 1. Add User Message to State
        const userMsg = {
            role: 'user',
            content: questionText,
            imageBase64: attachedImageBase64
        };
        currentSession.messages.push(userMsg);
        saveSessions();
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
            saveSessions();
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
                    <div class="message-bubble" style="border-color: rgba(255, 61, 0, 0.3); background: rgba(255, 61, 0, 0.05);">
                        <span style="color: var(--system-red); font-weight: 600;"><i class="fa-solid fa-triangle-exclamation"></i> Error:</span> ${err.message}
                    </div>
                </div>
            `;
            chatMessages.appendChild(botErrorDiv);
            scrollToBottom();
        }
    });

    // Paste Image Handler (Ctrl+V) anywhere in document
    document.addEventListener('paste', (e) => {
        const items = (e.clipboardData || e.originalEvent.clipboardData).items;
        for (let i = 0; i < items.length; i++) {
            if (items[i].type.indexOf('image') !== -1) {
                const file = items[i].getAsFile();
                handleImageAttachment(file);
                e.preventDefault(); // Intercept and block default text paste for files
                break;
            }
        }
    });

    // Global Drag & Drop over Main Chat Area
    const chatArea = document.querySelector('.chat-area');
    
    ['dragenter', 'dragover'].forEach(eventName => {
        chatArea.addEventListener(eventName, (e) => {
            e.preventDefault();
            chatArea.classList.add('dragover-active');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        chatArea.addEventListener(eventName, (e) => {
            e.preventDefault();
            chatArea.classList.remove('dragover-active');
        }, false);
    });

    chatArea.addEventListener('drop', (e) => {
        e.preventDefault();
        chatArea.classList.remove('dragover-active');
        
        const file = e.dataTransfer.files[0];
        if (file) {
            // If PDF dropped, upload & index it
            if (file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')) {
                handleFileUpload(file);
            } 
            // If Image dropped, attach it to chat prompt
            else if (file.type.startsWith('image/')) {
                handleImageAttachment(file);
            }
        }
    });

    // PDF Manual Upload Handlers (from sidebar zone)
    dropZone.addEventListener('click', () => fileInput.click());

    fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) handleFileUpload(file);
    });

    // File Upload API Helper
    async function handleFileUpload(file) {
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            alert("Solo se permiten archivos PDF de manuales de medicina.");
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        // Show Progress Bar UI
        uploadProgressContainer.style.display = 'block';
        uploadProgress.style.width = '20%';
        uploadStatusText.textContent = `Subiendo '${file.name}'...`;
        
        try {
            const res = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });

            uploadProgress.style.width = '70%';

            if (!res.ok) {
                const errData = await res.json();
                throw new Error(errData.detail || "Error del servidor en la subida.");
            }

            const data = await res.json();
            uploadProgress.style.width = '100%';
            uploadStatusText.textContent = "Procesando e indexando...";
            
            // Pulse dot to indexing status
            dbIndicator.className = 'pulse-dot indexing';
            dbIndicator.title = 'Indexando manual en segundo plano...';

            setTimeout(() => {
                alert(data.message);
                uploadProgressContainer.style.display = 'none';
                fileInput.value = '';
                fetchStatus();
            }, 800);

        } catch (err) {
            console.error("Upload error:", err);
            uploadProgress.style.width = '0%';
            uploadStatusText.textContent = "Error en subida.";
            alert("Error al subir archivo: " + err.message);
            setTimeout(() => {
                uploadProgressContainer.style.display = 'none';
            }, 2000);
        }
    }

    // Initialize Page
    loadSessions();
    fetchStatus();
    // Poll status every 5 seconds to track background indexing progress
    setInterval(fetchStatus, 5000);
});
