import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

const PALETTE = {
  excitatory: "#50ddc4",
  inhibitory: "#e79db4",
  
};
const MAX_PULSES = 1800;

export class NeuralView {
  constructor(container) {
    this.container = container;
    this.reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(42, 1, 0.1, 1000);
    this.camera.position.set(0, 35, 185);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 1.75));
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    container.prepend(this.renderer.domElement);
    this.renderer.domElement.setAttribute(
      "aria-label",
      "3D FlyWire subnetwork; graph layout, not anatomical coordinates",
    );
    this.renderer.domElement.addEventListener("webglcontextlost", (e) => {
      e.preventDefault();
      document.querySelector("#gpu-error").hidden = false;
      cancelAnimationFrame(this.frame);
    });
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.autoRotate = !this.reducedMotion;
    this.controls.autoRotateSpeed = 0.35;
    this.controls.minDistance = 80;
    this.controls.maxDistance = 320;
    this.controls.enablePan = false;
    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    this.composer.addPass(
      new UnrealBloomPass(new THREE.Vector2(800, 600), 0.9, 0.5, 0.65),
    );
    this.composer.addPass(new OutputPass());
    this.pulsePositions = new Float32Array(MAX_PULSES * 3).fill(10000);
    this.pulseGeometry = new THREE.BufferGeometry();
    this.pulseGeometry.setAttribute(
      "position",
      new THREE.BufferAttribute(this.pulsePositions, 3),
    );
    this.pulseMaterial = new THREE.PointsMaterial({
      color: "#adfff0",
      size: 1.5,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    this.pulseCloud = new THREE.Points(this.pulseGeometry, this.pulseMaterial);
    this.pulseCloud.frustumCulled = false;
    this.scene.add(this.pulseCloud);
    this.pulses = [];
    this.observer = new ResizeObserver(() => this.resize());
    this.observer.observe(container);
    this.last = performance.now();
    this.animate();
  }
  setGraph(graph) {
    if (this.nodes) {
      this.scene.remove(this.nodes, this.edges);
      this.nodes.geometry.dispose();
      this.nodes.material.dispose();
      this.nodes.dispose();
      this.edges.geometry.dispose();
      this.edges.material.dispose();
    }
    this.graph = graph;
    this.pulses = [];
    this.positions = graph.nodes.map((n) => new THREE.Vector3(...n.position));
    this.baseColors = graph.nodes.map((n) => new THREE.Color(PALETTE[n.role]));
    this.heat = new Float32Array(graph.nodes.length);
    this.outgoing = graph.nodes.map(() => []);
    this.nodes = new THREE.InstancedMesh(
      new THREE.SphereGeometry(0.48, 6, 5),
      new THREE.MeshBasicMaterial(),
      graph.nodes.length,
    );
    const dummy = new THREE.Object3D();
    graph.nodes.forEach((node, i) => {
      dummy.position.copy(this.positions[i]);
      dummy.scale.setScalar(node.role === "motor" ? 1.5 : 1);
      dummy.updateMatrix();
      this.nodes.setMatrixAt(i, dummy.matrix);
      this.nodes.setColorAt(i, this.baseColors[i].clone().multiplyScalar(0.6));
    });
    const vertices = [];
    graph.edges.forEach((edge) => {
      vertices.push(
        ...graph.nodes[edge.source].position,
        ...graph.nodes[edge.target].position,
      );
      this.outgoing[edge.source].push(edge.target);
    });
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(vertices, 3),
    );
    this.edges = new THREE.LineSegments(
      geometry,
      new THREE.LineBasicMaterial({
        color: "#467b92",
        transparent: true,
        opacity: 0.075,
        depthWrite: false,
      }),
    );
    this.scene.add(this.edges, this.nodes);
  }
  spike(frame) {
    if (!this.graph) return;
    const now = performance.now();
    for (const spike of frame.spikes) {
      this.heat[spike.id] = spike.intensity;
      if (!this.reducedMotion) {
        // Render a bounded sample of outgoing synapses, always driven by real spikes.
        for (const target of this.outgoing[spike.id].slice(0, 3)) {
          if (this.pulses.length >= MAX_PULSES) break;
          this.pulses.push({ source: spike.id, target, start: now });
        }
      }
    }
  }
  resize() {
    const width = this.container.clientWidth,
      height = this.container.clientHeight;
    if (!width || !height) return;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
    this.composer.setSize(width, height);
  }
  animate = () => {
    this.frame = requestAnimationFrame(this.animate);
    const now = performance.now(),
      delta = Math.min((now - this.last) / 1000, 0.1);
    this.last = now;
    if (document.hidden) return;
    if (this.nodes) {
      const color = new THREE.Color();
      for (let i = 0; i < this.heat.length; i++) {
        this.heat[i] *= Math.exp(-delta * 3);
        color.copy(this.baseColors[i]).multiplyScalar(0.55 + this.heat[i] * 5);
        this.nodes.setColorAt(i, color);
      }
      this.nodes.instanceColor.needsUpdate = true;
      this.pulses = this.pulses.filter((p) => now - p.start < 650);
      this.pulsePositions.fill(10000);
      const point = new THREE.Vector3();
      this.pulses.forEach((pulse, i) => {
        point.lerpVectors(
          this.positions[pulse.source],
          this.positions[pulse.target],
          (now - pulse.start) / 650,
        );
        point.toArray(this.pulsePositions, i * 3);
      });
      this.pulseGeometry.attributes.position.needsUpdate = true;
      this.pulseGeometry.setDrawRange(0, this.pulses.length);
    }
    this.controls.update(delta);
    this.composer.render();
  };
  dispose() {
    cancelAnimationFrame(this.frame);
    this.observer.disconnect();
    this.controls.dispose();
    this.scene.traverse((object) => {
      object.geometry?.dispose();
      object.material?.dispose();
    });
    this.nodes?.dispose();
    for (const pass of this.composer.passes) pass.dispose?.();
    this.composer.dispose();
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }
}
