import { useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { PacketVisual, SimulationEngine } from '../simulation/core/SimulationEngine';
import { COLORS, robotRenderPosition, smoothstep } from './common';
import { simClock, useSim } from '../store/simStore';

const a = new THREE.Vector3();
const b = new THREE.Vector3();
const c = new THREE.Color();

const antennaHeight = (engine: SimulationEngine, id: number) => (engine.robots[id].type === 'drone' ? 1.55 : 0.72);

/** Thin live links: green healthy, yellow weak/lossy, red partitioned or just lost. */
export function NetworkLinks({ engine }: { engine: SimulationEngine }) {
  const maxPairs = (engine.robots.length * (engine.robots.length - 1)) / 2;
  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(maxPairs * 6), 3));
    g.setAttribute('color', new THREE.BufferAttribute(new Float32Array(maxPairs * 6), 3));
    return g;
  }, [maxPairs]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  const lastUp = useRef(new Map<string, number>());
  const index = useMemo(() => new Map(engine.robots.map((r) => [r.name, r.id])), [engine]);

  useFrame(({ clock }) => {
    const positions = geometry.attributes.position.array as Float32Array;
    const colors = geometry.attributes.color.array as Float32Array;
    let n = 0;
    const step = engine.step;
    for (const [key, link] of engine.network.links) {
      const ia = index.get(link.a);
      const ib = index.get(link.b);
      if (ia === undefined || ib === undefined) continue;
      const ra = engine.robots[ia];
      const rb = engine.robots[ib];
      if (!ra.alive || !rb.alive) continue;
      const current = link.step === step;
      if (current && link.health !== 'down') lastUp.current.set(key, step);
      let col: string | null = null;
      let fade = 1;
      if (current && link.health === 'healthy') col = COLORS.healthy;
      else if (current && link.health === 'weak') col = COLORS.weak;
      else if (current && link.reason === 'partition') {
        col = COLORS.down;
        fade = 0.55 + 0.45 * Math.sin(clock.elapsedTime * 6);
      } else {
        const since = step - (lastUp.current.get(key) ?? -999);
        if (since < 12) {
          col = COLORS.down;
          fade = 1 - since / 12;
        }
      }
      if (!col) continue;
      robotRenderPosition(engine, ia, a);
      robotRenderPosition(engine, ib, b);
      a.y = antennaHeight(engine, ia);
      b.y = antennaHeight(engine, ib);
      positions.set([a.x, a.y, a.z, b.x, b.y, b.z], n * 6);
      c.set(col).multiplyScalar(fade);
      colors.set([c.r, c.g, c.b, c.r, c.g, c.b], n * 6);
      n++;
    }
    geometry.setDrawRange(0, n * 2);
    geometry.attributes.position.needsUpdate = true;
    geometry.attributes.color.needsUpdate = true;
    geometry.computeBoundingSphere();
  });

  return (
    <lineSegments geometry={geometry} frustumCulled={false}>
      <lineBasicMaterial vertexColors transparent opacity={0.85} toneMapped={false} depthWrite={false} />
    </lineSegments>
  );
}

const MAX_PACKETS = 160;

/** Animated pulses: delivered packets travel the link; lost ones fade out red mid-air. */
export function PacketPulses({ engine }: { engine: SimulationEngine }) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const active = useRef<PacketVisual[]>([]);
  const seenStep = useRef(-1);
  const index = useMemo(() => new Map(engine.robots.map((r) => [r.name, r.id])), [engine]);
  const tmp = useMemo(() => new THREE.Object3D(), []);

  useFrame(() => {
    const m = mesh.current;
    if (!m) return;
    if (engine.step !== seenStep.current) {
      seenStep.current = engine.step;
      // Keep loss/partition packets and anything carrying map data or evidence;
      // skip pure heartbeats when the team is large to avoid visual noise.
      const fresh = engine.packets.filter((p) => p.outcome !== 'in-flight' || p.mapCells > 0 || engine.robots.length <= 4);
      active.current = [...active.current, ...fresh].slice(-MAX_PACKETS);
    }
    const now = engine.step - 1 + simClock.alpha;
    let n = 0;
    const keep: PacketVisual[] = [];
    for (const p of active.current) {
      const duration = Math.max(1, p.arriveStep - p.sentStep);
      const t = (now - (p.sentStep - 1)) / duration;
      const lost = p.outcome === 'lost' || p.outcome === 'partition' || p.outcome === 'stale';
      const end = lost ? (p.outcome === 'partition' ? 0.45 : 0.75) : 1;
      if (t > end + 0.15) continue;
      keep.push(p);
      const ia = index.get(p.from);
      const ib = index.get(p.to);
      if (ia === undefined || ib === undefined) continue;
      robotRenderPosition(engine, ia, a);
      robotRenderPosition(engine, ib, b);
      a.y = antennaHeight(engine, ia);
      b.y = antennaHeight(engine, ib);
      const travel = lost ? Math.min(t, end * (p.outcome === 'partition' ? 0.5 : 0.6)) : smoothstep(t);
      tmp.position.lerpVectors(a, b, Math.max(0, travel));
      tmp.position.y += Math.sin(Math.max(0, Math.min(1, travel)) * Math.PI) * 0.35;
      const fade = lost ? Math.max(0, 1 - Math.max(0, t - end * 0.6) / (end * 0.4 + 0.15)) : 1;
      const size = (p.mapCells > 0 ? 0.07 : 0.045) * (lost ? 0.6 + fade * 0.8 : 1);
      tmp.scale.setScalar(Math.max(0.001, size * (t < 0 ? 0 : 1)));
      tmp.updateMatrix();
      m.setMatrixAt(n, tmp.matrix);
      c.set(lost ? COLORS.down : p.mapCells > 0 ? COLORS.healthy : '#bff7ff').multiplyScalar(lost ? fade * 1.5 : 1.6);
      m.setColorAt(n, c);
      n++;
    }
    active.current = keep;
    m.count = n;
    m.instanceMatrix.needsUpdate = true;
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
  });

  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, MAX_PACKETS]} frustumCulled={false}>
      <sphereGeometry args={[1, 10, 8]} />
      <meshBasicMaterial toneMapped={false} />
    </instancedMesh>
  );
}

/** Red ring around partitioned robots; green burst on reconnection. */
export function PartitionAndReconnect({ engine }: { engine: SimulationEngine }) {
  useSim((s) => s.version);
  const isolated = engine.network.isolatedAgents(engine.step);
  const bursts = engine.rawEvents.filter((e) => (e.event.type === 'rejoined' || e.event.type === 'partition_off') && engine.step - e.step <= 8);
  return (
    <>
      {engine.robots.map((r) => {
        const partitioned = isolated.has(r.name) && r.alive;
        const burst = bursts.find((e) =>
          e.event.type === 'rejoined' ? e.event.robot === r.name : e.event.type === 'partition_off' && e.event.robots.includes(r.name),
        );
        if (!partitioned && !burst) return null;
        return (
          <RobotAnchor key={r.name} engine={engine} id={r.id}>
            {partitioned && <PartitionRing />}
            {burst && <ReconnectBurst key={burst.step} />}
          </RobotAnchor>
        );
      })}
    </>
  );
}

export function RobotAnchor({ engine, id, children }: { engine: SimulationEngine; id: number; children: React.ReactNode }) {
  const ref = useRef<THREE.Group>(null);
  useFrame(() => {
    if (ref.current) robotRenderPosition(engine, id, ref.current.position);
  });
  return <group ref={ref}>{children}</group>;
}

function PartitionRing() {
  const ref = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    const m = ref.current;
    if (!m) return;
    const s = 1 + 0.12 * Math.sin(clock.elapsedTime * 5);
    m.scale.set(s, s, s);
    (m.material as THREE.MeshBasicMaterial).opacity = 0.55 + 0.35 * Math.sin(clock.elapsedTime * 5);
  });
  return (
    <group>
      <mesh ref={ref} rotation-x={-Math.PI / 2} position={[0, 0.08, 0]}>
        <ringGeometry args={[0.85, 1.0, 48]} />
        <meshBasicMaterial color={COLORS.down} transparent toneMapped={false} depthWrite={false} />
      </mesh>
      <mesh position={[0, 2.3, 0]}>
        <octahedronGeometry args={[0.14, 0]} />
        <meshBasicMaterial color={COLORS.down} toneMapped={false} />
      </mesh>
    </group>
  );
}

function ReconnectBurst() {
  const ref = useRef<THREE.Mesh>(null);
  const start = useRef<number | null>(null);
  useFrame(({ clock }) => {
    const m = ref.current;
    if (!m) return;
    if (start.current === null) start.current = clock.elapsedTime;
    const t = Math.min(1, (clock.elapsedTime - start.current) / 1.4);
    const s = 0.6 + t * 4;
    m.scale.set(s, s, s);
    (m.material as THREE.MeshBasicMaterial).opacity = 1 - t;
  });
  return (
    <mesh ref={ref} rotation-x={-Math.PI / 2} position={[0, 0.1, 0]}>
      <ringGeometry args={[0.9, 1.0, 48]} />
      <meshBasicMaterial color={COLORS.healthy} transparent toneMapped={false} depthWrite={false} />
    </mesh>
  );
}

/** Radio range discs (min of own and peer radius applies per link). */
export function CommRanges({ engine, only }: { engine: SimulationEngine; only: string | null }) {
  useSim((s) => s.version);
  return (
    <>
      {engine.robots
        .filter((r) => r.alive && (!only || r.name === only))
        .map((r) => (
          <RobotAnchor key={r.name} engine={engine} id={r.id}>
            <mesh rotation-x={-Math.PI / 2} position={[0, 0.025, 0]}>
              <ringGeometry args={[r.config.commRadius - 0.06, r.config.commRadius, 96]} />
              <meshBasicMaterial color={r.type === 'rover' ? COLORS.rover : COLORS.drone} transparent opacity={0.45} toneMapped={false} depthWrite={false} />
            </mesh>
            <mesh rotation-x={-Math.PI / 2} position={[0, 0.02, 0]}>
              <circleGeometry args={[r.config.commRadius, 96]} />
              <meshBasicMaterial color={r.type === 'rover' ? COLORS.rover : COLORS.drone} transparent opacity={0.035} toneMapped={false} depthWrite={false} />
            </mesh>
          </RobotAnchor>
        ))}
    </>
  );
}
