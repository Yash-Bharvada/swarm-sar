import { useEffect, useMemo, useRef } from 'react';
import { useFrame, type ThreeEvent } from '@react-three/fiber';
import * as THREE from 'three';
import type { SimulationEngine } from '../simulation/core/SimulationEngine';
import { FREE, Material, RUBBLE, WALL } from '../simulation/world/GridMap';
import { Rng } from '../simulation/core/Rng';
import { cellToWorld, COLORS, makeIsoTileTexture, makeWaterNormalTexture, type QualityProfile } from './common';

interface Block {
  position: [number, number, number];
  scale: [number, number, number];
  color: string;
  rotation?: [number, number, number];
}

/** Static decorations share geometry and materials instead of adding a draw call per tile. */
function Blocks({ items, shadows = true }: { items: Block[]; shadows?: boolean }) {
  const ref = useRef<THREE.InstancedMesh>(null);
  useEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    const object = new THREE.Object3D();
    const color = new THREE.Color();
    items.forEach((item, index) => {
      object.position.fromArray(item.position);
      object.scale.fromArray(item.scale);
      object.rotation.set(...(item.rotation ?? [0, 0, 0]));
      object.updateMatrix();
      mesh.setMatrixAt(index, object.matrix);
      mesh.setColorAt(index, color.set(item.color));
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mesh.computeBoundingSphere();
  }, [items]);
  if (!items.length) return null;
  return (
    <instancedMesh ref={ref} args={[undefined, undefined, items.length]} castShadow={shadows} receiveShadow>
      <boxGeometry />
      <meshStandardMaterial roughness={0.95} metalness={0} />
    </instancedMesh>
  );
}

/** Cutaway ruins keep every passage visible from the overview camera. */
function Ruins({ engine, perCell }: { engine: SimulationEngine; perCell: number }) {
  const blocks = useMemo(() => {
    const { grid, material, wallHeight, seed } = engine.scenario;
    const rng = new Rng(seed ^ 0x51ab);
    const list: Block[] = [];
    const p = new THREE.Vector3();
    const masonry = ['#ba8445', '#bf8c4e', '#c99a5c', '#ad773e'];
    const stone = ['#8f947c', '#a4a285', '#b0ad8d', '#909178'];
    for (let y = 0; y < grid.height; y++) {
      for (let x = 0; x < grid.width; x++) {
        const index = y * grid.width + x;
        cellToWorld(engine, x, y, p);
        if (grid.get(x, y) === RUBBLE) {
          for (let k = 0; k < perCell; k++) {
            const size = rng.uniform(0.16, 0.34);
            list.push({
              position: [p.x + rng.uniform(-0.31, 0.31), size * 0.36, p.z + rng.uniform(-0.31, 0.31)],
              scale: [size * rng.uniform(0.9, 1.4), size * 0.7, size],
              rotation: [rng.uniform(-0.1, 0.1), rng.uniform(0, Math.PI), rng.uniform(-0.1, 0.1)],
              color: rng.pick(['#c5ae8a', '#d6c4a4', '#a58e71', '#b49e7e']),
            });
          }
          continue;
        }
        if (grid.get(x, y) !== WALL) continue;
        const m = material[index];
        let deep = true;
        for (let dy = -1; dy <= 1; dy++) {
          for (let dx = -1; dx <= 1; dx++) {
            if (grid.inBounds(x + dx, y + dy) && grid.get(x + dx, y + dy) !== WALL) deep = false;
          }
        }
        const boundary = x === 0 || y === 0 || x === grid.width - 1 || y === grid.height - 1;
        const rock = m === Material.Rock;
        const furniture = m === Material.Desk || m === Material.Crate || m === Material.Shelf;
        const h = boundary ? 0.52 : deep ? 0.72 : Math.min(1.15, 0.5 + wallHeight[index] * 0.3);
        const width = m === Material.Pillar ? 0.7 : furniture ? 0.82 : 0.98;
        const depth = m === Material.Desk ? 0.62 : m === Material.Shelf ? 0.52 : width;
        list.push({
          position: [p.x, h / 2, p.z],
          scale: [width, h, depth],
          color: boundary || deep ? rng.pick(['#71833f', '#7a8e48', '#80924c']) : furniture ? rng.pick(['#986a37', '#af834b', '#a6783c']) : rng.pick(rock ? stone : masonry),
        });
        // Pale coping and green plateau tops give walls a readable silhouette.
        list.push({
          position: [p.x, h + 0.045, p.z],
          scale: [width + 0.035, 0.09, depth + 0.035],
          color: boundary || deep ? rng.pick(['#6d9d28', '#7da832', '#88b13d']) : furniture ? '#d0a162' : rng.pick(rock ? ['#bebc99', '#b6b48b'] : ['#d6ad6e', '#deba7b', '#cda565']),
        });
        if ((boundary || deep) && rng.random() < 0.12) {
          list.push({ position: [p.x + 0.13, h + 0.18, p.z - 0.08], scale: [0.4, 0.23, 0.37], color: rng.pick(['#4b7e2c', '#5e8f32', '#679536']) });
        }
        if (!boundary && !deep && !furniture && (x * 13 + y * 7) % 19 === 0) {
          // Planters sit on occupied wall cells, never in a robot's path.
          list.push({ position: [p.x, h + 0.17, p.z], scale: [0.54, 0.24, 0.48], color: '#537e31' });
          list.push({ position: [p.x + 0.12, h + 0.3, p.z - 0.08], scale: [0.3, 0.18, 0.3], color: '#739c3a' });
          list.push({ position: [p.x - 0.13, h + 0.31, p.z + 0.09], scale: [0.09, 0.08, 0.09], color: '#efbe92' });
        }
        // Subtle blocks along long stretches read as masonry without a busy texture.
        if (!boundary && !deep && !furniture && (x + y) % 2 === 0) {
          list.push({ position: [p.x, h * 0.42, p.z - 0.496], scale: [0.85, 0.018, 0.01], color: '#b38456' });
          list.push({ position: [p.x - 0.496, h * 0.42, p.z], scale: [0.01, 0.018, 0.85], color: '#b38456' });
        }
      }
    }
    return list;
  }, [engine, perCell]);
  return <Blocks items={blocks} />;
}

function Floor({ engine, onFloorClick }: { engine: SimulationEngine; onFloorClick?: (e: ThreeEvent<MouseEvent>) => void }) {
  const { width, height, preset, seed, grid } = engine.scenario;
  const texture = useMemo(() => makeIsoTileTexture(width, height, preset, seed, grid.cells), [width, height, preset, seed, grid]);
  useEffect(() => () => texture.dispose(), [texture]);
  return (
    <group>
      <mesh rotation-x={-Math.PI / 2} receiveShadow onClick={onFloorClick}>
        <planeGeometry args={[width, height]} />
        <meshStandardMaterial map={texture} roughness={0.95} />
      </mesh>
      <mesh position={[0, -0.7, 0]} receiveShadow>
        <boxGeometry args={[width, 1.38, height]} />
        <meshStandardMaterial color="#9c8256" roughness={1} />
      </mesh>
    </group>
  );
}

/** The coast is decoration outside the simulation grid; traversability stays exact. */
function Coast({ engine }: { engine: SimulationEngine }) {
  const scenery = useMemo(() => {
    const { width, height, seed } = engine.scenario;
    const rng = new Rng(seed ^ 0xc0a57);
    const land: Block[] = [];
    const trees: Block[] = [];
    const details: Block[] = [];
    const grass = ['#6d9d28', '#7da832', '#88b13d', '#71982c', '#7ca032'];
    const leaves = ['#2b6c39', '#367d38', '#4d8b35', '#609e3c', '#2b7048'];
    const addTree = (x: number, z: number) => {
      const h = rng.uniform(2.1, 3.1);
      const spread = rng.uniform(0.95, 1.2);
      trees.push({ position: [x, h * 0.34, z], scale: [0.29, h * 0.7, 0.3], color: '#896236' });
      trees.push({ position: [x, h * 0.72, z], scale: [1.62 * spread, 1.25, 1.5 * spread], color: rng.pick(leaves) });
      trees.push({ position: [x - 0.3, h * 0.95, z - 0.25], scale: [1.12 * spread, 0.86, 1.12 * spread], color: rng.pick(leaves) });
      trees.push({ position: [x + 0.48, h * 0.65, z + 0.27], scale: [1.02 * spread, 0.84, 1.1 * spread], color: rng.pick(leaves) });
      if (rng.random() < 0.6) trees.push({ position: [x - 0.57, h * 0.64, z + 0.29], scale: [0.76 * spread, 0.73, 0.8 * spread], color: rng.pick(leaves) });
    };
    const tile = (x: number, z: number, outer: boolean) => {
      const level = outer ? -0.22 : -0.06;
      land.push({ position: [x, level - 0.66, z], scale: [2.015, 1.32, 2.015], color: rng.pick(['#977c4c', '#8c7148', '#a58b59']) });
      land.push({ position: [x, level - 0.24, z], scale: [2.025, 0.28, 2.025], color: rng.pick(['#6a7839', '#748240', '#778342']) });
      land.push({ position: [x, level, z], scale: [2.035, 0.16, 2.035], color: rng.pick(grass) });
      if (rng.random() < (outer ? 0.37 : 0.15)) addTree(x + rng.uniform(-0.3, 0.3), z + rng.uniform(-0.3, 0.3));
      else if (rng.random() < 0.45) {
        const px = x + rng.uniform(-0.6, 0.6);
        const pz = z + rng.uniform(-0.6, 0.6);
        details.push({ position: [px, level + 0.22, pz], scale: [0.74, 0.38, 0.67], color: rng.pick(['#4b812b', '#5b922c', '#6a9d36']) });
        for (let f = 0; f < 3; f++) details.push({ position: [px + rng.uniform(-0.42, 0.42), level + 0.23, pz + rng.uniform(-0.42, 0.42)], scale: [0.11, 0.075, 0.11], color: rng.pick(['#fff2bc', '#f7ce8d', '#eeaa8c']) });
      }
      // Small highlights along the grass edge suggest a blocky shoreline.
      if (outer && rng.random() < 0.5) details.push({ position: [x + 0.8, level - 0.24, z + 0.65], scale: [0.32, 0.28, 0.45], color: '#cdbb91' });
    };
    // Four continuous grassy strips form a shoreline with irregular outer steps.
    for (let z = -height / 2 + 1; z < height / 2; z += 2) {
      for (const sign of [-1, 1]) {
        tile(sign * (width / 2 + 1), z, false);
        if (rng.random() > 0.2) tile(sign * (width / 2 + 3), z, true);
      }
    }
    for (let x = -width / 2 - 3; x < width / 2 + 4; x += 2) {
      for (const sign of [-1, 1]) {
        tile(x, sign * (height / 2 + 1), false);
        if (rng.random() > 0.3) tile(x, sign * (height / 2 + 3), true);
      }
    }
    // Small distant islets add depth without covering the operational site.
    for (let i = 0; i < 9; i++) {
      const side = i % 2 ? -1 : 1;
      const x = side * (width / 2 + rng.uniform(9, 17));
      const z = rng.uniform(-height / 2 - 8, height / 2 + 8);
      land.push({ position: [x, -0.93, z], scale: [rng.uniform(1.6, 3.2), 1.1, rng.uniform(1.5, 3)], color: '#9d875b' });
      land.push({ position: [x, -0.38, z], scale: [1.8, 0.16, 1.6], color: rng.pick(grass) });
      if (i % 3 === 0) addTree(x, z);
    }
    return { land, trees, details };
  }, [engine]);
  return <group><Blocks items={scenery.land} /><Blocks items={scenery.trees} /><Blocks items={scenery.details} shadows={false} /></group>;
}

function Water({ engine, animate }: { engine: SimulationEngine; animate: boolean }) {
  const { width, height, seed } = engine.scenario;
  const normal = useMemo(() => makeWaterNormalTexture(), []);
  useEffect(() => () => normal.dispose(), [normal]);
  const span = 1000;
  const detailSpan = Math.max(width, height) + 100;
  normal.repeat.set(span / 5, span / 5);
  useFrame(({ clock }) => {
    if (animate) normal.offset.set(clock.elapsedTime * 0.012, clock.elapsedTime * 0.007);
  });
  const ripples = useMemo(() => {
    const rng = new Rng(seed ^ 0x4a7e);
    const items: Block[] = [];
    for (let i = 0; i < 180; i++) {
      const x = rng.uniform(-detailSpan / 2, detailSpan / 2);
      const z = rng.uniform(-detailSpan / 2, detailSpan / 2);
      if (Math.abs(x) < width / 2 + 5 && Math.abs(z) < height / 2 + 5) continue;
      items.push({ position: [x, -1.435, z], scale: [rng.uniform(0.2, 0.65), 0.008, rng.uniform(0.04, 0.09)], color: rng.pick(['#6bcfc8', '#55c9c4', '#86d8cc', '#3dbab6']) });
    }
    return items;
  }, [width, height, detailSpan, seed]);
  return (
    <group>
      <mesh rotation-x={-Math.PI / 2} position={[0, -1.45, 0]}>
        <planeGeometry args={[span, span]} />
        <meshStandardMaterial color={COLORS.water} normalMap={normal} normalScale={new THREE.Vector2(0.18, 0.18)} roughness={0.68} metalness={0} />
      </mesh>
      <Blocks items={ripples} shadows={false} />
    </group>
  );
}

/** Small edge plants occupy only the margin of a cell, keeping routes legible. */
function SiteDetails({ engine }: { engine: SimulationEngine }) {
  const details = useMemo(() => {
    const { grid, seed, spawn } = engine.scenario;
    const rng = new Rng(seed ^ 0x6ee7);
    const list: Block[] = [];
    const p = new THREE.Vector3();
    for (let y = 1; y < grid.height - 1; y++) {
      for (let x = 1; x < grid.width - 1; x++) {
        if (grid.get(x, y) !== FREE || rng.random() > 0.34) continue;
        if (x >= spawn.x - 1 && x <= spawn.x + spawn.size && y >= spawn.y - 1 && y <= spawn.y + spawn.size) continue;
        const offsets = [[1, 0], [-1, 0], [0, 1], [0, -1]].filter(([dx, dy]) => grid.get(x + dx, y + dy) === WALL);
        if (!offsets.length) continue;
        const [dx, dy] = rng.pick(offsets);
        cellToWorld(engine, x + dx * 0.4, y + dy * 0.4, p);
        list.push({ position: [p.x, 0.14, p.z], scale: [dx ? 0.16 : 0.48, 0.28, dy ? 0.16 : 0.48], color: rng.pick(['#648f2d', '#759e34', '#527e29']) });
        if (rng.random() < 0.55) list.push({ position: [p.x, 0.31, p.z], scale: [0.095, 0.07, 0.095], color: rng.pick(['#f3d98e', '#eeb898', '#f1ebbc']) });
      }
    }
    // Sparse, compact debris conveys damage without obscuring robots or passage edges.
    for (const prop of engine.scenario.props) {
      if (prop.kind === 'cable' || prop.kind === 'pipe' || prop.kind === 'barrel') continue;
      cellToWorld(engine, prop.x, prop.y, p);
      list.push({ position: [p.x + 0.22, 0.065, p.z + 0.22], scale: prop.kind === 'beam' ? [0.12, 0.13, 0.7] : [0.23, 0.12, 0.24], rotation: [0, prop.rotation, 0], color: prop.kind === 'beam' ? '#a78050' : '#bdad90' });
    }
    return list;
  }, [engine]);
  return <Blocks items={details} />;
}

function StagingZone({ engine }: { engine: SimulationEngine }) {
  const { spawn } = engine.scenario;
  const c = cellToWorld(engine, spawn.x + spawn.size / 2 - 0.5, spawn.y + spawn.size / 2 - 0.5);
  const s = spawn.size;
  const markings = useMemo<Block[]>(() => {
    const items: Block[] = [];
    for (const sx of [-1, 1]) for (const sz of [-1, 1]) {
      items.push({ position: [c.x + sx * (s / 2 - 0.12), 0.022, c.z + sz * (s / 2 - 0.38)], scale: [0.075, 0.012, 0.62], color: '#f8f3d8' });
      items.push({ position: [c.x + sx * (s / 2 - 0.38), 0.022, c.z + sz * (s / 2 - 0.12)], scale: [0.62, 0.012, 0.075], color: '#f8f3d8' });
    }
    return items;
  }, [c.x, c.z, s]);
  return (
    <group>
      <mesh position={[c.x, 0.012, c.z]} rotation-x={-Math.PI / 2}>
        <planeGeometry args={[s - 0.12, s - 0.12]} />
        <meshBasicMaterial color="#749f88" transparent opacity={0.22} depthWrite={false} />
      </mesh>
      <Blocks items={markings} shadows={false} />
    </group>
  );
}

export function World({ engine, quality, onFloorClick }: { engine: SimulationEngine; quality: QualityProfile; onFloorClick?: (e: ThreeEvent<MouseEvent>) => void }) {
  return (
    <group>
      <Water engine={engine} animate={quality.animatedWater} />
      <Coast engine={engine} />
      <Floor engine={engine} onFloorClick={onFloorClick} />
      <Ruins engine={engine} perCell={quality.rubblePerCell} />
      <SiteDetails engine={engine} />
      <StagingZone engine={engine} />
    </group>
  );
}
