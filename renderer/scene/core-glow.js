// FILE: core-glow.js
// Creates the pulsing, additive inner glow at the center of the orb.
import * as THREE from 'three';
import { COLORS, CORE, FULLSCREEN } from '../constants.js';
function createCoreGlow() {
  const group = new THREE.Group();
  // Inner white-hot high-energy core
  const innerGeo = new THREE.SphereGeometry(CORE.radius * 0.45, 24, 24);
  const innerMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true,
    opacity: 0.85, blending: THREE.AdditiveBlending });
  const innerMesh = new THREE.Mesh(innerGeo, innerMat);
  group.add(innerMesh);

  // Outer chromatic breathing aura
  const outerGeo = new THREE.SphereGeometry(CORE.radius, 32, 32);
  const outerMat = new THREE.MeshBasicMaterial({ color: COLORS.idle.sphere, transparent: true,
    opacity: CORE.opacity, blending: THREE.AdditiveBlending });
  const outerMesh = new THREE.Mesh(outerGeo, outerMat);
  group.add(outerMesh);

  group.userData = { inner: innerMesh, outer: outerMesh };
  return group;
}
function updateCoreGlow(group, time, amplitude, colors, fullscreenFactor = 0) {
  const pulseSpeed = CORE.pulseSpeed + fullscreenFactor * (FULLSCREEN.core.pulseSpeed - CORE.pulseSpeed);
  const pulseAmount = CORE.pulseAmount + fullscreenFactor * (FULLSCREEN.core.pulseAmount - CORE.pulseAmount);

  // Organic harmonic heartbeat oscillation
  const pulse = Math.sin(time * pulseSpeed) * 0.65 + Math.sin(time * pulseSpeed * 2.2) * 0.35;
  const scale = (1.0 + fullscreenFactor * 0.28) * (1 + pulse * pulseAmount + amplitude * pulseAmount * 2.4);
  group.scale.setScalar(scale);

  const { inner, outer } = group.userData;
  if (outer) {
    const targetOpacity = CORE.opacity + fullscreenFactor * (FULLSCREEN.core.opacity - CORE.opacity);
    outer.material.opacity = targetOpacity;
    outer.material.color.lerp(new THREE.Color(colors.sphere), 0.08);
  }
  if (inner) {
    inner.material.opacity = 0.8 + fullscreenFactor * 0.15 + amplitude * 0.15;
    inner.scale.setScalar(1.0 + amplitude * 0.4);
  }
}
export { createCoreGlow, updateCoreGlow };
