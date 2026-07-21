const chatHistory = document.getElementById('chatHistory');
const userInput = document.getElementById('userInput');
const sendButton = document.getElementById('sendButton');
const documentList = document.getElementById('documentList');

const documents = [
  { id: 1, title: 'Política de logística', subtitle: 'Resumen de procesos y rutas', source: 'Logística / Manual' },
  { id: 2, title: 'Informe financiero', subtitle: 'Datos de costos y presupuesto', source: 'Financiero / Resumen' },
  { id: 3, title: 'Servicio al cliente', subtitle: 'Guía de atención y reclamos', source: 'Servicio al cliente / Protocolo' }
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
      alert('Gracias por tu feedback. Esto ayudará a mejorar al agente.');
    });
    card.appendChild(feedback);
  }

  chatHistory.appendChild(card);
  chatHistory.scrollTop = chatHistory.scrollHeight;
};

const renderDocuments = () => {
  documentList.innerHTML = '';
  documents.forEach((doc) => {
    const card = document.createElement('article');
    card.className = 'document-card';
    card.innerHTML = `
      <h3 class="document-card__title">${doc.title}</h3>
      <p class="document-card__meta">${doc.subtitle}</p>
      <p class="document-card__meta">Origen: ${doc.source}</p>
    `;
    documentList.appendChild(card);
  });
};

const sendMessage = () => {
  const question = userInput.value.trim();
  if (!question) return;

  addMessage({ role: 'user', text: question });
  userInput.value = '';
  userInput.focus();

  setTimeout(() => {
    const response = sampleAgentResponse(question);
    addMessage({ role: 'agent', text: response.text, sources: response.sources });
  }, 550);
};

sendButton.addEventListener('click', sendMessage);
userInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});

renderDocuments();
addMessage({ role: 'agent', text: 'Bienvenido al chat del Agente IA. Haz una pregunta y verás la respuesta con fuentes y feedback.', sources: [
  { label: 'Guía inicial', link: '#', caption: 'Explica cómo usar el chat' }
] });
