/*
    Stellt die Logik für die Input-Boxen bereit
*/

(function () {

    // Verknüpft den Speichern-Button einer Input-Box mit dem Sammeln der Felder und anschließenden Speichern der Informationen
    function initInputBox(container) {
        const saveButton = container.querySelector('.input-box__save-btn');
        const statusField = container.querySelector('.input-box__status');
        if (!saveButton) {
            return;
        }

        // Sobald der Button geklickt wird, werden alle relevanten Eingabefelder gesammelt und als Objekt vorbereitet
        saveButton.addEventListener('click', async () => {
            const values = {};
            container.querySelectorAll('[data-row-id][data-column-key]').forEach((input) => {
                const rowId = input.getAttribute('data-row-id');
                const columnKey = input.getAttribute('data-column-key');
                if (!rowId || !columnKey) {
                    return;
                }
                if (!values[rowId]) {
                    values[rowId] = {};
                }
                values[rowId][columnKey] = input.value;
            });

            // Status auf "Speichern" setzen, bevor der Request ausgelöst wird
            setStatus(statusField, 'Speichern …', 'pending');
            try {
                const response = await fetch(container.dataset.saveUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        componentId: container.dataset.componentId,
                        pageKey: container.dataset.pageKey,
                        values,
                    }),
                });

                const payload = await response.json();
                if (!response.ok || payload.status !== 'success') {
                    throw new Error(payload.message || 'Speichern fehlgeschlagen.');
                }

                // Erfolgreiches Speichern melden
                setStatus(statusField, 'Gespeichert', 'success');
            } catch (error) {
                console.error(error);

                // Fehlerzustand anzeigen, falls der Request scheitert
                setStatus(statusField, 'Fehler beim Speichern', 'error');
            }
        });
    }

    // Aktualisiert den visuellen Status einer Input-Box
    function setStatus(element, text, state) {
        if (!element) {
            return;
        }
        element.textContent = text;
        element.dataset.state = state;
    }

    // Initialisiert alle Input-Box-Komponenten auf der Seite
    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('.input-box').forEach((box) => initInputBox(box));
    });
})();
