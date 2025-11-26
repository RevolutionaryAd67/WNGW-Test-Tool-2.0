(function () {
    const state = {
        configs: [],
        currentId: null,
        currentConfig: null,
        run: null,
        poller: null,
    };

    const elements = {
        list: document.getElementById('config-list'),
        name: document.getElementById('selected-config-name'),
        ablaufBody: document.querySelector('#ablauf-table tbody'),
        startButton: document.getElementById('start-test-button'),
        abortButton: document.getElementById('abort-test-button'),
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
        state.currentConfig = configuration || null;
        if (state.run && configuration && state.run.configurationId !== configuration.id) {
            stopPolling();
            state.run = null;
        }
        if (elements.name) {
            elements.name.textContent = configuration ? configuration.name || 'Unbenannte Prüfung' : 'Prüfung auswählen';
        }
        renderConfigList();
        renderSteps(configuration);
    }

    function getStatusForIndex(index) {
        if (!state.run || !Array.isArray(state.run.teilpruefungen)) return '';
        const match = state.run.teilpruefungen.find((teil) => Number(teil.index) === Number(index));
        return match && match.status ? match.status : '';
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
            statusCell.textContent = getStatusForIndex(step.index || index + 1);
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

    function stopPolling() {
        if (state.poller) {
            clearInterval(state.poller);
            state.poller = null;
        }
    }

    function startPolling() {
        if (state.poller) return;
        state.poller = window.setInterval(fetchRunStatus, 1000);
    }

    function setRunState(run) {
        state.run = run || null;
        renderSteps(state.currentConfig);
        if (state.run && !state.run.finished) {
            startPolling();
        } else {
            stopPolling();
        }
    }

    async function fetchRunStatus() {
        try {
            const response = await fetch('/api/pruefungslauf/status');
            if (!response.ok) throw new Error('Status konnte nicht geladen werden.');
            const data = await response.json();
            setRunState(data.run || null);
        } catch (error) {
            console.error(error);
        }
    }

    async function startRun() {
        if (!state.currentId) return;
        try {
            const response = await fetch('/api/pruefungslauf/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ configId: state.currentId }),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.message || 'Prüfung konnte nicht gestartet werden.');
            setRunState(data.run || null);
        } catch (error) {
            console.error(error);
        }
    }

    async function abortRun() {
        try {
            const response = await fetch('/api/pruefungslauf/abbrechen', { method: 'POST' });
            const data = await response.json();
            setRunState(data.run || null);
        } catch (error) {
            console.error(error);
        }
    }

    function registerControls() {
        if (elements.startButton) {
            elements.startButton.addEventListener('click', startRun);
        }
        if (elements.abortButton) {
            elements.abortButton.addEventListener('click', abortRun);
        }
    }

    async function init() {
        registerControls();
        await loadConfigList();
        await fetchRunStatus();
    }

    document.addEventListener('DOMContentLoaded', init);
})();
