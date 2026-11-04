// FILE: stop-button.js
// Controls stop-button visibility and sends the cancel action when clicked.
function createStopButton(button, onCancel) {
  button.addEventListener('click', onCancel);
  const update = (state) => button.classList.toggle('is-active', ['thinking', 'speaking', 'confirming'].includes(state));
  return { update };
}
export { createStopButton };
