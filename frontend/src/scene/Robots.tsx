import { useRef } from 'react';
import { useFrame, type ThreeEvent } from '@react-three/fiber';
import { Html, Line, RoundedBox } from '@react-three/drei';
import * as THREE from 'three';
import type { SimulationEngine } from '../simulation/core/SimulationEngine';
import type { RobotState } from '../simulation/robots/RobotState';
import { cellToWorld, COLORS, glowTexture, robotRenderPosition, type QualityProfile } from './common';
import { useSim } from '../store/simStore';
import { batteryFillStyle, batteryPct } from '../app/format';

const WHEEL_POSITIONS: Array<[number, number, number]> = [
  [-0.36, 0.17, 0.25], [0.36, 0.17, 0.25],
  [-0.36, 0.17, -0.25], [0.36, 0.17, -0.25],
];
const ARM_ANGLES = [Math.PI / 4, (3 * Math.PI) / 4, (5 * Math.PI) / 4, (7 * Math.PI) / 4];
const ROTOR_SPEED = 92;

function batteryColor(robot: RobotState): string {
  if (!robot.alive) return '#77817d';
  const fraction = robot.battery / robot.maxBattery;
  return fraction > 0.5 ? '#35c58a' : fraction > 0.2 ? '#e8ac40' : '#e86752';
}

/** Rendering follows the physics segment, including its actual direction of travel. */
function useRobotMotion(engine: SimulationEngine, robot: RobotState, group: React.RefObject<THREE.Group>, preview = false, still = false) {
  const state = useRef({
    yaw: preview ? 0.55 : robot.heading,
    travelled: 0,
    speed: 0,
    turn: 0,
    position: new THREE.Vector3(),
    previous: new THREE.Vector3(),
    initialized: false,
  });
  useFrame(({ clock }, delta) => {
    const node = group.current;
    if (!node) return;
    if (preview) {
      node.position.set(0, robot.type === 'rover' ? -0.4 : 0, 0);
      if (!still) state.current.yaw += Math.min(delta, 0.05) * 0.35;
      node.rotation.y = state.current.yaw;
      return;
    }
    const motion = state.current;
    const dt = Math.min(delta, 0.1);
    robotRenderPosition(engine, robot.id, motion.position);
    if (motion.initialized) {
      const distance = motion.previous.distanceTo(motion.position);
      motion.travelled += distance;
      motion.speed = THREE.MathUtils.lerp(motion.speed, distance / Math.max(dt, 0.001), 1 - Math.exp(-dt * 10));
    }
    motion.previous.copy(motion.position);
    motion.initialized = true;
    const previous = engine.prevPositions.get(robot.id);
    const dx = previous ? robot.x - previous.x : 0;
    const dz = previous ? robot.y - previous.y : 0;
    const desiredYaw = dx || dz ? Math.atan2(dx, dz) : robot.heading;
    const difference = Math.atan2(Math.sin(desiredYaw - motion.yaw), Math.cos(desiredYaw - motion.yaw));
    motion.turn = difference;
    motion.yaw += difference * (1 - Math.exp(-dt * 18));
    const hovering = robot.alive && robot.type === 'drone';
    const altitude = hovering ? 1.25 + Math.sin(clock.elapsedTime * 2.1 + robot.id * 1.7) * 0.025 : 0;
    node.position.set(motion.position.x, altitude, motion.position.z);
    node.rotation.y = motion.yaw;
  });
  return state;
}

/** A clean, floor-anchored marker keeps the selected unit easy to find. */
function SelectionMarker({ selected, color, airborne = false }: { selected: boolean; color: string; airborne?: boolean }) {
  const marker = useRef<THREE.Group>(null);
  const ring = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (!marker.current) return;
    if (airborne && marker.current.parent) marker.current.position.y = -marker.current.parent.position.y + 0.045;
    if (ring.current) ring.current.scale.setScalar(1 + Math.sin(clock.elapsedTime * 2.5) * 0.025);
  });
  if (!selected) return null;
  return (
    <group ref={marker} position={[0, 0.045, 0]}>
      <mesh ref={ring} rotation-x={-Math.PI / 2}>
        <ringGeometry args={[0.65, 0.69, 48]} />
        <meshBasicMaterial color={color} transparent opacity={0.9} depthWrite={false} toneMapped={false} />
      </mesh>
      <mesh position={[0, 0.005, 0.84]} rotation-x={-Math.PI / 2} rotation-z={Math.PI}>
        <circleGeometry args={[0.1, 3]} />
        <meshBasicMaterial color={color} toneMapped={false} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

function RobotLabel({ robot, selected }: { robot: RobotState; selected: boolean }) {
  const show = useSim((s) => s.overlays.labels);
  const cleanView = useSim((s) => s.cleanView);
  if (cleanView || (!show && !selected)) return null;
  const percentage = robot.alive ? batteryPct(robot) : 0;
  return (
    <Html position={[0, robot.type === 'drone' ? 0.5 : 1.02, 0]} center zIndexRange={[20, 0]} style={{ pointerEvents: 'none' }}>
      <div className={`robot-tag ${robot.type} ${selected ? 'selected' : ''} ${robot.alive ? '' : 'dead'}`}>
        <span className="tag-icon" aria-hidden />
        {robot.manual && <span className="tag-manual">MANUAL</span>}
        {selected ? robot.label : robot.label.replace('Rover ', 'R').replace('Drone ', 'D')}
        {selected && <span className="tag-battery" title={`${percentage}% battery`}><span style={batteryFillStyle(percentage)} /></span>}
      </div>
    </Html>
  );
}

export function Rover({ engine, robot, quality, selected, onSelect, preview = false, still = false }: RobotProps) {
  const group = useRef<THREE.Group>(null);
  const wheels = useRef<Array<THREE.Group | null>>([]);
  const lidar = useRef<THREE.Group>(null);
  const motion = useRobotMotion(engine, robot, group, preview, still);
  useFrame(({ clock }) => {
    for (const wheel of wheels.current) if (wheel) wheel.rotation.x = motion.current.travelled / 0.17;
    if (lidar.current && robot.alive && !still) lidar.current.rotation.y = clock.elapsedTime * 3.5;
  });
  const body = robot.alive ? '#ed9650' : '#89938a';
  return (
    <group ref={group} name={preview ? `preview-${robot.name}` : undefined} onClick={onSelect}>
      <RoundedBox args={[0.62, 0.3, 0.78]} radius={0.065} smoothness={2} position={[0, 0.35, 0]} castShadow={quality.shadows}>
        <meshStandardMaterial color={body} roughness={0.68} />
      </RoundedBox>
      <RoundedBox args={[0.46, 0.15, 0.49]} radius={0.035} smoothness={2} position={[0, 0.565, -0.045]} castShadow={quality.shadows}>
        <meshStandardMaterial color="#fff0cc" roughness={0.8} />
      </RoundedBox>
      {/* Dark blue windscreen gives the chassis an unmistakable front. */}
      <mesh position={[0, 0.56, 0.205]}>
        <boxGeometry args={[0.35, 0.085, 0.018]} />
        <meshStandardMaterial color="#30585c" roughness={0.38} metalness={0.12} />
      </mesh>
      <RoundedBox args={[0.66, 0.085, 0.075]} radius={0.022} smoothness={1} position={[0, 0.23, 0.415]}>
        <meshStandardMaterial color="#435554" roughness={0.8} />
      </RoundedBox>
      {WHEEL_POSITIONS.map((position, index) => (
        <group key={index} ref={(node) => { wheels.current[index] = node; }} position={position}>
          <mesh rotation-z={Math.PI / 2} castShadow={quality.shadows}>
            <cylinderGeometry args={[0.17, 0.17, 0.13, 12]} />
            <meshStandardMaterial color="#374844" roughness={0.95} />
          </mesh>
          <mesh position={[position[0] < 0 ? -0.07 : 0.07, 0, 0]} rotation-z={Math.PI / 2}>
            <cylinderGeometry args={[0.09, 0.09, 0.015, 8]} />
            <meshStandardMaterial color="#ded8b5" roughness={0.7} />
          </mesh>
          <mesh position={[position[0] < 0 ? -0.081 : 0.081, 0, 0]}>
            <boxGeometry args={[0.013, 0.12, 0.026]} />
            <meshStandardMaterial color="#779087" roughness={0.8} />
          </mesh>
        </group>
      ))}
      <mesh position={[0, 0.7, -0.14]}>
        <cylinderGeometry args={[0.022, 0.022, 0.15, 8]} />
        <meshStandardMaterial color="#576a64" roughness={0.8} />
      </mesh>
      <group ref={lidar} position={[0, 0.79, -0.14]}>
        <mesh>
          <cylinderGeometry args={[0.1, 0.1, 0.075, 12]} />
          <meshStandardMaterial color="#ecedd4" roughness={0.75} />
        </mesh>
        <mesh position={[0, 0, 0.09]}>
          <boxGeometry args={[0.1, 0.035, 0.02]} />
          <meshStandardMaterial color="#247d7d" emissive="#247d7d" emissiveIntensity={robot.alive ? 0.2 : 0} />
        </mesh>
      </group>
      {[-0.21, 0.21].map((x) => (
        <mesh key={x} position={[x, 0.36, 0.395]}>
          <boxGeometry args={[0.085, 0.065, 0.018]} />
          <meshBasicMaterial color={robot.alive ? '#fff9df' : '#56625c'} toneMapped={false} />
        </mesh>
      ))}
      <mesh position={[0.14, 0.65, -0.2]}>
        <sphereGeometry args={[0.029, 8, 6]} />
        <meshBasicMaterial color={batteryColor(robot)} toneMapped={false} />
      </mesh>
      {!preview && <><SelectionMarker selected={selected} color={COLORS.rover} /><RobotLabel robot={robot} selected={selected} /></>}
    </group>
  );
}

export function Drone({ engine, robot, quality, selected, onSelect, preview = false, still = false }: RobotProps) {
  const group = useRef<THREE.Group>(null);
  const airframe = useRef<THREE.Group>(null);
  const rotors = useRef<Array<THREE.Group | null>>([]);
  const shadow = useRef<THREE.Mesh>(null);
  const motion = useRobotMotion(engine, robot, group, preview, still);
  useFrame((_, delta) => {
    const dt = Math.min(delta, 0.1);
    if (robot.alive && !still) rotors.current.forEach((rotor, index) => {
      if (rotor) rotor.rotation.y += dt * ROTOR_SPEED * (index % 2 ? -1 : 1);
    });
    if (shadow.current && group.current) shadow.current.position.y = -group.current.position.y + 0.035;
    if (airframe.current) {
      const bank = robot.alive ? THREE.MathUtils.clamp(motion.current.turn * -0.08, -0.11, 0.11) : 0;
      const pitch = robot.alive ? Math.min(motion.current.speed * 0.018, 0.085) : 0;
      const damping = 1 - Math.exp(-dt * 8);
      airframe.current.rotation.z = THREE.MathUtils.lerp(airframe.current.rotation.z, bank, damping);
      airframe.current.rotation.x = THREE.MathUtils.lerp(airframe.current.rotation.x, pitch, damping);
    }
  });
  return (
    <group ref={group} name={preview ? `preview-${robot.name}` : undefined} onClick={onSelect}>
      <group ref={airframe}>
        <RoundedBox args={[0.4, 0.14, 0.53]} radius={0.07} smoothness={2} castShadow={quality.shadows}>
          <meshStandardMaterial color={robot.alive ? '#2bafa4' : '#89938a'} roughness={0.65} />
        </RoundedBox>
        <RoundedBox args={[0.3, 0.075, 0.36]} radius={0.045} smoothness={2} position={[0, 0.1, -0.025]}>
          <meshStandardMaterial color="#fff0cc" roughness={0.8} />
        </RoundedBox>
        {/* A front-facing camera and landing skids establish flight direction. */}
        <mesh position={[0, -0.055, 0.28]}>
          <boxGeometry args={[0.17, 0.12, 0.1]} />
          <meshStandardMaterial color="#375d58" roughness={0.7} />
        </mesh>
        <mesh position={[0, -0.055, 0.335]} rotation-x={Math.PI / 2}>
          <cylinderGeometry args={[0.045, 0.045, 0.018, 12]} />
          <meshBasicMaterial color="#94e5d1" toneMapped={false} />
        </mesh>
        {[-0.15, 0.15].map((x) => (
          <mesh key={x} position={[x, -0.15, 0]}>
            <boxGeometry args={[0.035, 0.035, 0.42]} />
            <meshStandardMaterial color="#f5e7c6" roughness={0.8} />
          </mesh>
        ))}
        {ARM_ANGLES.map((angle, index) => (
          <group key={angle} rotation-y={angle}>
            <mesh position={[0, 0, 0.3]} castShadow={quality.shadows}>
              <boxGeometry args={[0.085, 0.06, 0.48]} />
              <meshStandardMaterial color="#eae4c9" roughness={0.8} />
            </mesh>
            <group position={[0, 0.045, 0.51]}>
              <mesh>
                <cylinderGeometry args={[0.075, 0.065, 0.1, 10]} />
                <meshStandardMaterial color="#2c6f67" roughness={0.7} />
              </mesh>
              <mesh rotation-x={-Math.PI / 2} position={[0, 0.06, 0]}>
                <ringGeometry args={[0.185, 0.202, 24]} />
                <meshStandardMaterial color="#f1e8cf" roughness={0.85} side={THREE.DoubleSide} />
              </mesh>
              <group ref={(node) => { rotors.current[index] = node; }} position={[0, 0.06, 0]}>
                <mesh rotation-x={-Math.PI / 2}>
                  <circleGeometry args={[0.18, 24]} />
                  <meshBasicMaterial color="#edf8df" transparent opacity={robot.alive ? 0.16 : 0} depthWrite={false} side={THREE.DoubleSide} />
                </mesh>
                <mesh>
                  <boxGeometry args={[0.36, 0.012, 0.035]} />
                  <meshStandardMaterial color="#44685d" roughness={0.8} />
                </mesh>
              </group>
            </group>
          </group>
        ))}
        <mesh position={[0.1, 0.15, -0.08]}>
          <sphereGeometry args={[0.026, 8, 6]} />
          <meshBasicMaterial color={batteryColor(robot)} toneMapped={false} />
        </mesh>
      </group>
      <mesh ref={shadow} rotation-x={-Math.PI / 2}>
        <planeGeometry args={[1.5, 1.5]} />
        <meshBasicMaterial map={glowTexture()} color="#245e4c" transparent opacity={0.24} depthWrite={false} />
      </mesh>
      {!preview && <><SelectionMarker selected={selected} color={COLORS.drone} airborne /><RobotLabel robot={robot} selected={selected} /></>}
    </group>
  );
}

interface RobotProps {
  preview?: boolean;
  still?: boolean;
  engine: SimulationEngine;
  robot: RobotState;
  quality: QualityProfile;
  selected: boolean;
  onSelect: (event: ThreeEvent<MouseEvent>) => void;
}

export function Robots({ engine, quality }: { engine: SimulationEngine; quality: QualityProfile }) {
  const selected = useSim((s) => s.selected);
  const cleanView = useSim((s) => s.cleanView);
  const select = useSim((s) => s.select);
  useSim((s) => s.version);
  return <>{engine.robots.map((robot) => {
    const Component = robot.type === 'rover' ? Rover : Drone;
    return <Component
      key={robot.name}
      engine={engine}
      robot={robot}
      quality={quality}
      selected={!cleanView && selected === robot.name}
      onSelect={(event) => {
        event.stopPropagation();
        if (event.delta < 4 && !useSim.getState().editingSurvivors && !useSim.getState().cleanView) select(selected === robot.name ? null : robot.name);
      }}
    />;
  })}</>;
}

/** Display only the selected unit's local plan so exploration stays readable. */
export function RobotPaths({ engine }: { engine: SimulationEngine }) {
  useSim((s) => s.version);
  const selected = useSim((s) => s.selected);
  const robot = engine.robots.find((unit) => unit.name === selected);
  if (!robot?.alive || robot.path.length < 2) return null;
  const points = robot.path.slice(0, 40).map((point) => {
    const position = cellToWorld(engine, point.x, point.y);
    return [position.x, 0.07, position.z] as [number, number, number];
  });
  const color = robot.type === 'rover' ? COLORS.rover : COLORS.drone;
  return (
    <group>
      <Line points={points} color={color} lineWidth={2} dashed dashSize={0.22} gapSize={0.14} transparent opacity={0.8} depthWrite={false} />
      <mesh position={points[points.length - 1]} rotation-x={-Math.PI / 2}>
        <ringGeometry args={[0.19, 0.25, 32]} />
        <meshBasicMaterial color={color} transparent opacity={0.9} toneMapped={false} depthWrite={false} />
      </mesh>
    </group>
  );
}
