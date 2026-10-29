import { useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import * as THREE from 'three';
import type { SimulationEngine } from '../simulation/core/SimulationEngine';
import { evidencePosition, maxThermal } from '../simulation/sensing/SensorModel';
import { UNKNOWN } from '../simulation/world/GridMap';
import { cellToWorld, COLORS, glowTexture, type QualityProfile } from './common';
import { RobotAnchor } from './Network';
import { useSim } from '../store/simStore';
import { SurvivorRescue } from './SurvivorRescue';

/**
 * A pale ground tint marks space that has not been sensed. Selecting a robot
 * shows its private belief; otherwise the tint combines delivered observations.
 */
export function CoverageFog({ engine, robot }: { engine: SimulationEngine; robot: string | null }) {
  const version = useSim((s) => s.version);
  const { width, height } = engine.scenario;
  const texture = useMemo(() => {
    const t = new THREE.DataTexture(new Uint8Array(width * height * 4), width, height, THREE.RGBAFormat);
    t.magFilter = THREE.LinearFilter;
    t.minFilter = THREE.LinearFilter;
    t.flipY = false;
    t.colorSpace = THREE.SRGBColorSpace;
    return t;
  }, [width, height]);
  useEffect(() => () => texture.dispose(), [texture]);

  useEffect(() => {
    const data = texture.image.data as Uint8Array;
    const only = robot ? engine.robots.find((r) => r.name === robot) : null;
    const sources = only ? [only] : engine.robots;
    for (let i = 0; i < width * height; i++) {
      let known = false;
      for (const r of sources)
        if (r.belief.cells[i] !== UNKNOWN) {
          known = true;
          break;
        }
      // Rows map to world +z; the plane is rotated so v runs along -z.
      const x = i % width;
      const y = Math.floor(i / width);
      const o = ((height - 1 - y) * width + x) * 4;
      data[o] = only ? 214 : 226;
      data[o + 1] = only ? 226 : 234;
      data[o + 2] = only ? 220 : 216;
      // An understated sage tint keeps terrain and agents readable, even before launch.
      data[o + 3] = known ? 0 : only ? 100 : 88;
    }
    texture.needsUpdate = true;
  }, [engine, robot, texture, version, width, height]);

  return (
    <mesh rotation-x={-Math.PI / 2} position={[0, 0.035, 0]} renderOrder={1}>
      <planeGeometry args={[width, height]} />
      <meshBasicMaterial map={texture} transparent depthWrite={false} toneMapped={false} />
    </mesh>
  );
}

/** Only actual confirmation events create human figures and rescue celebrations. */
export function Survivors({ engine, quality }: { engine: SimulationEngine; quality: QualityProfile }) {
  useSim((s) => s.version);
  return <>{engine.discoveredSurvivors().map((victim) => <SurvivorRescue key={victim.id} engine={engine} index={victim.id} quality={quality} position={cellToWorld(engine, victim.x, victim.y)} />)}</>;
}

/** Draft positions are visible only while the operator is editing the mission. */
export function PlacementMarkers({ engine }: { engine: SimulationEngine }) {
  const ref = useRef<THREE.InstancedMesh>(null);
  const victims = engine.scenario.victims;
  useEffect(() => {
    if (!ref.current) return;
    const object = new THREE.Object3D();
    for (let i = 0; i < victims.length; i++) {
      cellToWorld(engine, victims[i].x, victims[i].y, object.position);
      object.position.y = 0.3;
      object.updateMatrix();
      ref.current.setMatrixAt(i, object.matrix);
    }
    ref.current.count = victims.length;
    ref.current.instanceMatrix.needsUpdate = true;
    ref.current.computeBoundingSphere();
  }, [engine, victims]);
  return <instancedMesh ref={ref} args={[undefined, undefined, Math.max(1, victims.length)]} name="survivor-placement-markers" onClick={(event) => {
    if (event.delta > 4 || event.instanceId === undefined) return;
    event.stopPropagation();
    const victim = victims[event.instanceId];
    if (victim) useSim.getState().toggleSurvivorAt({ x: victim.x, y: victim.y });
  }}>
    <sphereGeometry args={[0.3, 10, 8]} />
    <meshBasicMaterial color="#d88742" toneMapped={false} />
  </instancedMesh>;
}

/** DEBUG ONLY: ground-truth survivor positions, never shown in the normal operator view. */
export function TruthDebug({ engine }: { engine: SimulationEngine }) {
  useSim((s) => s.version);
  return (
    <>
      {engine.scenario.victims
        .filter((v) => !v.found)
        .map((v) => {
          const p = cellToWorld(engine, v.x, v.y);
          return (
            <group key={v.id} position={p}>
              <mesh position={[0, 0.25, 0]}>
                <sphereGeometry args={[0.25, 12, 10]} />
                <meshBasicMaterial color="#ff2bd6" transparent opacity={0.65} toneMapped={false} />
              </mesh>
              <mesh position={[0, 1.6, 0]}>
                <cylinderGeometry args={[0.02, 0.02, 3, 6]} />
                <meshBasicMaterial color="#ff2bd6" toneMapped={false} />
              </mesh>
              <Html position={[0, 3.2, 0]} center style={{ pointerEvents: 'none' }}>
                <div className="debug-tag">DEBUG · truth</div>
              </Html>
            </group>
          );
        })}
    </>
  );
}

/**
 * Sensor evidence derived from each robot's *own* readings: heat-source
 * estimates (from odometry + strongest sector) and acoustic pings.
 */
export function EvidenceMarkers({ engine }: { engine: SimulationEngine }) {
  useSim((s) => s.version);
  return (
    <>
      {engine.robots.map((r) => {
        if (!r.alive) return null;
        const thermal = maxThermal(r.thermal);
        const est = thermal >= 0.16 ? evidencePosition(r) : null;
        const sound = r.acoustic >= 0.2;
        return (
          <group key={r.name}>
            {est && <HeatMarker position={cellToWorld(engine, est.x, est.y)} strength={thermal} />}
            {sound && (
              <RobotAnchor engine={engine} id={r.id}>
                <SoundPing strength={r.acoustic} />
              </RobotAnchor>
            )}
          </group>
        );
      })}
    </>
  );
}

function HeatMarker({ position, strength }: { position: THREE.Vector3; strength: number }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (ref.current) ref.current.scale.setScalar(1 + 0.15 * Math.sin(clock.elapsedTime * 7));
  });
  const size = 1.2 + Math.min(1, strength) * 2.2;
  return (
    <mesh ref={ref} position={[position.x, 0.06, position.z]} rotation-x={-Math.PI / 2}>
      <planeGeometry args={[size, size]} />
      <meshBasicMaterial map={glowTexture()} color={COLORS.heat} transparent opacity={0.4 + Math.min(0.5, strength)} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
    </mesh>
  );
}

function SoundPing({ strength }: { strength: number }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    const m = ref.current;
    if (!m) return;
    const p = (clock.elapsedTime % 1.1) / 1.1;
    m.scale.setScalar(0.5 + p * (2 + strength * 3));
    (m.material as THREE.MeshBasicMaterial).opacity = 0.7 * (1 - p);
  });
  return (
    <mesh ref={ref} rotation-x={-Math.PI / 2} position={[0, 0.07, 0]}>
      <ringGeometry args={[0.9, 1, 40]} />
      <meshBasicMaterial color={COLORS.sound} transparent depthWrite={false} toneMapped={false} />
    </mesh>
  );
}

/** Floating dust/smoke particles. */
export function Dust({ engine, count, fog }: { engine: SimulationEngine; count: number; fog: number }) {
  const ref = useRef<THREE.Points>(null);
  const { width, height } = engine.scenario;
  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry();
    const p = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      p[i * 3] = (Math.random() - 0.5) * width;
      p[i * 3 + 1] = Math.random() * 3;
      p[i * 3 + 2] = (Math.random() - 0.5) * height;
    }
    g.setAttribute('position', new THREE.BufferAttribute(p, 3));
    return g;
  }, [count, width, height]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  useFrame((_, dt) => {
    const arr = geometry.attributes.position.array as Float32Array;
    for (let i = 0; i < count; i++) {
      arr[i * 3] += Math.sin(i + arr[i * 3 + 1]) * dt * 0.05;
      arr[i * 3 + 1] += dt * (0.03 + (i % 7) * 0.006);
      if (arr[i * 3 + 1] > 3) arr[i * 3 + 1] = 0;
    }
    geometry.attributes.position.needsUpdate = true;
  });
  return (
    <points ref={ref} geometry={geometry} frustumCulled={false}>
      <pointsMaterial map={glowTexture()} size={0.12} sizeAttenuation color="#d8c9b0" transparent opacity={0.25 + fog * 0.35} depthWrite={false} toneMapped={false} />
    </points>
  );
}
