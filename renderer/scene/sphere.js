// FILE: sphere.js
// Creates the wireframe icosahedron sphere with time-based vertex displacement.
import * as THREE from 'three';
import { COLORS, SPHERE, FULLSCREEN } from '../constants.js';
function createSphere() {
  const geometry = new THREE.IcosahedronGeometry(SPHERE.radius, SPHERE.detail);
  geometry.userData.base = geometry.attributes.position.array.slice();
  const material = new THREE.MeshBasicMaterial({ color: COLORS.idle.sphere, wireframe: true,
    transparent: true, opacity: 0.82, blending: THREE.AdditiveBlending });
  return new THREE.Mesh(geometry, material);
}
function updateSphere(mesh, time, amplitude, colors, fullscreenFactor = 0) {
  const rotSpeedX = SPHERE.rotationSpeed.x + fullscreenFactor * (FULLSCREEN.sphere.rotationSpeed.x - SPHERE.rotationSpeed.x);
  const rotSpeedY = SPHERE.rotationSpeed.y + fullscreenFactor * (FULLSCREEN.sphere.rotationSpeed.y - SPHERE.rotationSpeed.y);
  mesh.rotation.x += rotSpeedX * (1 + amplitude);
  mesh.rotation.y += rotSpeedY * (1 + amplitude);

  const targetScale = 1.0 + fullscreenFactor * (FULLSCREEN.scale - 1.0);
  mesh.scale.setScalar(targetScale);

  const noiseSpeed = SPHERE.noiseSpeed + fullscreenFactor * (FULLSCREEN.sphere.noiseSpeed - SPHERE.noiseSpeed);
  const noiseAmp = SPHERE.noiseAmp + fullscreenFactor * (FULLSCREEN.sphere.noiseAmp - SPHERE.noiseAmp);
  const ampMultiplier = 1 + amplitude * 2.2;

  const position = mesh.geometry.attributes.position;
  const base = mesh.geometry.userData.base;
  for (let i = 0; i < position.count; i += 1) {
    const primary = Math.sin(time * noiseSpeed + i * 1.71);
    const harmonic = Math.cos(time * (noiseSpeed * 0.72) + i * 2.45) * 0.38;
    const wave = (primary + harmonic) * noiseAmp * ampMultiplier;
    const offset = i * 3;
    position.setXYZ(i, base[offset] * (1 + wave), base[offset + 1] * (1 + wave), base[offset + 2] * (1 + wave));
  }
  position.needsUpdate = true;
  mesh.material.opacity = 0.82 + fullscreenFactor * 0.16;
  mesh.material.color.lerp(new THREE.Color(colors.sphere), 0.06);
}
export { createSphere, updateSphere };
