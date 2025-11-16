const TOP_NAV_ITEMS = [
  { path: '/startseite', label: 'Startseite', description: 'Zur Übersicht' },
  { path: '/beobachten', label: 'Beobachten', description: 'Systeme beobachten' },
  { path: '/pruefung', label: 'Prüfung', description: 'Tests ausführen' },
  { path: '/hilfe', label: 'Hilfe', description: 'Dokumentation' },
  { path: '/einstellungen', label: 'Einstellungen', description: 'Konfiguration' },
];

const SUB_NAV_ITEMS = {
  Beobachten: [
    { path: '/beobachten/client-master', label: 'Client/Master', description: 'Client-Übersicht' },
    { path: '/beobachten/server-slave', label: 'Server/Slave', description: 'Server-Übersicht' },
    { path: '/beobachten/filter', label: 'Filter', description: 'Filter konfigurieren' },
    { path: '/beobachten/optionen', label: 'Optionen', description: 'Optionen anpassen' },
  ],
};

function createNavItem(item, activeLabel) {
  const listItem = document.createElement('li');
  if (item.label === activeLabel) {
    listItem.classList.add('active');
  }

  const link = document.createElement('a');
  link.href = item.path;
  link.textContent = item.label;
  link.title = item.description;

  listItem.appendChild(link);
  return listItem;
}

function renderNavigation() {
  const topNav = document.querySelector('.top-nav');
  const subNav = document.querySelector('.sub-nav');

  if (!topNav || !subNav) {
    return;
  }

  const topNavList = topNav.querySelector('ul');
  const subNavList = subNav.querySelector('ul');

  const activeTop = topNav.dataset.activeTop || '';
  const activeSub = subNav.dataset.activeSub || '';

  topNavList.innerHTML = '';
  TOP_NAV_ITEMS.forEach((item) => {
    topNavList.appendChild(createNavItem(item, activeTop));
  });

  subNavList.innerHTML = '';
  const subItems = SUB_NAV_ITEMS[activeTop] || [];

  if (!subItems.length) {
    const placeholder = document.createElement('li');
    placeholder.className = 'placeholder';
    placeholder.textContent = 'Keine zusätzlichen Optionen';
    subNavList.appendChild(placeholder);
    return;
  }

  subItems.forEach((item) => {
    subNavList.appendChild(createNavItem(item, activeSub));
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', renderNavigation);
} else {
  renderNavigation();
}
