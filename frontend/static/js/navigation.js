const TOP_NAV_ITEMS = [
  { path: '/startseite', label: 'Startseite', description: 'Zur Übersicht' },
  { path: '/beobachten', label: 'Beobachten', description: 'Systeme beobachten' },
  { path: '/pruefung', label: 'Prüfung', description: 'Tests ausführen' },
  { path: '/hilfe', label: 'Hilfe', description: 'Dokumentation' },
  { path: '/einstellungen', label: 'Einstellungen', description: 'Konfiguration' },
];

const SUB_NAV_ITEMS = {
  Beobachten: [
    {
      label: 'Client/Master',
      description: 'Client-Übersicht',
      dropdown: [
        { label: 'Aktivieren', description: 'Client/Master aktivieren' },
      ],
    },
    {
      label: 'Server/Slave',
      description: 'Server-Übersicht',
      dropdown: [
        { label: 'Aktivieren', description: 'Server/Slave aktivieren' },
      ],
    },
    { path: '/beobachten/filter', label: 'Filter', description: 'Filter konfigurieren' },
    { path: '/beobachten/optionen', label: 'Optionen', description: 'Optionen anpassen' },
  ],
};

function closeAllDropdowns() {
  document.querySelectorAll('.sub-nav li.has-dropdown.open').forEach((item) => {
    item.classList.remove('open');
    const toggle = item.querySelector('.dropdown-toggle');
    if (toggle) {
      toggle.setAttribute('aria-expanded', 'false');
    }
  });
}

let dropdownHandlersInitialized = false;

function ensureDropdownHandlers() {
  if (dropdownHandlersInitialized) {
    return;
  }
  document.addEventListener('click', (event) => {
    if (!event.target.closest('.sub-nav li.has-dropdown')) {
      closeAllDropdowns();
    }
  });
  dropdownHandlersInitialized = true;
}

function createNavItem(item, activeLabel) {
  const listItem = document.createElement('li');
  if (item.label === activeLabel) {
    listItem.classList.add('active');
  }

  if (item.dropdown && item.dropdown.length) {
    listItem.classList.add('has-dropdown');
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'dropdown-toggle';
    toggle.textContent = item.label;
    toggle.title = item.description;
    toggle.setAttribute('aria-haspopup', 'true');
    toggle.setAttribute('aria-expanded', 'false');

    const indicator = document.createElement('span');
    indicator.className = 'dropdown-indicator';
    indicator.textContent = '>';
    toggle.appendChild(indicator);

    toggle.addEventListener('click', (event) => {
      event.stopPropagation();
      const isOpen = listItem.classList.contains('open');
      closeAllDropdowns();
      if (!isOpen) {
        listItem.classList.add('open');
        toggle.setAttribute('aria-expanded', 'true');
      }
    });

    const dropdownMenu = document.createElement('ul');
    dropdownMenu.className = 'dropdown-menu';
    dropdownMenu.setAttribute('role', 'menu');

    item.dropdown.forEach((option) => {
      const optionItem = document.createElement('li');
      const optionLink = document.createElement('a');
      optionLink.href = option.path || '#';
      optionLink.textContent = option.label;
      optionLink.title = option.description || '';
      optionLink.setAttribute('role', 'menuitem');
      optionLink.addEventListener('click', () => {
        closeAllDropdowns();
      });
      optionItem.appendChild(optionLink);
      dropdownMenu.appendChild(optionItem);
    });

    listItem.appendChild(toggle);
    listItem.appendChild(dropdownMenu);
    ensureDropdownHandlers();
    return listItem;
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
