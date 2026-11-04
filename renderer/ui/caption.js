// FILE: caption.js
// Controls the caption typing animation and its delayed fade-out.
import { UI } from '../constants.js';
function createCaption(element) {
  let timer; let fadeTimer;
  const setText = (text) => {
    clearInterval(timer); clearTimeout(fadeTimer);
    const content = String(text ?? '').trim();
    if (!content) { element.textContent = ''; element.classList.add('is-hidden'); return; }
    element.textContent = ''; element.classList.remove('is-hidden'); let index = 0;
    timer = setInterval(() => { element.textContent += content[index] || ''; index += 1; if (index >= content.length) clearInterval(timer); }, 24);
    fadeTimer = setTimeout(() => element.classList.add('is-hidden'), UI.captionDelay);
  };
  const clear = () => { clearInterval(timer); clearTimeout(fadeTimer); element.classList.add('is-hidden'); };
  return { setText, clear };
}
export { createCaption };
