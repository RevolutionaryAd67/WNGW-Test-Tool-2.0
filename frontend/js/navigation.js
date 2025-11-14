import { showPanel } from './tests.js';

const subNavConfig = {
  home: [],
  observe: [
    { id: 'client-toggle', label: 'Client/Master' },
    { id: 'server-toggle', label: 'Server/Slave' },
    { id: 'observe-filter', label: 'Filter' },
    { id: 'observe-options', label: 'Optionen' },
  ],
  testing: [
    { id: 'testing-start', label: 'Prüfung starten' },
    { id: 'testing-configure', label: 'Prüfung konfigurieren' },
    { id: 'testing-logs', label: 'Prüfprotokolle' },
    { id: 'testing-options', label: 'Optionen' },
  ],
  help: [{ id: 'help-placeholder', label: 'Platzhalter' }],
  settings: [
    { id: 'settings-client', label: 'Client/Master' },
    { id: 'settings-server', label: 'Server/Slave' },
    { id: 'settings-options', label: 'Optionen' },
  ],
};

export function initNavigation(state) {
  const topNav = document.querySelectorAll('.top-nav button');
  const views = document.querySelectorAll('.view');
  topNav.forEach((button) => {
    button.addEventListener('click', () => {
      topNav.forEach((btn) => btn.classList.remove('active'));
      button.classList.add('active');
      const view = button.dataset.view;
      state.activeView = view;
      views.forEach((section) => {
        section.classList.toggle('active', section.id === `view-${view}`);
      });
      renderSubNavigation(view);
    });
  });
  document.querySelector('.top-nav button[data-view="home"]').classList.add('active');
  renderSubNavigation('home');
}

function renderSubNavigation(view) {
  const container = document.getElementById('sub-navigation');
  container.innerHTML = '';
  const entries = subNavConfig[view] ?? [];
  entries.forEach((entry) => {
    const btn = document.createElement('button');
    btn.textContent = entry.label;
    btn.dataset.id = entry.id;
    btn.addEventListener('click', () => handleSubNavClick(view, entry.id));
    container.appendChild(btn);
  });
}

function handleSubNavClick(view, id) {
  if (view === 'observe') {
    if (id === 'client-toggle') {
      document.dispatchEvent(new CustomEvent('observe:toggle-client'));
    } else if (id === 'server-toggle') {
      document.dispatchEvent(new CustomEvent('observe:toggle-server'));
    } else if (id === 'observe-options') {
      document.dispatchEvent(new CustomEvent('observe:options'));
    } else if (id === 'observe-filter') {
      alert('Filter werden später ergänzt.');
    }
  } else if (view === 'testing') {
    if (id === 'testing-start') {
      showPanel('run');
    } else if (id === 'testing-configure') {
      showPanel('configure');
    } else if (id === 'testing-logs') {
      showPanel('logs');
    }
  }
}
