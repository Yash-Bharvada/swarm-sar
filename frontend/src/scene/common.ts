import * as THREE from 'three';
import type { Quality } from '../store/simStore';
import type { SimulationEngine } from '../simulation/core/SimulationEngine';
import { simClock } from '../store/simStore';

/** One grid cell = one metre. Cell (x, y) maps to world (x, 0, y) centred on the map. */
export function cellToWorld(engine: SimulationEngine, x: number, y: number, target = new THREE.Vector3()): THREE.Vector3 {
  const { width, height } = engine.scenario;
  return target.set(x - width / 2 + 0.5, 0, y - height / 2 + 0.5);
}

export function worldToCell(engine: SimulationEngine, p: THREE.Vector3): { x: number; y: number } {
  const { width, height } = engine.scenario;
  return { x: Math.floor(p.x + width / 2), y: Math.floor(p.z + height / 2) };
}

/** Interpolated render position of a robot between its previous and current cell. */
export function robotRenderPosition(engine: SimulationEngine, id: number, target = new THREE.Vector3()): THREE.Vector3 {
  const r = engine.robots[id];
  const prev = engine.prevPositions.get(id) ?? r;
  const a = smoothstep(simClock.alpha);
  return cellToWorld(engine, prev.x + (r.x - prev.x) * a, prev.y + (r.y - prev.y) * a, target);
}

export const smoothstep = (t: number) => {
  const c = Math.min(1, Math.max(0, t));
  return c * c * (3 - 2 * c);
};

export interface QualityProfile {
  dpr: [number, number];
  antialias: boolean;
  shadows: boolean;
  dust: number;
  emergencyLights: number;
  robotSpotlights: boolean;
  lightShafts: boolean;
  rubblePerCell: number;
}

export const QUALITY: Record<Quality, QualityProfile> = {
  low: { dpr: [1, 1], antialias: false, shadows: false, dust: 120, emergencyLights: 2, robotSpotlights: false, lightShafts: false, rubblePerCell: 2 },
  medium: { dpr: [1, 1.5], antialias: true, shadows: false, dust: 320, emergencyLights: 4, robotSpotlights: false, lightShafts: true, rubblePerCell: 3 },
  high: { dpr: [1, 2], antialias: true, shadows: true, dust: 700, emergencyLights: 6, robotSpotlights: true, lightShafts: true, rubblePerCell: 4 },
};

export const COLORS = {
  rover: '#ff9a3c',
  drone: '#46d9ff',
  healthy: '#38f28a',
  weak: '#ffd23f',
  down: '#ff3b4a',
  survivor: '#7dffb2',
  heat: '#ff6a2b',
  sound: '#b48cff',
  manual: '#f5f5ff',
};

/** Deterministic hash-based noise for procedural textures. */
function hash2(x: number, y: number, seed: number): number {
  let h = (x * 374761393 + y * 668265263 + seed * 2246822519) >>> 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177) >>> 0;
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

/** Procedural concrete/rock floor with cracks, stains and (optionally) tile seams. */
export function makeFloorTexture(width: number, height: number, style: 'office' | 'mine' | 'apartment' | 'random' | 'demo', seed: number): THREE.CanvasTexture {
  const ppc = 24; // pixels per cell
  const canvas = document.createElement('canvas');
  canvas.width = Math.min(2048, width * ppc);
  canvas.height = Math.min(2048, height * ppc);
  const sx = canvas.width / width;
  const sy = canvas.height / height;
  const ctx = canvas.getContext('2d')!;
  const base = style === 'mine' ? [62, 52, 44] : style === 'random' ? [58, 56, 54] : [74, 74, 78];
  ctx.fillStyle = `rgb(${base.join(',')})`;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  // Mottled grime.
  for (let i = 0; i < width * height * 3; i++) {
    const x = hash2(i, 1, seed) * canvas.width;
    const y = hash2(i, 2, seed) * canvas.height;
    const r = 2 + hash2(i, 3, seed) * 10;
    const d = hash2(i, 4, seed) < 0.5 ? -1 : 1;
    const v = 10 + hash2(i, 5, seed) * 18;
    ctx.fillStyle = `rgba(${d > 0 ? 255 : 0},${d > 0 ? 250 : 0},${d > 0 ? 240 : 0},${(v / 255).toFixed(3)})`;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }
  // Tile seams for office/apartment floors.
  if (style === 'office' || style === 'apartment' || style === 'demo') {
    ctx.strokeStyle = 'rgba(0,0,0,0.25)';
    ctx.lineWidth = 1;
    for (let x = 0; x <= width; x += 2) {
      ctx.beginPath();
      ctx.moveTo(x * sx, 0);
      ctx.lineTo(x * sx, canvas.height);
      ctx.stroke();
    }
    for (let y = 0; y <= height; y += 2) {
      ctx.beginPath();
      ctx.moveTo(0, y * sy);
      ctx.lineTo(canvas.width, y * sy);
      ctx.stroke();
    }
  }
  // Cracks.
  ctx.strokeStyle = 'rgba(10,8,6,0.55)';
  for (let c = 0; c < Math.floor((width * height) / 40); c++) {
    let x = hash2(c, 11, seed) * canvas.width;
    let y = hash2(c, 12, seed) * canvas.height;
    let angle = hash2(c, 13, seed) * Math.PI * 2;
    ctx.lineWidth = 0.6 + hash2(c, 14, seed) * 1.6;
    ctx.beginPath();
    ctx.moveTo(x, y);
    const segments = 4 + Math.floor(hash2(c, 15, seed) * 8);
    for (let s = 0; s < segments; s++) {
      angle += (hash2(c, 20 + s, seed) - 0.5) * 1.4;
      const len = 6 + hash2(c, 40 + s, seed) * 18;
      x += Math.cos(angle) * len;
      y += Math.sin(angle) * len;
      ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
}

/** Soft radial sprite used for dust, glows and floor light pools. */
export function makeGlowTexture(): THREE.CanvasTexture {
  const size = 64;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d')!;
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, 'rgba(255,255,255,1)');
  g.addColorStop(0.35, 'rgba(255,255,255,0.45)');
  g.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  const t = new THREE.CanvasTexture(canvas);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

/** Yellow/black hazard stripes for the staging zone. */
export function makeHazardTexture(): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 128;
  const ctx = canvas.getContext('2d')!;
  ctx.fillStyle = '#16140f';
  ctx.fillRect(0, 0, 128, 128);
  ctx.fillStyle = '#e2b414';
  for (let i = -128; i < 256; i += 32) {
    ctx.beginPath();
    ctx.moveTo(i, 0);
    ctx.lineTo(i + 16, 0);
    ctx.lineTo(i + 16 + 128, 128);
    ctx.lineTo(i + 128, 128);
    ctx.fill();
  }
  const t = new THREE.CanvasTexture(canvas);
  t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return t;
}

let glow: THREE.CanvasTexture | null = null;
export function glowTexture(): THREE.CanvasTexture {
  if (!glow) glow = makeGlowTexture();
  return glow;
}
