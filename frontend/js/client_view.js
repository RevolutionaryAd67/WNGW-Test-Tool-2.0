import { AppState } from './app.js';

let container;
let column;

export function initClientView(state) {
  container = document.getElementById('client-log');
  column = document.getElementById('client-column');
  document.addEventListener('observe:toggle-client', () => {
    state.observe.clientVisible = !state.observe.clientVisible;
    applyVisibility(state);
  });
  document.addEventListener('observe:options', () => showOptions(state));
}

function applyVisibility(state) {
  column.style.display = state.observe.clientVisible ? 'flex' : 'none';
  adjustColumnLayout(state);
}

function adjustColumnLayout(state) {
  const serverColumn = document.getElementById('server-column');
  if (!state.observe.clientVisible && state.observe.serverVisible) {
    serverColumn.style.flex = '1 1 100%';
  } else {
    serverColumn.style.flex = '1 1 50%';
    column.style.flex = '1 1 50%';
  }
}

function showOptions(state) {
  const choice = window.prompt(
    'Optionen:\n1) Auto-Scroll umschalten\n2) Scroll synchron umschalten\n3) Verlauf löschen\n4) Verlauf exportieren'
  );
  switch (choice) {
    case '1':
      state.observe.autoScroll = !state.observe.autoScroll;
      alert(`Auto-Scroll ${state.observe.autoScroll ? 'aktiviert' : 'deaktiviert'}`);
      break;
    case '2':
      state.observe.syncScroll = !state.observe.syncScroll;
      alert(`Scrollen ${state.observe.syncScroll ? 'synchronisiert' : 'getrennt'}`);
      break;
    case '3':
      clearLogs();
      document.dispatchEvent(new CustomEvent('server:clear-log'));
      break;
    case '4':
      exportLogs();
      break;
    default:
      break;
  }
}

export function appendClientFrame(frame) {
  if (!container) return;
  const entry = document.createElement('div');
  entry.className = 'log-entry';
  if (frame.direction === 'out') {
    entry.classList.add('outgoing');
  }
  entry.textContent = formatFrame(frame, ++AppState.observe.clientSequence);
  container.appendChild(entry);
  autoScroll(container);
  if (AppState.observe.syncScroll) {
    const other = document.getElementById('server-log');
    other.scrollTop = container.scrollTop;
  }
}

function clearLogs() {
  container.innerHTML = '';
  AppState.observe.clientSequence = 0;
}

async function exportLogs() {
  await fetch('/api/logs/export', { method: 'POST' });
  alert('Logdateien wurden exportiert.');
}

function autoScroll(target) {
  if (!AppState.observe.autoScroll) {
    return;
  }
  target.scrollTop = target.scrollHeight;
}

function formatFrame(frame, index) {
  const timestamp = frame.timestamp ? new Date(frame.timestamp) : new Date();
  const timeStr = timestamp.toLocaleTimeString('de-DE', { hour12: false }) +
    '.' + String(timestamp.getMilliseconds()).padStart(3, '0');
  const header = `${String(index).padStart(4, ' ')} : ${frame.description ?? 'FRAME'}`;
  const lines = [
    header,
    `Zeit          : ${timeStr}`,
    `IP:Port       : ${frame.src_ip ?? '-'}:${frame.src_port ?? '-'} --> ${frame.dst_ip ?? '-'}:${frame.dst_port ?? '-'}`,
  ];
  if (frame.frame_format === 'I') {
    lines.push(`Typ           : ${frame.type_id ?? '-'} (I-Format)`);
    lines.push(
      `Ursache       : Aktivierung = ${frame.cot_byte1 ?? '-'}    Herkunft = ${frame.cot_byte2 ?? '-'}`
    );
    lines.push(`Station       : ${frame.ca ?? '-'}`);
    const ioa = frame.ioa ?? [0, 0, 0];
    lines.push(`IOA           : ${ioa[0]}- ${ioa[1]}- ${ioa[2]}`);
  } else {
    lines.push(`Typ          : (${frame.frame_format}-Format)`);
  }
  return lines.join('\n');
}

export function toggleClientStatus(active) {
  const footer = document.getElementById('footer-client');
  footer.classList.toggle('status-active', active);
  footer.classList.toggle('status-inactive', !active);
}

export function clearClientLogs() {
  clearLogs();
}
