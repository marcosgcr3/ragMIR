document.addEventListener('DOMContentLoaded', () => {
    // Mobile Sidebar Drawer Toggle
    const hamburger = document.getElementById('btn-hamburger');
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.getElementById('sidebar-overlay');

    if (hamburger && sidebar && overlay) {
        hamburger.addEventListener('click', () => {
            sidebar.classList.toggle('mobile-open');
            overlay.classList.toggle('visible');
        });

        overlay.addEventListener('click', () => {
            sidebar.classList.remove('mobile-open');
            overlay.classList.remove('visible');
        });
    }

    // Auto-adjust textarea sizing on mobile input focus
    const chatInput = document.getElementById('chat-input');
    if (chatInput) {
        chatInput.addEventListener('focus', () => {
            setTimeout(() => {
                chatInput.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }, 300);
        });
    }
    // Documents Modal Open/Close
    const btnDocs = document.getElementById('btn-show-docs');
    const docsModal = document.getElementById('docs-modal');
    const btnCloseDocs = document.getElementById('btn-close-docs');

    if (btnDocs && docsModal) {
        btnDocs.addEventListener('click', async () => {
            docsModal.style.display = 'flex';
            // Only fetch and render dynamically if we are NOT on the chat page (where app.js manages it)
            const isChatPage = !!document.querySelector('script[src*="app.js"]');
            if (isChatPage) return;

            const modalList = document.getElementById('indexed-files-list');
            if (modalList) {
                modalList.innerHTML = '<li style="justify-content: center; color: var(--text-muted);"><i class="fa-solid fa-spinner fa-spin"></i> Cargando documentos...</li>';
                try {
                    const res = await fetch('/api/database/status');
                    if (res.ok) {
                        const status = await res.json();
                        renderModalFiles(status.files, modalList);
                    } else {
                        modalList.innerHTML = '<li style="justify-content: center; color: var(--system-red); padding: 10px;">Error al cargar documentos.</li>';
                    }
                } catch (e) {
                    modalList.innerHTML = '<li style="justify-content: center; color: var(--system-red); padding: 10px;">Error de red.</li>';
                }
            }
        });
    }

    function renderModalFiles(files, listElement) {
        listElement.innerHTML = '';
        
        // Convert dict files to list if needed
        let filesList = [];
        if (files && typeof files === 'object') {
            if (Array.isArray(files)) {
                filesList = files;
            } else {
                filesList = Object.entries(files).map(([name, info]) => ({
                    name: name,
                    chunks: info.chunks
                }));
            }
        }

        if (filesList.length === 0) {
            listElement.innerHTML = '<li style="justify-content: center; color: var(--text-muted); padding: 10px;">No hay documentos indexados.</li>';
            return;
        }
        
        filesList.forEach(file => {
            const li = document.createElement('li');
            li.style.display = 'flex';
            li.style.alignItems = 'center';
            li.style.justifyContent = 'space-between';
            li.style.padding = '10px 12px';
            li.style.background = 'rgba(255, 255, 255, 0.02)';
            li.style.border = '1px solid rgba(255, 255, 255, 0.04)';
            li.style.borderRadius = '8px';
            li.style.marginBottom = '8px';
            li.style.fontSize = '13px';
            
            li.innerHTML = `
                <div style="display: flex; align-items: center; gap: 8px;">
                    <i class="fa-solid fa-file-pdf" style="color: #ff4a4a;"></i>
                    <span style="font-weight: 500; color: #fff;">${file.name.replace('.pdf', '')}</span>
                </div>
                <span style="font-size: 11px; color: var(--text-muted); background: rgba(255,255,255,0.05); padding: 2px 6px; border-radius: 4px;">
                    ${file.chunks} chunks
                </span>
            `;
            listElement.appendChild(li);
        });
    }

    if (btnCloseDocs && docsModal) {
        btnCloseDocs.addEventListener('click', () => {
            docsModal.style.display = 'none';
        });
        
        // Close modal on clicking outside card
        docsModal.addEventListener('click', (e) => {
            if (e.target === docsModal) {
                docsModal.style.display = 'none';
            }
        });
    }
});
