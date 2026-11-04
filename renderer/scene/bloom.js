// FILE: bloom.js
// Configures render, bloom, and output post-processing pipeline.
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { BLOOM } from '../constants.js';

const AlphaFromLuminanceShader = {
  uniforms: { tDiffuse: { value: null }, uFullscreen: { value: 0.0 } },
  vertexShader: /* glsl */`
    varying vec2 vUv;
    void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }
  `,
  fragmentShader: /* glsl */`
    uniform sampler2D tDiffuse;
    uniform float uFullscreen;
    varying vec2 vUv;
    void main() {
      vec4 color = texture2D(tDiffuse, vUv);
      float luminance = max(color.r, max(color.g, color.b));
      float baseAlpha = smoothstep(0.012, 0.18, luminance);
      float alpha = mix(baseAlpha, 1.0, uFullscreen);
      gl_FragColor = vec4(color.rgb, alpha);
    }
  `,
};

function createBloom(renderer, scene, camera) {
  renderer.setClearColor(0x000000, 0);
  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(
    new THREE.Vector2(window.innerWidth, window.innerHeight),
    BLOOM.strength,
    BLOOM.radius,
    BLOOM.threshold
  );
  composer.addPass(bloom);
  composer.addPass(new OutputPass());
  const alphaPass = new ShaderPass(AlphaFromLuminanceShader);
  composer.addPass(alphaPass);
  return { composer, bloom, alphaPass };
}

function updateBloom(pipeline, colors, fullscreenFactor = 0) {
  const bloom = pipeline.bloom || pipeline;
  const targetStrength = (colors.bloom || BLOOM.strength) * (1.0 + fullscreenFactor * 0.3);
  const targetRadius = BLOOM.radius * (1.0 + fullscreenFactor * 0.2);
  bloom.strength += (targetStrength - bloom.strength) * 0.06;
  bloom.radius += (targetRadius - bloom.radius) * 0.06;
  if (pipeline.alphaPass?.uniforms?.uFullscreen) {
    pipeline.alphaPass.uniforms.uFullscreen.value = fullscreenFactor;
  }
}

export { createBloom, updateBloom };
