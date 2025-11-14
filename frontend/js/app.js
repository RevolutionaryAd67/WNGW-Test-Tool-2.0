import { initNavigation } from './navigation.js';
import { initWebSockets } from './websocket.js';
import { initClientView } from './client_view.js';
import { initServerView } from './server_view.js';
import { initSettings } from './settings.js';
import { initTests } from './tests.js';
import { initLogs } from './logs.js';

export const AppState = {
  activeView: 'home',
  observe: {
    clientVisible: true,
    serverVisible: true,
    autoScroll: true,
    syncScroll: false,
    clientSequence: 0,
    serverSequence: 0,
  },
  testing: {
    activeRun: null,
  },
};

document.addEventListener('DOMContentLoaded', () => {
  initNavigation(AppState);
  initClientView(AppState);
  initServerView(AppState);
  initSettings(AppState);
  initTests(AppState);
  initLogs(AppState);
  initWebSockets(AppState);
});
