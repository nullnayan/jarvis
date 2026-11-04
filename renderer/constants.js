// FILE: constants.js
// All tunable values: colors, sizes, speeds, counts. Import from here, never hardcode.
// Two personas: jarvis (cyan/blue) and ultron (molten gold/amber as seen in Neural Stack video).

const PALETTES = {
  jarvis: {
    idle: { primary: '#00d4ff', secondary: '#0066cc', glow: '#00f0ff', aura: 'rgba(0, 180, 255, 0.22)', sphere: '#00d4ff', bloom: 0.85 },
    listening: { primary: '#00f5ff', secondary: '#0099ff', glow: '#66ffff', aura: 'rgba(0, 230, 255, 0.35)', sphere: '#00f5ff', bloom: 1.2 },
    thinking: { primary: '#00ffc8', secondary: '#009988', glow: '#33ffdd', aura: 'rgba(0, 255, 200, 0.35)', sphere: '#00ffc8', bloom: 1.4 },
    speaking: { primary: '#bbf2f6', secondary: '#00aaff', glow: '#ffffff', aura: 'rgba(120, 220, 255, 0.3)', sphere: '#bbf2f6', bloom: 1.1 },
    confirming: { primary: '#00b4d8', secondary: '#0055aa', glow: '#48cae4', aura: 'rgba(0, 160, 255, 0.25)', sphere: '#00b4d8', bloom: 0.95 },
    error: { primary: '#ff3344', secondary: '#aa0011', glow: '#ff0033', aura: 'rgba(255, 50, 50, 0.35)', sphere: '#ff3344', bloom: 1.6 },
  },
  ultron: {
    // Molten golden amber globe aesthetic matching reference video
    idle: { primary: '#ff9900', secondary: '#cc5500', glow: '#ffbb33', aura: 'rgba(255, 140, 0, 0.22)', sphere: '#ff9900', bloom: 0.85 },
    listening: { primary: '#ffbb00', secondary: '#ff7700', glow: '#ffdd55', aura: 'rgba(255, 180, 0, 0.35)', sphere: '#ffbb00', bloom: 1.2 },
    thinking: { primary: '#ff4400', secondary: '#cc2200', glow: '#ff6600', aura: 'rgba(255, 60, 0, 0.35)', sphere: '#ff4400', bloom: 1.4 },
    speaking: { primary: '#ffddaa', secondary: '#ff8800', glow: '#ffffff', aura: 'rgba(255, 200, 100, 0.3)', sphere: '#ffddaa', bloom: 1.1 },
    confirming: { primary: '#ff8800', secondary: '#cc4400', glow: '#ffaa33', aura: 'rgba(255, 130, 0, 0.25)', sphere: '#ff8800', bloom: 0.95 },
    error: { primary: '#ff1100', secondary: '#880000', glow: '#ff0000', aura: 'rgba(255, 0, 0, 0.35)', sphere: '#ff1100', bloom: 1.6 },
  },
};

export const COLORS = { ...PALETTES.jarvis };
export const setActivePersona = (persona) => {
  Object.assign(COLORS, PALETTES[persona] || PALETTES.jarvis);
};

export const BLOOM = { strength: 0.85, radius: 0.45, threshold: 0.22 };
export const CAMERA = { fov: 45, near: 0.1, far: 100, z: 4.2 };
export const FULLSCREEN = {
  scale: 1.28,
  bloom: { strengthMult: 1.3, radiusMult: 1.25 },
};
export const TRANSITION_DURATION = 450;
export const UI = { captionDelay: 5000, demoThinking: 2000, demoSpeaking: 2500 };

export const GESTURE = {
  smoothing: 0.12,
  positionScaleX: 2.4,
  positionScaleY: 1.8,
  rotationScale: 1.6,
  scaleMin: 0.55,
  scaleMax: 2.2,
  pinchThreshold: 0.28,
  spreadThreshold: 0.65,
  inertiaFriction: 0.94,
  deadZone: 0.012,
  flickThreshold: 0.07,
};
