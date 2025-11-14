import { AppState } from './app.js';
import { loadLogList } from './logs.js';

let currentConfig = null;
let currentSteps = [];

export function initTests(state) {
  document.getElementById('new-test-config').addEventListener('click', () => {
    currentConfig = { id: null, name: '', steps: [] };
    currentSteps = [];
    renderConfig();
  });
  document.getElementById('save-test-config').addEventListener('click', saveConfig);
  document.getElementById('delete-test-config').addEventListener('click', deleteConfig);
  document.getElementById('add-test-step').addEventListener('click', addStep);
  document.getElementById('start-test-run').addEventListener('click', startRun);
  document.getElementById('stop-test-run').addEventListener('click', stopRun);
  loadConfigs();
}

export function showPanel(panel) {
  const configure = document.getElementById('testing-start');
  const run = document.getElementById('testing-run');
  const logs = document.getElementById('testing-logs');
  configure.classList.add('hidden');
  run.classList.add('hidden');
  logs.classList.add('hidden');
  if (panel === 'configure') {
    configure.classList.remove('hidden');
  } else if (panel === 'run') {
    run.classList.remove('hidden');
  } else if (panel === 'logs') {
    logs.classList.remove('hidden');
    loadLogList();
  }
}

async function loadConfigs() {
  const response = await fetch('/api/tests/configs');
  const data = await response.json();
  const list = document.getElementById('test-config-list');
  list.innerHTML = '';
  data.configs.forEach((config) => {
    const li = document.createElement('li');
    li.textContent = config.name;
    li.addEventListener('click', () => selectConfig(config));
    list.appendChild(li);
  });
}

function selectConfig(config) {
  currentConfig = { ...config };
  currentSteps = config.steps ? [...config.steps] : [];
  renderConfig();
  renderRunTable();
}

function renderConfig() {
  document.getElementById('test-config-name').value = currentConfig?.name ?? '';
  renderSteps();
}

function renderSteps() {
  const tbody = document.querySelector('#test-steps-table tbody');
  tbody.innerHTML = '';
  currentSteps.forEach((step, index) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${index + 1}</td>
      <td>${step.type}</td>
      <td>${step.signal_list ?? '-'}</td>
      <td>
        <button data-action="up" data-index="${index}">▲</button>
        <button data-action="down" data-index="${index}">▼</button>
        <button data-action="delete" data-index="${index}">X</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
  tbody.querySelectorAll('button').forEach((btn) => {
    btn.addEventListener('click', handleStepAction);
  });
}

function handleStepAction(event) {
  const index = Number(event.target.dataset.index);
  const action = event.target.dataset.action;
  if (action === 'delete') {
    currentSteps.splice(index, 1);
  } else if (action === 'up' && index > 0) {
    [currentSteps[index - 1], currentSteps[index]] = [currentSteps[index], currentSteps[index - 1]];
  } else if (action === 'down' && index < currentSteps.length - 1) {
    [currentSteps[index + 1], currentSteps[index]] = [currentSteps[index], currentSteps[index + 1]];
  }
  renderSteps();
}

async function addStep() {
  const type = document.getElementById('step-type').value;
  const fileInput = document.getElementById('step-signal');
  let signalPath = null;
  if (fileInput.files[0]) {
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    const response = await fetch('/api/settings/signals/upload', { method: 'POST', body: formData });
    const data = await response.json();
    signalPath = data.path;
    fileInput.value = '';
  }
  currentSteps.push({ index: currentSteps.length + 1, type, signal_list: signalPath });
  renderSteps();
}

async function saveConfig() {
  if (!currentConfig) {
    currentConfig = { id: null };
  }
  const name = document.getElementById('test-config-name').value;
  if (!name) {
    alert('Bitte einen Namen vergeben.');
    return;
  }
  currentConfig.name = name;
  currentConfig.steps = currentSteps.map((step, idx) => ({
    index: idx + 1,
    type: step.type,
    signal_list: step.signal_list,
  }));
  const method = currentConfig.id ? 'PUT' : 'POST';
  const url = currentConfig.id ? `/api/tests/configs/${currentConfig.id}` : '/api/tests/configs';
  const response = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(currentConfig),
  });
  const data = await response.json();
  currentConfig = data.config;
  loadConfigs();
  alert('Konfiguration gespeichert.');
}

async function deleteConfig() {
  if (!currentConfig?.id) {
    alert('Keine Konfiguration ausgewählt.');
    return;
  }
  await fetch(`/api/tests/configs/${currentConfig.id}`, { method: 'DELETE' });
  currentConfig = null;
  currentSteps = [];
  renderConfig();
  loadConfigs();
  alert('Konfiguration gelöscht.');
}

async function startRun() {
  if (!currentConfig?.id) {
    alert('Bitte Konfiguration auswählen.');
    return;
  }
  const response = await fetch(`/api/tests/run/${currentConfig.id}`, { method: 'POST' });
  if (!response.ok) {
    alert('Prüfung konnte nicht gestartet werden.');
    return;
  }
  const data = await response.json();
  AppState.testing.activeRun = data.run_id;
  renderRunTable();
}

async function stopRun() {
  await fetch('/api/tests/run/stop', { method: 'POST' });
  AppState.testing.activeRun = null;
}

function renderRunTable() {
  const tbody = document.querySelector('#run-steps-table tbody');
  tbody.innerHTML = '';
  (currentConfig?.steps ?? []).forEach((step) => {
    const tr = document.createElement('tr');
    tr.dataset.step = step.index;
    tr.innerHTML = `
      <td>${step.index}</td>
      <td>${step.type}</td>
      <td>${step.signal_list ?? '-'}</td>
      <td class="status-cell">In Warteschlange</td>
    `;
    tbody.appendChild(tr);
  });
}

export function handleTestEvent(event) {
  if (event.event === 'status_update') {
    const row = document.querySelector(`#run-steps-table tr[data-step="${event.step}"] .status-cell`);
    if (row) {
      row.textContent = event.status;
    }
  }
}
