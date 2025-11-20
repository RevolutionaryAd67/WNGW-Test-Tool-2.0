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
const SIGNAL_LIST_IOA_MAP = new Map();
const HISTORY_LIMIT = 1000;
const SCROLL_TOLERANCE = 8;
const STATUS_ENDPOINT = '/api/backend/status';
const SIGNAL_LIST_ENDPOINT = '/api/einstellungen/kommunikation/signalliste';
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

// Liefert das HTML-Element des Telegramm-Feeds
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

// Ändert den Detailmodus (eingeklappt/ausgeklappt) für einen Feed und aktualisiert die Ansicht
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

// Extrahiert eine lesbare IP aus einem Statusobjekt
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

// Liefert das Element, das den aktuellen Monitoring-Status für eine Seite anzeigt
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

// Aktualisiert die Anzeige des Verbindungsstatus für Client oder Server
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

// Lädt einen einmaligen Snapshot des Verbindungsstatus 
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

// Formatiert Zeilen zweistellig mit führenden Nullen
function pad(value) {
  return value.toString().padStart(2, '0');
}

// Wandelt einen Unix-Timestamp in eine Uhrzeit mit Millisekunden um
function formatTimestamp(epochSeconds) {
  const date = new Date(epochSeconds * 1000);
  const ms = date.getMilliseconds().toString().padStart(3, '0');
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}.${ms}`;
}

// Formatiert eine Zeitdifferenz in Sekunden mit drei Nachkommastellen
function formatDelta(deltaSeconds) {
  return deltaSeconds.toFixed(3).replace('.', ',');
}

// Extrahiert einen gültigen IOA-Bytewert (0-255) aus einem Signallisten-Eintrag
function parseIoaPart(value) {
  if (value === undefined || value === null) {
    return null;
  }
  const parsed = Number.parseInt(String(value).trim(), 10);
  if (Number.isNaN(parsed) || parsed < 0 || parsed > 255) {
    return null;
  }
  return parsed;
}

// Berechnet die IOA-Zahl (LSB -> MSB) aus einer Zeile der Signalliste
function extractIoaFromRow(row) {
  const parts = [parseIoaPart(row['IOA 1']), parseIoaPart(row['IOA 2']), parseIoaPart(row['IOA 3'])];
  if (parts.some((part) => part === null)) {
    return null;
  }
  return parts[0] + (parts[1] << 8) + (parts[2] << 16);
}

// Baut ein Lookup für IOA -> Meldetext aus der Signalliste auf
function buildSignalListLookup(signalliste) {
  SIGNAL_LIST_IOA_MAP.clear();
  if (!signalliste || !Array.isArray(signalliste.rows)) {
    return;
  }
  signalliste.rows.forEach((row) => {
    if (!row || typeof row !== 'object') {
      return;
    }
    const label = typeof row['Datenpunkt / Meldetext'] === 'string' ? row['Datenpunkt / Meldetext'].trim() : '';
    if (!label) {
      return;
    }
    const ioa = extractIoaFromRow(row);
    if (ioa === null) {
      return;
    }
    SIGNAL_LIST_IOA_MAP.set(ioa, label);
  });
}

// Lädt die Signalliste für die Kommunikationsanzeige und baut das Lookup auf
async function loadSignalListMapping() {
  try {
    const response = await fetch(SIGNAL_LIST_ENDPOINT);
    if (!response.ok) {
      throw new Error('HTTP ' + response.status);
    }
    const payload = await response.json();
    if (payload.status === 'success' && payload.signalliste) {
      buildSignalListLookup(payload.signalliste);
    }
  } catch (error) {
    console.warn('Konnte Signalliste nicht laden', error);
    SIGNAL_LIST_IOA_MAP.clear();
  }
}

// Ermittelt die anzuzeigende Beschriftung für ein Telegramm
function resolveTelegramLabel(raw) {
  if (raw && raw.frame_family === 'I' && typeof raw.ioa === 'number') {
    if (raw.ioa === 0) {
      return raw.label;
    }
    const mapped = SIGNAL_LIST_IOA_MAP.get(raw.ioa);
    if (mapped) {
      return mapped;
    }
  }
  return raw.label;
}

// Teilt eine IOA in ihre 3-Byte-Segmente auf und gibt sie als Zeichenketten zurück
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

// Entfernt die leere Platzhalternachricht aus einem Feed
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

// Hängt ein neues Telegramm an den entsprechenden Feed an und hält das Scroll-Verhalten konsistent
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

// Fügt eine leere Platzhalter-Nachricht hinzu, wenn keine Telegramme vorhanden sind
function addEmptyState(container) {
  if (!container.querySelector('.telegram-feed__empty')) {
    const empty = document.createElement('div');
    empty.className = 'telegram-feed__empty';
    empty.textContent = 'Noch keine Telegramme erfasst.';
    container.appendChild(empty);
  }
}

// Setzt die lokal gespeicherten Telegramme und die Anzeige für eine Seite zurück
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

// Löscht den Verlauf einer Seite aus der JSON-Datei und aktualisiert die Anzeige
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

// Schließt alle offenen Optionsmenüs
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

// Bindet die Events für die Optionsmenüs 
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

// Überführt rohe Telegramm-Daten aus dem Backend in UI-fähige Objekte und rendert sie
function handleTelegramEvent(raw) {
  const target = raw.side;
  if (!target || !TELEGRAM_STATE[target]) {
    return;
  }

  const telegram = {
    sequence: raw.sequence,
    label: resolveTelegramLabel(raw),
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

// Reagiert auf neue Nachrichten aus dem Event-Stream (Telegramme und Status-Updates)
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

// Baut die SSE-verbindung zum Backend auf und versucht bei Verbindungsverlust einen Neuaufbau
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

// Startet Client oder Server über die Backend-API und schützt den Button währenddessen
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

// Stoppt den Client oder Server über die Backend-API und verhindert doppelte Klicks
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

// Bindet die Steuerelemente für Start/Stop und zeigt während des Aufbaus einen Status an
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

// Lädt die bisherigen Telegramme aus dem Backend und initialisiert die Feeds
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

// Initialisiert die gesamte Beobachten-Seite inklusive Controls, Menüs und Livestream
async function initBeobachten() {
  bindControls();
  bindOptionMenus();
  bindFeedInteractions();
  fetchConnectionStatusSnapshot();
  await loadSignalListMapping();
  await loadExistingTelegrams();
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
