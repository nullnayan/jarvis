// FILE: main.js
// Starts the always-on-top Jarvis Electron window and receives renderer IPC stubs.
const { app, BrowserWindow, ipcMain } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const crypto = require('crypto');
const WebSocket = require('ws');
const OPEN_INTENT_VERBS = require('./shared/open_intent.json');

let windowRef;
let pythonSocket;
let supervisorProcess;
let reconnectAttempts = 0;
let isQuitting = false;
let reconnectTimer;
let DOT_SIZE = 48;
const WINDOW = { width: 300, height: 340, minWidth: 180, minHeight: 200, maxWidth: 900, maxHeight: 1080, step: 50 };
const PYTHON_URL = 'ws://127.0.0.1:8765';
const LOCAL_AUTH_TOKEN = process.env.JARVIS_LOCAL_AUTH_TOKEN || crypto.randomBytes(32).toString('hex');
const RECONNECT_DELAY = 2000;

let isFullscreenMode = false;
let savedBoundsBeforeFullscreen = null;
let savedPosition = null;

function displayForWindow() {
  const { screen } = require('electron');
  const point = windowRef && !windowRef.isDestroyed()
    ? windowRef.getBounds()
    : screen.getCursorScreenPoint();
  return screen.getDisplayNearestPoint({ x: point.x, y: point.y });
}

function sendToPython(message) {
  if (pythonSocket?.readyState === WebSocket.OPEN) pythonSocket.send(JSON.stringify(message));
}

function isOpenIntent(text) {
  if (!text || typeof text !== 'string') return false;
  if (/gesture|hand tracking/i.test(text)) return false;
  const normalized = text.trim().toLowerCase();
  return OPEN_INTENT_VERBS.some((verb) => new RegExp(`\\b${verb}\\b`, 'i').test(normalized));
}

function connectToPython() {
  pythonSocket = new WebSocket(PYTHON_URL, { headers: { Authorization: `Bearer ${LOCAL_AUTH_TOKEN}` } });
  pythonSocket.on('open', () => {
    reconnectAttempts = 0;
    console.log('Connected to Python backend');
    windowRef?.webContents.send('backend-status', 'online');
  });
  pythonSocket.on('message', (raw) => {
    try {
      const message = JSON.parse(raw);

      // Clean application shutdown request from Python backend
      if (message.type === 'app_exit' || message.type === 'quit') {
        if (windowRef && !windowRef.isDestroyed()) {
          windowRef.close();
        }
        app.quit();
        return;
      }

      // Explicit dodge or open app intent: immediately exit fullscreen to corner if in fullscreen
      if (message.type === 'dodge' || message.type === 'shrink_to_corner' || message.type === 'open_app_intent') {
        if (windowRef && !windowRef.isDestroyed()) {
          if (isFullscreenMode) {
            exitFullscreen(true);
          } else {
            savedPosition = windowRef.getPosition();
            const { screen } = require('electron');
            const display = displayForWindow();
            const { x: dx, y: dy, width: dw, height: dh } = display.workArea;
            const targetPos = message.value === 'top-left'
              ? [dx + 20, dy + 20]
              : [dx + dw - WINDOW.width - 20, dy + dh - WINDOW.height - 20];
            windowRef.setPosition(targetPos[0], targetPos[1], true);
          }
        }
        return;
      }

      if (message.type === 'undodge') {
        if (windowRef && !windowRef.isDestroyed()) {
          if (savedPosition) {
            windowRef.setPosition(savedPosition[0], savedPosition[1], true);
            savedPosition = null;
          } else {
            const { screen } = require('electron');
            const display = displayForWindow();
            const { x: dx, y: dy, width: dw } = display.workArea;
            const wx = dx + dw - WINDOW.width - 20;
            const wy = dy + 8;
            windowRef.setPosition(Math.max(dx, wx), Math.max(dy, wy), true);
          }
        }
        return;
      }

      if (message.type === 'minimize' || message.type === 'window_minimize') {
        if (windowRef && !windowRef.isDestroyed()) {
          windowRef.minimize();
        }
        return;
      }

      if (message.type === 'restore' || message.type === 'window_restore') {
        if (windowRef && !windowRef.isDestroyed()) {
          windowRef.restore();
        }
        return;
      }

      if (message.type === 'shrink_to_dot' || message.type === 'hide_orb') {
        if (windowRef && !windowRef.isDestroyed()) {
          if (isFullscreenMode) exitFullscreen(false);
          savedPosition = windowRef.getBounds();
          const { screen } = require('electron');
          const { x: dx, y: dy, width: dw } = displayForWindow().workArea;
          windowRef.setMinimumSize(0, 0);
          windowRef.setBounds({ x: dx + dw - DOT_SIZE - 10, y: dy + 8, width: DOT_SIZE, height: DOT_SIZE });
          windowRef.webContents.send('set-hidden', true);
        }
        return;
      }

      if (message.type === 'restore_orb') {
        if (windowRef && !windowRef.isDestroyed()) {
          windowRef.setMinimumSize(WINDOW.minWidth, WINDOW.minHeight);
          if (savedPosition) {
            windowRef.setBounds(savedPosition);
          } else {
            const { screen } = require('electron');
            const { x: dx, y: dy, width: dw } = displayForWindow().workArea;
            windowRef.setBounds({ x: dx + dw - WINDOW.width - 20, y: dy + 8, width: WINDOW.width, height: WINDOW.height });
          }
          windowRef.webContents.send('set-hidden', false);
        }
        return;
      }

      // If in fullscreen and an open/launch task is detected in speech/caption, auto-shrink to corner
      if (windowRef && !windowRef.isDestroyed() && isFullscreenMode) {
        if ((message.type === 'user_speech' || message.type === 'command' || message.type === 'caption' || message.type === 'jarvis_speech') && isOpenIntent(message.value)) {
          exitFullscreen(true);
        }
      }

      // Hand gesture tracking data stream
      if (message.type === 'hand_gesture') {
        if (windowRef && !windowRef.isDestroyed()) {
          windowRef.webContents.send('hand-gesture', message.value);
        }
        return;
      }

      // Voice-controlled fullscreen mode toggle for 3D gestures
      if (message.type === 'fullscreen_toggle') {
        if (message.value) {
          enterFullscreen();
        } else {
          exitFullscreen(false);
        }
        return;
      }

      const channel = {
        state: 'state-change',
        caption: 'set-caption',
        amplitude: 'set-amplitude',
        persona: 'persona-change',
        user_speech: 'user-speech',
        jarvis_speech: 'jarvis-speech',
        approval_request: 'approval-request',
        self_audit: 'self-audit',
        plan_progress: 'plan-progress',
        permission_request: 'permission-request',
        settings_values: 'settings-values',
        phone_status: 'phone-status'
      }[message.type];

      if (channel && windowRef && !windowRef.isDestroyed()) {
        windowRef.webContents.send(channel, message.value);
      }
    } catch (error) {
      console.error('Invalid Python message:', error.message);
    }
  });

  pythonSocket.on('error', (error) => console.warn('Python socket:', error.message));
  pythonSocket.on('close', () => {
    if (isQuitting) return;
    reconnectAttempts += 1;
    windowRef?.webContents.send('backend-status', 'reconnecting');
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(connectToPython, Math.min(30000, RECONNECT_DELAY * (2 ** Math.min(reconnectAttempts, 4))));
  });
}

function startSupervisor() {
  if (supervisorProcess) return;
  const python = path.join(__dirname, 'backend', '.venv', 'Scripts', 'python.exe');
  supervisorProcess = spawn(python, ['supervisor.py'], {
    cwd: path.join(__dirname, 'backend'), windowsHide: true,
    env: { ...process.env, JARVIS_LOCAL_AUTH_TOKEN: LOCAL_AUTH_TOKEN }
  });
  supervisorProcess.on('exit', () => { supervisorProcess = null; });
}

function createWindow() {
  const { screen } = require('electron');
  windowRef = new BrowserWindow({
    width: WINDOW.width,
    height: WINDOW.height,
    minWidth: WINDOW.minWidth,
    minHeight: WINDOW.minHeight,
    maxWidth: WINDOW.maxWidth,
    maxHeight: WINDOW.maxHeight,
    title: 'Jarvis',
    frame: false,
    alwaysOnTop: true,
    resizable: true,
    skipTaskbar: false,
    transparent: true,
    backgroundColor: '#00000000',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });

  // Center window on the primary display work area
  const display = displayForWindow();
  const { x: dx, y: dy, width: dw, height: dh } = display.workArea;
  const wx = dx + Math.round((dw - WINDOW.width) / 2);
  const wy = dy + Math.round((dh - WINDOW.height) / 2);
  windowRef.setPosition(wx, wy);

  windowRef.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  windowRef.webContents.on('will-navigate', (event) => event.preventDefault());
  windowRef.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  windowRef.setAlwaysOnTop(true, 'floating');

  // Intercept Escape key at webContents input level
  windowRef.webContents.on('before-input-event', (event, input) => {
    if (input.key === 'Escape' && input.type === 'keyDown') {
      if (isFullscreenMode) {
        event.preventDefault();
        exitFullscreen(false);
      }
    }
  });

  connectToPython();
}

function enterFullscreen() {
  if (!windowRef || windowRef.isDestroyed() || isFullscreenMode) return;
  isFullscreenMode = true;
  savedBoundsBeforeFullscreen = windowRef.getBounds();

  const { screen, globalShortcut } = require('electron');
  const display = displayForWindow();

  windowRef.setResizable(true);
  windowRef.setMinimumSize(0, 0);
  windowRef.setMaximumSize(10000, 10000);
  windowRef.setBounds(display.bounds);

  try { windowRef.setFullScreen(true); } catch (e) {}

  windowRef.setAlwaysOnTop(true, 'screen-saver');
  windowRef.focus();
  windowRef.webContents.focus();

  // Register OS-level Escape global shortcut while in fullscreen
  try { globalShortcut.unregister('Escape'); } catch (e) {}
  try {
    globalShortcut.register('Escape', () => {
      if (isFullscreenMode) {
        exitFullscreen(false);
      }
    });
  } catch (e) {
    console.error('Failed to register global Escape shortcut:', e);
  }

  windowRef.webContents.send('set-fullscreen-mode', true);
  sendToPython({ type: 'gesture_control', value: 'start' });
}

function exitFullscreen(toCorner = false) {
  if (!windowRef || windowRef.isDestroyed() || !isFullscreenMode) return;
  isFullscreenMode = false;

  sendToPython({ type: 'gesture_control', value: 'stop' });

  const { screen, globalShortcut } = require('electron');
  try { globalShortcut.unregister('Escape'); } catch (e) {}
  try { windowRef.setFullScreen(false); } catch (e) {}

  windowRef.setResizable(true);
  windowRef.setMaximumSize(WINDOW.maxWidth, WINDOW.maxHeight);
  windowRef.setMinimumSize(WINDOW.minWidth, WINDOW.minHeight);

  const display = displayForWindow();
  const { x: dx, y: dy, width: dw, height: dh } = display.workArea;

  if (toCorner) {
    // Dock to bottom-right corner with 20px padding
    const targetX = dx + dw - WINDOW.width - 20;
    const targetY = dy + dh - WINDOW.height - 20;
    windowRef.setBounds({ x: targetX, y: targetY, width: WINDOW.width, height: WINDOW.height });
  } else if (savedBoundsBeforeFullscreen && savedBoundsBeforeFullscreen.width <= WINDOW.maxWidth && savedBoundsBeforeFullscreen.height <= WINDOW.maxHeight) {
    windowRef.setBounds(savedBoundsBeforeFullscreen);
    savedBoundsBeforeFullscreen = null;
  } else {
    // Center window on screen
    const targetX = dx + Math.round((dw - WINDOW.width) / 2);
    const targetY = dy + Math.round((dh - WINDOW.height) / 2);
    windowRef.setBounds({ x: targetX, y: targetY, width: WINDOW.width, height: WINDOW.height });
  }

  windowRef.setAlwaysOnTop(true, 'floating');
  windowRef.webContents.send('set-fullscreen-mode', false);
}

app.whenReady().then(() => { startSupervisor(); createWindow(); });

app.on('window-all-closed', () => {
  isQuitting = true;
  clearTimeout(reconnectTimer);
  if (pythonSocket) {
    try { pythonSocket.close(); } catch (e) {}
  }
  if (supervisorProcess) {
    try { supervisorProcess.kill(); } catch (e) {}
  }
  const { globalShortcut } = require('electron');
  try { globalShortcut.unregisterAll(); } catch (e) {}
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

ipcMain.on('command', (_event, text) => {
  if (isFullscreenMode && isOpenIntent(text)) {
    exitFullscreen(true);
  }
  sendToPython({ type: 'command', value: text });
});

ipcMain.on('cancel-action', () => sendToPython({ type: 'cancel' }));
ipcMain.on('approval-response', (_event, approved) => sendToPython({ type: 'command', value: approved ? 'approve' : 'reject' }));
ipcMain.on('open-source-file', (_event, relPath) => {
  if (typeof relPath !== 'string' || path.isAbsolute(relPath) || relPath.includes('..')) return;
  spawn('code', [path.join(__dirname, relPath)], { windowsHide: true });
});
ipcMain.on('settings-set', (_event, key, value) => sendToPython({ type: 'settings', key, value }));
ipcMain.on('settings-get', () => sendToPython({ type: 'settings-get' }));
ipcMain.on('toggle-mic', (_event, muted) => sendToPython({ type: 'mic-toggle', value: muted }));
ipcMain.on('toggle-tts', (_event, muted) => sendToPython({ type: 'tts-toggle', value: muted }));
ipcMain.on('phone-connect', (_event, host, port, code) => {
  const parts = ['connect to my phone'];
  if (host) parts.push(host);
  if (port) parts.push(port);
  if (code) parts.push(code);
  sendToPython({ type: 'command', value: parts.join(' ') });
});
ipcMain.on('phone-disconnect', () => sendToPython({ type: 'command', value: 'disconnect from my phone' }));
ipcMain.on('phone-mirror', (_event, action) => sendToPython({ type: 'command', value: action === 'stop' ? 'stop mirroring' : 'mirror my phone' }));
ipcMain.on('phone-screencap', () => sendToPython({ type: 'command', value: "what's on my phone" }));
ipcMain.on('window-minimize', () => windowRef?.minimize());

ipcMain.on('window-hide', () => {
  if (!windowRef) return;
  if (isFullscreenMode) exitFullscreen(false);
  const { screen } = require('electron');
  const { x: dx, y: dy, width: dw } = displayForWindow().workArea;
  DOT_SIZE = 48;
  windowRef.setMinimumSize(0, 0);
  windowRef.setResizable(true);
  windowRef.setBounds({ x: dx + dw - DOT_SIZE, y: dy + 8, width: DOT_SIZE, height: DOT_SIZE });
  windowRef.setResizable(false);
  windowRef.webContents.send('set-hidden', true);
});

ipcMain.on('window-restore', () => {
  if (!windowRef) return;
  const { screen } = require('electron');
  const { x: dx, y: dy, width: dw } = displayForWindow().workArea;
  windowRef.setResizable(true);
  windowRef.setMinimumSize(WINDOW.minWidth, WINDOW.minHeight);
  windowRef.setBounds({ x: dx + dw - WINDOW.width, y: dy + 8, width: WINDOW.width, height: WINDOW.height });
  windowRef.webContents.send('set-hidden', false);
});

ipcMain.on('window-close', () => windowRef?.close());
ipcMain.on('enter-fullscreen', () => enterFullscreen());
ipcMain.on('exit-fullscreen', () => exitFullscreen(false));
ipcMain.on('exit-fullscreen-to-corner', () => exitFullscreen(true));
ipcMain.on('toggle-fullscreen', () => {
  if (isFullscreenMode) {
    exitFullscreen(false);
  } else {
    enterFullscreen();
  }
});
