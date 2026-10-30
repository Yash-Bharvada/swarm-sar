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
  const a = Math.min(1, Math.max(0, simClock.alpha));
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
  shadowMapSize: number;
  dust: number;
  rubblePerCell: number;
  /** Subtle water animation is disabled on the lightest profile. */
  animatedWater: boolean;
  commFx: boolean;
}

export const QUALITY: Record<Quality, QualityProfile> = {
  low: {
    dpr: [1, 1],
    antialias: false,
    shadows: false,
    shadowMapSize: 1024,
    dust: 0,
    rubblePerCell: 2,
    animatedWater: false,
    commFx: false,
  },
  medium: {
    dpr: [1, 1.5],
    antialias: true,
    shadows: true,
    shadowMapSize: 1024,
    dust: 36,
    rubblePerCell: 3,
    animatedWater: true,
    commFx: true,
  },
  high: {
    dpr: [1, 2],
    antialias: true,
    shadows: true,
    shadowMapSize: 2048,
    dust: 72,
    rubblePerCell: 4,
    animatedWater: true,
    commFx: true,
  },
};

export const COLORS = {
  rover: '#d78136',
  drone: '#2cafa7',
  healthy: '#38f28a',
  weak: '#ffd23f',
  down: '#ff3b4a',
  survivor: '#309b64',
  heat: '#ff6a2b',
  sound: '#b48cff',
  manual: '#f5f5ff',
  // Warm game-art palette for the environment and comm effects.
  sand: '#f1d9a0',
  sandDark: '#e9cc8d',
  grout: '#dfc18b',
  terracotta: '#cd853f',
  sienna: '#a0522d',
  saddle: '#8b4513',
  leaf: '#4caf50',
  leafDark: '#2e7d32',
  water: '#2bafa9',
  sun: '#fff5e0',
  sky: '#d7f0e9',
  ember: '#ff7043',
  discovery: '#ffeb3b',
  merge: '#80deea',
};

/** Deterministic hash-based noise for procedural textures. */
function hash2(x: number, y: number, seed: number): number {
  let h = (x * 374761393 + y * 668265263 + seed * 2246822519) >>> 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177) >>> 0;
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

type FloorStyle = 'office' | 'mine' | 'apartment' | 'random' | 'maze' | 'demo';

/** Sand palettes per site: [light tile, dark tile, grout]. Mines run darker ochre. */
const TILE_PALETTE: Record<FloorStyle, [string, string, string]> = {
  office: [COLORS.sand, COLORS.sandDark, COLORS.grout],
  maze: [COLORS.sand, COLORS.sandDark, COLORS.grout],
  apartment: ['#ead3a8', '#d8bf8e', '#a88c62'],
  demo: [COLORS.sand, COLORS.sandDark, COLORS.grout],
  random: ['#dcc596', '#c9b27f', '#9a8458'],
  mine: ['#c9a66b', '#b58f58', '#7f6440'],
};

function shade(hex: string, k: number): string {
  const c = new THREE.Color(hex);
  c.r = Math.min(1, c.r * k);
  c.g = Math.min(1, c.g * k);
  c.b = Math.min(1, c.b * k);
  return `#${c.getHexString()}`;
}

/**
 * Chunky game-art floor: one bevelled tile per grid cell. Each tile gets a
 * checker tone, a lit top/left rim and a shaded bottom/right rim, so a flat
 * plane reads like raised isometric blocks. Pebbles and grass tufts add life.
 */
export function makeIsoTileTexture(width: number, height: number, style: FloorStyle, seed: number, cells?: Int8Array): THREE.CanvasTexture {
  const ppc = Math.max(8, Math.min(32, Math.floor(2048 / Math.max(width, height))));
  const canvas = document.createElement('canvas');
  canvas.width = width * ppc;
  canvas.height = height * ppc;
  const ctx = canvas.getContext('2d')!;
  const [light, dark, grout] = TILE_PALETTE[style];
  ctx.fillStyle = grout;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  const bevel = 1;
  for (let y = 0; y < height; y++)
    for (let x = 0; x < width; x++) {
      const px = x * ppc;
      const py = y * ppc;
      // The overgrown courtyards remain traversable. Their sandy borders and
      // cross-paths make the actual walls and open routes easy to distinguish.
      const openInterior = cells?.[y * width + x] === 0 && x > 2 && y > 2 && x < width - 3 && y < height - 3
        && [[-2, 0], [2, 0], [0, -2], [0, 2], [-1, 0], [1, 0], [0, -1], [0, 1]].every(([dx, dy]) => cells[(y + dy) * width + x + dx] === 0);
      const meadow = style !== 'mine' && openInterior && hash2(Math.floor(x / 8), Math.floor(y / 8), seed + 55) > 0.25
        && x % 9 !== 4 && y % 10 !== 5;
      const base = shade(meadow ? (hash2(x, y, seed + 21) > 0.5 ? '#84ab32' : '#7da22b') : hash2(x, y, seed + 2) > 0.72 ? dark : light, 0.96 + hash2(x, y, seed) * 0.08);
      if (meadow) {
        ctx.fillStyle = base;
        ctx.fillRect(px, py, ppc, ppc);
        for (let blade = 0; blade < 4; blade++) {
          const s = Math.max(1, Math.round(ppc / 12));
          ctx.fillStyle = shade(base, blade % 2 ? 1.11 : 0.91);
          ctx.fillRect(px + hash2(x + blade, y, seed + 25) * (ppc - s), py + hash2(x, y + blade, seed + 26) * (ppc - s), s, s * 2);
        }
        if (hash2(x, y, seed + 27) > 0.9) {
          ctx.fillStyle = '#f9e9bb';
          ctx.fillRect(px + ppc * 0.35, py + ppc * 0.4, Math.max(2, ppc / 10), Math.max(2, ppc / 10));
        }
        continue;
      }
      // Inset by 1px of grout, then paint top face, highlight rim and shadow rim.
      ctx.fillStyle = base;
      ctx.fillRect(px + 1, py + 1, ppc - 2, ppc - 2);
      ctx.fillStyle = shade(base, 1.035);
      ctx.fillRect(px + 1, py + 1, ppc - 2, bevel);
      ctx.fillRect(px + 1, py + 1, bevel, ppc - 2);
      ctx.fillStyle = shade(base, 0.96);
      ctx.fillRect(px + 1, py + ppc - 1 - bevel, ppc - 2, bevel);
      ctx.fillRect(px + ppc - 1 - bevel, py + 1, bevel, ppc - 2);
      const roll = hash2(x, y, seed + 7);
      if (roll < 0.12) {
        // Pebbles: a few square "pixels" in warm stone tones.
        for (let k = 0; k < 3; k++) {
          ctx.fillStyle = shade(dark, 0.7 + hash2(x, y + k, seed + 9) * 0.2);
          const s = Math.max(2, Math.round(ppc / 9));
          ctx.fillRect(px + 3 + hash2(x + k, y, seed) * (ppc - 8), py + 3 + hash2(x, y + k, seed + 3) * (ppc - 8), s, s);
        }
      } else if (roll < 0.17 && style !== 'mine') {
        // Grass tuft creeping through the cracks.
        ctx.fillStyle = COLORS.leaf;
        const s = Math.max(2, Math.round(ppc / 8));
        const gx = px + 2 + hash2(x, y, seed + 11) * (ppc - 6);
        const gy = py + 2 + hash2(x, y, seed + 13) * (ppc - 6);
        ctx.fillRect(gx, gy, s, s * 2);
        ctx.fillRect(gx + s, gy + s, s, s);
        ctx.fillStyle = COLORS.leafDark;
        ctx.fillRect(gx - s, gy + s, s, s);
      }
    }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  // Crisp pixel edges up close; mipmaps keep it calm when zoomed out.
  texture.magFilter = THREE.NearestFilter;
  return texture;
}

/** Tileable normal map of soft sine ripples, scrolled over time to animate water. */
export function makeWaterNormalTexture(): THREE.DataTexture {
  const size = 64;
  const data = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y++)
    for (let x = 0; x < size; x++) {
      const u = (x / size) * Math.PI * 2;
      const v = (y / size) * Math.PI * 2;
      // Gradient of h = sin(2u + v) + 0.6 sin(u - 3v), packed into RGB.
      const dx = 2 * Math.cos(2 * u + v) + 0.6 * Math.cos(u - 3 * v);
      const dy = Math.cos(2 * u + v) - 1.8 * Math.cos(u - 3 * v);
      const n = new THREE.Vector3(-dx * 0.25, -dy * 0.25, 1).normalize();
      const o = (y * size + x) * 4;
      data[o] = (n.x * 0.5 + 0.5) * 255;
      data[o + 1] = (n.y * 0.5 + 0.5) * 255;
      data[o + 2] = (n.z * 0.5 + 0.5) * 255;
      data[o + 3] = 255;
    }
  const t = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.magFilter = THREE.LinearFilter;
  t.minFilter = THREE.LinearMipmapLinearFilter;
  t.generateMipmaps = true;
  t.needsUpdate = true;
  return t;
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

let glow: THREE.CanvasTexture | null = null;
export function glowTexture(): THREE.CanvasTexture {
  if (!glow) glow = makeGlowTexture();
  return glow;
}
