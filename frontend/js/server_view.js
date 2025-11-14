import { AppState } from './app.js';

let container;
let column;

export function initServerView(state) {
  container = document.getElementById('server-log');
  column = document.getElementById('server-column');
  document.addEventListener('observe:toggle-server', () => {
    state.observe.serverVisible = !state.observe.serverVisible;
    applyVisibility(state);
  });
  document.addEventListener('server:clear-log', () => clearLogs());
}

function applyVisibility(state) {
  column.style.display = state.observe.serverVisible ? 'flex' : 'none';
  const clientColumn = document.getElementById('client-column');
  if (!state.observe.serverVisible && state.observe.clientVisible) {
    clientColumn.style.flex = '1 1 100%';
  } else {
    column.style.flex = '1 1 50%';
    clientColumn.style.flex = '1 1 50%';
  }
}

export function appendServerFrame(frame) {
  if (!container) return;
  const entry = document.createElement('div');
  entry.className = 'log-entry';
  if (frame.direction === 'out') {
    entry.classList.add('outgoing');
  }
  entry.textContent = formatFrame(frame, ++AppState.observe.serverSequence);
  container.appendChild(entry);
  if (AppState.observe.autoScroll) {
    container.scrollTop = container.scrollHeight;
  }
  if (AppState.observe.syncScroll) {
    const other = document.getElementById('client-log');
    other.scrollTop = container.scrollTop;
  }
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

function clearLogs() {
  container.innerHTML = '';
  AppState.observe.serverSequence = 0;
}

export function toggleServerStatus(active) {
  const footer = document.getElementById('footer-server');
  footer.classList.toggle('status-active', active);
  footer.classList.toggle('status-inactive', !active);
}
