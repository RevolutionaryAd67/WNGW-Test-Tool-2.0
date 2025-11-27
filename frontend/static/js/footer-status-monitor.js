/* 
    Dieses Skript verwaltet die Statusanzeige von Client und Server im Footer.
    Durch dieses Skript werden die Verbindungszustände automatisch synchron gehalten.                
                
    Statusanzeigen:
    - Grün: Wenn Client/Server eine aktive TCP-Verbindung hat
    - Rot: Wenn Client/Server keine aktive TCP-Verbindung hat
*/

(function () {
  // Datenquelle vom Backend: REST-Endpunkt, über den der initiale Status geladen wird
  const STATUS_ENDPOINT = '/api/backend/status';  // Wie ist der Zustand jetzt?
  // Datenquelle vom Backend: Server-Sent-Events-Endpunkt für die kontinuierliche Statusübertragung
  const STREAM_ENDPOINT = '/api/backend/stream';  // Sag sofort Bescheid, wenn sich der Status ändert!
  // Datenquelle für den Status des aktuellen Prüfungsdurchlaufs
  const EXAM_STATUS_ENDPOINT = '/api/pruefungslauf/status';
  // Cache der DOM-Elemente, die einzelne Statusanzeigen repräsentieren
  const statusElements = {};
  // DOM-Element für den Prüfungsstatus
  let examStatusElement = null;
  // DOM-Element für den Link zur laufenden Prüfung
  let examLinkElement = null;
  // Referenz auf die aktuelle EventSource, um sie steuern zu können
  let footerStatusSource = null;
  // Timer-Handle für erneute Verbindungsversuche nach Fehlern
  let reconnectTimer = null;
  // Timer-Handle für die zyklische Abfrage des Prüfungsstatus
  let examStatusTimer = null;

  // Liest alle relevanten DOM-Elemente ein und speichert sie im Cache
  function cacheFooterStatusElements() {
    const nodes = document.querySelectorAll('[data-footer-status]');
    nodes.forEach((node) => {
      const key = node.dataset.footerStatus;
      if (key) {
        statusElements[key] = node;
      }
    });
    examStatusElement = document.querySelector('[data-footer-exam-status]');
    examLinkElement = document.querySelector('[data-footer-exam-link]');
    return (
      Object.keys(statusElements).length > 0 ||
      Boolean(examStatusElement) ||
      Boolean(examLinkElement)
    );
  }

  // Schaltet den optischen Zustand eines Status-Elemenmts anhand der Verbindung 
  // (Ändert die Anzeige eines Statuspunktes)
  function setFooterStatus(side, connected) {
    const element = statusElements[side];
    if (!element) {
      return;
    }
    element.classList.toggle('footer-status__item--active', connected);
    element.classList.toggle('footer-status__item--inactive', !connected);
  }

  // Überträgt eine Snapshot-Antwort auf alle bekannten DOM-Elemente
  // (Wenn das Backend beim Start ein "Status-Paket" schickt, wird dieses komplett übernommen)
  function applyStatusSnapshot(snapshot) {
    if (!snapshot || typeof snapshot !== 'object') {
      return;
    }
    Object.keys(statusElements).forEach((side) => {
      const connected = Boolean(snapshot[side] && snapshot[side].connected);
      setFooterStatus(side, connected);
    });
  }

  // Holt den Status initial einmal per Fetch und setzt die Anzeige entsprechend
  // (Beim Starten der Seite wird der aktuelle Status vom Backend abgefragt)
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

  // Verarbeitet eingehende SSE-Nachrichten und setzt Statusänderungen um
  // (Verarbeitung von Live-Nachrichten aus dem Stream)
  // (Wenn das Backend einen Status meldet setzt das Skript die richtige Farbe)
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

  // Baut den SSE-Stream auf und behandelt Fehler mit automatischen Reconnect
  // (Browser verbindet sich mit dem Backend-Stream)
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

  // Setzt den angezeigten Prüfungsstatus im Footer
  function setExamStatus(runState) {
    if (!examStatusElement) {
      return;
    }
    examStatusElement.textContent = '';
    examStatusElement.classList.remove(
      'footer-status__exam-value--running',
      'footer-status__exam-value--finished'
    );
    if (examLinkElement) {
      examLinkElement.hidden = true;
    }
    if (!runState) {
      return;
    }
    if (runState.finished) {
      examStatusElement.textContent = 'Abgeschlossen';
      examStatusElement.classList.add('footer-status__exam-value--finished');
    } else {
      examStatusElement.textContent = 'Läuft';
      examStatusElement.classList.add('footer-status__exam-value--running');
      if (examLinkElement) {
        examLinkElement.hidden = false;
      }
    }
  }

  // Holt den aktuellen Prüfungsstatus ab
  async function fetchExamStatus() {
    if (!examStatusElement) {
      return;
    }
    try {
      const response = await fetch(EXAM_STATUS_ENDPOINT);
      if (!response.ok) {
        throw new Error('HTTP ' + response.status);
      }
      const data = await response.json();
      setExamStatus(data.run);
    } catch (error) {
      console.warn('Konnte Prüfungsstatus nicht laden', error);
    }
  }

  // Startet die regelmäßige Abfrage des Prüfungsstatus
  function startExamStatusPolling() {
    if (examStatusTimer || !examStatusElement) {
      return;
    }
    examStatusTimer = window.setInterval(fetchExamStatus, 2000);
  }

  // Einsteigspunkt: Cache füllen, initialen Status laden und Stream öffnen
  // (Startknopf: Statusanzeige-Elemente suchen, Anfangsstatus laden, Live-Stream öffnen)
  function initFooterStatusMonitor() {
    if (!cacheFooterStatusElements()) {
      return;
    }
    fetchFooterStatusSnapshot();
    connectFooterStatusStream();
    fetchExamStatus();
    startExamStatusPolling();
  }

  // Auf DOM-Bereitschaft warten, falls nötig
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFooterStatusMonitor);
  } else {
    initFooterStatusMonitor();
  }

  // Beim Verlassen der Seite offene Verbindungen und Timer aufräumen
  window.addEventListener('beforeunload', () => {
    if (footerStatusSource) {
      footerStatusSource.close();
    }
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
    }
    if (examStatusTimer) {
      clearInterval(examStatusTimer);
    }
  });
})();
