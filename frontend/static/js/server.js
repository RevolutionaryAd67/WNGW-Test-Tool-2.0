/*
    Verwaltet die Signalliste, die auf der Seite "Server" hochgeladen wird
*/

(function () {
    const elements = {
        fileInput: document.getElementById('server-signallist-file'),
        fileLabel: document.getElementById('server-signallist-label'),
        fileName: document.getElementById('server-signallist-name'),
        status: document.getElementById('server-signallist-status'),
        saveButton: document.getElementById('server-signallist-save'),
    };

    const ENDPOINT = '/api/einstellungen/server/signalliste';
    const DEFAULT_LABEL = 'Excel-Datei auswählen';
    const DEFAULT_NAME = '–';

    // Aktualisiert den Statusbereich mit Text und optionmalem Zustand (success/error/pending)
    function setStatus(text, state) {
        if (!elements.status) return;
        elements.status.textContent = text || '';
        if (state) {
            elements.status.dataset.state = state;
        } else {
            delete elements.status.dataset.state;
        }
    }

    // Setzt den Dateinamen in der Anzeige oder den Standardplatzhalter, falls kein Name vorhanden ist
    function updateFileName(name) {
        if (elements.fileName) {
            elements.fileName.textContent = name || DEFAULT_NAME;
        }
    }

    // Leert das Datei-Input-Feld und stellt das ursprüngliche Label wieder her
    function resetFileInput() {
        if (elements.fileInput) {
            elements.fileInput.value = '';
        }
        if (elements.fileLabel) {
            elements.fileLabel.textContent = DEFAULT_LABEL;
        }
    }

    // Lädt eine bereits gespeicherte Signalliste vom Server und zeigt deren Dateinamen an
    async function loadExisting() {
        try {
            const response = await fetch(ENDPOINT);
            const payload = await response.json();
            if (!response.ok || payload.status === 'error') {
                throw new Error(payload.message || 'Fehler beim Laden der Signalliste.');
            }
            if (payload.status === 'success' && payload.signalliste) {
                updateFileName(payload.signalliste.filename || DEFAULT_NAME);
            } else {
                updateFileName(DEFAULT_NAME);
            }
        } catch (error) {
            console.error(error);
            setStatus(error.message, 'error');
        }
    }

    // Reagiert auf Änderungen im Datei-Input und spiegelt den ausgewählten Dateinamen im Label wider 
    function handleFileChange() {
        if (!elements.fileInput) return;
        const file = elements.fileInput.files && elements.fileInput.files[0];
        const name = file ? file.name : DEFAULT_LABEL;
        if (elements.fileLabel) {
            elements.fileLabel.textContent = name;
        }
    }

    // Übermittelt die ausgewählte Signalliste an den Server, validiert Rückmeldungen und aktualisiert die Oberfläche
    async function handleSave() {
        if (!elements.fileInput || !elements.saveButton) return;
        const file = elements.fileInput.files && elements.fileInput.files[0];
        if (!file) {
            setStatus('Bitte wählen Sie eine Signalliste aus.', 'error');
            return;
        }
        const formData = new FormData();
        formData.append('signalliste', file);
        setStatus('Speichern …', 'pending');
        elements.saveButton.disabled = true;
        try {
            const response = await fetch(ENDPOINT, {
                method: 'POST',
                body: formData,
            });
            const payload = await response.json();
            if (!response.ok || payload.status !== 'success') {
                throw new Error(payload.message || 'Speichern fehlgeschlagen.');
            }
            const savedName = payload.signalliste && payload.signalliste.filename;
            updateFileName(savedName || file.name);
            resetFileInput();
            setStatus('Gespeichert', 'success');
        } catch (error) {
            console.error(error);
            setStatus(error.message, 'error');
        } finally {
            elements.saveButton.disabled = false;
        }
    }

    // Initialisiert das Skript nach dem Laden des DOMs und registriert alle benötigten Event Listener
    document.addEventListener('DOMContentLoaded', () => {
        loadExisting();
        if (elements.fileInput) {
            elements.fileInput.addEventListener('change', handleFileChange);
        }
        if (elements.saveButton) {
            elements.saveButton.addEventListener('click', handleSave);
        }
    });
})();
