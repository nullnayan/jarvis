// FILE: rings.js
// Creates three thin, tilted orbital rings and rotates them by state-aware speeds.
import * as THREE from 'three';
import { COLORS, RINGS, FULLSCREEN } from '../constants.js';
function createRings() {
  const group = new THREE.Group();
  RINGS.tilts.forEach((tilt, index) => {
    const ringRadius = RINGS.radius * (0.85 + (index / (RINGS.count - 1)) * 0.35);
    const geometry = new THREE.TorusGeometry(ringRadius, RINGS.tubeRadius, 8, 120);
    const material = new THREE.MeshBasicMaterial({ color: COLORS.idle.sphere, transparent: true,
      opacity: 0.5, blending: THREE.AdditiveBlending });
    const ring = new THREE.Mesh(geometry, material);
    ring.rotation.x = THREE.MathUtils.degToRad(tilt);
    ring.rotation.y = THREE.MathUtils.degToRad(tilt * 0.5);
    ring.userData.speed = RINGS.speeds[index];
    ring.userData.baseOpacity = 0.45 + (index % 2) * 0.15;
    group.add(ring);
  });
  return group;
}
function updateRings(group, colors, state, fullscreenFactor = 0) {
  const targetScale = 1.0 + fullscreenFactor * (FULLSCREEN.rings.radiusScale - 1.0);
  group.scale.setScalar(targetScale);

  const fsSpeed = 1.0 + fullscreenFactor * (FULLSCREEN.rings.speedMult - 1.0);
  const multiplier = (state === 'thinking' ? 4 : state === 'confirming' || state === 'error' ? 0 : 1) * fsSpeed;

  group.children.forEach((ring) => {
    ring.rotation.z += ring.userData.speed * multiplier;
    ring.rotation.x += ring.userData.speed * 0.2 * multiplier;
    ring.material.opacity = ring.userData.baseOpacity + fullscreenFactor * 0.25;
    ring.material.color.lerp(new THREE.Color(colors.sphere), 0.05);
  });
}
export { createRings, updateRings };
