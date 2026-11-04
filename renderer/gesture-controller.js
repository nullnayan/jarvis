// FILE: gesture-controller.js
// Physics-based gesture smoothing and state machine for 3D globe hand tracking.
// Applies Exponential Moving Average (EMA) filtering, velocity inertia, and
// maps normalized hand landmarks to 3D spatial transforms.

import { GESTURE } from './constants.js';

export function createGestureController(globeAPI) {
  let isFullscreen = false;
  let currentState = 'idle'; // 'idle' | 'tracking' | 'grabbed' | 'released'

  // EMA smoothed values
  const smoothed = {
    x: 0,
    y: 0,
    yaw: 0,
    pitch: 0,
    roll: 0,
    scale: 1.0,
    pinch: 1.0,
    spread: 0.0,
  };

  // Inertia state for release / flick
  const inertia = {
    vx: 0,
    vy: 0,
    active: false,
  };

  let lastRawX = 0;
  let lastRawY = 0;
  let lastTime = performance.now();
  let animationFrameId = null;

  function ema(current, target, alpha) {
    return current + (target - current) * alpha;
  }

  function onGestureData(data) {
    if (!isFullscreen || !globeAPI) return;

    const now = performance.now();
    const dt = Math.max(0.001, (now - lastTime) / 1000);
    lastTime = now;

    if (!data || !data.detected) {
      if (currentState !== 'idle' && currentState !== 'released') {
        // Hand just left frame; check if flick inertia should trigger
        const speed = Math.hypot(inertia.vx, inertia.vy);
        if (speed > GESTURE.flickThreshold) {
          currentState = 'released';
          inertia.active = true;
        } else {
          resetToIdle();
        }
      }
      return;
    }

    globeAPI.setGestureActive(true);

    const rawX = typeof data.palm_x === 'number' ? data.palm_x : 0;
    const rawY = typeof data.palm_y === 'number' ? data.palm_y : 0;
    const rawYaw = typeof data.yaw === 'number' ? data.yaw : 0;
    const rawPitch = typeof data.pitch === 'number' ? data.pitch : 0;
    const rawRoll = typeof data.roll === 'number' ? data.roll : 0;
    const rawScale = typeof data.scale === 'number' ? data.scale : 1.0;
    const rawPinch = typeof data.pinch === 'number' ? data.pinch : 1.0;
    const rawSpread = typeof data.spread === 'number' ? data.spread : 0.0;

    // Track instant velocity for flick/inertia
    const deltaX = rawX - lastRawX;
    const deltaY = rawY - lastRawY;
    lastRawX = rawX;
    lastRawY = rawY;

    inertia.vx = deltaX / dt;
    inertia.vy = deltaY / dt;

    // Apply dead zone filtering to micro-movements
    const targetX = Math.abs(rawX - smoothed.x) < GESTURE.deadZone ? smoothed.x : rawX;
    const targetY = Math.abs(rawY - smoothed.y) < GESTURE.deadZone ? smoothed.y : rawY;

    // EMA smoothing
    const alpha = GESTURE.smoothing;
    smoothed.x = ema(smoothed.x, targetX, alpha);
    smoothed.y = ema(smoothed.y, targetY, alpha);
    smoothed.yaw = ema(smoothed.yaw, rawYaw, alpha);
    smoothed.pitch = ema(smoothed.pitch, rawPitch, alpha);
    smoothed.roll = ema(smoothed.roll, rawRoll, alpha);
    smoothed.scale = ema(smoothed.scale, rawScale, alpha);
    smoothed.pinch = ema(smoothed.pinch, rawPinch, alpha * 1.5);
    smoothed.spread = ema(smoothed.spread, rawSpread, alpha * 1.5);

    // State machine transitions
    if (smoothed.pinch < GESTURE.pinchThreshold) {
      currentState = 'grabbed';
      globeAPI.setAutoSpin(false);
    } else {
      currentState = 'tracking';
      globeAPI.setAutoSpin(false);
    }

    inertia.active = false;

    // Map coordinates to Three.js world space
    const worldX = smoothed.x * GESTURE.positionScaleX;
    const worldY = smoothed.y * GESTURE.positionScaleY;

    // Hand orientation tilts
    const rotX = -smoothed.pitch * GESTURE.rotationScale;
    const rotY = smoothed.yaw * GESTURE.rotationScale;
    const rotZ = -smoothed.roll * (GESTURE.rotationScale * 0.7);

    // Hand scale clamping
    const clampedScale = Math.max(GESTURE.scaleMin, Math.min(GESTURE.scaleMax, smoothed.scale));

    // Update globe via public API
    globeAPI.setTargetPosition(worldX, worldY, 0);
    globeAPI.setTargetRotation(rotX, rotY, rotZ);
    globeAPI.setTargetScale(clampedScale);
    globeAPI.setPinchFactor(smoothed.pinch);
    globeAPI.setSpreadFactor(smoothed.spread);
  }

  function resetToIdle() {
    currentState = 'idle';
    inertia.active = false;
    inertia.vx = 0;
    inertia.vy = 0;
    smoothed.x = 0;
    smoothed.y = 0;
    smoothed.yaw = 0;
    smoothed.pitch = 0;
    smoothed.roll = 0;
    smoothed.scale = 1.0;
    smoothed.pinch = 1.0;
    smoothed.spread = 0.0;

    if (globeAPI) {
      globeAPI.setGestureActive(false);
      globeAPI.setTargetPosition(0, 0, 0);
      globeAPI.setTargetRotation(0, 0, 0);
      globeAPI.setTargetScale(1.0);
      globeAPI.setPinchFactor(1.0);
      globeAPI.setSpreadFactor(0.0);
      globeAPI.setAutoSpin(true);
    }
  }

  // Physics animation loop for handling decaying inertia
  function updateInertiaLoop() {
    if (inertia.active && currentState === 'released' && globeAPI) {
      inertia.vx *= GESTURE.inertiaFriction;
      inertia.vy *= GESTURE.inertiaFriction;

      smoothed.yaw += inertia.vx * 0.02;
      smoothed.pitch += inertia.vy * 0.02;

      globeAPI.setTargetRotation(
        -smoothed.pitch * GESTURE.rotationScale,
        smoothed.yaw * GESTURE.rotationScale,
        0
      );

      if (Math.hypot(inertia.vx, inertia.vy) < 0.005) {
        resetToIdle();
      }
    }

    animationFrameId = requestAnimationFrame(updateInertiaLoop);
  }

  animationFrameId = requestAnimationFrame(updateInertiaLoop);

  return {
    onGestureData,
    setFullscreen: (full) => {
      isFullscreen = !!full;
      if (!isFullscreen) {
        resetToIdle();
      }
    },
    getState: () => currentState,
    reset: resetToIdle,
    destroy: () => {
      if (animationFrameId) cancelAnimationFrame(animationFrameId);
      resetToIdle();
    },
  };
}
