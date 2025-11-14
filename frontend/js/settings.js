export function initSettings(state) {
  loadSettings();
  const clientForm = document.getElementById('client-settings-form');
  clientForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const payload = readForm(clientForm);
    await fetch('/api/settings/client', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    alert('Client-Einstellungen gespeichert.');
  });

  const serverForm = document.getElementById('server-settings-form');
  serverForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const payload = readForm(serverForm);
    await fetch('/api/settings/server', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    alert('Server-Einstellungen gespeichert.');
  });

  const upload = document.getElementById('server-signal-upload');
  upload.addEventListener('change', async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    await fetch('/api/settings/signals/upload', { method: 'POST', body: formData });
    alert('Signalliste hochgeladen.');
  });
}

async function loadSettings() {
  const [client, server] = await Promise.all([
    fetch('/api/settings/client').then((res) => res.json()),
    fetch('/api/settings/server').then((res) => res.json()),
  ]);
  writeForm(document.getElementById('client-settings-form'), client);
  writeForm(document.getElementById('server-settings-form'), server);
}

function readForm(form) {
  const payload = {};
  form.querySelectorAll('input').forEach((input) => {
    const path = input.name.split('.');
    setValue(payload, path, input.type === 'number' ? Number(input.value) : input.value);
  });
  return payload;
}

function writeForm(form, data) {
  form.querySelectorAll('input').forEach((input) => {
    const path = input.name.split('.');
    const value = getValue(data, path);
    if (value !== undefined) {
      input.value = value;
    }
  });
}

function setValue(target, path, value) {
  let cursor = target;
  for (let i = 0; i < path.length - 1; i++) {
    const key = path[i];
    cursor[key] = cursor[key] ?? {};
    cursor = cursor[key];
  }
  cursor[path[path.length - 1]] = value;
}

function getValue(source, path) {
  return path.reduce((acc, key) => (acc ? acc[key] : undefined), source);
}
