import { useMemo, useRef } from 'react';
import { useFrame, type ThreeEvent } from '@react-three/fiber';
import { Html, Line } from '@react-three/drei';
import * as THREE from 'three';
import type { SimulationEngine } from '../simulation/core/SimulationEngine';
import type { RobotState } from '../simulation/robots/RobotState';
import { cellToWorld, COLORS, glowTexture, robotRenderPosition, type QualityProfile } from './common';
import { useSim } from '../store/simStore';

const pos = new THREE.Vector3();

function batteryColor(r: RobotState): string {
  if (!r.alive) return '#333';
  const f = r.battery / r.maxBattery;
  return f > 0.5 ? '#3dff8a' : f > 0.2 ? '#ffd23f' : '#ff3b4a';
}

/** Shared per-robot motion: interpolated position, smoothed heading, travel distance. */
function useRobotMotion(engine: SimulationEngine, robot: RobotState, group: React.RefObject<THREE.Group>, height: (t: number) => number) {
  const state = useRef({ yaw: robot.heading, travelled: 0, last: new THREE.Vector3(NaN, 0, 0) });
  useFrame(({ clock }, dt) => {
    const g = group.current;
    if (!g) return;
    robotRenderPosition(engine, robot.id, pos);
    const s = state.current;
    if (!Number.isNaN(s.last.x)) s.travelled += pos.distanceTo(s.last);
    s.last.copy(pos);
    g.position.set(pos.x, height(clock.elapsedTime), pos.z);
    // Shortest-arc yaw smoothing towards the robot's latest heading.
    let diff = robot.heading - s.yaw;
    diff = Math.atan2(Math.sin(diff), Math.cos(diff));
    s.yaw += diff * Math.min(1, dt * 8);
    g.rotation.y = s.yaw;
  });
  return state;
}

function SelectionRing({ selected, color }: { selected: boolean; color: string }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (!ref.current) return;
    const s = 1 + Math.sin(clock.elapsedTime * 4) * 0.06;
    ref.current.scale.set(s, s, s);
  });
  if (!selected) return null;
  return (
    <mesh ref={ref} rotation-x={-Math.PI / 2} position={[0, 0.03, 0]}>
      <ringGeometry args={[0.55, 0.64, 40]} />
      <meshBasicMaterial color={color} transparent opacity={0.9} toneMapped={false} />
    </mesh>
  );
}

/** Expanding floor sweep showing the sensor footprint. */
function ScanSweep({ radius, color, period, y = 0.04 }: { radius: number; color: string; period: number; y?: number }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    const m = ref.current;
    if (!m) return;
    const t = (clock.elapsedTime % period) / period;
    const s = 0.3 + t * radius;
    m.scale.set(s, s, s);
    (m.material as THREE.MeshBasicMaterial).opacity = 0.55 * (1 - t);
  });
  return (
    <mesh ref={ref} rotation-x={-Math.PI / 2} position={[0, y, 0]}>
      <ringGeometry args={[0.92, 1, 48]} />
      <meshBasicMaterial color={color} transparent depthWrite={false} toneMapped={false} />
    </mesh>
  );
}

function RobotLabel({ robot, manual }: { robot: RobotState; manual: boolean }) {
  const show = useSim((s) => s.overlays.labels);
  if (!show) return null;
  return (
    <Html position={[0, robot.type === 'drone' ? 0.55 : 1.0, 0]} center zIndexRange={[20, 0]} style={{ pointerEvents: 'none' }}>
      <div className={`robot-tag ${robot.type} ${robot.alive ? '' : 'dead'}`}>
        {manual && <span className="tag-manual">MANUAL</span>}
        {robot.label}
      </div>
    </Html>
  );
}

export function Rover({ engine, robot, quality, selected, onSelect }: RobotProps) {
  const group = useRef<THREE.Group>(null);
  const wheels = useRef<Array<THREE.Mesh | null>>([]);
  const lidar = useRef<THREE.Mesh>(null);
  const led = useRef<THREE.MeshBasicMaterial>(null);
  const motion = useRobotMotion(engine, robot, group, () => 0);
  useFrame(({ clock }) => {
    const roll = motion.current.travelled / 0.13;
    for (const w of wheels.current) if (w) w.rotation.x = roll;
    if (lidar.current && robot.alive) lidar.current.rotation.y = clock.elapsedTime * 6;
    if (led.current) {
      led.current.color.set(batteryColor(robot));
      if (robot.alive && robot.battery / robot.maxBattery < 0.2) led.current.color.multiplyScalar(0.5 + 0.5 * Math.abs(Math.sin(clock.elapsedTime * 6)));
    }
  });
  const body = robot.alive ? '#e8892c' : '#555';
  const wheelPositions: Array<[number, number, number]> = [
    [0.31, 0.13, 0.22],
    [-0.31, 0.13, 0.22],
    [0.31, 0.13, -0.22],
    [-0.31, 0.13, -0.22],
  ];
  return (
    <group ref={group} onClick={onSelect}>
      <mesh position={[0, 0.24, 0]} castShadow>
        <boxGeometry args={[0.5, 0.18, 0.68]} />
        <meshStandardMaterial color={body} roughness={0.5} metalness={0.35} />
      </mesh>
      <mesh position={[0, 0.36, -0.04]} castShadow>
        <boxGeometry args={[0.4, 0.07, 0.46]} />
        <meshStandardMaterial color="#2a2d33" roughness={0.6} metalness={0.5} />
      </mesh>
      {/* Bumper and roll cage */}
      <mesh position={[0, 0.2, 0.37]}>
        <boxGeometry args={[0.54, 0.08, 0.05]} />
        <meshStandardMaterial color="#1c1c1f" metalness={0.7} roughness={0.4} />
      </mesh>
      {wheelPositions.map((p, i) => (
        <mesh key={i} ref={(el) => (wheels.current[i] = el)} position={p} rotation-z={Math.PI / 2} castShadow>
          <cylinderGeometry args={[0.13, 0.13, 0.11, 14]} />
          <meshStandardMaterial color="#141414" roughness={0.95} />
        </mesh>
      ))}
      {/* Sensor mast with spinning lidar head */}
      <mesh position={[0, 0.52, -0.16]}>
        <cylinderGeometry args={[0.022, 0.022, 0.3, 8]} />
        <meshStandardMaterial color="#888" metalness={0.8} roughness={0.3} />
      </mesh>
      <mesh ref={lidar} position={[0, 0.7, -0.16]}>
        <cylinderGeometry args={[0.075, 0.075, 0.07, 16]} />
        <meshStandardMaterial color="#1b1f26" emissive={robot.alive ? COLORS.drone : '#000'} emissiveIntensity={0.6} metalness={0.6} />
      </mesh>
      {/* Headlights */}
      {[-0.14, 0.14].map((x) => (
        <mesh key={x} position={[x, 0.26, 0.345]}>
          <boxGeometry args={[0.08, 0.05, 0.02]} />
          <meshBasicMaterial color={robot.alive ? '#fff6d8' : '#222'} toneMapped={false} />
        </mesh>
      ))}
      {robot.alive && quality.robotSpotlights && <Headlight />}
      {robot.alive && (
        <mesh position={[0, 0.03, 1.0]} rotation-x={-Math.PI / 2}>
          <planeGeometry args={[1.0, 1.6]} />
          <meshBasicMaterial map={glowTexture()} color="#fff1c4" transparent opacity={0.28} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
        </mesh>
      )}
      <mesh position={[0.16, 0.41, -0.26]}>
        <sphereGeometry args={[0.035, 10, 10]} />
        <meshBasicMaterial ref={led} toneMapped={false} />
      </mesh>
      {robot.alive && <ScanSweep radius={robot.config.visionRadius} color={COLORS.rover} period={1.6} />}
      <SelectionRing selected={selected} color={COLORS.rover} />
      <RobotLabel robot={robot} manual={robot.manual} />
    </group>
  );
}

function Headlight() {
  const light = useRef<THREE.SpotLight>(null);
  const target = useMemo(() => new THREE.Object3D(), []);
  return (
    <>
      <primitive object={target} position={[0, 0, 3]} />
      <spotLight ref={light} position={[0, 0.3, 0.35]} target={target} angle={0.6} penumbra={0.6} intensity={8} distance={7} color="#fff1c4" />
    </>
  );
}

export function Drone({ engine, robot, quality, selected, onSelect }: RobotProps) {
  const group = useRef<THREE.Group>(null);
  const rotors = useRef<Array<THREE.Group | null>>([]);
  const shadow = useRef<THREE.Mesh>(null);
  const altitude = (t: number) => (robot.alive ? 1.55 + Math.sin(t * 2.1 + robot.id) * 0.07 : 0.12);
  useRobotMotion(engine, robot, group, altitude);
  const led = useRef<THREE.MeshBasicMaterial>(null);
  useFrame(({ clock }, dt) => {
    if (robot.alive) for (const r of rotors.current) if (r) r.rotation.y += dt * 40;
    if (shadow.current && group.current) {
      // Ground shadow stays on the floor to give an altitude cue.
      shadow.current.position.y = -group.current.position.y + 0.02;
    }
    if (led.current) led.current.color.set(batteryColor(robot));
    if (group.current && robot.alive) group.current.rotation.z = Math.sin(clock.elapsedTime * 1.3 + robot.id) * 0.04;
  });
  const arms: Array<[number, number]> = [
    [0.3, 0.3],
    [-0.3, 0.3],
    [0.3, -0.3],
    [-0.3, -0.3],
  ];
  return (
    <group ref={group} onClick={onSelect}>
      <mesh castShadow>
        <boxGeometry args={[0.26, 0.09, 0.32]} />
        <meshStandardMaterial color={robot.alive ? '#e9eef2' : '#555'} roughness={0.35} metalness={0.4} />
      </mesh>
      <mesh position={[0, 0.06, 0]}>
        <sphereGeometry args={[0.1, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2]} />
        <meshStandardMaterial color="#1d2a33" metalness={0.6} roughness={0.2} emissive={COLORS.drone} emissiveIntensity={robot.alive ? 0.25 : 0} />
      </mesh>
      {[Math.PI / 4, -Math.PI / 4].map((a) => (
        <mesh key={a} rotation-y={a}>
          <boxGeometry args={[0.86, 0.025, 0.045]} />
          <meshStandardMaterial color="#2b3138" metalness={0.5} roughness={0.5} />
        </mesh>
      ))}
      {arms.map(([x, z], i) => (
        <group key={i} position={[x, 0.04, z]} ref={(el) => (rotors.current[i] = el)}>
          <mesh rotation-x={-Math.PI / 2}>
            <circleGeometry args={[0.17, 24]} />
            <meshBasicMaterial color="#cfe9ff" transparent opacity={robot.alive ? 0.16 : 0.05} depthWrite={false} side={THREE.DoubleSide} />
          </mesh>
          <mesh>
            <boxGeometry args={[0.32, 0.008, 0.03]} />
            <meshStandardMaterial color="#111" transparent opacity={0.7} />
          </mesh>
        </group>
      ))}
      <mesh position={[0, -0.05, 0.17]}>
        <sphereGeometry args={[0.03, 8, 8]} />
        <meshBasicMaterial ref={led} toneMapped={false} />
      </mesh>
      {robot.alive && (
        <>
          {/* Searchlight cone */}
          <mesh position={[0, -0.8, 0]}>
            <coneGeometry args={[1.25, 1.55, 24, 1, true]} />
            <meshBasicMaterial color={COLORS.drone} transparent opacity={0.07} depthWrite={false} blending={THREE.AdditiveBlending} side={THREE.DoubleSide} toneMapped={false} />
          </mesh>
          {quality.robotSpotlights && <DroneSpot />}
        </>
      )}
      <group>
        <mesh ref={shadow} rotation-x={-Math.PI / 2}>
          <planeGeometry args={[2.6, 2.6]} />
          <meshBasicMaterial map={glowTexture()} color={robot.alive ? '#9fe8ff' : '#000'} transparent opacity={robot.alive ? 0.32 : 0.4} depthWrite={false} blending={robot.alive ? THREE.AdditiveBlending : THREE.NormalBlending} toneMapped={false} />
        </mesh>
      </group>
      {robot.alive && <DroneSweep radius={robot.config.visionRadius} />}
      <SelectionRing selected={selected} color={COLORS.drone} />
      <RobotLabel robot={robot} manual={robot.manual} />
    </group>
  );
}

/** Drone sensor pulse rendered on the floor beneath the aircraft. */
function DroneSweep({ radius }: { radius: number }) {
  const ref = useRef<THREE.Group>(null);
  useFrame(() => {
    const g = ref.current;
    if (g && g.parent) g.position.y = -g.parent.position.y;
  });
  return (
    <group ref={ref}>
      <ScanSweep radius={radius} color={COLORS.drone} period={2.2} y={0.05} />
    </group>
  );
}

function DroneSpot() {
  const target = useMemo(() => new THREE.Object3D(), []);
  return (
    <>
      <primitive object={target} position={[0, -3, 0.2]} />
      <spotLight position={[0, -0.05, 0]} target={target} angle={0.7} penumbra={0.7} intensity={10} distance={6} color="#bfefff" />
    </>
  );
}

interface RobotProps {
  engine: SimulationEngine;
  robot: RobotState;
  quality: QualityProfile;
  selected: boolean;
  onSelect: (e: ThreeEvent<MouseEvent>) => void;
}

export function Robots({ engine, quality }: { engine: SimulationEngine; quality: QualityProfile }) {
  const selected = useSim((s) => s.selected);
  const select = useSim((s) => s.select);
  useSim((s) => s.version);
  return (
    <>
      {engine.robots.map((r) => {
        const Comp = r.type === 'rover' ? Rover : Drone;
        return (
          <Comp
            key={r.name}
            engine={engine}
            robot={r}
            quality={quality}
            selected={selected === r.name}
            onSelect={(e) => {
              e.stopPropagation();
              select(selected === r.name ? null : r.name);
            }}
          />
        );
      })}
    </>
  );
}

/** Planned path of each robot, from its own local A* plan. */
export function RobotPaths({ engine }: { engine: SimulationEngine }) {
  useSim((s) => s.version);
  const selected = useSim((s) => s.selected);
  return (
    <>
      {engine.robots.map((r) => {
        if (!r.alive || r.path.length < 2) return null;
        const pts = r.path.slice(0, 40).map((p) => {
          const w = cellToWorld(engine, p.x, p.y);
          return [w.x, 0.06, w.z] as [number, number, number];
        });
        const color = r.manual ? COLORS.manual : r.type === 'rover' ? COLORS.rover : COLORS.drone;
        const goal = pts[pts.length - 1];
        const emphasis = !selected || selected === r.name;
        return (
          <group key={r.name}>
            <Line points={pts} color={color} lineWidth={emphasis ? 2.2 : 1.2} dashed dashSize={0.35} gapSize={0.2} transparent opacity={emphasis ? 0.85 : 0.35} />
            <mesh position={goal} rotation-x={-Math.PI / 2}>
              <ringGeometry args={[0.22, 0.3, 4]} />
              <meshBasicMaterial color={color} transparent opacity={emphasis ? 0.9 : 0.4} toneMapped={false} />
            </mesh>
          </group>
        );
      })}
    </>
  );
}
