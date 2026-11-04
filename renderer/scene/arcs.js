// FILE: arcs.js
// Creates energy trails that orbit the sphere to suggest flowing holographic electricity.
import * as THREE from 'three';
import { ARC, COLORS, FULLSCREEN } from '../constants.js';
function createArc(index) {
  const points = Array.from({ length: ARC.points }, (_, point) => {
    const angle = (point / (ARC.points - 1)) * Math.PI * 2;
    const wobble = Math.sin(index * 1.5 + point * 0.8) * 0.28;
    return new THREE.Vector3(
      Math.cos(angle) * (ARC.radius + wobble),
      Math.sin(angle * 2 + index * 1.1) * 0.48,
      Math.sin(angle) * (ARC.radius + wobble)
    );
  });
  const curve = new THREE.CatmullRomCurve3(points, true);
  const geometry = new THREE.TubeGeometry(curve, 80, ARC.tubeRadius, 6, true);
  const material = new THREE.MeshBasicMaterial({ color: COLORS.idle.sphere, transparent: true, opacity: 0.65, blending: THREE.AdditiveBlending });
  return new THREE.Mesh(geometry, material);
}
function createArcs() {
  const group = new THREE.Group();
  for (let i = 0; i < ARC.count; i += 1) group.add(createArc(i));
  return group;
}
function updateArcs(group, time, colors, fullscreenFactor = 0) {
  const targetScale = 1.0 + fullscreenFactor * (FULLSCREEN.arcs.radiusScale - 1.0);
  group.scale.setScalar(targetScale);

  const speedMult = 1.0 + fullscreenFactor * (FULLSCREEN.arcs.speedMult - 1.0);
  group.children.forEach((arc, index) => {
    arc.rotation.y = time * 0.0004 * (index + 1) * speedMult;
    arc.rotation.x = Math.sin(time * 0.0006 * speedMult + index * 1.2) * 0.6;
    arc.rotation.z = Math.cos(time * 0.0004 * speedMult + index * 0.8) * 0.4;
    arc.material.opacity = 0.65 + fullscreenFactor * 0.25;
    arc.material.color.lerp(new THREE.Color(colors.sphere), 0.05);
  });
}
export { createArcs, updateArcs };
