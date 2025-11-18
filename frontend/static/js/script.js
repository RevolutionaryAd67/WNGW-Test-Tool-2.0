(function () {
  const STATUS_ENDPOINT = '/api/backend/status';
  const STREAM_ENDPOINT = '/api/backend/stream';
  const statusElements = {};
  let footerStatusSource = null;
  let reconnectTimer = null;

  function cacheFooterStatusElements() {
    const nodes = document.querySelectorAll('[data-footer-status]');
    nodes.forEach((node) => {
      const key = node.dataset.footerStatus;
      if (key) {
        statusElements[key] = node;
      }
    });
    return Object.keys(statusElements).length > 0;
  }

  function setFooterStatus(side, connected) {
    const element = statusElements[side];
    if (!element) {
      return;
    }
    element.classList.toggle('footer-status__item--active', connected);
    element.classList.toggle('footer-status__item--inactive', !connected);
  }

  function applyStatusSnapshot(snapshot) {
    if (!snapshot || typeof snapshot !== 'object') {
      return;
    }
    Object.keys(statusElements).forEach((side) => {
      const connected = Boolean(snapshot[side] && snapshot[side].connected);
      setFooterStatus(side, connected);
    });
  }

  async function fetchFooterStatusSnapshot() {
    try {
      const response = await fetch(STATUS_ENDPOINT);
      if (!response.ok) {
        throw new Error('HTTP ' + response.status);
      }
      const snapshot = await response.json();
      applyStatusSnapshot(snapshot);
    } catch (error) {
      console.warn('Konnte Status nicht laden', error);
    }
  }

  function handleStreamEvent(event) {
    if (!event || !event.data) {
      return;
    }
    try {
      const payload = JSON.parse(event.data);
      if (payload.type === 'status' && payload.payload) {
        const side = payload.payload.side;
        if (side) {
          setFooterStatus(side, Boolean(payload.payload.connected));
        }
      }
    } catch (error) {
      console.warn('Unbekannte Nachricht im Status-Stream', error);
    }
  }

  function connectFooterStatusStream() {
    if (footerStatusSource) {
      footerStatusSource.close();
    }
    footerStatusSource = new EventSource(STREAM_ENDPOINT);
    footerStatusSource.onmessage = handleStreamEvent;
    footerStatusSource.onerror = () => {
      if (footerStatusSource) {
        footerStatusSource.close();
      }
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
      }
      reconnectTimer = window.setTimeout(connectFooterStatusStream, 3000);
    };
  }

  function initFooterStatusMonitor() {
    if (!cacheFooterStatusElements()) {
      return;
    }
    fetchFooterStatusSnapshot();
    connectFooterStatusStream();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFooterStatusMonitor);
  } else {
    initFooterStatusMonitor();
  }

  window.addEventListener('beforeunload', () => {
    if (footerStatusSource) {
      footerStatusSource.close();
    }
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
    }
  });
})();
