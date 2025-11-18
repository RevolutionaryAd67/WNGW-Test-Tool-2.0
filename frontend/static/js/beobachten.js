const sampleClientTelegrams = [
  {
    index: 1,
    message: 'MELDETEXT',
    timestamp: '08:35:54.983',
    delta: '0.004',
    frameFamily: 'U',
    typeCode: null,
    direction: 'outgoing',
    source: '192.168.1.10:2404',
    target: '192.168.1.50:2404',
    cause: null,
    station: null,
    ioa: null,
  },
  {
    index: 2,
    message: 'MELDETEXT',
    timestamp: '08:35:55.983',
    delta: '1.050',
    frameFamily: 'I',
    typeCode: '100',
    direction: 'incoming',
    source: '192.168.1.50:2404',
    target: '192.168.1.10:2404',
    cause: { activation: 6, origin: 11 },
    station: '49331',
    ioa: ['0', '0', '0'],
  },
];

const sampleServerTelegrams = [
  {
    index: 1,
    message: 'MELDETEXT',
    timestamp: '08:36:10.125',
    delta: '0.003',
    frameFamily: 'S',
    typeCode: null,
    direction: 'incoming',
    source: '192.168.1.10:2404',
    target: '192.168.1.50:2404',
    cause: null,
    station: null,
    ioa: null,
  },
  {
    index: 2,
    message: 'MELDETEXT',
    timestamp: '08:36:12.902',
    delta: '0.875',
    frameFamily: 'I',
    typeCode: '47',
    direction: 'outgoing',
    source: '192.168.1.50:2404',
    target: '192.168.1.10:2404',
    cause: { activation: 3, origin: 5 },
    station: '49331',
    ioa: ['1', '15', '7'],
  },
];

const frameLabelMap = {
  I: 'I-Format',
  S: 'S-Format',
  U: 'U-Format',
};

const directionArrow = {
  incoming: '&larr;',
  outgoing: '&rarr;',
};

function createLine(label, value, extraClass = '') {
  const line = document.createElement('div');
  line.className = `telegram__line ${extraClass}`.trim();

  const labelEl = document.createElement('span');
  labelEl.className = 'telegram__label';
  labelEl.textContent = label;

  const valueEl = document.createElement('span');
  valueEl.className = 'telegram__value';
  valueEl.innerHTML = value;

  line.append(labelEl, valueEl);
  return line;
}

function createTelegramElement(telegram) {
  const article = document.createElement('article');
  const variant = telegram.direction === 'incoming' ? 'incoming' : 'outgoing';
  article.className = `telegram telegram--${variant}`;

  const headline = document.createElement('div');
  headline.className = 'telegram__line telegram__line--headline';
  const indexSpan = document.createElement('span');
  indexSpan.className = 'telegram__index';
  indexSpan.textContent = telegram.index;
  const messageSpan = document.createElement('span');
  messageSpan.textContent = telegram.message || 'MELDETEXT';
  headline.append(indexSpan, document.createTextNode(' : '), messageSpan);
  article.appendChild(headline);

  const timeValue = `${telegram.timestamp} (d = ${telegram.delta} s)`;
  article.appendChild(createLine('Time', timeValue));

  const arrow = directionArrow[variant] || '&rarr;';
  const ipValue = `${telegram.source} <span class="telegram__arrow">${arrow}</span> ${telegram.target}`;
  article.appendChild(createLine('IP:Port', ipValue));

  const frameLabel = frameLabelMap[telegram.frameFamily] || telegram.frameFamily;
  const typeValue = telegram.frameFamily === 'I'
    ? `${telegram.typeCode || ''} (${frameLabel})`
    : `(${frameLabel})`;
  article.appendChild(createLine('Typ', typeValue.trim()));

  if (telegram.frameFamily === 'I' && telegram.cause) {
    const causeValue = `Aktivierung = ${telegram.cause.activation}      Herkunft = ${telegram.cause.origin}`;
    article.appendChild(createLine('Ursache', causeValue));
  }

  if (telegram.frameFamily === 'I' && telegram.station) {
    article.appendChild(createLine('Station', telegram.station));
  }

  if (telegram.frameFamily === 'I' && telegram.ioa) {
    const ioaValue = telegram.ioa.map((segment) => segment.padStart(2, ' ')).join(' - ');
    article.appendChild(createLine('IOA', ioaValue));
  }

  return article;
}

function renderTelegrams(target, telegrams) {
  const container = document.querySelector(`.telegram-feed[data-telegrams="${target}"]`);
  if (!container) {
    return;
  }

  container.innerHTML = '';
  if (!telegrams || telegrams.length === 0) {
    container.innerHTML = '<div class="telegram-feed__empty">Noch keine Telegramme erfasst.</div>';
    return;
  }

  const fragment = document.createDocumentFragment();
  telegrams.forEach((telegram) => {
    fragment.appendChild(createTelegramElement(telegram));
  });
  container.appendChild(fragment);
}

function initTelegramFeeds() {
  renderTelegrams('client', sampleClientTelegrams);
  renderTelegrams('server', sampleServerTelegrams);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initTelegramFeeds);
} else {
  initTelegramFeeds();
}
