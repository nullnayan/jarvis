// FILE: subtitle.js
// Shows user speech and Jarvis responses as lightweight subtitles below the orb.
// Each line auto-fades after 5 seconds.

function createSubtitle(userEl, jarvisEl) {
  let userTimer = null;
  let jarvisTimer = null;
  const FADE_DELAY = 5000; // 5 seconds

  const showUser = (text) => {
    clearTimeout(userTimer);
    const content = String(text ?? '').trim();
    if (!content) { userEl.textContent = ''; userEl.classList.add('is-hidden'); return; }
    userEl.textContent = `"${content}"`;
    userEl.classList.remove('is-hidden');
    userTimer = setTimeout(() => userEl.classList.add('is-hidden'), FADE_DELAY);
  };

  const showJarvis = (text) => {
    clearTimeout(jarvisTimer);
    const content = String(text ?? '').trim();
    if (!content) { jarvisEl.textContent = ''; jarvisEl.classList.add('is-hidden'); return; }
    jarvisEl.textContent = content;
    jarvisEl.classList.remove('is-hidden');
    jarvisTimer = setTimeout(() => jarvisEl.classList.add('is-hidden'), FADE_DELAY);
  };

  const clear = () => {
    clearTimeout(userTimer);
    clearTimeout(jarvisTimer);
    userEl.classList.add('is-hidden');
    jarvisEl.classList.add('is-hidden');
  };

  return { showUser, showJarvis, clear };
}

export { createSubtitle };
