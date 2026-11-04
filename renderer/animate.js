// FILE: animate.js
// Runs the animation loop and coordinates 3D Globe visual updates.
import { getAmplitude } from './audio-reactive.js';
import { updateBloom } from './scene/bloom.js';

function startAnimation(globe, pipeline, machine, getFullscreenState = () => false) {
  let fullscreenFactor = 0;
  const tick = (time) => {
    const isFullscreen = getFullscreenState();
    const targetFullscreen = isFullscreen ? 1.0 : 0.0;
    fullscreenFactor += (targetFullscreen - fullscreenFactor) * 0.055;

    const state = machine.getState();
    const colors = machine.getVisuals();
    const amplitude = getAmplitude(state, time);

    globe.update(time, amplitude, colors, state, fullscreenFactor);
    updateBloom(pipeline, colors, fullscreenFactor);
    pipeline.composer.render();

    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

export { startAnimation };
