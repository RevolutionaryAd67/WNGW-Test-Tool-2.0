export function initLogs(state) {
  loadLogList();
}

export async function loadLogList() {
  const response = await fetch('/api/tests/logs');
  const data = await response.json();
  const list = document.getElementById('test-log-list');
  list.innerHTML = '';
  data.runs
    .sort((a, b) => b.created - a.created)
    .forEach((run) => {
      const li = document.createElement('li');
      li.innerHTML = `<strong>${run.run_id}</strong>`;
      const files = document.createElement('div');
      run.steps.forEach((file) => {
        const link = document.createElement('a');
        link.href = `/api/tests/logs/${run.run_id}/${file}`;
        link.textContent = file;
        link.target = '_blank';
        files.appendChild(link);
        files.appendChild(document.createElement('br'));
      });
      li.appendChild(files);
      list.appendChild(li);
    });
}

export function updateFooterClock(timestamp) {
  const footer = document.getElementById('footer-clock');
  const date = new Date(timestamp);
  const time = date.toLocaleTimeString('de-DE', { hour12: false }) +
    '.' + String(date.getMilliseconds()).padStart(3, '0');
  footer.textContent = time;
}

export function updateFooterTest(text) {
  const footer = document.getElementById('footer-test');
  footer.textContent = text;
}
