(function () {
    const statusElement = document.getElementById('exam-settings-status');
    const saveButton = document.getElementById('exam-settings-save');
    const DEFAULT_LABEL = 'Excel-Datei auswählen';
    const DEFAULT_NAME = '–';

    function setStatus(text, state) {
        if (!statusElement) return;
        statusElement.textContent = text || '';
        if (state) {
            statusElement.dataset.state = state;
        } else {
            delete statusElement.dataset.state;
        }
    }

    function createUploader(config) {
        const elements = {
            fileInput: document.getElementById(config.selectors.fileInputId),
            fileLabel: document.getElementById(config.selectors.fileLabelId),
            fileName: document.getElementById(config.selectors.fileNameId),
        };

        function updateFileName(name) {
            if (elements.fileName) {
                elements.fileName.textContent = name || DEFAULT_NAME;
            }
        }

        function resetFileInput() {
            if (elements.fileInput) {
                elements.fileInput.value = '';
            }
            if (elements.fileLabel) {
                elements.fileLabel.textContent = DEFAULT_LABEL;
            }
        }

        async function loadExisting() {
            try {
                const response = await fetch(config.endpoints.get);
                const payload = await response.json();
                if (!response.ok || payload.status === 'error') {
                    throw new Error(payload.message || 'Fehler beim Laden der Datei.');
                }
                if (payload.status === 'success' && payload[config.key]) {
                    updateFileName(payload[config.key].filename || DEFAULT_NAME);
                } else {
                    updateFileName(DEFAULT_NAME);
                }
            } catch (error) {
                console.error(error);
                setStatus(error.message, 'error');
            }
        }

        function handleFileChange() {
            if (!elements.fileInput) return;
            const file = elements.fileInput.files && elements.fileInput.files[0];
            const name = file ? file.name : DEFAULT_LABEL;
            if (elements.fileLabel) {
                elements.fileLabel.textContent = name;
            }
        }

        async function saveIfNeeded() {
            if (!elements.fileInput) return false;
            const file = elements.fileInput.files && elements.fileInput.files[0];
            if (!file) return false;

            const formData = new FormData();
            formData.append(config.key, file);

            const response = await fetch(config.endpoints.post, {
                method: 'POST',
                body: formData,
            });
            const payload = await response.json();
            if (!response.ok || payload.status !== 'success') {
                throw new Error(payload.message || 'Speichern fehlgeschlagen.');
            }
            const savedName = payload[config.key] && payload[config.key].filename;
            updateFileName(savedName || file.name);
            resetFileInput();
            return true;
        }

        function hasPendingFile() {
            return Boolean(elements.fileInput && elements.fileInput.files && elements.fileInput.files[0]);
        }

        function bindEvents() {
            if (elements.fileInput) {
                elements.fileInput.addEventListener('change', handleFileChange);
            }
        }

        return {
            loadExisting,
            bindEvents,
            saveIfNeeded,
            hasPendingFile,
        };
    }

    const uploaders = [
        {
            key: 'signalliste',
            selectors: {
                fileInputId: 'exam-settings-file',
                fileLabelId: 'exam-settings-file-label',
                fileNameId: 'exam-settings-file-name',
            },
            endpoints: {
                get: '/api/einstellungen/pruefungseinstellungen/signalliste',
                post: '/api/einstellungen/pruefungseinstellungen/signalliste',
            },
        },
    ].map(createUploader);

    async function loadExistingFiles() {
        await Promise.all(uploaders.map((uploader) => uploader.loadExisting()));
    }

    async function handleSave() {
        if (!saveButton) return;
        const pendingUploads = uploaders
            .filter((uploader) => uploader.hasPendingFile())
            .map((uploader) => uploader.saveIfNeeded());

        if (pendingUploads.length === 0) {
            setStatus('Bitte wählen Sie mindestens eine Datei aus.', 'error');
            return;
        }

        setStatus('Speichern …', 'pending');
        saveButton.disabled = true;
        try {
            await Promise.all(pendingUploads);
            setStatus('Gespeichert', 'success');
        } catch (error) {
            console.error(error);
            setStatus(error.message, 'error');
        } finally {
            saveButton.disabled = false;
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        loadExistingFiles();
        uploaders.forEach((uploader) => uploader.bindEvents());
        if (saveButton) {
            saveButton.addEventListener('click', handleSave);
        }
    });
})();
