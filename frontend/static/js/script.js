(function () {
    const MAX_ENTRIES = 20;

    function createMonitorState() {
        return {
            incomingCount: 0,
            outgoingCount: 0,
            lastTimestamp: {
                incoming: null,
                outgoing: null,
            },
        };
    }

    const monitorStates = {
        client: createMonitorState(),
        server: createMonitorState(),
    };

    function formatTimestamp(timestamp) {
        const date = new Date(timestamp * 1000);
        const pad = (value, size = 2) => String(value).padStart(size, '0');
        return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}.${pad(date.getMilliseconds(), 3)}`;
    }

    function formatDelta(current, previous) {
        if (!previous) {
            return '';
        }
        const delta = current - previous;
        return `(d = ${delta.toFixed(3)} s)`;
    }

    function formatEndpoint(endpoint) {
        if (!endpoint) {
            return '0.0.0.0:0';
        }
        const ip = endpoint.ip || '0.0.0.0';
        const port = endpoint.port ?? endpoint.station_address ?? '0';
        return `${ip}:${port}`;
    }

    function formatIoa(ioaValues) {
        const values = Array.isArray(ioaValues) ? ioaValues.slice(0, 3) : [0, 0, 0];
        while (values.length < 3) {
            values.push(0);
        }
        return values
            .map((value) => String(value).padStart(3, ' '))
            .join('-     ')
            .trim();
    }

    function label(text) {
        return text.padEnd(15, ' ');
    }

    function frameTitle(frame) {
        if (frame.type === 'U') {
            return frame.command || 'U-FRAME';
        }
        if (frame.type === 'S') {
            return `S-ACK ${frame.seq}`;
        }
        const payload = frame.payload || {};
        return payload.description || payload.label || 'I-FRAME';
    }

    function frameTypeText(frame) {
        if (frame.type === 'I') {
            const typeId = frame.asdu?.type_id ?? 0;
            return `${typeId} (I-Format)`;
        }
        if (frame.type === 'S') {
            return '(S-Format)';
        }
        return '(U-Format)';
    }

    function causeText(frame) {
        const cause = frame.asdu?.cause || {};
        const activation = cause.activation ?? 6;
        const origin = cause.origin ?? 11;
        return `Aktivierung = ${activation}      Herkunft = ${origin}`;
    }

    function stationText(frame) {
        return frame.asdu?.station_address || '0';
    }

    function buildFrameBlock(direction, frame, index, deltaText) {
        const timestamp = frame.timestamp || Date.now() / 1000;
        const timeLine = `${label('Time')}:     ${formatTimestamp(timestamp)} ${deltaText}`.trimEnd();
        const arrow = direction === 'outgoing' ? '\u2192' : '\u2190';
        const source = frame.routing?.source || {};
        const destination = frame.routing?.destination || {};
        const leftEndpoint = direction === 'outgoing' ? formatEndpoint(source) : formatEndpoint(destination);
        const rightEndpoint = direction === 'outgoing' ? formatEndpoint(destination) : formatEndpoint(source);
        const ipLine = `${label('IP:Port')}:     ${leftEndpoint}     ${arrow}     ${rightEndpoint}`;
        const lines = [];
        lines.push(`${String(index).padEnd(18, ' ')}:     ${frameTitle(frame)}`);
        lines.push(timeLine);
        lines.push('');
        lines.push(ipLine);
        lines.push('');
        lines.push(`${label('Typ')}:     ${frameTypeText(frame)}`);
        if (frame.type === 'I') {
            lines.push(`${label('Ursache')}:    ${causeText(frame)}`);
            lines.push(`${label('Station')}:    ${stationText(frame)}`);
            const ioa = frame.asdu?.ioa || [0, 0, 0];
            lines.push(`${label('IOA')}:     ${formatIoa(ioa)}`);
        }
        return lines.join('\n');
    }

    function prependEntry(list, entry) {
        const emptyPlaceholder = list.querySelector('.comm-list__empty');
        if (emptyPlaceholder) {
            emptyPlaceholder.remove();
        }
        list.prepend(entry);
        while (list.children.length > MAX_ENTRIES) {
            list.removeChild(list.lastElementChild);
        }
    }

    function addFrame(direction, frame, list, monitorState) {
        const counterKey = direction === 'incoming' ? 'incomingCount' : 'outgoingCount';
        monitorState[counterKey] += 1;
        const index = monitorState[counterKey];
        const timestamp = frame.timestamp || Date.now() / 1000;
        const lastTs = monitorState.lastTimestamp[direction];
        const deltaText = formatDelta(timestamp, lastTs);
        monitorState.lastTimestamp[direction] = timestamp;
        const item = document.createElement('li');
        item.className = `comm-entry comm-entry--${direction}`;
        item.textContent = buildFrameBlock(direction, frame, index, deltaText);
        prependEntry(list, item);
    }

    function connectWebSocket(url, handlers) {
        let socket;
        function connect() {
            socket = new WebSocket(url);
            socket.addEventListener('message', (event) => {
                handlers.onMessage(event);
            });
            socket.addEventListener('close', () => {
                setTimeout(connect, 3000);
            });
            socket.addEventListener('error', () => {
                socket.close();
            });
        }
        connect();
        return () => socket && socket.close();
    }

    function initChannelMonitor({
        monitorSelector,
        incomingSelector,
        outgoingSelector,
        wsPath,
        stateKey,
    }) {
        const monitor = document.querySelector(monitorSelector);
        if (!monitor) {
            return;
        }
        const incomingList = monitor.querySelector(incomingSelector);
        const outgoingList = monitor.querySelector(outgoingSelector);
        const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const url = `${protocol}://${window.location.host}${wsPath}`;
        const monitorState = monitorStates[stateKey];
        connectWebSocket(url, {
            onMessage(event) {
                try {
                    const data = JSON.parse(event.data);
                    if (data.type !== 'frame' || !data.frame) {
                        return;
                    }
                    if (data.direction === 'incoming') {
                        addFrame('incoming', data.frame, incomingList, monitorState);
                    } else if (data.direction === 'outgoing') {
                        addFrame('outgoing', data.frame, outgoingList, monitorState);
                    }
                } catch (err) {
                    console.error('Fehler beim Verarbeiten eines WebSocket-Frames', err);
                }
            },
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        if (window.WNGW?.observeMonitorEnabled) {
            initChannelMonitor({
                monitorSelector: '[data-client-monitor]',
                incomingSelector: '[data-client-incoming]',
                outgoingSelector: '[data-client-outgoing]',
                wsPath: '/ws/client',
                stateKey: 'client',
            });
            initChannelMonitor({
                monitorSelector: '[data-server-monitor]',
                incomingSelector: '[data-server-incoming]',
                outgoingSelector: '[data-server-outgoing]',
                wsPath: '/ws/server',
                stateKey: 'server',
            });
        }
    });
})();
