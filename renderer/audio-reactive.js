// FILE: audio-reactive.js
// Produces smooth simulated audio amplitude until real microphone data is available.
let realAmplitude = null;
let amplitudeTimeout;
function setRealAmplitude(value) {
  realAmplitude = Math.min(Math.max(Number(value) || 0, 0), 1);
  clearTimeout(amplitudeTimeout);
  amplitudeTimeout = setTimeout(() => { realAmplitude = null; }, 200);
}
function getAmplitude(state, time) {
  if (realAmplitude !== null) return realAmplitude;
  if (state === 'listening') return 0.22 + Math.sin(time * 0.006) * 0.16 + Math.sin(time * 0.017) * 0.09;
  if (state === 'speaking') return 0.3 + Math.abs(Math.sin(time * 0.014)) * 0.42;
  if (state === 'thinking') return 0.16 + Math.abs(Math.sin(time * 0.009)) * 0.2;
  return 0.04 + Math.sin(time * 0.002) * 0.025;
}
export { getAmplitude, setRealAmplitude };
