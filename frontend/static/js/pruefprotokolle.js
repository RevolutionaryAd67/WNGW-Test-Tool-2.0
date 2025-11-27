(function () {
    const state = {
        protocols: [],
        currentId: null,
        currentProtocol: null,
    };

    const elements = {
        list: document.getElementById('protocol-list'),
        title: document.getElementById('selected-protocol-name'),
        tableBody: document.querySelector('#protocol-table tbody'),
        deleteButton: document.getElementById('delete-protocol'),
    };

    function getProtocolIdFromUrl() {
        const params = new URLSearchParams(window.location.search);
        const value = params.get('protocolId');
        return value ? value.trim() : null;
    }

    function renderProtocolList() {
        if (!elements.list) return;
        elements.list.innerHTML = '';
        const sorted = [...state.protocols].sort(
            (a, b) => (b.finishedAt || 0) - (a.finishedAt || 0)
        );
        sorted.forEach((protocol) => {
            const item = document.createElement('li');
            item.className = 'config-list__item';
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'config-list__button';
            button.textContent = protocol.displayName || protocol.name || 'Unbenanntes Protokoll';
            if (state.currentId === protocol.id) {
                button.classList.add('config-list__button--active');
            }
            button.addEventListener('click', () => loadProtocol(protocol.id));
            item.appendChild(button);
            elements.list.appendChild(item);
        });
        if (!state.currentId && sorted.length) {
            loadProtocol(sorted[0].id);
        } else if (!sorted.length) {
            updateSelection(null);
        }
    }

    function renderTable(protocol) {
        if (!elements.tableBody) return;
        elements.tableBody.innerHTML = '';
        if (!protocol) {
            const row = document.createElement('tr');
            row.className = 'protocol-table__empty';
            const cell = document.createElement('td');
            cell.colSpan = 4;
            cell.textContent = 'Bitte ein Prüfprotokoll auswählen.';
            row.appendChild(cell);
            elements.tableBody.appendChild(row);
            return;
        }
        const rows = Array.isArray(protocol.teilpruefungen) ? protocol.teilpruefungen : [];
        if (!rows.length) {
            const row = document.createElement('tr');
            row.className = 'protocol-table__empty';
            const cell = document.createElement('td');
            cell.colSpan = 4;
            cell.textContent = 'Keine Teilprüfungen vorhanden.';
            row.appendChild(cell);
            elements.tableBody.appendChild(row);
            return;
        }
        rows.forEach((teil) => {
            const row = document.createElement('tr');

            const indexCell = document.createElement('td');
            indexCell.textContent = teil.index != null ? String(teil.index) : '';
            row.appendChild(indexCell);

            const typeCell = document.createElement('td');
            typeCell.textContent = teil.pruefungsart || '';
            row.appendChild(typeCell);

            const statusCell = document.createElement('td');
            statusCell.textContent = teil.status || '';
            row.appendChild(statusCell);

            const actionCell = document.createElement('td');
            if (teil.logFile && state.currentId) {
                const link = document.createElement('a');
                link.className = 'protocol-action';
                link.href = `/api/pruefprotokolle/${encodeURIComponent(state.currentId)}/teilpruefungen/${encodeURIComponent(teil.index)}/log`;
                link.textContent = 'Prüfprotokoll ansehen >';
                link.setAttribute('download', '');
                actionCell.appendChild(link);
            }
            row.appendChild(actionCell);

            elements.tableBody.appendChild(row);
        });
    }

    function updateSelection(protocol) {
        state.currentProtocol = protocol;
        state.currentId = protocol ? protocol.id : null;
        if (elements.title) {
            elements.title.textContent = protocol ? protocol.name || 'Prüfprotokoll' : 'Prüfprotokoll auswählen';
        }
        if (elements.deleteButton) {
            elements.deleteButton.disabled = !protocol;
        }
        renderProtocolList();
        renderTable(protocol);
    }

    async function loadProtocolList() {
        try {
            const response = await fetch('/api/pruefprotokolle');
            if (!response.ok) throw new Error('Protokolle konnten nicht geladen werden.');
            const data = await response.json();
            state.protocols = data.protocols || [];
            const preferredId = getProtocolIdFromUrl();
            const hasPreferred = preferredId && state.protocols.some((protocol) => protocol.id === preferredId);
            const hasCurrent = state.currentId && state.protocols.some((protocol) => protocol.id === state.currentId);
            if (hasPreferred) {
                state.currentId = preferredId;
            } else if (!hasCurrent) {
                state.currentId = null;
            }
            renderProtocolList();
            const shouldLoadCurrent =
                state.currentId &&
                (!state.currentProtocol || state.currentProtocol.id !== state.currentId);
            if (shouldLoadCurrent) {
                await loadProtocol(state.currentId);
            }
        } catch (error) {
            console.error(error);
        }
    }

    async function loadProtocol(id) {
        if (!id) {
            updateSelection(null);
            return;
        }
        try {
            const response = await fetch(`/api/pruefprotokolle/${encodeURIComponent(id)}`);
            if (!response.ok) throw new Error('Protokoll konnte nicht geladen werden.');
            const data = await response.json();
            updateSelection(data.protocol || null);
        } catch (error) {
            console.error(error);
        }
    }

    async function init() {
        if (elements.deleteButton) {
            elements.deleteButton.addEventListener('click', deleteProtocol);
        }
        await loadProtocolList();
    }

    async function deleteProtocol() {
        if (!state.currentId) {
            return;
        }
        try {
            const response = await fetch(`/api/pruefprotokolle/${encodeURIComponent(state.currentId)}`, {
                method: 'DELETE',
            });
            if (!response.ok) {
                const error = await response.json().catch(() => ({ message: 'Löschen fehlgeschlagen.' }));
                throw new Error(error.message || 'Löschen fehlgeschlagen.');
            }
            state.currentId = null;
            state.currentProtocol = null;
            await loadProtocolList();
        } catch (error) {
            console.error(error);
        }
    }

    document.addEventListener('DOMContentLoaded', init);
})();
