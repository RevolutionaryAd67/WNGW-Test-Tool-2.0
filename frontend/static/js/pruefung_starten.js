(function () {
    const state = {
        configs: [],
        currentId: null,
    };

    const elements = {
        list: document.getElementById('config-list'),
        name: document.getElementById('selected-config-name'),
        ablaufBody: document.querySelector('#ablauf-table tbody'),
    };

    function renderConfigList() {
        if (!elements.list) return;
        elements.list.innerHTML = '';
        const sorted = [...state.configs].sort((a, b) => a.name.localeCompare(b.name, 'de', { sensitivity: 'base' }));
        sorted.forEach((config) => {
            const item = document.createElement('li');
            item.className = 'config-list__item';
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'config-list__button';
            button.textContent = config.name || 'Unbenannte Prüfung';
            if (state.currentId === config.id) {
                button.classList.add('config-list__button--active');
            }
            button.addEventListener('click', () => loadConfiguration(config.id));
            item.appendChild(button);
            elements.list.appendChild(item);
        });
        if (!state.currentId && sorted.length) {
            loadConfiguration(sorted[0].id);
        } else if (!sorted.length) {
            updateSelection(null);
        }
    }

    function updateSelection(configuration) {
        state.currentId = configuration ? configuration.id : null;
        if (elements.name) {
            elements.name.textContent = configuration ? configuration.name || 'Unbenannte Prüfung' : 'Prüfung auswählen';
        }
        renderConfigList();
        renderSteps(configuration);
    }

    function renderSteps(configuration) {
        if (!elements.ablaufBody) return;
        elements.ablaufBody.innerHTML = '';
        const steps = (configuration && Array.isArray(configuration.teilpruefungen)) ? configuration.teilpruefungen : [];
        if (!steps.length) {
            const emptyRow = document.createElement('tr');
            emptyRow.className = 'ablauf-table__empty';
            const cell = document.createElement('td');
            cell.colSpan = 4;
            cell.textContent = configuration ? 'Kein Ablauf hinterlegt.' : 'Bitte eine Prüfung auswählen.';
            emptyRow.appendChild(cell);
            elements.ablaufBody.appendChild(emptyRow);
            return;
        }
        steps.forEach((step, index) => {
            const row = document.createElement('tr');

            const indexCell = document.createElement('td');
            indexCell.textContent = String(index + 1);
            row.appendChild(indexCell);

            const typeCell = document.createElement('td');
            typeCell.textContent = step.pruefungsart || '';
            row.appendChild(typeCell);

            const fileCell = document.createElement('td');
            const fileName = step.signalliste && step.signalliste.filename ? step.signalliste.filename : '';
            fileCell.textContent = fileName;
            row.appendChild(fileCell);

            const statusCell = document.createElement('td');
            statusCell.className = 'ablauf-table__status';
            statusCell.textContent = '';
            row.appendChild(statusCell);

            elements.ablaufBody.appendChild(row);
        });
    }

    async function loadConfigList() {
        try {
            const response = await fetch('/api/pruefungskonfigurationen');
            if (!response.ok) throw new Error('Konfigurationen konnten nicht geladen werden.');
            const data = await response.json();
            state.configs = data.configurations || [];
            renderConfigList();
        } catch (error) {
            console.error(error);
        }
    }

    async function loadConfiguration(id) {
        if (!id) {
            updateSelection(null);
            return;
        }
        try {
            const response = await fetch(`/api/pruefungskonfigurationen/${encodeURIComponent(id)}`);
            if (!response.ok) throw new Error('Konfiguration konnte nicht geladen werden.');
            const data = await response.json();
            if (data.configuration) {
                updateSelection(data.configuration);
            }
        } catch (error) {
            console.error(error);
        }
    }

    document.addEventListener('DOMContentLoaded', loadConfigList);
})();
