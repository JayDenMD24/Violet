(function () {
  'use strict';

  let state = {
    taskId: null,
    isUploading: false,
    cancelRequested: false,
    selectedItems: [],
    uploadAbortController: null,
    webhooks: [],
    selectedWebhook: '',
    editingIndex: null,
    loggedIn: false,
  };

  const $ = (id) => document.getElementById(id);

  // ── Utils ──
  function logMessage(msg, tag) {
    const area = $('log-area');
    if (!area) return;
    const ts = new Date().toLocaleTimeString('es-ES', { hour12: false });
    const prefix = { info: 'INFO', ok: 'OK  ', warn: 'WARN', err: 'ERR ' }[tag] || '    ';
    const line = document.createElement('span');
    line.className = 'log-line';
    line.innerHTML = `<span class="log-ts">[${ts}]  </span><span class="log-${tag}">${prefix}  ${msg}</span>`;
    area.appendChild(line);
    area.scrollTop = area.scrollHeight;
    try {
      localStorage.setItem('violet_log', area.innerHTML);
    } catch(e) {}
  }

  function clearLog() {
    const area = $('log-area');
    if (!area) return;
    area.innerHTML = '';
    try {
      localStorage.removeItem('violet_log');
    } catch(e) {}
    logMessage('Log limpiado.', 'info');
  }

  function setStatus(label, level) {
    const dot = $('status-dot');
    const txt = $('status-text');
    if (!dot || !txt) return;
    const colors = {
      ok: 'var(--fg-ok)', warn: 'var(--fg-warn)', err: 'var(--fg-err)',
      info: 'var(--fg-info)', idle: 'var(--fg-muted)', cancel: 'var(--fg-err)',
    };
    dot.style.background = colors[level] || 'var(--fg-muted)';
    txt.textContent = label;
    txt.style.color = colors[level] || 'var(--fg-muted)';
  }

  function setProgress(pct, msg) {
    const fill = $('progress-fill');
    const txt = $('progress-text');
    if (fill) fill.style.width = Math.min(pct, 100) + '%';
    if (txt) txt.textContent = msg || '';
  }

  function formatFileSize(bytes) {
    if (!bytes || bytes === 0) return 'N/A';
    const units = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return (bytes / Math.pow(1024, i)).toFixed(i > 0 ? (i > 1 ? 2 : 1) : 0) + ' ' + units[i];
  }

  function getFileIcon(name, isFolder) {
    const base = ' viewBox="0 0 256 256" fill="currentColor"';

    if (isFolder)
      return `<svg width="20" height="20"${base}><path d="M232,208a8,8,0,0,1-8,8H32a8,8,0,0,1,0-16H224A8,8,0,0,1,232,208Zm-16-32V80a16,16,0,0,0-16-16H112a16,16,0,0,1-16-16V40a16,16,0,0,0-16-16H40A16,16,0,0,0,24,40V176a16,16,0,0,0,16,16H200A16,16,0,0,0,216,176Z"/></svg>`;

    const ext = name.split('.').pop().toLowerCase();
    const video = ['mp4', 'mov', 'avi', 'mkv', 'webm', 'wmv', 'flv', 'm4v'];
    const image = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'];
    const audio = ['mp3', 'wav', 'flac', 'ogg', 'm4a'];
    const doc = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt'];
    const arch = ['zip', 'rar', '7z', 'tar', 'gz'];

    if (video.includes(ext))
      return `<svg width="20" height="20"${base}><path d="M232,208a8,8,0,0,1-8,8H32a8,8,0,0,1,0-16H224A8,8,0,0,1,232,208Zm0-152V168a16,16,0,0,1-16,16H40a16,16,0,0,1-16-16V56A16,16,0,0,1,40,40H216A16,16,0,0,1,232,56Zm-68,56a8,8,0,0,0-3.41-6.55l-40-28A8,8,0,0,0,108,84v56a8,8,0,0,0,12.59,6.55l40-28A8,8,0,0,0,164,112Z"/></svg>`;
    if (image.includes(ext))
      return `<svg width="20" height="20"${base}><path d="M216,40H40A16,16,0,0,0,24,56V200a16,16,0,0,0,16,16H216a16,16,0,0,0,16-16V56A16,16,0,0,0,216,40ZM156,88a12,12,0,1,1-12,12A12,12,0,0,1,156,88Zm60,112H40V160.69l46.34-46.35a8,8,0,0,1,11.32,0h0L165,181.66a8,8,0,0,0,11.32-11.32l-17.66-17.65L173,138.34a8,8,0,0,1,11.31,0L216,170.07V200Z"/></svg>`;
    if (audio.includes(ext))
      return `<svg width="20" height="20"${base}><path d="M210.3,56.34l-80-24A8,8,0,0,0,120,40V148.26A48,48,0,1,0,136,184V98.75l69.7,20.91A8,8,0,0,0,216,112V64A8,8,0,0,0,210.3,56.34Z"/></svg>`;
    if (doc.includes(ext))
      return `<svg width="20" height="20"${base}><path d="M213.66,82.34l-56-56A8,8,0,0,0,152,24H56A16,16,0,0,0,40,40V216a16,16,0,0,0,16,16H200a16,16,0,0,0,16-16V88A8,8,0,0,0,213.66,82.34ZM160,176H96a8,8,0,0,1,0-16h64a8,8,0,0,1,0,16Zm0-32H96a8,8,0,0,1,0-16h64a8,8,0,0,1,0,16Zm-8-56V44l44,44Z"/></svg>`;
    if (arch.includes(ext))
      return `<svg width="20" height="20"${base}><path d="M213.66,82.34l-56-56A8,8,0,0,0,152,24H56A16,16,0,0,0,40,40V216a16,16,0,0,0,16,16H92a4,4,0,0,0,4-4V208H88.27A8.17,8.17,0,0,1,80,200.53,8,8,0,0,1,88,192h8V176H88.27A8.17,8.17,0,0,1,80,168.53,8,8,0,0,1,88,160h8V144H88.27A8.17,8.17,0,0,1,80,136.53,8,8,0,0,1,88,128h8v-7.73a8.18,8.18,0,0,1,7.47-8.25,8,8,0,0,1,8.53,8v8h7.73a8.17,8.17,0,0,1,8.25,7.47,8,8,0,0,1-8,8.53h-8v16h7.73a8.17,8.17,0,0,1,8.25,7.47,8,8,0,0,1-8,8.53h-8v16h7.73a8.17,8.17,0,0,1,8.25,7.47,8,8,0,0,1-8,8.53h-8v20a4,4,0,0,0,4,4h84a16,16,0,0,0,16-16V88A8,8,0,0,0,213.66,82.34ZM152,88V44l44,44Z"/></svg>`;
    return `<svg width="20" height="20"${base}><path d="M213.66,82.34l-56-56A8,8,0,0,0,152,24H56A16,16,0,0,0,40,40V216a16,16,0,0,0,16,16H200a16,16,0,0,0,16-16V88A8,8,0,0,0,213.66,82.34ZM152,88V44l44,44Z"/></svg>`;
  }

  // ── Drag-and-drop helpers ──
  function traverseEntry(entry) {
    return new Promise((resolve) => {
      if (entry.isFile) {
        entry.file((file) => {
          const relPath = entry.fullPath.replace(/^\//, '');
          resolve({ type: 'file', file, relPath });
        });
      } else if (entry.isDirectory) {
        const folderName = entry.name;
        const folderRelPath = entry.fullPath.replace(/^\//, '');
        const files = [];
        const reader = entry.createReader();
        const readBatch = () => {
          reader.readEntries((entries) => {
            if (!entries.length) {
              resolve({ type: 'folder', name: folderName, relPath: folderRelPath, files });
              return;
            }
            Promise.all(entries.map((child) => traverseEntry(child))).then((results) => {
              for (const r of results) {
                if (r) {
                  if (r.type === 'file') files.push(r);
                  else if (r.type === 'folder')
                    for (const f of r.files) files.push(f);
                }
              }
              readBatch();
            });
          });
        };
        readBatch();
      } else {
        resolve(null);
      }
    });
  }

  function addItems(items) {
    state.selectedItems = [...state.selectedItems, ...items];
    renderItems(state.selectedItems);
    updateFolderNameVisibility(state.selectedItems);
    $('btn-upload').disabled = false;
  }

  // ── Folder picker (File System Access API) ──
  async function readDirectory(dirHandle, rootPath, children) {
    for await (const [name, entry] of dirHandle.entries()) {
      if (entry.kind === 'file') {
        const file = await entry.getFile();
        children.push({ type: 'file', file, relPath: rootPath + '/' + name });
      } else if (entry.kind === 'directory') {
        await readDirectory(entry, rootPath + '/' + name, children);
      }
    }
  }

  async function pickFolder() {
    if ('showDirectoryPicker' in window) {
      try {
        const handle = await window.showDirectoryPicker({ mode: 'read' });
        const realName = handle.name;
        const children = [];
        await readDirectory(handle, realName, children);
        if (!children.length) {
          logMessage('La carpeta seleccionada est\u00e1 vac\u00eda.', 'warn');
          return;
        }
        const folderItem = {
          type: 'folder',
          name: realName,
          relPath: realName,
          fromFolderInput: true,
          files: children,
        };
        const input = $('folder-name-input');
        if (input) input.value = realName;
        addItems([folderItem]);
        logMessage(`Carpeta "${realName}" agregada (${children.length} archivo(s)).`, 'info');
        return;
      } catch (e) {
        if (e.name === 'AbortError') return;
      }
    }
    $('folder-input').click();
  }

  // ── File select ──
  function initFileSelect() {
    const fileInput = $('file-input');
    const folderInput = $('folder-input');
    const browseFiles = $('btn-browse-files');
    const browseFolder = $('btn-browse-folder');
    const dropzone = $('dropzone');
    if (!fileInput || !folderInput || !browseFiles || !browseFolder || !dropzone) return;

    browseFiles.addEventListener('click', () => fileInput.click());
    browseFolder.addEventListener('click', pickFolder);

    fileInput.addEventListener('change', () => {
      if (fileInput.files.length) processFiles(fileInput.files, true);
      fileInput.value = '';
    });

    folderInput.addEventListener('change', () => {
      if (folderInput.files.length) {
        const files = Array.from(folderInput.files);
        const children = files.map(f => ({
          type: 'file',
          file: f,
          relPath: f.webkitRelativePath || f.name,
        }));
        const d = new Date();
        const dd = String(d.getDate()).padStart(2, '0');
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const yyyy = d.getFullYear();
        const defaultName = `Subida ${dd}-${mm}-${yyyy}`;
        const folderItem = {
          type: 'folder',
          name: defaultName,
          relPath: defaultName,
          fromFolderInput: true,
          files: children,
        };
        addItems([folderItem]);
        logMessage(`Carpeta "${defaultName}" agregada (${children.length} archivo(s)).`, 'info');
      }
      folderInput.value = '';
    });

    dropzone.addEventListener('click', (e) => {
      if (e.target.tagName === 'BUTTON' || e.target.closest('.item-entry') || e.target.closest('#items-toolbar')) return;
      fileInput.click();
    });

    ['dragenter', 'dragover'].forEach(ev => {
      dropzone.addEventListener(ev, (e) => {
        e.preventDefault();
        dropzone.classList.add('drag-over');
      });
    });
    dropzone.addEventListener('dragleave', () => {
      dropzone.classList.remove('drag-over');
    });
    dropzone.addEventListener('drop', async (e) => {
      e.preventDefault();
      dropzone.classList.remove('drag-over');
      const entries = [];
      for (const item of e.dataTransfer.items) {
        if (item.kind !== 'file') continue;
        const entry = item.webkitGetAsEntry();
        if (entry) entries.push(entry);
      }
      const results = await Promise.all(entries.map((entry) => traverseEntry(entry)));
      const raw = results.filter(r => r !== null);
      if (!raw.length) {
        logMessage('No se pudieron leer los archivos arrastrados.', 'warn');
        return;
      }
      const groups = {};
      const final = [];
      for (const item of raw) {
        if (item.type === 'folder') {
          final.push(item);
        } else {
          const parts = item.relPath.split('/');
          if (parts.length > 1) {
            const root = parts[0];
            if (!groups[root]) groups[root] = [];
            groups[root].push(item);
          } else {
            final.push(item);
          }
        }
      }
      for (const [root, files] of Object.entries(groups)) {
        final.push({ type: 'folder', name: root, relPath: root, files });
      }
      addItems(final);
      logMessage(final.length + ' elemento(s) arrastrado(s).', 'info');
    });
  }

  function processFiles(fileList, append) {
    const raw = [];
    for (const file of fileList) {
      const relPath = file.webkitRelativePath || file.name;
      if (file.size > 0 || file.webkitRelativePath) {
        raw.push({ type: 'file', file, relPath });
      }
    }
    if (!raw.length) return;

    const groups = {};
    const items = [];
    for (const item of raw) {
      const parts = item.relPath.split('/');
      if (parts.length > 1) {
        const root = parts[0];
        if (!groups[root]) groups[root] = [];
        groups[root].push(item);
      } else {
        items.push(item);
      }
    }
    for (const [root, files] of Object.entries(groups)) {
      items.push({ type: 'folder', name: root, relPath: root, files });
    }

    state.selectedItems = append ? [...state.selectedItems, ...items] : items;
    renderItems(state.selectedItems);
    updateFolderNameVisibility(state.selectedItems);
    $('btn-upload').disabled = false;
    logMessage(items.length + ' elemento(s) seleccionado(s).', 'info');
  }

  function getTopLevelRoots(items) {
    const roots = new Set();
    for (const item of items) {
      const root = item.relPath.split('/')[0];
      roots.add(root);
    }
    return roots;
  }

  function updateFolderNameVisibility(items) {
    const rootCount = getTopLevelRoots(items).size;
    const fromFolderInput = items.some(i => i.fromFolderInput);
    const card = $('card-folder-name');
    const input = $('folder-name-input');
    if (!card || !input) return;

    if (rootCount > 1 || fromFolderInput) {
      card.hidden = false;
      if (!input.value) {
        const d = new Date();
        const dd = String(d.getDate()).padStart(2, '0');
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const yyyy = d.getFullYear();
        input.value = `Subida ${dd}-${mm}-${yyyy}`;
      }
    } else {
      card.hidden = true;
    }
  }

  function renderItems(items) {
    const dropzone = $('dropzone');
    const container = $('items-list');
    const countEl = $('items-count');
    if (!dropzone || !container || !countEl) return;

    if (!items.length) {
      dropzone.classList.remove('has-items');
      return;
    }
    dropzone.classList.add('has-items');

    const totalEntries = items.reduce((sum, item) => {
      return sum + (item.type === 'folder' ? item.files.length : 1);
    }, 0);
    countEl.textContent = totalEntries + ' archivo(s)';

    container.innerHTML = '';
    for (const item of items) {
      const entry = document.createElement('div');
      entry.className = 'item-entry';
      if (item.type === 'folder') {
        const totalSize = item.files.reduce((sum, f) => sum + f.file.size, 0);
        const fileCount = item.files.length;
        entry.innerHTML = `
          <span class="item-icon">${getFileIcon(item.name, true)}</span>
          <span class="item-name" title="${item.relPath}">${item.name}</span>
          <span class="item-size">${fileCount} archivo(s) \u00B7 ${formatFileSize(totalSize)}</span>
          <button class="item-remove" title="Eliminar">
            <svg width="12" height="12" viewBox="0 0 256 256" fill="currentColor"><path d="M205.66,194.34a8,8,0,0,1-11.32,11.32L128,139.31,61.66,205.66a8,8,0,0,1-11.32-11.32L116.69,128,50.34,61.66A8,8,0,0,1,61.66,50.34L128,116.69l66.34-66.35a8,8,0,0,1,11.32,11.32L139.31,128Z"/></svg>
          </button>
        `;
      } else {
        const filename = item.relPath.split('/').pop();
        entry.innerHTML = `
          <span class="item-icon">${getFileIcon(filename)}</span>
          <span class="item-name" title="${item.relPath}">${filename}</span>
          <span class="item-size">${formatFileSize(item.file.size)}</span>
          <button class="item-remove" title="Eliminar">
            <svg width="12" height="12" viewBox="0 0 256 256" fill="currentColor"><path d="M205.66,194.34a8,8,0,0,1-11.32,11.32L128,139.31,61.66,205.66a8,8,0,0,1-11.32-11.32L116.69,128,50.34,61.66A8,8,0,0,1,61.66,50.34L128,116.69l66.34-66.35a8,8,0,0,1,11.32,11.32L139.31,128Z"/></svg>
          </button>
        `;
      }
      entry.querySelector('.item-remove').addEventListener('click', (e) => {
        e.stopPropagation();
        removeItem(item.relPath);
      });
      container.appendChild(entry);
    }
  }

  function removeItem(relPath) {
    state.selectedItems = state.selectedItems.filter(item => item.relPath !== relPath);
    if (state.selectedItems.length === 0) {
      clearSelection();
    } else {
      renderItems(state.selectedItems);
      updateFolderNameVisibility(state.selectedItems);
    }
  }

  function removeAll() {
    if (!state.selectedItems.length) return;
    clearSelection();
    logMessage('Todos los elementos eliminados.', 'info');
  }

  // ── Auth ──
  function initTopbarAuth() {
    $('btn-login').addEventListener('click', doGoogleLogin);
    $('btn-logout').addEventListener('click', doGoogleLogout);
    refreshAuthState();
  }

  async function refreshAuthState() {
    try {
      const resp = await fetch('/api/auth/status');
      const data = await resp.json();
      state.loggedIn = data.logged_in;
      updateAuthButtons(data.email);
    } catch (e) {}
  }

  function updateAuthButtons(emailFromPoll) {
    const login = $('btn-login');
    const logout = $('btn-logout');
    const email = $('topbar-email');
    if (!login || !logout) return;
    if (state.loggedIn) {
      login.style.display = 'none';
      logout.style.display = '';
      if (email) {
        if (emailFromPoll) {
          email.textContent = emailFromPoll;
          email.classList.add('visible');
        } else {
          (async () => {
            try {
              const resp = await fetch('/api/auth/status');
              const data = await resp.json();
              if (data.email) {
                email.textContent = data.email;
                email.classList.add('visible');
              }
            } catch(e) {}
          })();
        }
      }
    } else {
      login.style.display = '';
      login.disabled = false;
      login.textContent = 'Iniciar sesi\u00f3n';
      logout.style.display = 'none';
      if (email) email.classList.remove('visible');
    }
  }

  async function doGoogleLogin() {
    try {
      const resp = await fetch('/api/auth/start', { method: 'POST' });
      const data = await resp.json();
      if (data.ok) {
        toast('Revis\u00e1 tu navegador para iniciar sesi\u00f3n con Google.', 'info');
        pollAuthStatus();
      } else {
        toast(data.error || 'Error al iniciar sesi\u00f3n.', 'err');
      }
    } catch (e) {
      toast('Error al iniciar sesi\u00f3n.', 'err');
    }
  }

  function pollAuthStatus() {
    const interval = setInterval(async () => {
      try {
        const resp = await fetch('/api/auth/status');
        const data = await resp.json();
        if (!data.auth_in_progress) {
          clearInterval(interval);
          if (data.logged_in) {
            state.loggedIn = true;
            updateAuthButtons(data.email);
            toast('\u2713  Sesi\u00f3n iniciada.');
          } else if (data.auth_error) {
            toast('Error: ' + data.auth_error, 'err');
          }
          return;
        }
      } catch (e) {}
    }, 500);
  }

  async function doGoogleLogout() {
    if (!confirm('\u00bfCerrar sesi\u00f3n de Google Drive?')) return;
    try {
      await fetch('/api/auth/logout', { method: 'POST' });
      state.loggedIn = false;
      updateAuthButtons();
      toast('\u2713  Sesi\u00f3n cerrada.');
    } catch (e) {
      toast('Error al cerrar sesi\u00f3n.', 'err');
    }
  }

  // ── Webhooks ──
  function initWebhooks() {
    loadWebhooks();
    $('btn-editor-save').addEventListener('click', saveWebhookEditor);
    $('btn-editor-cancel').addEventListener('click', closeWebhookEditor);
  }

  async function loadWebhooks() {
    try {
      const resp = await fetch('/api/config');
      const data = await resp.json();
      state.webhooks = data.webhooks || [];
      state.selectedWebhook = data.selected_webhook || '0';
      renderWebhooks();
    } catch (e) {
      logMessage('Error al cargar webhooks.', 'err');
    }
  }

  function renderWebhooks() {
    const container = $('webhooks-list');
    if (!container) return;

    container.innerHTML = '';
    for (const wh of state.webhooks) {
      const isActive = String(wh.index) === String(state.selectedWebhook);
      const item = document.createElement('div');
      item.className = 'webhook-item' + (isActive ? ' active' : '');
      item.dataset.index = wh.index;

      const displayName = wh.name || `Webhook #${wh.index + 1}`;
      const displayUrl = wh.url || 'Sin configurar';

      item.innerHTML = `
        <input type="radio" name="webhook" value="${wh.index}" ${isActive ? 'checked' : ''}>
        <div class="wh-label">
          <span class="wh-name-text">${escapeHtml(displayName)}</span>
          <span class="wh-url-text">${escapeHtml(displayUrl)}</span>
        </div>
        <button class="wh-edit" title="Editar">
          <svg viewBox="0 0 256 256" fill="currentColor"><path d="M227.31,73.37,182.63,28.68a16,16,0,0,0-22.63,0L36.69,152A15.86,15.86,0,0,0,32,163.31V208a16,16,0,0,0,16,16H92.69A15.86,15.86,0,0,0,104,219.31L227.31,96a16,16,0,0,0,0-22.63ZM92.69,208H48V163.31l88-88L180.69,120ZM192,108.68,147.31,64l24-24L216,84.68Z"/></svg>
        </button>
      `;

      item.querySelector('input[type="radio"]').addEventListener('change', () => {
        state.selectedWebhook = wh.index;
        renderWebhooks();
      });

      item.querySelector('.wh-edit').addEventListener('click', (e) => {
        e.stopPropagation();
        toggleWebhookEditor(wh.index);
      });

      item.addEventListener('click', (e) => {
        if (e.target.closest('.wh-edit') || e.target.tagName === 'INPUT') return;
        const radio = item.querySelector('input[type="radio"]');
        radio.checked = true;
        radio.dispatchEvent(new Event('change'));
      });

      container.appendChild(item);
    }
  }

  function toggleWebhookEditor(index) {
    const editor = $('webhook-editor');
    if (!editor) return;

    if (!editor.hidden && state.editingIndex === index) {
      editor.hidden = true;
      state.editingIndex = null;
      return;
    }

    state.editingIndex = index;
    const wh = state.webhooks[index];
    $('webhook-edit-name').value = wh.name || '';
    $('webhook-edit-url').value = wh.url || '';
    $('webhook-editor-title').textContent = `EDITAR WEBHOOK #${index + 1}`;
    editor.hidden = false;
    $('webhook-edit-name').focus();
    editor.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function closeWebhookEditor() {
    $('webhook-editor').hidden = true;
    state.editingIndex = null;
  }

  async function saveWebhookEditor() {
    const idx = state.editingIndex;
    if (idx === null) return;

    const name = $('webhook-edit-name').value.trim();
    const url = $('webhook-edit-url').value.trim();

    const data = {};
    for (const wh of state.webhooks) {
      if (String(wh.index) === String(idx)) {
        data[`name_${wh.index}`] = name;
        data[`url_${wh.index}`] = url;
      } else {
        data[`name_${wh.index}`] = wh.name;
        data[`url_${wh.index}`] = wh.url;
      }
    }
    data.selected_webhook = state.selectedWebhook;

    try {
      const resp = await fetch('/api/settings/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      const result = await resp.json();
      if (result.ok) {
        state.webhooks[idx].name = name;
        state.webhooks[idx].url = url;
        renderWebhooks();
        closeWebhookEditor();
        toast('\u2713  Webhook guardado.');
      } else {
        toast('Error al guardar.', 'err');
      }
    } catch (e) {
      toast('Error al guardar.', 'err');
    }
  }

  // ── Upload ──
  function initUpload() {
    const uploadBtn = $('btn-upload');
    const cancelBtn = $('btn-cancel');
    if (!uploadBtn || !cancelBtn) return;

    uploadBtn.addEventListener('click', startUpload);
    cancelBtn.addEventListener('click', cancelUpload);
  }

  async function startUpload() {
    const items = state.selectedItems;
    if (!items.length) {
      logMessage('No hay elementos seleccionados.', 'err');
      return;
    }

    const selectedRadio = document.querySelector('input[name="webhook"]:checked');
    if (!selectedRadio) {
      logMessage('No has seleccionado un webhook.', 'err');
      setStatus('Sin webhook', 'err');
      return;
    }
    const webhookIdx = selectedRadio.value;

    try {
      const resp = await fetch('/api/auth/status');
      const data = await resp.json();
      if (!data.logged_in) {
        logMessage('No has iniciado sesi\u00f3n con Google Drive.', 'err');
        setStatus('Sin sesi\u00f3n', 'err');
        return;
      }
    } catch (e) {
      logMessage('Error al verificar autenticaci\u00f3n.', 'err');
      return;
    }

    const folderName = $('folder-name-input') ? $('folder-name-input').value.trim() : '';
    const roots = getTopLevelRoots(items);
    const fromFolderInput = items.some(i => i.fromFolderInput);
    const useFolderName = (roots.size > 1 || fromFolderInput) ? folderName : '';

    setProgress(0, '');
    setStatus('Subiendo...', 'info');
    setProgress(0, 'Preparando archivos...');
    state.isUploading = true;
    state.cancelRequested = false;
    setUploadMode(true);

    const form = new FormData();
    for (const item of items) {
      if (item.type === 'folder') {
        for (const f of item.files) {
          form.append('files[]', f.file);
          form.append('paths[]', f.relPath);
        }
      } else {
        form.append('files[]', item.file);
        form.append('paths[]', item.relPath);
      }
    }
    form.append('webhook_index', webhookIdx);
    if (useFolderName) form.append('folder_name', useFolderName);

    const controller = new AbortController();
    state.uploadAbortController = controller;

    try {
      const resp = await fetch('/api/upload', { method: 'POST', body: form, signal: controller.signal });
      const data = await resp.json();
      if (!data.ok) {
        logMessage('Error: ' + data.error, 'err');
        setStatus('Error', 'err');
        setUploadMode(false);
        state.isUploading = false;
        return;
      }
      state.taskId = data.task_id;
      const totalFiles = items.reduce((sum, it) => sum + (it.type === 'folder' ? it.files.length : 1), 0);
      logMessage('Iniciando subida (' + totalFiles + ' archivo(s)).', 'info');
      pollUploadStatus(data.task_id);
    } catch (e) {
      if (e.name === 'AbortError') return;
      logMessage('Error de conexi\u00f3n al iniciar subida.', 'err');
      setStatus('Error', 'err');
      setUploadMode(false);
      state.isUploading = false;
    }
  }

  function pollUploadStatus(taskId) {
    let lastLogLen = 0;
    let stopped = false;
    const check = async () => {
      if (stopped) return;
      try {
        const resp = await fetch('/api/upload/status/' + taskId);
        const data = await resp.json();
        if (data.state === 'not_found') { stopped = true; return; }
        if (!state.cancelRequested) setProgress(data.progress, data.message);
        if (data.log && data.log.length > lastLogLen) {
          for (let i = lastLogLen; i < data.log.length; i++) {
            logMessage(data.log[i], 'info');
          }
          lastLogLen = data.log.length;
        }
        const cancelBtn = $('btn-cancel');
        if (cancelBtn) cancelBtn.disabled = state.cancelRequested;
        if (data.state === 'done') {
          logMessage('\u2713  Completado', 'ok');
          setStatus('Completado', 'ok');
          setProgress(100, '');
          state.isUploading = false;
          state.taskId = null;
          setUploadMode(false);
          clearSelection();
          stopped = true;
          return;
        }
        if (data.state === 'error' || data.state === 'cancelled') {
          if (!state.cancelRequested) {
            const tag = data.state === 'error' ? 'err' : 'warn';
            const msg = data.state === 'cancelled' ? 'Subida cancelada por el usuario.' : 'Error: ' + data.message;
            logMessage(msg, tag);
            setStatus(data.state === 'error' ? 'Error' : 'Cancelado', data.state === 'error' ? 'err' : 'cancel');
            setProgress(0, '');
          }
          state.isUploading = false;
          state.taskId = null;
          setUploadMode(false);
          stopped = true;
          return;
        }
      } catch (e) {
        logMessage('Error de conexi\u00f3n durante la subida.', 'err');
        setStatus('Error', 'err');
        state.isUploading = false;
        setUploadMode(false);
        stopped = true;
        return;
      }
      if (!stopped) setTimeout(check, 200);
    };
    check();
  }

  async function cancelUpload() {
    if (state.cancelRequested) return;
    state.cancelRequested = true;
    const btn = $('btn-cancel');
    if (btn) btn.disabled = true;
    setStatus('Cancelado', 'cancel');
    setProgress(0, 'Cancelado');
    logMessage('Cancelado por el usuario.', 'warn');

    if (!state.taskId) {
      if (state.uploadAbortController) {
        state.uploadAbortController.abort();
        state.uploadAbortController = null;
      }
      state.isUploading = false;
      setUploadMode(false);
      return;
    }

    try {
      await fetch('/api/upload/cancel/' + state.taskId, { method: 'POST' });
    } catch (e) {}
  }

  function setUploadMode(active) {
    const uploadBtn = $('btn-upload');
    const cancelBtn = $('btn-cancel');
    const wrap = $('progress-wrapper');
    const browseFiles = $('btn-browse-files');
    const browseFolder = $('btn-browse-folder');
    if (!uploadBtn || !cancelBtn || !wrap) return;

    uploadBtn.disabled = active;
    cancelBtn.disabled = !active;
    wrap.hidden = !active;
    if (browseFiles) browseFiles.disabled = active;
    if (browseFolder) browseFolder.disabled = active;
  }

  function clearSelection() {
    state.selectedItems = [];
    const dropzone = $('dropzone');
    const container = $('items-list');
    const fnameCard = $('card-folder-name');
    const fnameInput = $('folder-name-input');
    const uploadBtn = $('btn-upload');
    if (dropzone) dropzone.classList.remove('has-items');
    if (container) container.innerHTML = '';
    if (fnameCard) fnameCard.hidden = true;
    if (fnameInput) fnameInput.value = '';
    if (uploadBtn) uploadBtn.disabled = true;
  }

  function toast(msg, type) {
    const el = $('footer-toast');
    if (!el) return;
    el.textContent = msg;
    el.className = type === 'err' ? 'error' : '';
    el.classList.add('show');
    clearTimeout(el._timer);
    el._timer = setTimeout(() => el.classList.remove('show'), 3500);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // ── Init ──
  document.addEventListener('DOMContentLoaded', () => {
    initFileSelect();
    initUpload();
    initWebhooks();
    initTopbarAuth();
    $('btn-remove-all')?.addEventListener('click', removeAll);
    $('btn-clear-log')?.addEventListener('click', clearLog);
    try {
      const saved = localStorage.getItem('violet_log');
      if (saved) {
        const area = $('log-area');
        if (area) {
          area.innerHTML = saved;
          area.scrollTop = area.scrollHeight;
        }
      }
    } catch(e) {}
    setStatus('Sin actividad', 'idle');
  });

})();
