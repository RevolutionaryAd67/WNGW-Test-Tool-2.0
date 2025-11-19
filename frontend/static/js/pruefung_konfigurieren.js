(function () {
    const state = {
        configs: [],
        current: createEmptyConfig(),
    };

    const elements = {
        list: document.getElementById('config-list'),
        nameInput: document.getElementById('config-name'),
        deleteButton: document.getElementById('delete-config'),
        saveButton: document.getElementById('save-config'),
        feedback: document.getElementById('config-feedback'),
        nextIndex: document.getElementById('next-step-index'),
        typeSelect: document.getElementById('teilpruefung-type'),
        fileInput: document.getElementById('signalliste-file'),
        fileLabel: document.getElementById('signalliste-label'),
        addStepButton: document.getElementById('add-step-button'),
        ablaufTableBody: document.querySelector('#ablauf-table tbody'),
    };

    const REQUIRED_HEADERS = [
        'Datenpunkt / Meldetext',
        'IOA 3',
        'IOA 2',
        'IOA 1',
        'IEC104- Typ',
    ];

    function createEmptyConfig() {
        return {
            id: null,
            name: '',
            teilpruefungen: [],
        };
    }

    function uuid() {
        if (window.crypto && 'randomUUID' in window.crypto) {
            return window.crypto.randomUUID();
        }
        return `tmp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
    }

    function setFeedback(message, type = 'info') {
        elements.feedback.textContent = message || '';
        elements.feedback.dataset.state = type;
    }

    function renderConfigList() {
        if (!elements.list) return;
        elements.list.innerHTML = '';
        const newItem = document.createElement('li');
        newItem.className = 'config-list__item';
        const newButton = document.createElement('button');
        newButton.type = 'button';
        newButton.className = `config-list__button${state.current.id === null ? ' config-list__button--active' : ''}`;
        newButton.textContent = '+ Neue Konfiguration';
        newButton.addEventListener('click', () => {
            setCurrentConfig(createEmptyConfig());
        });
        newItem.appendChild(newButton);
        elements.list.appendChild(newItem);

        const sorted = [...state.configs].sort((a, b) => a.name.localeCompare(b.name, 'de', { sensitivity: 'base' }));
        sorted.forEach((config) => {
            const item = document.createElement('li');
            item.className = 'config-list__item';
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'config-list__button';
            if (state.current.id === config.id) {
                button.classList.add('config-list__button--active');
            }
            button.textContent = config.name || 'Unbenannte Prüfung';
            button.addEventListener('click', () => loadConfig(config.id));
            item.appendChild(button);
            elements.list.appendChild(item);
        });
    }

    function renderSteps() {
        const tbody = elements.ablaufTableBody;
        if (!tbody) return;
        tbody.innerHTML = '';
        if (!state.current.teilpruefungen.length) {
            const emptyRow = document.createElement('tr');
            emptyRow.className = 'ablauf-table__empty';
            const cell = document.createElement('td');
            cell.colSpan = 4;
            cell.textContent = '/';
            emptyRow.appendChild(cell);
            tbody.appendChild(emptyRow);
        } else {
            state.current.teilpruefungen.forEach((step, index) => {
                const row = document.createElement('tr');
                const indexCell = document.createElement('td');
                indexCell.textContent = String(index + 1);
                row.appendChild(indexCell);

                const typeCell = document.createElement('td');
                typeCell.textContent = step.pruefungsart;
                row.appendChild(typeCell);

                const fileCell = document.createElement('td');
                fileCell.textContent = (step.signalliste && step.signalliste.filename) || '';
                row.appendChild(fileCell);

                const actionsCell = document.createElement('td');
                const deleteButton = document.createElement('button');
                deleteButton.type = 'button';
                deleteButton.className = 'icon-button';
                deleteButton.title = 'Teilprüfung entfernen';
                deleteButton.textContent = '✕';
                deleteButton.addEventListener('click', () => removeStep(index));

                const upButton = document.createElement('button');
                upButton.type = 'button';
                upButton.className = 'icon-button';
                upButton.title = 'Nach oben verschieben';
                upButton.textContent = '↑';
                upButton.disabled = index === 0;
                upButton.addEventListener('click', () => moveStep(index, -1));

                const downButton = document.createElement('button');
                downButton.type = 'button';
                downButton.className = 'icon-button';
                downButton.title = 'Nach unten verschieben';
                downButton.textContent = '↓';
                downButton.disabled = index === state.current.teilpruefungen.length - 1;
                downButton.addEventListener('click', () => moveStep(index, 1));

                actionsCell.appendChild(deleteButton);
                actionsCell.appendChild(upButton);
                actionsCell.appendChild(downButton);
                row.appendChild(actionsCell);
                tbody.appendChild(row);
            });
        }
        updateNextIndex();
    }

    function updateNextIndex() {
        if (elements.nextIndex) {
            elements.nextIndex.textContent = String(state.current.teilpruefungen.length + 1);
        }
    }

    function setCurrentConfig(config) {
        state.current = {
            id: config.id || null,
            name: config.name || '',
            teilpruefungen: Array.isArray(config.teilpruefungen) ? config.teilpruefungen.map((step) => ({
                id: step.id || uuid(),
                pruefungsart: step.pruefungsart,
                signalliste: step.signalliste,
            })) : [],
        };
        if (elements.nameInput) {
            elements.nameInput.value = state.current.name;
        }
        resetAddForm();
        renderConfigList();
        renderSteps();
    }

    function resetAddForm() {
        if (elements.fileInput) {
            elements.fileInput.value = '';
        }
        if (elements.fileLabel) {
            elements.fileLabel.textContent = 'Excel-Datei auswählen';
        }
        setFeedback('');
    }

    function removeStep(index) {
        state.current.teilpruefungen.splice(index, 1);
        renderSteps();
    }

    function moveStep(index, direction) {
        const targetIndex = index + direction;
        if (targetIndex < 0 || targetIndex >= state.current.teilpruefungen.length) {
            return;
        }
        const temp = state.current.teilpruefungen[index];
        state.current.teilpruefungen[index] = state.current.teilpruefungen[targetIndex];
        state.current.teilpruefungen[targetIndex] = temp;
        renderSteps();
    }

    async function loadConfigList() {
        try {
            const response = await fetch('/api/pruefungskonfigurationen');
            if (!response.ok) throw new Error('Konfigurationen konnten nicht geladen werden.');
            const data = await response.json();
            state.configs = data.configurations || [];
            renderConfigList();
        } catch (error) {
            setFeedback(error.message, 'error');
        }
    }

    async function loadConfig(id) {
        try {
            const response = await fetch(`/api/pruefungskonfigurationen/${encodeURIComponent(id)}`);
            if (!response.ok) throw new Error('Konfiguration konnte nicht geladen werden.');
            const data = await response.json();
            if (data.configuration) {
                setCurrentConfig(data.configuration);
            }
        } catch (error) {
            setFeedback(error.message, 'error');
        }
    }

    async function uploadSignalliste(file) {
        const formData = new FormData();
        formData.append('signalliste', file);
        const response = await fetch('/api/pruefungskonfigurationen/signalliste', {
            method: 'POST',
            body: formData,
        });
        if (!response.ok) {
            const error = await response.json().catch(() => ({ message: 'Datei konnte nicht hochgeladen werden.' }));
            throw new Error(error.message || 'Datei konnte nicht hochgeladen werden.');
        }
        return response.json();
    }

    async function handleAddStep() {
        const type = elements.typeSelect ? elements.typeSelect.value : '';
        const file = elements.fileInput && elements.fileInput.files ? elements.fileInput.files[0] : undefined;
        if (!type) {
            setFeedback('Bitte eine Prüfungsart wählen.', 'error');
            return;
        }
        if (!file) {
            setFeedback('Bitte eine Signalliste auswählen.', 'error');
            return;
        }
        try {
            const signalliste = await uploadSignalliste(file);
            const headers = Array.isArray(signalliste.headers) ? signalliste.headers : [];
            const missingHeaders = REQUIRED_HEADERS.filter((header) => headers.indexOf(header) === -1);
            if (missingHeaders.length) {
                throw new Error(`Signalliste unvollständig: ${missingHeaders.join(', ')}`);
            }
            state.current.teilpruefungen.push({
                id: uuid(),
                pruefungsart: type,
                signalliste,
            });
            renderSteps();
            resetAddForm();
            setFeedback('Teilprüfung hinzugefügt.', 'success');
        } catch (error) {
            setFeedback(error.message, 'error');
        }
    }

    async function saveConfig() {
        const name = elements.nameInput && typeof elements.nameInput.value === 'string'
            ? elements.nameInput.value.trim()
            : '';
        if (!name) {
            setFeedback('Bitte einen Namen für die Prüfung vergeben.', 'error');
            return;
        }
        const payload = {
            id: state.current.id,
            name,
            teilpruefungen: state.current.teilpruefungen.map((step, index) => ({
                index: index + 1,
                pruefungsart: step.pruefungsart,
                signalliste: step.signalliste,
            })),
        };
        try {
            const response = await fetch('/api/pruefungskonfigurationen', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!response.ok) {
                const error = await response.json().catch(() => ({ message: 'Speichern fehlgeschlagen.' }));
                throw new Error(error.message || 'Speichern fehlgeschlagen.');
            }
            const data = await response.json();
            if (data.configuration) {
                setCurrentConfig(data.configuration);
            }
            await loadConfigList();
            setFeedback('Prüfung gespeichert.', 'success');
        } catch (error) {
            setFeedback(error.message, 'error');
        }
    }

    async function deleteConfig() {
        if (!state.current.id) {
            setCurrentConfig(createEmptyConfig());
            setFeedback('Neue Konfiguration bereit.', 'info');
            return;
        }
        try {
            const response = await fetch(`/api/pruefungskonfigurationen/${encodeURIComponent(state.current.id)}`, {
                method: 'DELETE',
            });
            if (!response.ok) {
                const error = await response.json().catch(() => ({ message: 'Löschen fehlgeschlagen.' }));
                throw new Error(error.message || 'Löschen fehlgeschlagen.');
            }
            await loadConfigList();
            setCurrentConfig(createEmptyConfig());
            setFeedback('Prüfung gelöscht.', 'success');
        } catch (error) {
            setFeedback(error.message, 'error');
        }
    }

    function handleNameChange(event) {
        state.current.name = event.target.value;
        renderConfigList();
    }

    function handleFileLabel() {
        if (!elements.fileInput || !elements.fileLabel) return;
        const file = elements.fileInput.files && elements.fileInput.files[0];
        elements.fileLabel.textContent = file ? file.name : 'Excel-Datei auswählen';
    }

    function registerEvents() {
        if (elements.addStepButton) {
            elements.addStepButton.addEventListener('click', handleAddStep);
        }
        if (elements.saveButton) {
            elements.saveButton.addEventListener('click', saveConfig);
        }
        if (elements.deleteButton) {
            elements.deleteButton.addEventListener('click', deleteConfig);
        }
        if (elements.nameInput) {
            elements.nameInput.addEventListener('input', handleNameChange);
        }
        if (elements.fileInput) {
            elements.fileInput.addEventListener('change', handleFileLabel);
        }
    }

    function init() {
        registerEvents();
        renderConfigList();
        renderSteps();
        loadConfigList();
    }

    document.addEventListener('DOMContentLoaded', init);
})();
