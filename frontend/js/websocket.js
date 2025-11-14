import { appendClientFrame, toggleClientStatus } from './client_view.js';
import { appendServerFrame, toggleServerStatus } from './server_view.js';
import { updateFooterClock, updateFooterTest } from './logs.js';
import { handleTestEvent } from './tests.js';

export function initWebSockets(state) {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const base = `${protocol}://${window.location.host}`;
  connect(`${base}/ws/client`, handleClientMessage);
  connect(`${base}/ws/server`, handleServerMessage);
  connect(`${base}/ws/system`, handleSystemMessage);
  connect(`${base}/ws/tests`, handleTestMessage);
}

function connect(url, handler) {
  const socket = new WebSocket(url);
  socket.addEventListener('message', (event) => {
    try {
      const data = JSON.parse(event.data);
      handler(data);
    } catch (err) {
      console.error('WebSocket message error', err);
    }
  });
  socket.addEventListener('close', () => {
    setTimeout(() => connect(url, handler), 3000);
  });
}

function handleClientMessage(data) {
  if (data.event === 'client_status') {
    toggleClientStatus(data.active);
    return;
  }
  appendClientFrame(data);
}

function handleServerMessage(data) {
  if (data.event === 'server_status') {
    toggleServerStatus(data.active);
    return;
  }
  appendServerFrame(data);
}

function handleSystemMessage(data) {
  if (data.event === 'clock') {
    updateFooterClock(data.timestamp);
  }
}

function handleTestMessage(data) {
  handleTestEvent(data);
  if (data.event === 'test_finished') {
    updateFooterTest(`Prüfung abgeschlossen – Run ${data.run_id}`);
  } else if (data.event === 'status_update') {
    updateFooterTest(`Prüfung läuft – Schritt ${data.step}`);
  } else if (data.event === 'test_error') {
    updateFooterTest(`Fehler: ${data.message}`);
  }
}
