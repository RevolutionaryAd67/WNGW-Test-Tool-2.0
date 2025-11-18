const TELEGRAM_STATE = {
  client: [],
  server: [],
};

const FRAME_LABELS = {
  I: 'I-Format',
  U: 'U-Format',
  S: 'S-Format',
  TCP: 'TCP',
};

const DIRECTION_ARROW = {
  incoming: '&larr;',
  outgoing: '&rarr;',
};

let eventSource = null;

function pad(value) {
  return value.toString().padStart(2, '0');
}

function formatTimestamp(epochSeconds) {
  const date = new Date(epochSeconds * 1000);
  const ms = date.getMilliseconds().toString().padStart(3, '0');
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}.${ms}`;
}

function formatDelta(deltaSeconds) {
  return deltaSeconds.toFixed(3).replace('.', ',');
}

function splitIoa(ioaValue) {
  const segments = [ioaValue & 0xff, (ioaValue >> 8) & 0xff, (ioaValue >> 16) & 0xff];
  return segments.map((value) => value.toString().padStart(3, ' '));
}

function createLine(label, value) {
  const line = document.createElement('div');
  line.className = 'telegram__line';

  const labelEl = document.createElement('span');
  labelEl.className = 'telegram__label';
  labelEl.textContent = label;

  const valueEl = document.createElement('span');
  valueEl.className = 'telegram__value';
  valueEl.innerHTML = value;

  line.append(labelEl, valueEl);
  return line;
}

function removeEmptyState(container) {
  const empty = container.querySelector('.telegram-feed__empty');
  if (empty) {
    empty.remove();
  }
}

function createTelegramElement(telegram) {
  const article = document.createElement('article');
  const variant = telegram.direction === 'incoming' ? 'incoming' : 'outgoing';
  article.className = `telegram telegram--${variant}`;

  const headline = document.createElement('div');
  headline.className = 'telegram__line telegram__headline';
  const indexSpan = document.createElement('span');
  indexSpan.className = 'telegram__index';
  indexSpan.textContent = telegram.sequence;
  const messageSpan = document.createElement('span');
  messageSpan.textContent = telegram.label || 'Telegramm';
  headline.append(indexSpan, document.createTextNode(' : '), messageSpan);
  article.appendChild(headline);

  const timeValue = `${telegram.timestampText} (d = ${telegram.deltaText} s)`;
  article.appendChild(createLine('Time', timeValue));

  const arrow = DIRECTION_ARROW[variant] || '&rarr;';
  const ipValue = `${telegram.localEndpoint} <span class="telegram__arrow">${arrow}</span> ${telegram.remoteEndpoint}`;
  article.appendChild(createLine('IP:Port', ipValue));

  const frameLabel = FRAME_LABELS[telegram.frameFamily] || telegram.frameFamily;
  const typeValue = telegram.frameFamily === 'I'
    ? `${telegram.typeId ?? ''} (${frameLabel})`
    : `(${frameLabel})`;
  article.appendChild(createLine('Typ', typeValue.trim()));

  if (telegram.frameFamily === 'I' && typeof telegram.cause === 'number') {
    article.appendChild(createLine('Ursache', String(telegram.cause)));
  }
  if (telegram.frameFamily === 'I' && typeof telegram.originator === 'number') {
    article.appendChild(createLine('Herkunft', String(telegram.originator)));
  }
  if (telegram.frameFamily === 'I' && typeof telegram.station === 'number') {
    article.appendChild(createLine('Station', String(telegram.station)));
  }
  if (telegram.frameFamily === 'I' && typeof telegram.ioa === 'number') {
    const ioaSegments = splitIoa(telegram.ioa).join(' - ');
    article.appendChild(createLine('IOA', ioaSegments));
  }

  return article;
}

function appendTelegram(side, telegram) {
  const container = document.querySelector(`.telegram-feed[data-telegrams="${side}"]`);
  if (!container) {
    return;
  }
  removeEmptyState(container);
  container.appendChild(createTelegramElement(telegram));
  container.scrollTop = container.scrollHeight;
}

function handleTelegramEvent(raw) {
  const target = raw.side;
  if (!target || !TELEGRAM_STATE[target]) {
    return;
  }

  const telegram = {
    sequence: raw.sequence,
    label: raw.label,
    direction: raw.direction,
    frameFamily: raw.frame_family,
    localEndpoint: raw.local_endpoint,
    remoteEndpoint: raw.remote_endpoint,
    typeId: raw.type_id ?? null,
    cause: raw.cause ?? null,
    originator: raw.originator ?? null,
    station: raw.station ?? null,
    ioa: typeof raw.ioa === 'number' ? raw.ioa : null,
    timestampText: formatTimestamp(raw.timestamp),
    deltaText: formatDelta(raw.delta ?? 0),
  };

  TELEGRAM_STATE[target].push(telegram);
  appendTelegram(target, telegram);
}

function connectEventStream() {
  if (eventSource) {
    eventSource.close();
  }
  eventSource = new EventSource('/api/backend/stream');
  eventSource.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload.type === 'telegram' && payload.payload) {
        handleTelegramEvent(payload.payload);
      }
    } catch (err) {
      console.error('Fehler beim Lesen des Streams', err);
    }
  };
  eventSource.onerror = () => {
    if (eventSource) {
      eventSource.close();
    }
    console.warn('Verbindung zum Stream verloren, versuche Neuaufbau ...');
    setTimeout(connectEventStream, 3000);
  };
}

async function startComponent(kind) {
  const endpoint = kind === 'client' ? '/api/backend/client/start' : '/api/backend/server/start';
  const button = document.querySelector(`[data-action="start-${kind}"]`);
  const status = document.querySelector(`.monitoring-status[data-status="${kind}"]`);
  if (button) {
    button.disabled = true;
  }
  try {
    const response = await fetch(endpoint, { method: 'POST' });
    if (!response.ok) {
      throw new Error('HTTP ' + response.status);
    }
    const result = await response.json();
    if (status) {
      status.textContent = result.status === 'already_running'
        ? 'Bereits aktiv.'
        : 'Gestartet.';
    }
  } catch (error) {
    console.error('Start fehlgeschlagen', error);
    if (status) {
      status.textContent = 'Start fehlgeschlagen. Details siehe Konsole.';
    }
  } finally {
    if (button) {
      setTimeout(() => {
        button.disabled = false;
      }, 800);
    }
  }
}

function bindControls() {
  const clientButton = document.querySelector('[data-action="start-client"]');
  const serverButton = document.querySelector('[data-action="start-server"]');
  if (clientButton) {
    clientButton.addEventListener('click', () => startComponent('client'));
  }
  if (serverButton) {
    serverButton.addEventListener('click', () => startComponent('server'));
  }
}

function initBeobachten() {
  bindControls();
  connectEventStream();
}

window.addEventListener('beforeunload', () => {
  if (eventSource) {
    eventSource.close();
  }
});

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initBeobachten);
} else {
  initBeobachten();
}
