const chatHistory = document.getElementById('chatHistory');
const userInput = document.getElementById('userInput');
const sendButton = document.getElementById('sendButton');
const documentList = document.getElementById('documentList');
const documentDetails = document.getElementById('documentDetails');
const documentDetailsTitle = document.getElementById('documentDetailsTitle');
const documentDetailsDescription = document.getElementById('documentDetailsDescription');
const documentDetailsList = document.getElementById('documentDetailsList');

let documentFolders = [];

let currentOpenFolderId = null;

const addFeedbackControls = (container, logId) => {
  const controls = document.createElement('div');
  controls.className = 'feedback-controls';

  const positiveButton = document.createElement('button');
  positiveButton.type = 'button';
  positiveButton.className = 'feedback-button feedback-button--thumb';
  positiveButton.setAttribute('aria-label', 'Marcar respuesta como útil');
  positiveButton.setAttribute('aria-pressed', 'false');
  positiveButton.title = 'Respuesta útil';
  positiveButton.innerHTML = '👍';

  const negativeButton = document.createElement('button');
  negativeButton.type = 'button';
  negativeButton.className = 'feedback-button feedback-button--thumb';
  negativeButton.setAttribute('aria-label', 'Marcar respuesta como poco útil');
  negativeButton.setAttribute('aria-pressed', 'false');
  negativeButton.title = 'Respuesta poco útil';
  negativeButton.innerHTML = '👎';

  const selectFeedback = async (selectedButton, otherButton, rating) => {
    selectedButton.classList.add('is-selected');
    otherButton.classList.remove('is-selected');
    selectedButton.setAttribute('aria-pressed', 'true');
    otherButton.setAttribute('aria-pressed', 'false');
    controls.dataset.feedback = String(rating);

    try {
      const response = await fetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ log_id: logId, rating }),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
    } catch (error) {
      console.error('No se pudo guardar el feedback:', error);
    }
  };

  positiveButton.addEventListener('click', () => {
    selectFeedback(positiveButton, negativeButton, 1);
  });

  negativeButton.addEventListener('click', () => {
    selectFeedback(negativeButton, positiveButton, -1);
  });

  controls.appendChild(positiveButton);
  controls.appendChild(negativeButton);
  container.appendChild(controls);
};

const addMessage = ({ role, text, sources, logId = null, showFeedback = false }) => {
  const card = document.createElement('article');
  card.className = `message ${role}`;

  const meta = document.createElement('div');
  meta.className = 'message__meta';
  meta.innerHTML = `
    <span>${role === 'agent' ? 'Agente IA' : 'Usuario'}</span>
    <span>${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
  `;

  const content = document.createElement('p');
  content.className = 'message__content';
  content.textContent = text;

  card.appendChild(meta);
  card.appendChild(content);

  if (role === 'agent' && sources?.length) {
    const sourcesSection = document.createElement('div');
    sourcesSection.className = 'message__sources';
    sourcesSection.innerHTML = '<strong>Fuentes citadas</strong>';

    const list = document.createElement('div');
    list.className = 'sources-list';

    sources.forEach((source) => {
      const item = document.createElement('div');
      item.className = 'source-item';
      item.innerHTML = `<a href="${source.link}" target="_blank" rel="noopener noreferrer">${source.label}</a><span>${source.caption}</span>`;
      list.appendChild(item);
    });

    sourcesSection.appendChild(list);
    card.appendChild(sourcesSection);

    if (showFeedback && logId !== null) {
      addFeedbackControls(card, logId);
    }
  }

  chatHistory.appendChild(card);
  chatHistory.scrollTop = chatHistory.scrollHeight;
};

const showDocumentDetails = (folder) => {
  // Toggle behavior: close if same folder is already open
  if (currentOpenFolderId === folder.id && !documentDetails.classList.contains('hidden')) {
    documentDetails.classList.add('hidden');
    currentOpenFolderId = null;
    return;
  }

  currentOpenFolderId = folder.id;
  documentDetailsTitle.textContent = folder.title;
  documentDetailsDescription.textContent = `Archivos en la carpeta ${folder.source}`;
  documentDetailsList.innerHTML = '';
  folder.files.forEach((file) => {
    const item = document.createElement('li');
    item.className = 'document-details__item';
    const link = document.createElement('a');
    // file may be an object { name, relative_path }
    const rel = (file.relative_path || file).split('/').map(encodeURIComponent).join('/');
    link.href = `/documentos/${rel}`;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = file.name || file;
    item.appendChild(link);
    documentDetailsList.appendChild(item);
  });
  documentDetails.classList.remove('hidden');
};

const renderDocuments = async () => {
  documentList.innerHTML = '';
  try {
    const resp = await fetch('/api/documents');
    const data = await resp.json();
    const folders = Array.isArray(data.folders) ? data.folders : [];
    documentFolders = folders;
    folders.forEach((folder) => {
      const card = document.createElement('article');
      card.className = 'document-card';
      card.innerHTML = `
        <h3 class="document-card__title">${folder.title}</h3>
        <p class="document-card__meta">Origen: ${folder.source}</p>
      `;
      card.addEventListener('click', () => showDocumentDetails(folder));
      documentList.appendChild(card);
    });
  } catch (err) {
    console.error('No se pudo obtener la lista de documentos:', err);
    documentList.innerHTML = '<p class="error">No se pudieron cargar los documentos.</p>';
  }
};

const apiUrl = 'http://127.0.0.1:8000/api/ask';

const sendMessage = async () => {
  const question = userInput.value.trim();
  if (!question) return;

  addMessage({ role: 'user', text: question });
  userInput.value = '';
  userInput.focus();

  const loadingMessage = addMessage({ role: 'agent', text: 'Consultando al agente IA...', sources: [] });

  try {
    const response = await fetch(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ question }),
      mode: 'cors',
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => null);
      const serverMessage = errorBody?.error || `${response.status} ${response.statusText}`;
      throw new Error(serverMessage);
    }

    const data = await response.json();
    if (data.error) {
      throw new Error(data.error);
    }

    const answer = data.answer || 'No se recibió respuesta del agente.';
    const sources = Array.isArray(data.sources) ? data.sources : [];

    // Reemplazar el mensaje de carga por la respuesta real
    const lastMessage = chatHistory.lastElementChild;
    if (lastMessage && lastMessage.classList.contains('agent')) {
      lastMessage.querySelector('.message__content').textContent = answer;
      const previousSources = lastMessage.querySelector('.message__sources');
      if (previousSources) {
        previousSources.remove();
      }

      if (sources.length) {
        const sourcesSection = document.createElement('div');
        sourcesSection.className = 'message__sources';
        sourcesSection.innerHTML = '<strong>Fuentes citadas</strong>';

        const list = document.createElement('div');
        list.className = 'sources-list';

        sources.forEach((source) => {
          const item = document.createElement('div');
          item.className = 'source-item';
          item.innerHTML = `<a href="${source.link}" target="_blank" rel="noopener noreferrer">${source.label}</a><span>${source.caption || ''}</span>`;
          list.appendChild(item);
        });

        sourcesSection.appendChild(list);
        lastMessage.appendChild(sourcesSection);
      }

      addFeedbackControls(lastMessage, data.log_id);
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Error inesperado al conectar con el agente.';
    console.error('Error en fetch /api/ask:', error);
    addMessage({ role: 'agent', text: `Error al conectar con el agente: ${errorMessage}`, sources: [] });
  }
};

sendButton.addEventListener('click', sendMessage);
userInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});

renderDocuments();
