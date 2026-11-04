// FILE: globe.js
// Creates a 3D glowing particle globe matching the reference video (Neural Stack Ultron/Jarvis globe).
// Features circular anti-aliased glow particles, Fibonacci sphere lattice, coordinate rings,
// floating stardust embers, and 3D gesture-ready rotation controls.

import * as THREE from 'three';
import { COLORS } from '../constants.js';

function createGlowSprite() {
  const canvas = document.createElement('canvas');
  canvas.width = 128;
  canvas.height = 128;
  const ctx = canvas.getContext('2d');
  const grad = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
  grad.addColorStop(0, 'rgba(255, 255, 255, 1)');
  grad.addColorStop(0.2, 'rgba(255, 255, 255, 0.95)');
  grad.addColorStop(0.45, 'rgba(255, 255, 255, 0.45)');
  grad.addColorStop(0.75, 'rgba(255, 255, 255, 0.12)');
  grad.addColorStop(1, 'rgba(255, 255, 255, 0)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 128, 128);
  const texture = new THREE.CanvasTexture(canvas);
  texture.generateMipmaps = true;
  return texture;
}

function createGlobeScene() {
  const glowTexture = createGlowSprite();
  const root = new THREE.Group();

  // 1. The 3D Rotating Globe Particle Shell (Fibonacci Sphere)
  const POINT_COUNT = 1800;
  const GLOBE_RADIUS = 1.28;
  const positions = new Float32Array(POINT_COUNT * 3);
  const basePositions = new Float32Array(POINT_COUNT * 3);
  const seeds = new Float32Array(POINT_COUNT);

  for (let i = 0; i < POINT_COUNT; i++) {
    const y = 1 - (i / (POINT_COUNT - 1)) * 2;
    const rad = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = i * 2.39996323; // Golden angle in radians

    const x = Math.cos(theta) * rad * GLOBE_RADIUS;
    const py = y * GLOBE_RADIUS;
    const z = Math.sin(theta) * rad * GLOBE_RADIUS;

    positions[i * 3] = x;
    positions[i * 3 + 1] = py;
    positions[i * 3 + 2] = z;

    basePositions[i * 3] = x;
    basePositions[i * 3 + 1] = py;
    basePositions[i * 3 + 2] = z;

    seeds[i] = Math.random() * Math.PI * 2;
  }

  const globeGeo = new THREE.BufferGeometry();
  globeGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  globeGeo.userData = { base: basePositions, seeds };

  const globeMat = new THREE.PointsMaterial({
    map: glowTexture,
    size: 0.052,
    color: new THREE.Color(COLORS.idle.primary || '#00d4ff'),
    blending: THREE.AdditiveBlending,
    transparent: true,
    opacity: 0.95,
    depthWrite: false,
  });

  const globePoints = new THREE.Points(globeGeo, globeMat);
  root.add(globePoints);

  // 2. Coordinate Latitude / Longitude Rings
  const ringsGroup = new THREE.Group();

  function makeRing(radius, yPos, rotX = 0, rotY = 0) {
    const segments = 96;
    const ringGeo = new THREE.BufferGeometry();
    const ringPos = new Float32Array((segments + 1) * 3);
    for (let i = 0; i <= segments; i++) {
      const a = (i / segments) * Math.PI * 2;
      ringPos[i * 3] = Math.cos(a) * radius;
      ringPos[i * 3 + 1] = yPos;
      ringPos[i * 3 + 2] = Math.sin(a) * radius;
    }
    ringGeo.setAttribute('position', new THREE.BufferAttribute(ringPos, 3));
    const ringMat = new THREE.LineBasicMaterial({
      color: new THREE.Color(COLORS.idle.primary || '#00d4ff'),
      transparent: true,
      opacity: 0.35,
      blending: THREE.AdditiveBlending,
    });
    const line = new THREE.Line(ringGeo, ringMat);
    line.rotation.x = rotX;
    line.rotation.y = rotY;
    ringsGroup.add(line);
    return line;
  }

  // Equator + Tropics
  const ringEquator = makeRing(GLOBE_RADIUS * 1.01, 0);
  const ringNorth = makeRing(GLOBE_RADIUS * 0.85, GLOBE_RADIUS * 0.52);
  const ringSouth = makeRing(GLOBE_RADIUS * 0.85, -GLOBE_RADIUS * 0.52);
  // Meridiens
  const ringMeridian1 = makeRing(GLOBE_RADIUS * 1.01, 0, Math.PI / 2, 0);
  const ringMeridian2 = makeRing(GLOBE_RADIUS * 1.01, 0, Math.PI / 2, Math.PI / 2);

  root.add(ringsGroup);

  // 3. Central Glowing Holographic Singularity
  const coreGeo = new THREE.SphereGeometry(0.35, 32, 32);
  const coreMat = new THREE.MeshBasicMaterial({
    color: new THREE.Color(COLORS.idle.primary || '#00d4ff'),
    transparent: true,
    opacity: 0.65,
    blending: THREE.AdditiveBlending,
  });
  const coreMesh = new THREE.Mesh(coreGeo, coreMat);
  root.add(coreMesh);

  const innerWhiteGeo = new THREE.SphereGeometry(0.16, 24, 24);
  const innerWhiteMat = new THREE.MeshBasicMaterial({
    color: 0xffffff,
    transparent: true,
    opacity: 0.95,
    blending: THREE.AdditiveBlending,
  });
  const innerWhiteMesh = new THREE.Mesh(innerWhiteGeo, innerWhiteMat);
  root.add(innerWhiteMesh);

  // 4. Outer Drifting Cosmic Stardust Embers (As seen in Neural Stack video)
  const DUST_COUNT = 450;
  const dustPositions = new Float32Array(DUST_COUNT * 3);
  const dustSeeds = new Float32Array(DUST_COUNT);
  const dustSpeeds = new Float32Array(DUST_COUNT);

  for (let i = 0; i < DUST_COUNT; i++) {
    const r = 1.45 + Math.random() * 1.35;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    dustPositions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
    dustPositions[i * 3 + 1] = r * Math.cos(phi);
    dustPositions[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta);
    dustSeeds[i] = Math.random() * Math.PI * 2;
    dustSpeeds[i] = 0.0008 + Math.random() * 0.0016;
  }

  const dustGeo = new THREE.BufferGeometry();
  dustGeo.setAttribute('position', new THREE.BufferAttribute(dustPositions, 3));
  dustGeo.userData = { seeds: dustSeeds, speeds: dustSpeeds };

  const dustMat = new THREE.PointsMaterial({
    map: glowTexture,
    size: 0.045,
    color: new THREE.Color(COLORS.idle.glow || '#00f0ff'),
    blending: THREE.AdditiveBlending,
    transparent: true,
    opacity: 0.75,
    depthWrite: false,
  });
  const dustPoints = new THREE.Points(dustGeo, dustMat);
  root.add(dustPoints);

  // 5. 3D Orientation & Gesture Movement State
  const gestureState = {
    targetRotation: { x: 0, y: 0, z: 0 },
    currentRotation: { x: 0, y: 0, z: 0 },
    targetPosition: { x: 0, y: 0, z: 0 },
    currentPosition: { x: 0, y: 0, z: 0 },
    targetScale: 1.0,
    currentScale: 1.0,
    pinchFactor: 1.0, // 0 = fully pinched, 1 = normal/open
    currentPinch: 1.0,
    spreadFactor: 0.0, // 0 = normal, 1 = maximum spread
    currentSpread: 0.0,
    gestureActive: false,
    autoSpin: true,
  };

  // Expose on window for gesture connection
  window.jarvisGlobe = {
    setTargetRotation: (rx, ry, rz = 0) => {
      gestureState.targetRotation.x = rx;
      gestureState.targetRotation.y = ry;
      gestureState.targetRotation.z = rz;
    },
    setTargetPosition: (x, y, z = 0) => {
      gestureState.targetPosition.x = x;
      gestureState.targetPosition.y = y;
      gestureState.targetPosition.z = z;
    },
    setTargetScale: (s) => {
      gestureState.targetScale = Math.max(0.4, Math.min(3.0, s));
    },
    setPinchFactor: (p) => {
      gestureState.pinchFactor = Math.max(0, Math.min(1, p));
    },
    setSpreadFactor: (s) => {
      gestureState.spreadFactor = Math.max(0, Math.min(1, s));
    },
    setGestureActive: (active) => {
      gestureState.gestureActive = !!active;
      if (!active) {
        // Smoothly return to center
        gestureState.targetPosition.x = 0;
        gestureState.targetPosition.y = 0;
        gestureState.targetPosition.z = 0;
        gestureState.targetScale = 1.0;
        gestureState.pinchFactor = 1.0;
        gestureState.spreadFactor = 0.0;
        gestureState.autoSpin = true;
      }
    },
    setAutoSpin: (enabled) => {
      gestureState.autoSpin = !!enabled;
    },
    getGroup: () => root,
  };

  // Optional mouse parallax when gesture tracking is not actively driving the orb
  window.addEventListener('mousemove', (e) => {
    if (gestureState.gestureActive) return;
    const nx = (e.clientX / window.innerWidth) * 2 - 1;
    const ny = -(e.clientY / window.innerHeight) * 2 + 1;
    gestureState.targetRotation.y = nx * 0.6;
    gestureState.targetRotation.x = -ny * 0.45;
  });

  // 6. Update function called each frame
  function update(time, amplitude, colors, state, fullscreenFactor = 0) {
    const primaryColor = new THREE.Color(colors.primary || colors.sphere || '#00d4ff');
    const glowColor = new THREE.Color(colors.glow || colors.primary || '#00f0ff');

    globeMat.color.lerp(primaryColor, 0.08);
    dustMat.color.lerp(glowColor, 0.08);
    coreMat.color.lerp(primaryColor, 0.08);
    ringsGroup.children.forEach((r) => r.material.color.lerp(primaryColor, 0.08));

    // Smooth position interpolation
    const posLerp = 0.08;
    gestureState.currentPosition.x += (gestureState.targetPosition.x - gestureState.currentPosition.x) * posLerp;
    gestureState.currentPosition.y += (gestureState.targetPosition.y - gestureState.currentPosition.y) * posLerp;
    gestureState.currentPosition.z += (gestureState.targetPosition.z - gestureState.currentPosition.z) * posLerp;
    root.position.set(gestureState.currentPosition.x, gestureState.currentPosition.y, gestureState.currentPosition.z);

    // Smooth 3D Gesture Rotation interpolation
    const lerpSpeed = 0.08;
    gestureState.currentRotation.x += (gestureState.targetRotation.x - gestureState.currentRotation.x) * lerpSpeed;
    gestureState.currentRotation.y += (gestureState.targetRotation.y - gestureState.currentRotation.y) * lerpSpeed;
    gestureState.currentRotation.z += (gestureState.targetRotation.z - gestureState.currentRotation.z) * lerpSpeed;

    const baseSpin = gestureState.autoSpin ? time * 0.0007 : 0;
    root.rotation.x = gestureState.currentRotation.x;
    root.rotation.y = baseSpin + gestureState.currentRotation.y;
    root.rotation.z = gestureState.currentRotation.z;

    // Counter-rotate coordinate rings
    ringsGroup.rotation.y = -time * 0.0004;

    // Smooth pinch & spread physics
    gestureState.currentPinch += (gestureState.pinchFactor - gestureState.currentPinch) * 0.08;
    gestureState.currentSpread += (gestureState.spreadFactor - gestureState.currentSpread) * 0.08;

    const pinchInv = 1.0 - gestureState.currentPinch; // 1 when pinched, 0 when open
    const spreadVal = gestureState.currentSpread;

    // Ring opacity responds dynamically to pinch & spread
    const dynamicRingOpacity = 0.35 + pinchInv * 0.35 + spreadVal * 0.25;
    ringsGroup.children.forEach((r) => {
      r.material.opacity = dynamicRingOpacity;
    });

    // Pulse central core (compresses into intense singularity on pinch, disperses on spread)
    const coreScale = (1.0 + Math.sin(time * 0.004) * 0.12 + amplitude * 0.45 + fullscreenFactor * 0.25) *
      (1.0 + pinchInv * 0.5 - spreadVal * 0.2);
    coreMesh.scale.setScalar(coreScale);
    coreMat.opacity = 0.65 + pinchInv * 0.3;
    innerWhiteMesh.scale.setScalar((1.0 + amplitude * 0.35) * (1.0 + pinchInv * 0.6));

    // Dynamic shell radius offset from pinch & spread
    // Pinch contracts shell by up to 18%; Spread expands shell by up to 25%
    const shellRadialFactor = 1.0 - pinchInv * 0.18 + spreadVal * 0.25;

    // Wave ripples on globe surface
    const gPositions = globeGeo.attributes.position;
    const gBase = globeGeo.userData.base;
    const gSeeds = globeGeo.userData.seeds;
    const waveAmp = (0.04 + amplitude * 0.18) * (state === 'thinking' ? 2.0 : 1.0);
    const waveSpeed = time * 0.003 * (state === 'thinking' ? 2.5 : 1.0);

    for (let i = 0; i < POINT_COUNT; i++) {
      const idx = i * 3;
      const seed = gSeeds[i];
      const disp = (1.0 + Math.sin(waveSpeed + seed * 3.0) * waveAmp) * shellRadialFactor;
      gPositions.array[idx] = gBase[idx] * disp;
      gPositions.array[idx + 1] = gBase[idx + 1] * disp;
      gPositions.array[idx + 2] = gBase[idx + 2] * disp;
    }
    gPositions.needsUpdate = true;

    // Drifting ambient stardust embers (spread expands drifting radius)
    const dPositions = dustGeo.attributes.position;
    const dSeeds = dustGeo.userData.seeds;
    const dSpeeds = dustGeo.userData.speeds;
    const vortexAngle = time * (0.0003 + spreadVal * 0.0006);
    const cosV = Math.cos(vortexAngle);
    const sinV = Math.sin(vortexAngle);
    const dustExpansion = 1.0 + spreadVal * 0.35;

    for (let i = 0; i < DUST_COUNT; i++) {
      const idx = i * 3;
      const seed = dSeeds[i];
      const spd = dSpeeds[i];
      const dy = Math.sin(time * spd + seed) * 0.004;
      dPositions.array[idx + 1] += dy;

      const px = dPositions.array[idx] * (1.0 + (dustExpansion - 1.0) * 0.01);
      const pz = dPositions.array[idx + 2] * (1.0 + (dustExpansion - 1.0) * 0.01);
      dPositions.array[idx] = px * cosV - pz * sinV;
      dPositions.array[idx + 2] = px * sinV + pz * cosV;
    }
    dustGeo.attributes.position.needsUpdate = true;

    // Smooth overall scale (combines fullscreen factor with hand depth scale)
    const scaleLerp = 0.06;
    gestureState.currentScale += (gestureState.targetScale - gestureState.currentScale) * scaleLerp;
    const totalScale = (1.0 + fullscreenFactor * 0.28) * gestureState.currentScale;
    root.scale.setScalar(totalScale);
  }

  return { root, update };
}

export { createGlobeScene };
