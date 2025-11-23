/*
    Verwaltung der "Prüfung konfigurieren"-Seite

    Aufgaben des Skripts:
        1. Konfigurationen hinzufügen, verschieben und entfernen
        2. Hochgeladene Signallisten auf Vollständigkeit prüfen
        3. Prüfungen in JSON-Dateien abspeichern
*/

(function () {

    // Globale Zustandsobjekte: Gespeicherte Konfigurationen
    const state = {
        configs: [],
        current: createEmptyConfig(),
        requiredHeaders: [],
    };

    // Referenzen auf relevante DOM-Elemente
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

    // Erzeugt eine leere Konfiguration
    function createEmptyConfig() {
        return {
            id: null,
            name: '',
            teilpruefungen: [],
        };
    }

    // Erstellt eine UUID (128-Bit-identifikator für den Namen der JSON-Datei je Konfiguration)
    function uuid() {
        if (window.crypto && 'randomUUID' in window.crypto) {
            return window.crypto.randomUUID();
        }
        return `tmp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
    }

    // Zeigt ein Feedback im UI an
    function setFeedback(message, type = 'info') {
        elements.feedback.textContent = message || '';
        elements.feedback.dataset.state = type;
    }

    // Baut die Seitenleiste mit allen verfügbaren Konfigurationen auf
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

    // Stellt die Tabelle der Teilprüfungen dar
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
                const actionsWrapper = document.createElement('div');
                actionsWrapper.className = 'ablauf-table__actions';

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

                actionsWrapper.appendChild(deleteButton);
                actionsWrapper.appendChild(upButton);
                actionsWrapper.appendChild(downButton);
                actionsCell.appendChild(actionsWrapper);
                row.appendChild(actionsCell);
                tbody.appendChild(row);
            });
        }
        updateNextIndex();
    }

    // Aktualisiert die Anzeige der nächsten Indexnummer im Eingabeformular
    function updateNextIndex() {
        if (elements.nextIndex) {
            elements.nextIndex.textContent = String(state.current.teilpruefungen.length + 1);
        }
    }

    // Setzte den aktuellen Zustand auf die übergebene Konfiguration und rendert das UI neu
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

    // Setzt das Formular für das Hinzufügen einer Teilprüfung zurück
    function resetAddForm() {
        if (elements.fileInput) {
            elements.fileInput.value = '';
        }
        if (elements.fileLabel) {
            elements.fileLabel.textContent = 'Excel-Datei auswählen';
        }
        setFeedback('');
    }

    // Entfernt eine Teilprüfung anhand des Index
    function removeStep(index) {
        state.current.teilpruefungen.splice(index, 1);
        renderSteps();
    }

    // Verschiebt die Teilprüfung innerhalb der Liste 
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

    // Lädt die Liste aller gespeicherten Konfigurationen 
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

    // Lädt eine konkrete Konfiguration anhand ihrer ID
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

    // Lädt eine Signalliste hoch und validiert die enthaltenen Spalten
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

    // Lädt die notwendigen Spaltenüberschriften aus dem Backend
    async function loadRequiredHeaders() {
        try {
            const response = await fetch('/api/pruefungskonfigurationen/required_headers');
            if (!response.ok) {
                throw new Error('Erforderliche Spaltenüberschriften konnten nicht geladen werden.');
            }
            const data = await response.json();
            state.requiredHeaders = Array.isArray(data.headers) ? data.headers : [];
        } catch (error) {
            state.requiredHeaders = [];
            setFeedback(error.message, 'error');
        }
    }

    // Fügt eine neue Teilprüfung hinzu, nachdem die Signalliste geprüft wurde
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
        if (!state.requiredHeaders.length) {
            setFeedback('Erforderliche Spaltenüberschriften konnten nicht geladen werden.', 'error');
            return;
        }
        try {
            const signalliste = await uploadSignalliste(file);
            const headers = Array.isArray(signalliste.headers) ? signalliste.headers : [];
            const missingHeaders = state.requiredHeaders.filter((header) => headers.indexOf(header) === -1);
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

    // Speichert die aktuelle Konfiguration 
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

    // Löscht die aktuelle Konfiguration
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

    // Namensänderung
    function handleNameChange(event) {
        state.current.name = event.target.value;
        renderConfigList();
    }

    // Aktualisiert das Label des Datei-Uploads mit dem Dateinamen
    function handleFileLabel() {
        if (!elements.fileInput || !elements.fileLabel) return;
        const file = elements.fileInput.files && elements.fileInput.files[0];
        elements.fileLabel.textContent = file ? file.name : 'Excel-Datei auswählen';
    }

    // Registriert alle relevanten Event-Handler
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

    // Initialisiert die Seite
    async function init() {
        registerEvents();
        renderConfigList();
        renderSteps();
        await loadRequiredHeaders();
        loadConfigList();
    }

    document.addEventListener('DOMContentLoaded', init);
})();
