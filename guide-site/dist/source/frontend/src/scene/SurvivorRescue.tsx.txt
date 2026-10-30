import { useEffect, useMemo, useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import { Html, RoundedBox } from '@react-three/drei';
import * as THREE from 'three';
import type { SimulationEngine } from '../simulation/core/SimulationEngine';
import type { QualityProfile } from './common';
import { RESCUE_CELEBRATION_SECONDS, rescueCelebrationProgress, rescueCelebrationStart } from './rescueCelebration';
import { survivorStory } from '../presentation/survivorStories';
import { useSim } from '../store/simStore';

function useReducedMotion() {
  const [reduced, setReduced] = useState(() => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const change = () => setReduced(preference.matches);
    preference.addEventListener('change', change);
    return () => preference.removeEventListener('change', change);
  }, []);
  return reduced;
}

type Position = [number, number, number];

/** Rounded joints keep the small figure recognizably human at inspection zoom. */
function Limb({ from, to, radius, color, shadow }: { from: Position; to: Position; radius: number; color: string; shadow: boolean }) {
  const transform = useMemo(() => {
    const start = new THREE.Vector3(...from);
    const end = new THREE.Vector3(...to);
    const direction = end.clone().sub(start);
    return {
      length: Math.max(0.015, direction.length() - radius * 2),
      position: start.add(end).multiplyScalar(0.5),
      quaternion: new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize()),
    };
  }, [from[0], from[1], from[2], to[0], to[1], to[2], radius]);
  return <mesh position={transform.position} quaternion={transform.quaternion} castShadow={shadow}>
    <capsuleGeometry args={[radius, transform.length, 3, 8]} />
    <meshStandardMaterial color={color} roughness={0.9} />
  </mesh>;
}

/** Civilians rest where the team confirmed them; this is not an evacuation animation. */
function SurvivorPerson({ index, start, reducedMotion, shadows }: { index: number; start: number; reducedMotion: boolean; shadows: boolean }) {
  const wave = useRef<THREE.Group>(null);
  const skin = ['#d8a37c', '#a76f4f', '#e3b38e', '#c58b65'][index % 4];
  const hair = ['#51412f', '#303931', '#735037', '#44372c'][index % 4];
  const shirt = ['#d99953', '#629fa9', '#b67e79', '#8494b7'][index % 4];
  useFrame(() => {
    if (!wave.current) return;
    const age = performance.now() / 1000 - start;
    const lift = reducedMotion ? 0 : 1 - THREE.MathUtils.smoothstep(age, 1.15, 2.0);
    wave.current.rotation.z = 0.04 + lift * (2.3 + Math.sin(age * 11) * 0.15);
  });
  return <group position={[-0.08, 0, 0.02]} name="survivor-person">
    <RoundedBox args={[0.33, 0.31, 0.28]} radius={0.055} smoothness={1} position={[0, 0.155, -0.035]} castShadow={shadows}>
      <meshStandardMaterial color="#b8a88d" roughness={1} />
    </RoundedBox>
    <RoundedBox args={[0.27, 0.17, 0.23]} radius={0.055} smoothness={2} position={[0, 0.385, 0]} castShadow={shadows}>
      <meshStandardMaterial color="#5a7280" roughness={0.95} />
    </RoundedBox>
    <RoundedBox args={[0.31, 0.43, 0.23]} radius={0.065} smoothness={2} position={[0, 0.68, 0]} castShadow={shadows}>
      <meshStandardMaterial color={shirt} roughness={0.85} />
    </RoundedBox>
    <mesh position={[0, 0.915, 0]}>
      <cylinderGeometry args={[0.056, 0.06, 0.1, 8]} />
      <meshStandardMaterial color={skin} roughness={0.9} />
    </mesh>
    <group position={[0, 1.08, 0.015]}>
      <mesh scale={[0.92, 1.08, 0.94]} castShadow={shadows}>
        <sphereGeometry args={[0.139, 12, 10]} />
        <meshStandardMaterial color={skin} roughness={0.9} flatShading />
      </mesh>
      <mesh position={[0, 0.02, -0.009]} scale={[0.95, 1.05, 1.01]} castShadow={shadows}>
        <sphereGeometry args={[0.142, 12, 6, 0, Math.PI * 2, 0, Math.PI * 0.49]} />
        <meshStandardMaterial color={hair} roughness={1} flatShading />
      </mesh>
      {[-1, 1].map((side) => <group key={side}>
        <mesh position={[side * 0.127, -0.005, 0]}>
          <sphereGeometry args={[0.029, 8, 6]} />
          <meshStandardMaterial color={skin} roughness={0.9} />
        </mesh>
        <mesh position={[side * 0.044, 0.014, 0.125]}>
          <sphereGeometry args={[0.012, 6, 6]} />
          <meshBasicMaterial color="#354139" />
        </mesh>
      </group>)}
      <mesh position={[0, -0.022, 0.136]}>
        <sphereGeometry args={[0.022, 8, 6]} />
        <meshStandardMaterial color={skin} roughness={0.9} />
      </mesh>
      <mesh position={[0, -0.061, 0.123]} rotation-z={0.03}>
        <boxGeometry args={[0.037, 0.007, 0.008]} />
        <meshBasicMaterial color="#a16f58" />
      </mesh>
    </group>
    {[-1, 1].map((side) => <group key={side}>
      <Limb from={[side * 0.09, 0.39, 0.025]} to={[side * 0.12, 0.245, 0.275]} radius={0.073} color="#5a7280" shadow={shadows} />
      <Limb from={[side * 0.12, 0.245, 0.275]} to={[side * 0.13, 0.085, 0.39]} radius={0.057} color="#526b77" shadow={shadows} />
      <RoundedBox args={[0.13, 0.09, 0.23]} radius={0.025} smoothness={1} position={[side * 0.13, 0.055, 0.43]} castShadow={shadows}>
        <meshStandardMaterial color="#3f514d" roughness={0.95} />
      </RoundedBox>
    </group>)}
    <Limb from={[-0.18, 0.82, 0]} to={[-0.235, 0.575, 0.095]} radius={0.053} color={shirt} shadow={shadows} />
    <Limb from={[-0.235, 0.575, 0.095]} to={[-0.19, 0.44, 0.29]} radius={0.043} color={skin} shadow={shadows} />
    <mesh position={[-0.19, 0.43, 0.31]} scale={[0.8, 1, 0.85]}>
      <sphereGeometry args={[0.055, 8, 6]} />
      <meshStandardMaterial color={skin} roughness={0.9} />
    </mesh>
    <group ref={wave} position={[0.18, 0.82, 0]} rotation-x={-0.13}>
      <Limb from={[0, 0, 0]} to={[0.045, -0.245, 0.06]} radius={0.053} color={shirt} shadow={shadows} />
      <Limb from={[0.045, -0.245, 0.06]} to={[0.015, -0.37, 0.24]} radius={0.043} color={skin} shadow={shadows} />
      <mesh position={[0.015, -0.38, 0.265]} scale={[0.8, 1, 0.85]}>
        <sphereGeometry args={[0.055, 8, 6]} />
        <meshStandardMaterial color={skin} roughness={0.9} />
      </mesh>
    </group>
  </group>;
}

function makeRescueFlagTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 128;
  const context = canvas.getContext('2d')!;
  context.fillStyle = '#417553';
  context.fillRect(0, 0, 256, 128);
  context.strokeStyle = '#dbedc5';
  context.lineWidth = 3;
  context.strokeRect(8, 8, 240, 112);
  context.fillStyle = '#fbf9d9';
  context.font = 'bold 25px sans-serif';
  context.textAlign = 'center';
  context.fillText('SURVIVOR', 128, 53);
  context.fillText('SAVED', 128, 89);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function RescueFlag({ reducedMotion, shadows, index }: { reducedMotion: boolean; shadows: boolean; index: number }) {
  const geometry = useMemo(() => new THREE.PlaneGeometry(0.73, 0.37, 8, 2), []);
  const texture = useMemo(makeRescueFlagTexture, []);
  useEffect(() => () => { geometry.dispose(); texture.dispose(); }, [geometry, texture]);
  useFrame(({ clock }) => {
    if (reducedMotion) return;
    const positions = geometry.attributes.position;
    for (let i = 0; i < positions.count; i++) {
      const x = positions.getX(i);
      positions.setZ(i, Math.sin(clock.elapsedTime * 2.8 - x * 8 + index) * 0.025 * (x / 0.73 + 0.5));
    }
    positions.needsUpdate = true;
  });
  return <group position={[0.43, 0, -0.11]} name="survivor-saved-flag">
    <mesh position={[0, 0.8, 0]} castShadow={shadows}>
      <cylinderGeometry args={[0.017, 0.022, 1.6, 8]} />
      <meshStandardMaterial color="#778b72" roughness={0.7} />
    </mesh>
    <mesh position={[0, 1.62, 0]}>
      <sphereGeometry args={[0.032, 8, 6]} />
      <meshStandardMaterial color="#ddc37c" roughness={0.6} />
    </mesh>
    <mesh position={[0.355, 1.375, 0]} geometry={geometry}>
      <meshStandardMaterial map={texture} roughness={0.95} side={THREE.DoubleSide} />
    </mesh>
  </group>;
}

function RescueConfetti({ start, count, index }: { start: number; count: number; index: number }) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const object = useRef(new THREE.Object3D());
  const material = useRef<THREE.MeshBasicMaterial>(null);
  const [active, setActive] = useState(() => rescueCelebrationProgress(start, performance.now() / 1000) < 1);
  const particles = useMemo(() => {
    const data = new Float32Array(count * 5);
    for (let i = 0; i < count; i++) {
      data[i * 5] = i * 2.39996 + index;
      data[i * 5 + 1] = 0.38 + ((i * 17 + index * 7) % 19) / 19 * 0.7;
      data[i * 5 + 2] = 1.9 + ((i * 11 + index * 3) % 17) / 17 * 0.9;
      data[i * 5 + 3] = (i % 2 ? -1 : 1) * (3 + i % 6);
      data[i * 5 + 4] = i * 0.73;
    }
    return data;
  }, [count, index]);
  useEffect(() => {
    if (!mesh.current) return;
    const color = new THREE.Color();
    const palette = ['#f0ca64', '#65b69a', '#d78c74', '#e8dfb1', '#90b8ca'];
    for (let i = 0; i < count; i++) mesh.current.setColorAt(i, color.set(palette[i % palette.length]));
    if (mesh.current.instanceColor) mesh.current.instanceColor.needsUpdate = true;
  }, [count]);
  useFrame(() => {
    if (!active || !mesh.current) return;
    const now = performance.now() / 1000;
    const progress = rescueCelebrationProgress(start, now);
    if (progress >= 1) {
      mesh.current.visible = false;
      setActive(false);
      return;
    }
    const age = progress * RESCUE_CELEBRATION_SECONDS;
    for (let i = 0; i < count; i++) {
      const offset = i * 5;
      const angle = particles[offset];
      const speed = particles[offset + 1];
      const spin = particles[offset + 3];
      const y = 0.65 + particles[offset + 2] * age - 1.9 * age * age;
      object.current.position.set(Math.cos(angle) * speed * age * 0.68, Math.max(0.03, y), Math.sin(angle) * speed * age * 0.68);
      object.current.rotation.set(age * spin, particles[offset + 4] + age * spin * 0.7, age * spin * 0.45);
      object.current.scale.setScalar(y < 0 ? Math.max(0, 1 - (age - 1.4) * 2) : 1);
      object.current.updateMatrix();
      mesh.current.setMatrixAt(i, object.current.matrix);
    }
    mesh.current.instanceMatrix.needsUpdate = true;
    if (material.current) material.current.opacity = Math.min(1, (1 - progress) / 0.2);
  });
  if (!active) return null;
  return <instancedMesh ref={mesh} args={[undefined, undefined, count]} frustumCulled={false} name="rescue-confetti">
    <planeGeometry args={[0.045, 0.085]} />
    <meshBasicMaterial ref={material} color="#ffffff" side={THREE.DoubleSide} transparent depthWrite={false} toneMapped={false} />
  </instancedMesh>;
}

/** Found-only presentation; a saved flag denotes confirmation, not physical extraction. */
export function SurvivorRescue({ engine, position, quality, index }: { engine: SimulationEngine; position: THREE.Vector3; quality: QualityProfile; index: number }) {
  const cleanView = useSim((s) => s.cleanView);
  const inspecting = useSim((s) => s.encounter !== null);
  const name = survivorStory(engine.scenario.seed, index).name;
  const reducedMotion = useReducedMotion();
  const [start] = useState(() => rescueCelebrationStart(engine, index, performance.now() / 1000));
  return <group position={position} name={'confirmed-survivor-' + index} onClick={(event) => {
    event.stopPropagation();
    if (event.delta <= 4) useSim.getState().inspectSurvivor(index);
  }}>
    <mesh rotation-x={-Math.PI / 2} position={[0, 0.025, 0]}>
      <ringGeometry args={[0.49, 0.53, 32]} />
      <meshBasicMaterial color="#6a9d67" transparent opacity={0.65} depthWrite={false} toneMapped={false} />
    </mesh>
    <SurvivorPerson index={index} start={start} reducedMotion={reducedMotion} shadows={quality.shadows} />
    <RescueFlag reducedMotion={reducedMotion} shadows={quality.shadows} index={index} />
    {!reducedMotion && <RescueConfetti start={start} count={quality.shadows ? 36 : 20} index={index} />}
    {!cleanView && !inspecting && <Html position={[0, 1.85, 0]} center zIndexRange={[15, 0]}>
      <button type="button" className="survivor-saved-tag" aria-label={`Talk to survivor ${index + 1}`} title={`Hear ${name}’s story`} onClick={(event) => { event.stopPropagation(); useSim.getState().inspectSurvivor(index); }}><span className="saved-check" aria-hidden>✓</span><span>{name}</span><span className="survivor-chat" aria-hidden>···</span></button>
    </Html>}
  </group>;
}
