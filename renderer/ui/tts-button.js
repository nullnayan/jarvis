// FILE: tts-button.js
// Toggles Jarvis's voice (TTS) on/off independently of the microphone.
function createTtsButton(button) {
  let muted = false;
  button.addEventListener('click', () => {
    muted = !muted;
    button.classList.toggle('is-muted', muted);
    button.textContent = muted ? '🔇' : '🔊';
    window.jarvis?.toggleTts(muted);
  });
  return { isMuted: () => muted };
}
export { createTtsButton };
