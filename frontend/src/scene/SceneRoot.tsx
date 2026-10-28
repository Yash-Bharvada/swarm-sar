import { useEffect, useRef } from 'react';
import { Canvas, useFrame, useThree, type ThreeEvent } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import { simClock, TICKS_PER_SECOND, useSim } from '../store/simStore';
import type { SimulationEngine } from '../simulation/core/SimulationEngine';
import { QUALITY, cellToWorld, worldToCell } from './common';
import { World } from './World';
import { RobotPaths, Robots } from './Robots';
import { CommRanges, NetworkLinks, PacketPulses, PartitionAndReconnect } from './Network';
import { CoverageFog, Dust, EvidenceMarkers, Survivors, TruthDebug } from './Overlays';

/** Fixed-tick simulation driver. Rendering only reads the interpolation alpha. */
function SimDriver() {
  const acc = useRef(0);
  useFrame((_, dt) => {
    const { status, settings, advance } = useSim.getState();
    if (status !== 'running') {
      simClock.alpha = 1;
      acc.current = 0;
      return;
    }
    const interval = 1 / TICKS_PER_SECOND;
    acc.current += Math.min(dt, 0.1) * settings.speed;
    let ticks = 0;
    while (acc.current >= interval && ticks < 8) {
      acc.current -= interval;
      ticks++;
    }
    if (ticks) advance(ticks);
    simClock.alpha = Math.min(1, acc.current / interval);
  });
  return null;
}

function CameraRig({ engine }: { engine: SimulationEngine }) {
  const camera = useThree((s) => s.camera);
  const controls = useThree((s) => s.controls) as unknown as { target: THREE.Vector3; update: () => void } | null;
  useEffect(() => {
    const { width, height } = engine.scenario;
    const span = Math.max(width, height);
    camera.position.set(-width * 0.05, span * 0.6, height * 0.5 + span * 0.12);
    camera.lookAt(0, 0, 0);
    if (controls) {
      controls.target.set(0, 0, 0);
      controls.update();
    }
  }, [engine, camera, controls]);

  // Glide the orbit target to a robot on request, keeping a close chase view.
  const focus = useSim((s) => s.focus);
  const glide = useRef<{ target: THREE.Vector3; position: THREE.Vector3; t: number } | null>(null);
  useEffect(() => {
    if (!focus) return;
    const r = engine.robots.find((x) => x.name === focus.robot);
    if (!r) return;
    const target = cellToWorld(engine, r.x, r.y);
    glide.current = { target, position: target.clone().add(new THREE.Vector3(-3, 7, 7)), t: 0 };
  }, [focus, engine]);
  useFrame((_, dt) => {
    const g = glide.current;
    if (!g || !controls) return;
    g.t = Math.min(1, g.t + dt * 1.8);
    const k = Math.min(1, dt * 6);
    controls.target.lerp(g.target, k);
    camera.position.lerp(g.position, k);
    controls.update();
    if (g.t >= 1) glide.current = null;
  });
  return null;
}

function Lighting({ engine, shadows }: { engine: SimulationEngine; shadows: boolean }) {
  const { width, height } = engine.scenario;
  const span = Math.max(width, height);
  return (
    <>
      <ambientLight intensity={0.5} color="#8fa0c4" />
      <hemisphereLight args={['#6d86b8', '#3a2818', 1.1]} />
      <directionalLight
        position={[-width * 0.4, 26, -height * 0.35]}
        intensity={1.9}
        color="#a8c2ff"
        castShadow={shadows}
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
        shadow-camera-left={-span / 1.6}
        shadow-camera-right={span / 1.6}
        shadow-camera-top={span / 1.6}
        shadow-camera-bottom={-span / 1.6}
        shadow-bias={-0.0006}
      />
      {/* Warm fire-glow fill from the far side of the collapse */}
      <directionalLight position={[width * 0.5, 8, height * 0.5]} intensity={0.6} color="#ff8a4a" />
    </>
  );
}

function Scene() {
  const engine = useSim((s) => s.engine);
  const overlays = useSim((s) => s.overlays);
  const selected = useSim((s) => s.selected);
  const qualityName = useSim((s) => s.settings.quality);
  const fog = useSim((s) => s.settings.fog);
  const quality = QUALITY[qualityName];
  const scene = useThree((s) => s.scene);

  useEffect(() => {
    scene.fog = new THREE.FogExp2('#0b0f18', 0.002 + fog * 0.018);
    scene.background = new THREE.Color('#06080c');
  }, [scene, fog]);

  const onFloorClick = (e: ThreeEvent<MouseEvent>) => {
    const { selected: sel, engine: eng, settings, issue, select } = useSim.getState();
    const robot = sel ? eng.robots.find((r) => r.name === sel) : null;
    if (robot && settings.mode !== 'autonomous' && robot.manual) {
      e.stopPropagation();
      const cell = worldToCell(eng, e.point);
      if (eng.scenario.grid.inBounds(cell.x, cell.y)) issue({ kind: 'manualWaypoint', robot: robot.name, target: cell });
      return;
    }
    if (e.delta < 4) select(null);
  };

  return (
    <>
      <SimDriver />
      <CameraRig engine={engine} />
      <Lighting engine={engine} shadows={quality.shadows} />
      <group key={`${engine.scenario.preset}-${engine.scenario.seed}-${engine.robots.length}`}>
        <World engine={engine} quality={quality} onFloorClick={onFloorClick} />
        <Robots engine={engine} quality={quality} />
        {overlays.paths && <RobotPaths engine={engine} />}
        {overlays.links && <NetworkLinks engine={engine} />}
        {overlays.packets && <PacketPulses engine={engine} />}
        <PartitionAndReconnect engine={engine} />
        {(overlays.ranges || selected) && <CommRanges engine={engine} only={overlays.ranges ? null : selected} />}
        {overlays.evidence && <EvidenceMarkers engine={engine} />}
        <Survivors engine={engine} quality={quality} />
        {overlays.truth && <TruthDebug engine={engine} />}
        {overlays.coverage && <CoverageFog engine={engine} robot={selected} />}
        <Dust engine={engine} count={quality.dust} fog={fog} />
      </group>
      <OrbitControls makeDefault enableDamping dampingFactor={0.08} maxPolarAngle={1.32} minDistance={6} maxDistance={110} />
    </>
  );
}

export function SceneRoot() {
  const qualityName = useSim((s) => s.settings.quality);
  const quality = QUALITY[qualityName];
  return (
    <Canvas
      key={qualityName}
      shadows={quality.shadows}
      dpr={quality.dpr}
      gl={{ antialias: quality.antialias, powerPreference: 'high-performance' }}
      camera={{ fov: 42, near: 0.1, far: 400, position: [0, 40, 30] }}
    >
      <Scene />
    </Canvas>
  );
}
