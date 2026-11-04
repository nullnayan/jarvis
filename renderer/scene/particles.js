// FILE: particles.js
// Creates a drifting cloud of additive particles around the holographic sphere.
import * as THREE from 'three';
import { COLORS, PARTICLES, FULLSCREEN } from '../constants.js';
function createParticles() {
  const positions = new Float32Array(PARTICLES.count * 3);
  const seeds = new Float32Array(PARTICLES.count);
  for (let i = 0; i < PARTICLES.count; i += 1) {
    const radius = 0.82 + Math.random() * FULLSCREEN.particles.spreadRadius;
    const theta = Math.random() * Math.PI * 2; const phi = Math.acos(2 * Math.random() - 1);
    positions.set([radius * Math.sin(phi) * Math.cos(theta), radius * Math.cos(phi), radius * Math.sin(phi) * Math.sin(theta)], i * 3);
    seeds[i] = Math.random() * Math.PI * 2;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setDrawRange(0, PARTICLES.normalCount);
  const material = new THREE.PointsMaterial({ color: COLORS.idle.particles, size: PARTICLES.size,
    transparent: true, opacity: 0.86, blending: THREE.AdditiveBlending, depthWrite: false });
  const cloud = new THREE.Points(geometry, material);
  cloud.userData.seeds = seeds;
  cloud.userData.initialPositions = new Float32Array(positions);
  return cloud;
}
function updateParticles(cloud, time, amplitude, colors, state, fullscreenFactor = 0) {
  const activeCount = Math.floor(PARTICLES.normalCount + fullscreenFactor * (PARTICLES.count - PARTICLES.normalCount));
  cloud.geometry.setDrawRange(0, activeCount);

  const positions = cloud.geometry.attributes.position;
  const initial = cloud.userData.initialPositions;
  const seeds = cloud.userData.seeds;
  const speedMult = (state === 'thinking' ? 3.0 : 1.0) * (1.0 + fullscreenFactor * (FULLSCREEN.particles.speedMult - 1.0));
  const radialScale = (1.0 + amplitude * 0.22) * (1.0 + fullscreenFactor * 0.32);

  cloud.material.size = PARTICLES.size + fullscreenFactor * (FULLSCREEN.particles.size - PARTICLES.size);
  cloud.material.opacity = 0.86 + fullscreenFactor * 0.14;

  const vortexAngle = time * 0.00025 * (1.0 + fullscreenFactor * 1.5);
  const cosV = Math.cos(vortexAngle);
  const sinV = Math.sin(vortexAngle);

  for (let i = 0; i < activeCount; i += 1) {
    const p = i * 3;
    const seed = seeds[i];
    const dx = Math.sin(time * 0.001 * speedMult + seed) * 0.06;
    const dy = Math.cos(time * 0.0008 * speedMult + seed * 1.3) * 0.06;
    const dz = Math.sin(time * 0.0012 * speedMult + seed * 0.7) * 0.06;

    const ix = (initial[p] + dx) * radialScale;
    const iy = (initial[p + 1] + dy) * radialScale;
    const iz = (initial[p + 2] + dz) * radialScale;

    // Apply gentle celestial vortex rotation around Y axis
    positions.array[p] = ix * cosV - iz * sinV;
    positions.array[p + 1] = iy;
    positions.array[p + 2] = ix * sinV + iz * cosV;
  }
  positions.needsUpdate = true;
  cloud.material.color.lerp(new THREE.Color(colors.particles), 0.06);
}
export { createParticles, updateParticles };
