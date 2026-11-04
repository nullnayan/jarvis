// FILE: prompt-box.js
// Handles prompt submission, focus behavior, and text clearing for the overlay input.
function createPromptBox(input, onSubmit) {
  input.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter') return; const text = input.value.trim(); if (!text) return;
    input.value = ''; input.blur(); onSubmit(text);
  });
  return { focus: () => input.focus(), clear: () => { input.value = ''; } };
}
export { createPromptBox };
