// FILE: state-machine.js
// Defines valid orb states and exposes smoothly interpolated visual state values.
import { COLORS, TRANSITION_DURATION } from './constants.js';

function parseColor(str) {
  if (!str) return [0, 212, 255, 1];
  if (str.startsWith('#')) {
    let hex = str.slice(1);
    if (hex.length === 3) hex = hex.split('').map(x => x + x).join('');
    const n = parseInt(hex, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255, 1];
  }
  const m = str.match(/rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)/);
  if (m) return [Number(m[1]), Number(m[2]), Number(m[3]), m[4] !== undefined ? Number(m[4]) : 1];
  return [0, 212, 255, 1];
}

function lerpColor(c1, c2, t) {
  const [r1, g1, b1, a1] = parseColor(c1);
  const [r2, g2, b2, a2] = parseColor(c2);
  const r = Math.round(r1 + (r2 - r1) * t);
  const g = Math.round(g1 + (g2 - g1) * t);
  const b = Math.round(b1 + (b2 - b1) * t);
  const a = +(a1 + (a2 - a1) * t).toFixed(3);
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}

const STATES = Object.keys(COLORS);
function createStateMachine() {
  let current = 'idle';
  let started = performance.now();
  let from = COLORS.idle;
  const target = () => COLORS[current];

  const setState = (next, force = false) => {
    if (STATES.includes(next) && (force || next !== current)) {
      from = getVisuals();
      current = next;
      started = performance.now();
    }
  };

  const getVisuals = () => {
    const progress = Math.min((performance.now() - started) / TRANSITION_DURATION, 1);
    const eased = progress * (2 - progress);
    const to = target();
    return {
      primary: lerpColor(from.primary, to.primary, eased),
      secondary: lerpColor(from.secondary, to.secondary, eased),
      glow: lerpColor(from.glow, to.glow, eased),
      aura: lerpColor(from.aura, to.aura, eased),
      sphere: lerpColor(from.sphere || from.primary, to.sphere || to.primary, eased),
    };
  };

  return { setState, getVisuals, getState: () => current, states: STATES };
}
export { createStateMachine };
