/*
    Verwaltung der "Beobachten"-Seite

    Aufgaben des Skripts:
        1. Vorhandene Telegrammverläufe aus JSON-Datei laden (client.jsonl und server.jsonl)
        2. Live-Updates für Client- und Server-Events darstellen (z.B. ein- und ausgehende Telegrammer)
        3. Verbindungszustände von Client und Server darstellen
        4. Steuerelemente für die Seite "Beobachten" definieren
*/

// Telegramm-Historie getrennt nach Client und Server speichern
const TELEGRAM_STATE = {
  client: [],
  server: [],
};

// Seiten (Client/Server), die im UI dargestellt werden
const TELEGRAM_SIDES = ['client', 'server'];
const VIEW_OPTIONS = TELEGRAM_SIDES.reduce((acc, side) => {
  acc[side] = {
    detailMode: 'expanded',
  };
  return acc;
}, {});
const HISTORY_LIMIT = 1000;
const SCROLL_TOLERANCE = 8;
const STATUS_ENDPOINT = '/api/backend/status';
const STATUS_MESSAGES = {
  client: {
    active: 'Client ist aktiv',
    inactive: 'Client ist nicht aktiv',
  },
  server: {
    active: 'Server ist aktiv',
    inactive: 'Server ist nicht aktiv',
  },
};
const CONNECTING_STATUS_MESSAGE = 'Kommunikation wird aufgebaut';
const CONNECTING_TIMEOUT_MS = 30000;
const pendingStatusTimers = {};

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

const CAUSE_MEANINGS = {
  1: 'Zyklisch',
  2: 'Hintergrundabfrage',
  3: 'Spontan',
  4: 'Initialisiert',
  6: 'Aktivierung',
  7: 'Bestätigung der Aktivierung',
  8: 'Abbruch der Aktivierung',
  9: 'Bestätigung des Abbruchs der Aktivierung',
  10: 'Beendigung der Aktivierung',
  11: 'Rückmeldung verursacht durch Fernbefehl',
  12: 'Rückmeldung verursacht durch örtlichen Befehl',
  20: 'Generalabfrage',
};

const ORIGINATOR_MEANINGS = {
  0: 'Herkunftsadresse nicht vorhanden',
  10: 'Fernsteuerung von Verteilnetz-Anlagen',
  11: 'Steuerung von Kundenanlagen',
  12: 'Fernsteuerung von Verteilnetz-Anlagen',
  13: 'Fernsteuerung von Verteilnetz-Anlagen',
  14: 'Fernsteuerung von Verteilnetz-Anlagen',
  15: 'Niederspannungsmessung',
  16: 'Fernsteuerung von Verteilnetz-Anlagen',
  17: 'Fernsteuerung von Verteilnetz-Anlagen',
  18: 'Fernsteuerung von Verteilnetz-Anlagen',
  19: 'Fernsteuerung von Verteilnetz-Anlagen',
};

let eventSource = null;

function getFeedElement(side) {
  return document.querySelector(`.telegram-feed[data-telegrams="${side}"]`);
}

// Prüft, ob ein Feed nah am unteren Rand ist, um automatisches Scrollen zu steuern
function isNearBottom(container) {
  if (!container) {
    return false;
  }
  const distance = container.scrollHeight - container.scrollTop - container.clientHeight;
  return distance <= SCROLL_TOLERANCE;
}

// Aktiviert/Deaktiviert die komprimierte Darstellung der Telegramm-Details
// (Details einklappen / Details ausklappen)
function applyDetailMode(side) {
  const container = getFeedElement(side);
  if (!container || !VIEW_OPTIONS[side]) {
    return;
  }
  const collapsed = VIEW_OPTIONS[side].detailMode === 'collapsed';
  container.classList.toggle('telegram-feed--collapsed', collapsed);
}

function setDetailMode(side, mode) {
  if (!VIEW_OPTIONS[side] || (mode !== 'collapsed' && mode !== 'expanded')) {
    return;
  }
  if (VIEW_OPTIONS[side].detailMode === mode) {
    return;
  }
  VIEW_OPTIONS[side].detailMode = mode;
  applyDetailMode(side);
}

function formatListeningIp(statusInfo) {
  if (!statusInfo) {
    return '';
  }
  if (statusInfo.local_ip) {
    return statusInfo.local_ip;
  }
  if (typeof statusInfo.local_endpoint === 'string') {
    return statusInfo.local_endpoint.split(':')[0];
  }
  return '';
}

function getMonitoringStatusElement(side) {
  return document.querySelector(`.monitoring-status[data-status="${side}"]`);
}

// Stellt den Status neutral dar (keine Aktiv/Inaktiv-Färbung)
function setNeutralMonitoringStatus(statusEl, text) {
  if (!statusEl) {
    return;
  }
  statusEl.textContent = text;
  statusEl.classList.remove('monitoring-status--active', 'monitoring-status--inactive');
}

// Löscht einen laufenden Timeout, der einen neutralen Status zurücksetzt
function clearPendingStatus(side) {
  if (!pendingStatusTimers[side]) {
    return;
  }
  clearTimeout(pendingStatusTimers[side]);
  pendingStatusTimers[side] = null;
}

// Zeigt einen "Verbindung wird aufgebaut"-Hinweis und plant ein Zurücksetzen, falls keine Antwort kommt
function showConnectingStatus(side) {
  const statusEl = getMonitoringStatusElement(side);
  if (!statusEl) {
    return;
  }
  clearPendingStatus(side);
  setNeutralMonitoringStatus(statusEl, CONNECTING_STATUS_MESSAGE);
  pendingStatusTimers[side] = setTimeout(() => {
    pendingStatusTimers[side] = null;
    updateConnectionIndicator(side, null);
  }, CONNECTING_TIMEOUT_MS);
}

function updateConnectionIndicator(side, statusInfo) {
  const status = getMonitoringStatusElement(side);
  if (!status) {
    return;
  }
  const isActive = Boolean(statusInfo && statusInfo.connected);
  if (isActive) {
    clearPendingStatus(side);
  } else if (pendingStatusTimers[side]) {
    return;
  }
  const labels = STATUS_MESSAGES[side] || {};
  const activeText = labels.active || 'Aktiv';
  const inactiveText = labels.inactive || 'Nicht aktiv';
  if (isActive) {
    const listeningIp = formatListeningIp(statusInfo);
    status.textContent = listeningIp ? `${activeText} - ${listeningIp}` : activeText;
  } else {
    status.textContent = inactiveText;
  }
  status.classList.toggle('monitoring-status--active', isActive);
  status.classList.toggle('monitoring-status--inactive', !isActive);
}

async function fetchConnectionStatusSnapshot() {
  try {
    const response = await fetch(STATUS_ENDPOINT);
    if (!response.ok) {
      throw new Error('HTTP ' + response.status);
    }
    const snapshot = await response.json();
    Object.keys(STATUS_MESSAGES).forEach((side) => {
      const statusInfo = snapshot && snapshot[side] ? snapshot[side] : null;
      updateConnectionIndicator(side, statusInfo);
    });
  } catch (error) {
    console.warn('Konnte Verbindungsstatus nicht laden', error);
  }
}

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

// Hilfsfunktion zum Erzeugen einer beschrifteten Zeile innerhalb eines Telegramms
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

// Baut das HTML für ein einzelnes Telegramm zusammen
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
  headline.append(indexSpan, messageSpan);
  article.appendChild(headline);

  const details = document.createElement('div');
  details.className = 'telegram__details';
  const timeValue = `${telegram.timestampText} (d = ${telegram.deltaText} s)`;
  details.appendChild(createLine('Time', timeValue));

  const arrow = DIRECTION_ARROW[variant] || '&rarr;';
  const ipValue = `${telegram.localEndpoint} <span class="telegram__arrow">${arrow}</span> ${telegram.remoteEndpoint}`;
  details.appendChild(createLine('IP:Port', ipValue));

  const frameLabel = FRAME_LABELS[telegram.frameFamily] || telegram.frameFamily;
  const typeValue = telegram.frameFamily === 'I'
    ? `${telegram.typeId ?? ''} (${frameLabel})`
    : `(${frameLabel})`;
  details.appendChild(createLine('Typ', typeValue.trim()));

  if (telegram.frameFamily === 'I' && typeof telegram.cause === 'number') {
    const meaning = CAUSE_MEANINGS[telegram.cause];
    const causeText = meaning ? `${telegram.cause} (${meaning})` : String(telegram.cause);
    details.appendChild(createLine('Ursache', causeText));
  }
  if (telegram.frameFamily === 'I' && typeof telegram.originator === 'number') {
    const meaning = ORIGINATOR_MEANINGS[telegram.originator];
    const originatorText = meaning ? `${telegram.originator} (${meaning})` : String(telegram.originator);
    details.appendChild(createLine('Herkunft', originatorText));
  }
  if (telegram.frameFamily === 'I' && typeof telegram.station === 'number') {
    details.appendChild(createLine('Station', String(telegram.station)));
  }
  if (telegram.frameFamily === 'I' && typeof telegram.ioa === 'number') {
    const ioaSegments = splitIoa(telegram.ioa).join(' - ');
    details.appendChild(createLine('IOA', ioaSegments));
  }

  article.appendChild(details);

  return article;
}

function appendTelegram(side, telegram) {
  const container = getFeedElement(side);
  if (!container) {
    return;
  }
  const shouldStickToBottom = isNearBottom(container);
  removeEmptyState(container);
  container.appendChild(createTelegramElement(telegram));
  if (shouldStickToBottom) {
    container.scrollTop = container.scrollHeight;
  }
}

function addEmptyState(container) {
  if (!container.querySelector('.telegram-feed__empty')) {
    const empty = document.createElement('div');
    empty.className = 'telegram-feed__empty';
    empty.textContent = 'Noch keine Telegramme erfasst.';
    container.appendChild(empty);
  }
}

function resetTelegrams(side) {
  const container = getFeedElement(side);
  if (!container || !TELEGRAM_STATE[side]) {
    return;
  }
  TELEGRAM_STATE[side] = [];
  container.innerHTML = '';
  addEmptyState(container);
  applyDetailMode(side);
}

async function clearHistory(side) {
  const menuToggle = document.querySelector(`.monitoring-menu[data-menu="${side}"] [data-menu-toggle]`);
  if (menuToggle) {
    menuToggle.disabled = true;
  }
  try {
    const response = await fetch(`/api/backend/history/${side}/clear`, { method: 'POST' });
    if (!response.ok) {
      throw new Error('HTTP ' + response.status);
    }
    resetTelegrams(side);
  } catch (error) {
    console.error('Verlauf konnte nicht gelöscht werden', error);
  } finally {
    if (menuToggle) {
      menuToggle.disabled = false;
    }
  }
}

function closeAllMenus(except = null) {
  document.querySelectorAll('.monitoring-menu').forEach((menu) => {
    if (menu !== except) {
      menu.classList.remove('monitoring-menu--open');
    }
  });
}

// Reagiert auf Einträge im Optionsmenü eines Telegramms-Feeds
function handleMenuOption(side, option) {
  switch (option) {
    case 'clear-history':
      clearHistory(side);
      break;
    case 'collapse-details':
      setDetailMode(side, 'collapsed');
      break;
    case 'expand-details':
      setDetailMode(side, 'expanded');
      break;
    default:
      break;
  }
}

function bindOptionMenus() {
  const menus = document.querySelectorAll('.monitoring-menu');
  menus.forEach((menu) => {
    const side = menu.dataset.menu;
    const toggle = menu.querySelector('[data-menu-toggle]');
    const dropdown = menu.querySelector('.monitoring-menu__dropdown');
    if (!side || !toggle || !dropdown) {
      return;
    }
    toggle.addEventListener('click', (event) => {
      event.stopPropagation();
      const isOpen = menu.classList.contains('monitoring-menu--open');
      closeAllMenus(menu);
      if (!isOpen) {
        menu.classList.add('monitoring-menu--open');
      } else {
        menu.classList.remove('monitoring-menu--open');
      }
    });
    dropdown.addEventListener('click', (event) => {
      event.stopPropagation();
      const optionButton = event.target.closest('[data-menu-option]');
      if (!optionButton) {
        return;
      }
      handleMenuOption(side, optionButton.dataset.menuOption);
      menu.classList.remove('monitoring-menu--open');
    });
  });
  document.addEventListener('click', () => closeAllMenus());
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      closeAllMenus();
    }
  });
}

// Stellt initial die Detail-Ansicht der Feeds ein
function bindFeedInteractions() {
  TELEGRAM_SIDES.forEach((side) => {
    const container = getFeedElement(side);
    if (!container) {
      return;
    }
    applyDetailMode(side);
  });
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

function handleStreamMessage(event) {
  try {
    const payload = JSON.parse(event.data);
    if (payload.type === 'telegram' && payload.payload) {
      handleTelegramEvent(payload.payload);
    }
    if (payload.type === 'status' && payload.payload) {
      const side = payload.payload.side;
      if (side) {
        updateConnectionIndicator(side, payload.payload);
      }
    }
  } catch (err) {
    console.error('Fehler beim Lesen des Streams', err);
  }
}

function connectEventStream() {
  if (eventSource) {
    eventSource.close();
  }
  eventSource = new EventSource('/api/backend/stream');
  eventSource.onmessage = handleStreamMessage;
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
  if (button) {
    button.disabled = true;
  }
  try {
    const response = await fetch(endpoint, { method: 'POST' });
    if (!response.ok) {
      throw new Error('HTTP ' + response.status);
    }
    await response.json();
  } catch (error) {
    console.error('Start fehlgeschlagen', error);
  } finally {
    if (button) {
      setTimeout(() => {
        button.disabled = false;
      }, 800);
    }
  }
}

async function stopComponent(kind) {
  const endpoint = kind === 'client' ? '/api/backend/client/stop' : '/api/backend/server/stop';
  const button = document.querySelector(`[data-action="stop-${kind}"]`);
  if (button) {
    button.disabled = true;
  }
  try {
    const response = await fetch(endpoint, { method: 'POST' });
    if (!response.ok) {
      throw new Error('HTTP ' + response.status);
    }
    await response.json();
  } catch (error) {
    console.error('Stopp fehlgeschlagen', error);
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
  const stopClientButton = document.querySelector('[data-action="stop-client"]');
  const stopServerButton = document.querySelector('[data-action="stop-server"]');
  if (clientButton) {
    clientButton.addEventListener('click', () => {
      showConnectingStatus('client');
      startComponent('client');
    });
  }
  if (serverButton) {
    serverButton.addEventListener('click', () => {
      showConnectingStatus('server');
      startComponent('server');
    });
  }
  if (stopClientButton) {
    stopClientButton.addEventListener('click', () => stopComponent('client'));
  }
  if (stopServerButton) {
    stopServerButton.addEventListener('click', () => stopComponent('server'));
  }
}

async function loadExistingTelegrams() {
  try {
    const response = await fetch(`/api/backend/history?limit=${HISTORY_LIMIT}`);
    if (!response.ok) {
      throw new Error('HTTP ' + response.status);
    }
    const history = await response.json();
    TELEGRAM_SIDES.forEach((side) => {
      resetTelegrams(side);
      const entries = history && Array.isArray(history[side]) ? history[side] : [];
      entries.forEach((entry) => handleTelegramEvent(entry));
    });
  } catch (error) {
    console.warn('Konnte Verlauf nicht laden', error);
  }
}

function initBeobachten() {
  bindControls();
  bindOptionMenus();
  bindFeedInteractions();
  fetchConnectionStatusSnapshot();
  loadExistingTelegrams().finally(() => {
    connectEventStream();
  });
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
