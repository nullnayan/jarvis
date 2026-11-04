// FILE: app.js
// Builds the 3D Holographic Globe scene, wires UI controls, and coordinates state testing.
import { createScene } from './scene/create-scene.js';
import { createGlobeScene } from './scene/globe.js';
import { createBloom } from './scene/bloom.js';
import { createStateMachine } from './state-machine.js';
import { startAnimation } from './animate.js';
import { createCaption } from './ui/caption.js';
import { createSubtitle } from './ui/subtitle.js';
import { createPromptBox } from './ui/prompt-box.js';
import { createStopButton } from './ui/stop-button.js';
import { createMicButton } from './ui/mic-button.js';
import { createTtsButton } from './ui/tts-button.js';
import { createWindowControls } from './ui/window-controls.js';
import { setRealAmplitude } from './audio-reactive.js';
import { COLORS, UI, setActivePersona } from './constants.js';
import { createGestureController } from './gesture-controller.js';

const canvas = document.querySelector('#orb-canvas');
const stage = createScene(canvas);
const machine = createStateMachine();
const globe = createGlobeScene();
stage.scene.add(globe.root);
const pipeline = createBloom(stage.renderer, stage.scene, stage.camera);
const gestureController = createGestureController(window.jarvisGlobe);

const caption = createCaption(document.querySelector('#caption-text'));
let demoTimers = [];
const subtitle = createSubtitle(document.querySelector('#subtitle-user'), document.querySelector('#subtitle-jarvis'));
let isFullscreen = false;
const getFullscreenState = () => isFullscreen;

const setState = (state) => {
  machine.setState(state);
  const color = COLORS[state] || COLORS.idle;
  document.documentElement.style.setProperty('--orb-color', color.sphere || color.primary);
  stop.update(state);
};

window.addEventListener('resize', () => {
  stage.resize();
  const width = window.innerWidth;
  const height = window.innerHeight;
  pipeline.composer.setSize(width, height);
  pipeline.bloom.setSize(width, height);
});

const cancel = () => {
  demoTimers.forEach(clearTimeout);
  demoTimers = [];
  window.jarvis?.cancelAction();
  // A user-initiated stop is not an error: settle straight back to idle.
  setState('idle');
};

const stop = createStopButton(document.querySelector('#stop-btn'), cancel);
createMicButton(document.querySelector('#mic-btn'));
createTtsButton(document.querySelector('#tts-btn'));
createWindowControls(document.querySelector('#window-controls'));

const promptInput = document.querySelector('#prompt-input');
createPromptBox(promptInput, (text) => {
  window.jarvis?.sendCommand(text);
});

window.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    if (isFullscreen) {
      event.preventDefault();
      event.stopPropagation();
      window.jarvis?.exitFullscreen();
      return;
    }
    cancel();
    return;
  }

  // Ignore demo state shortcuts while the user is typing in the prompt box.
  if (event.target instanceof HTMLElement && (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA')) return;

  const states = machine.states;
  if (/^[1-6]$/.test(event.key)) setState(states[Number(event.key) - 1]);
}, { capture: true });

window.jarvis?.onFullscreenChange((fullscreen) => {
  isFullscreen = !!fullscreen;
  gestureController.setFullscreen(isFullscreen);
  document.body.classList.toggle('is-fullscreen', isFullscreen);
  stage.resize();
  pipeline.composer.setSize(window.innerWidth, window.innerHeight);
  pipeline.bloom.setSize(window.innerWidth, window.innerHeight);
});

window.jarvis?.onHandGesture((gestureData) => {
  gestureController.onGestureData(gestureData);
});

window.jarvis?.onStateChange(setState);

window.jarvis?.onCaption((text) => {
  caption.setText(text);
});

window.jarvis?.onAmplitude(setRealAmplitude);

window.jarvis?.onUserSpeech((text) => {
  subtitle.showUser(text);
});

window.jarvis?.onJarvisSpeech((text) => {
  subtitle.showJarvis(text);
});

window.jarvis?.onHiddenChange((hidden) => {
  document.body.classList.toggle('is-hidden', hidden);
  if (hidden) { caption.setText(''); subtitle.clear(); }
});

window.jarvis?.onBackendStatus((status) => {
  const indicator = document.querySelector('#backend-status');
  const offline = status !== 'online';
  indicator.classList.toggle('is-hidden', !offline);
  document.body.classList.toggle('backend-offline', offline);
});

const approvalPanel = document.querySelector('#approval-panel');
const approvalDiff = document.querySelector('#approval-diff');
let approvalPath = null;
window.jarvis?.onApprovalRequest((request) => {
  const file = request.files?.[0];
  approvalPath = file?.path || null;
  approvalDiff.textContent = file ? `${file.path}\n\n${file.diff}` : 'No diff available.';
  approvalPanel.classList.remove('is-hidden');
});
document.querySelector('#approval-yes').addEventListener('click', () => { window.jarvis?.sendApproval(true); approvalPanel.classList.add('is-hidden'); });
document.querySelector('#approval-no').addEventListener('click', () => { window.jarvis?.sendApproval(false); approvalPanel.classList.add('is-hidden'); });
document.querySelector('#approval-open').addEventListener('click', () => { if (approvalPath) window.jarvis?.openFile(approvalPath); });
window.addEventListener('keydown', (event) => {
  if (approvalPanel.classList.contains('is-hidden')) return;
  // Never trigger approval shortcuts while the user is typing in a text field.
  if (event.target instanceof HTMLElement && (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA')) return;
  if (event.key.toLowerCase() === 'y') { window.jarvis?.sendApproval(true); approvalPanel.classList.add('is-hidden'); }
  if (event.key.toLowerCase() === 'n') { window.jarvis?.sendApproval(false); approvalPanel.classList.add('is-hidden'); }
});
window.jarvis?.onSelfAudit((findings) => {
  const panel = document.querySelector('#audit-panel');
  document.querySelector('#audit-findings').textContent = findings.map((f) => `${f.severity}: ${f.file}:${f.line} — ${f.title}`).join('\n') || 'No findings.';
  panel.classList.remove('is-hidden');
});

// Plan-progress: show which step is executing; hide when plan finishes
let _planHideTimer = null;
window.jarvis?.onPlanProgress((data) => {
  const panel = document.querySelector('#plan-progress-panel');
  const txt = document.querySelector('#plan-progress-text');
  if (!panel || !txt) return;
  if (data && data.step != null) {
    txt.textContent = `Step ${data.step} / ${data.total} — ${data.status || ''}`;
    panel.classList.remove('is-hidden');
    clearTimeout(_planHideTimer);
    if (data.step >= data.total) {
      _planHideTimer = setTimeout(() => panel.classList.add('is-hidden'), 3000);
    }
  }
});

// Permission-request: brief toast when a tool action is denied
let _permHideTimer = null;
window.jarvis?.onPermissionRequest((data) => {
  const toast = document.querySelector('#permission-toast');
  if (!toast) return;
  toast.textContent = `⛔ ${data?.tool || 'Action'} not permitted`;
  toast.classList.remove('is-hidden');
  clearTimeout(_permHideTimer);
  _permHideTimer = setTimeout(() => toast.classList.add('is-hidden'), 4000);
});

const settingsPanel = document.querySelector('#settings-panel');
document.querySelector('#settings-toggle').addEventListener('click', () => {
  const hidden = settingsPanel.classList.toggle('is-hidden');
  if (!hidden) window.jarvis?.getSettings();
});
document.querySelector('#settings-close').addEventListener('click', () => settingsPanel.classList.add('is-hidden'));
document.querySelector('#settings-save').addEventListener('click', () => {
  settingsPanel.querySelectorAll('[data-setting]').forEach((input) => {
    if (input.value.trim()) window.jarvis?.setSetting(input.dataset.setting, input.value.trim());
  });
  settingsPanel.classList.add('is-hidden');
});
window.jarvis?.onSettingsValues((values) => {
  settingsPanel.querySelectorAll('[data-setting]').forEach((input) => {
    const v = values?.[input.dataset.setting];
    if (v !== undefined && v !== null) input.value = v;
  });
});

// Clicking the mini badge (shrunken window) restores the full UI
document.querySelector('#mini-badge').addEventListener('click', () => {
  if (document.body.classList.contains('is-hidden')) window.jarvis?.restoreWindow();
});

window.jarvis?.onPersonaChange((persona) => {
  setActivePersona(persona);
  machine.setState(machine.getState(), true);
  const activeColor = COLORS[machine.getState()] || COLORS.idle;
  document.documentElement.style.setProperty('--orb-color', activeColor.sphere || activeColor.primary);
  caption.setText(persona === 'ultron' ? 'ULTRON ACTIVE' : 'JARVIS ONLINE');
  const badge = document.querySelector('#mini-badge');
  if (badge) badge.textContent = persona === 'ultron' ? 'U' : 'J';
});

// Phone Link Panel
const phonePanel = document.querySelector('#phone-panel');
const phoneStatusLine = document.querySelector('#phone-status-line');
document.querySelector('#phone-toggle')?.addEventListener('click', () => {
  phonePanel?.classList.toggle('is-hidden');
});
document.querySelector('#phone-close')?.addEventListener('click', () => phonePanel?.classList.add('is-hidden'));
document.querySelector('#phone-connect-btn')?.addEventListener('click', () => {
  const host = document.querySelector('#phone-host')?.value?.trim();
  const port = document.querySelector('#phone-port')?.value?.trim();
  const code = document.querySelector('#phone-code')?.value?.trim();
  window.jarvis?.sendPhoneConnect(host, port, code);
});
document.querySelector('#phone-disconnect-btn')?.addEventListener('click', () => {
  window.jarvis?.sendPhoneDisconnect();
});
document.querySelector('#phone-mirror-btn')?.addEventListener('click', () => {
  window.jarvis?.sendPhoneMirror('start');
});
document.querySelector('#phone-screencap-btn')?.addEventListener('click', () => {
  window.jarvis?.sendPhoneScreencap(true);
});
window.jarvis?.onPhoneStatus((data) => {
  if (phoneStatusLine && data) {
    phoneStatusLine.textContent = data.state === 'connected' ? `Connected: ${data.device || 'Android'}` : 'Disconnected';
  }
});

console.log('WebSocket backend connects when available; 3D Globe running.');
startAnimation(globe, pipeline, machine, getFullscreenState);
