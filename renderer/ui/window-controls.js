// FILE: window-controls.js
// Wires the frameless-window buttons to secure Electron window control bridge actions.
function createWindowControls(container) {
  container.addEventListener('click', (event) => {
    const action = event.target.closest('button')?.dataset.action;
    if (action === 'hide') window.jarvis?.hideWindow();
    if (action === 'minimize') window.jarvis?.minimizeWindow();
    if (action === 'fullscreen') window.jarvis?.toggleFullscreen();
    if (action === 'close') window.jarvis?.closeWindow();
  });
}
export { createWindowControls };
