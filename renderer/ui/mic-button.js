// FILE: mic-button.js
// Toggles microphone on/off and updates button visual state.
function createMicButton(button) {
  let muted = false;
  button.addEventListener('click', () => {
    muted = !muted;
    button.classList.toggle('is-muted', muted);
    button.textContent = muted ? '🔇' : '🎤';
    window.jarvis?.toggleMic(muted);
  });
  return { isMuted: () => muted };
}
export { createMicButton };
