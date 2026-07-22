const chatHistory = document.getElementById('chatHistory');
const userInput = document.getElementById('userInput');
const sendButton = document.getElementById('sendButton');
const documentList = document.getElementById('documentList');
const documentDetails = document.getElementById('documentDetails');
const documentDetailsTitle = document.getElementById('documentDetailsTitle');
const documentDetailsDescription = document.getElementById('documentDetailsDescription');
const documentDetailsList = document.getElementById('documentDetailsList');
const feedbackModal = document.getElementById('feedbackModal');
const feedbackClose = document.getElementById('feedbackClose');
const feedbackForm = document.getElementById('feedbackForm');
const feedbackText = document.getElementById('feedbackText');

const documentFolders = [
  {
    id: 1,
    title: 'Logística',
    subtitle: 'Carpeta de proceso y rutas',
    source: 'Logística / Manual',
    files: [
      'Manual de operaciones de logística.pdf',
      'Rutas y cronograma.xlsx',
      'Política de envíos.docx'
    ]
  },
  {
    id: 2,
    title: 'Financiero',
    subtitle: 'Carpeta de presupuestos y costos',
    source: 'Financiero / Resumen',
    files: [
      'Informe de costos 2026.pdf',
      'Presupuesto trimestral.xlsx',
      'Análisis de ahorros.docx'
    ]
  },
  {
    id: 3,
    title: 'Servicio al cliente',
    subtitle: 'Carpeta de atención y reclamos',
    source: 'Servicio al cliente / Protocolo',
    files: [
      'Guía de atención al cliente.pdf',
      'Proceso de reclamos.xlsx',
      'FAQ y soporte.docx'
    ]
  }
];

const sampleAgentResponse = (question) => ({
  text: `Hola, esta es una respuesta del agente para: "${question}". He revisado los documentos disponibles y te brindo la información más relevante.`,
  sources: [
    { label: 'Documento de logística', link: '#', caption: 'Sección: seguimiento de envíos' },
    { label: 'Informe financiero', link: '#', caption: 'Costos y optimización' }
  ]
});

const addMessage = ({ role, text, sources }) => {
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

    const feedback = document.createElement('button');
    feedback.className = 'feedback-button';
    feedback.textContent = 'Dar feedback';
    feedback.addEventListener('click', () => {
      feedbackModal.classList.remove('hidden');
      feedbackText.focus();
    });
    card.appendChild(feedback);
  }

  chatHistory.appendChild(card);
  chatHistory.scrollTop = chatHistory.scrollHeight;
};

const showDocumentDetails = (folder) => {
  documentDetailsTitle.textContent = folder.title;
  documentDetailsDescription.textContent = `Archivos en la carpeta ${folder.source}`;
  documentDetailsList.innerHTML = '';
  folder.files.forEach((file) => {
    const item = document.createElement('li');
    item.className = 'document-details__item';
    item.textContent = file;
    documentDetailsList.appendChild(item);
  });
  documentDetails.classList.remove('hidden');
};

const renderDocuments = () => {
  documentList.innerHTML = '';
  documentFolders.forEach((folder) => {
    const card = document.createElement('article');
    card.className = 'document-card';
    card.innerHTML = `
      <h3 class="document-card__title">${folder.title}</h3>
      <p class="document-card__meta">${folder.subtitle}</p>
      <p class="document-card__meta">Origen: ${folder.source}</p>
    `;
    card.addEventListener('click', () => showDocumentDetails(folder));
    documentList.appendChild(card);
  });
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

      const feedbackButton = document.createElement('button');
      feedbackButton.className = 'feedback-button';
      feedbackButton.textContent = 'Dar feedback';
      feedbackButton.addEventListener('click', () => {
        feedbackModal.classList.remove('hidden');
        feedbackText.focus();
      });
      lastMessage.appendChild(feedbackButton);
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

feedbackClose.addEventListener('click', () => {
  feedbackModal.classList.add('hidden');
});

feedbackModal.addEventListener('click', (event) => {
  if (event.target === feedbackModal || event.target.classList.contains('modal__backdrop')) {
    feedbackModal.classList.add('hidden');
  }
});

feedbackForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const comment = feedbackText.value.trim();
  if (!comment) return;

  feedbackModal.classList.add('hidden');
  feedbackText.value = '';
  addMessage({ role: 'agent', text: 'Gracias por tu feedback. Hemos registrado tu comentario para mejorar las respuestas del agente.' });
});

renderDocuments();
addMessage({ role: 'agent', text: 'Bienvenido al chat del Agente IA. Haz una pregunta y verás la respuesta con fuentes y feedback.', sources: [
  { label: 'Guía inicial', link: '#', caption: 'Explica cómo usar el chat' }
] });
