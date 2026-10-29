import { useEffect, useLayoutEffect, useRef } from 'react';
import { Canvas, useFrame, useThree, type ThreeEvent } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib';
import * as THREE from 'three';
import { simClock, TICKS_PER_SECOND, useSim } from '../store/simStore';
import type { SimulationEngine } from '../simulation/core/SimulationEngine';
import { COLORS, QUALITY, robotRenderPosition, worldToCell, type QualityProfile } from './common';
import { World } from './World';
import { RobotPaths, Robots } from './Robots';
import { CommEvents, CommRanges, MapMergeFlash, NetworkLinks, PacketPulses, PartitionAndReconnect } from './Network';
import { CoverageFog, Dust, EvidenceMarkers, PlacementMarkers, Survivors, TruthDebug } from './Overlays';
import { applyAnchoredZoom, captureGroundAnchor, overviewOffset, type GroundZoomAnchor } from './cameraMath';
import { soundscape } from '../audio/Soundscape';

/** Fixed ticks stay deterministic; pausing preserves the exact rendered pose. */
function SimDriver({ engine }: { engine: SimulationEngine }) {
  const acc = useRef(0);
  useLayoutEffect(() => { acc.current = 0; simClock.alpha = 1; }, [engine]);
  useFrame((_, dt) => {
    const { status, settings, advance } = useSim.getState();
    if (status === 'paused' || status === 'ready') return;
    if (status === 'complete') {
      simClock.alpha = Math.min(1, simClock.alpha + dt * TICKS_PER_SECOND * settings.speed);
      return;
    }
    const interval = 1 / TICKS_PER_SECOND;
    acc.current += Math.min(dt, 0.1) * settings.speed;
    const ticks = Math.min(8, Math.floor(acc.current / interval));
    if (ticks) {
      acc.current -= ticks * interval;
      advance(ticks);
    }
    simClock.alpha = Math.min(1, acc.current / interval);
  }, -100);
  return null;
}

function CameraRig({ engine }: { engine: SimulationEngine }) {
  const camera = useThree((s) => s.camera) as THREE.OrthographicCamera;
  const controls = useThree((s) => s.controls) as OrbitControlsImpl | undefined;
  const size = useThree((s) => s.size);
  const canvas = useThree((s) => s.gl.domElement);
  const request = useSim((s) => s.cameraRequest);
  const focus = useSim((s) => s.focus);
  const fitZoom = useRef(1);
  const desired = useRef<{ target: THREE.Vector3; position: THREE.Vector3; zoom: number; following?: boolean; zoomOnly?: boolean; anchor?: GroundZoomAnchor | null } | null>(null);
  const lastPointer = useRef<THREE.Vector2 | null>(null);
  const targetPosition = useRef(new THREE.Vector3());
  const cameraOffset = useRef(new THREE.Vector3());
  const previousSize = useRef({ width: 0, height: 0 });
  const initialized = useRef<SimulationEngine | null>(null);
  const telemetryAt = useRef(0);
  const span = Math.max(engine.scenario.width, engine.scenario.height);

  useEffect(() => {
    const remember = (event: PointerEvent | WheelEvent) => {
      const rect = canvas.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      if (!lastPointer.current) lastPointer.current = new THREE.Vector2();
      lastPointer.current.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
    };
    canvas.addEventListener('pointermove', remember);
    canvas.addEventListener('pointerdown', remember);
    canvas.addEventListener('wheel', remember, { passive: true });
    return () => {
      canvas.removeEventListener('pointermove', remember);
      canvas.removeEventListener('pointerdown', remember);
      canvas.removeEventListener('wheel', remember);
    };
  }, [canvas]);

  const measureFit = () => {
    const { width, height } = engine.scenario;
    const overview = camera.clone();
    overview.position.copy(overviewOffset(span));
    overview.lookAt(0, 0, 0);
    overview.updateMatrixWorld();
    const point = new THREE.Vector3();
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const x of [-width / 2 - 5, width / 2 + 5]) {
      for (const z of [-height / 2 - 5, height / 2 + 5]) {
        for (const y of [-1, 3]) {
          point.set(x, y, z).applyMatrix4(overview.matrixWorldInverse);
          minX = Math.min(minX, point.x); maxX = Math.max(maxX, point.x);
          minY = Math.min(minY, point.y); maxY = Math.max(maxY, point.y);
        }
      }
    }
    // Reserve room for the playback bar while keeping the whole island visible.
    return Math.max(1, Math.min(size.width * 0.86 / (maxX - minX), Math.max(120, size.height - 135) * 0.94 / (maxY - minY)));
  };

  useLayoutEffect(() => {
    if (!controls || !size.width || !size.height) return;
    const previous = initialized.current;
    const preserveEditorView = previous && useSim.getState().editingSurvivors && previous.scenario.seed === engine.scenario.seed && previous.scenario.preset === engine.scenario.preset;
    if (initialized.current !== engine && !preserveEditorView) {
      initialized.current = engine;
      desired.current = null;
      controls.target.set(0, 0, 0);
      camera.position.copy(overviewOffset(span));
      camera.lookAt(0, 0, 0);
      controls.update();
      fitZoom.current = measureFit();
      camera.zoom = fitZoom.current;
      camera.updateProjectionMatrix();
      useSim.setState({ cameraView: 'isometric', following: false, cameraZoom: 100 });
    } else if (previousSize.current.width && previousSize.current.height) {
      // A drawer or window resize preserves the operator’s current framing.
      const ratio = camera.zoom / fitZoom.current;
      fitZoom.current = measureFit();
      camera.zoom = fitZoom.current * ratio;
      camera.updateProjectionMatrix();
      if (desired.current) desired.current.zoom = Math.max(fitZoom.current * 0.6, Math.min(fitZoom.current * 4, desired.current.zoom));
    }
    initialized.current = engine;
    controls.minZoom = fitZoom.current * 0.6;
    controls.maxZoom = fitZoom.current * 4;
    previousSize.current = { width: size.width, height: size.height };
  }, [engine, camera, controls, size.width, size.height]);

  useEffect(() => {
    if (!controls) return;
    const stopGlide = () => { desired.current = null; useSim.getState().updateCamera(Math.round(camera.zoom / fitZoom.current * 100), false); };
    let drag: { x: number; y: number; pointer: number } | null = null;
    const down = (event: PointerEvent) => { drag = { x: event.clientX, y: event.clientY, pointer: event.pointerId }; };
    const move = (event: PointerEvent) => {
      if (!drag || event.pointerId !== drag.pointer) return;
      if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > 4) { stopGlide(); drag = null; }
    };
    const up = () => { drag = null; };
    // A click can select the next robot without cancelling the existing lock.
    // Only actual camera dragging or scrolling releases it.
    canvas.addEventListener('pointerdown', down);
    canvas.addEventListener('wheel', stopGlide, { capture: true, passive: true });
    canvas.ownerDocument.addEventListener('pointermove', move);
    canvas.ownerDocument.addEventListener('pointerup', up);
    canvas.ownerDocument.addEventListener('pointercancel', up);
    return () => {
      canvas.removeEventListener('pointerdown', down);
      canvas.removeEventListener('wheel', stopGlide, true);
      canvas.ownerDocument.removeEventListener('pointermove', move);
      canvas.ownerDocument.removeEventListener('pointerup', up);
      canvas.ownerDocument.removeEventListener('pointercancel', up);
    };
  }, [controls, camera, canvas]);

  useEffect(() => {
    if (!request || !controls || useSim.getState().cameraRequest !== request) return;
    const { action } = request;
    const target = controls.target.clone();
    const position = camera.position.clone();
    let zoom = desired.current?.zoom ?? camera.zoom;
    if (action === 'zoomIn') zoom = Math.min(fitZoom.current * 4, zoom * 1.25);
    else if (action === 'zoomOut') zoom = Math.max(fitZoom.current * 0.6, zoom / 1.25);
    else if (action === 'reset') { target.set(0, 0, 0); position.copy(overviewOffset(span)); zoom = fitZoom.current; }
    else if (action === 'top') position.copy(target).add(new THREE.Vector3(0, span * 4, span * 0.06));
    else if (action === 'isometric') position.copy(target).add(overviewOffset(span));
    else if (action === 'follow') {
      const state = useSim.getState();
      const robot = engine.robots.find((r) => r.name === state.selected);
      if (!robot || !state.following) { desired.current = null; return; }
      robotRenderPosition(engine, robot.id, target);
      cameraOffset.current.copy(camera.position).sub(controls.target);
      position.copy(target).add(cameraOffset.current);
      zoom = Math.min(fitZoom.current * 4, Math.max(zoom, fitZoom.current * 2.4));
    }
    const zoomOnly = action === 'zoomIn' || action === 'zoomOut';
    const anchor = zoomOnly && lastPointer.current ? captureGroundAnchor(camera, lastPointer.current) : null;
    desired.current = { target, position, zoom, following: action === 'follow', zoomOnly, anchor };
  }, [request, controls, engine, camera]);

  useEffect(() => {
    if (!focus || !controls || useSim.getState().focus !== focus || !useSim.getState().following) return;
    const robot = engine.robots.find((r) => r.name === focus.robot);
    if (!robot) return;
    const target = robotRenderPosition(engine, robot.id);
    const offset = camera.position.clone().sub(controls.target);
    cameraOffset.current.copy(offset);
    desired.current = { target, position: target.clone().add(offset), zoom: fitZoom.current * 3.2, following: true };
  }, [focus, controls, engine, camera]);

  useFrame((state, dt) => {
    if (!controls) return;
    const follow = useSim.getState();
    if (desired.current?.following && !follow.following) desired.current = null;
    const glide = desired.current;
    const factor = 1 - Math.exp(-dt * 7);
    if (follow.following && follow.selected) {
      const robot = engine.robots.find((r) => r.name === follow.selected);
      if (robot) {
        robotRenderPosition(engine, robot.id, targetPosition.current);
        if (glide) { glide.target.copy(targetPosition.current); glide.position.copy(targetPosition.current).add(cameraOffset.current); }
        else {
          cameraOffset.current.copy(camera.position).sub(controls.target);
          controls.target.lerp(targetPosition.current, factor);
          camera.position.copy(controls.target).add(cameraOffset.current);
        }
      }
    }
    if (glide) {
      const zoom = THREE.MathUtils.lerp(camera.zoom, glide.zoom, factor);
      if (glide.zoomOnly) applyAnchoredZoom(camera, controls.target, zoom, glide.anchor ?? null);
      else {
        controls.target.lerp(glide.target, factor);
        camera.position.lerp(glide.position, factor);
        camera.zoom = zoom;
        camera.updateProjectionMatrix();
      }
      if ((glide.zoomOnly || camera.position.distanceToSquared(glide.position) < 0.0001) && Math.abs(camera.zoom - glide.zoom) < 0.002) desired.current = null;
    }
    // Bound extreme pans without pulling normal cursor zoom back to the map centre.
    const halfW = span * 3, halfH = span * 3;
    const clampedX = THREE.MathUtils.clamp(controls.target.x, -halfW, halfW);
    const clampedZ = THREE.MathUtils.clamp(controls.target.z, -halfH, halfH);
    camera.position.x += clampedX - controls.target.x;
    camera.position.z += clampedZ - controls.target.z;
    controls.target.x = clampedX; controls.target.z = clampedZ;
    controls.update();
    soundscape.updateSpatial(controls.target.x, controls.target.z, camera.matrix.elements[0], camera.matrix.elements[2], span / Math.max(1, camera.zoom / fitZoom.current) * 0.6);
    if (state.clock.elapsedTime - telemetryAt.current > 0.12) {
      telemetryAt.current = state.clock.elapsedTime;
      const percent = Math.round(camera.zoom / fitZoom.current * 100);
      if (useSim.getState().cameraZoom !== percent) useSim.getState().updateCamera(percent);
    }
  });
  return null;
}

function Lighting({ engine, quality }: { engine: SimulationEngine; quality: QualityProfile }) {
  const span = Math.max(engine.scenario.width, engine.scenario.height);
  return <>
    <ambientLight intensity={0.5} color="#fff5dd" />
    <hemisphereLight args={['#dff7ef', '#b0a279', 0.85]} />
    <directionalLight position={[-span * 0.5, span, span * 0.35]} intensity={2.1} color={COLORS.sun}
      castShadow={quality.shadows} shadow-mapSize-width={quality.shadowMapSize} shadow-mapSize-height={quality.shadowMapSize}
      shadow-camera-left={-span * 0.8} shadow-camera-right={span * 0.8} shadow-camera-top={span * 0.8} shadow-camera-bottom={-span * 0.8}
      shadow-camera-near={1} shadow-camera-far={span * 3} shadow-bias={-0.0004} shadow-normalBias={0.035} shadow-radius={3} />
    <directionalLight position={[span, span * 0.5, -span]} intensity={0.4} color="#b9e4df" />
  </>;
}

function Scene() {
  const engine = useSim((s) => s.engine);
  const overlays = useSim((s) => s.overlays);
  const selected = useSim((s) => s.selected);
  const editingSurvivors = useSim((s) => s.editingSurvivors);
  const cleanView = useSim((s) => s.cleanView);
  const qualityName = useSim((s) => s.settings.quality);
  const fog = useSim((s) => s.settings.fog);
  const quality = QUALITY[qualityName];
  const scene = useThree((s) => s.scene);
  const generation = useRef({ engine, revision: 0 });
  if (generation.current.engine !== engine) generation.current = { engine, revision: generation.current.revision + 1 };
  useEffect(() => {
    const span = Math.max(engine.scenario.width, engine.scenario.height);
    scene.background = new THREE.Color('#b4dfd2');
    scene.fog = fog > 0 ? new THREE.Fog('#b4dfd2', span * 6, span * (16 - fog * 5)) : null;
  }, [scene, fog, engine]);

  const onFloorClick = (e: ThreeEvent<MouseEvent>) => {
    if (e.delta > 4) return;
    const { selected, engine: eng, settings, issue, select, editingSurvivors: editing, toggleSurvivorAt } = useSim.getState();
    if (editing) {
      e.stopPropagation();
      toggleSurvivorAt(worldToCell(eng, e.point));
      return;
    }
    const robot = selected ? eng.robots.find((r) => r.name === selected) : null;
    if (robot && settings.mode !== 'autonomous' && robot.manual) {
      e.stopPropagation();
      const cell = worldToCell(eng, e.point);
      if (eng.scenario.grid.isTraversable(cell.x, cell.y)) issue({ kind: 'manualWaypoint', robot: robot.name, target: cell });
      return;
    }
    select(null);
  };

  return <>
    <SimDriver engine={engine} />
    <Lighting engine={engine} quality={quality} />
    <group key={generation.current.revision}>
      <World engine={engine} quality={quality} onFloorClick={onFloorClick} />
      <Robots engine={engine} quality={quality} />
      {!cleanView && <>
      {overlays.paths && <RobotPaths engine={engine} />}
      {overlays.links && <NetworkLinks engine={engine} />}
      {overlays.packets && <PacketPulses engine={engine} arcs={quality.commFx} />}
      {overlays.packets && quality.commFx && <CommEvents engine={engine} />}
      {overlays.packets && quality.commFx && <MapMergeFlash engine={engine} />}
      <PartitionAndReconnect engine={engine} />
      {overlays.ranges && <CommRanges engine={engine} only={null} />}
      {overlays.evidence && <EvidenceMarkers engine={engine} />}
      </>}
      <Survivors engine={engine} quality={quality} />
      {editingSurvivors && !cleanView && <PlacementMarkers engine={engine} />}
      {overlays.truth && !cleanView && <TruthDebug engine={engine} />}
      {overlays.coverage && !cleanView && <CoverageFog engine={engine} robot={selected} />}
      {quality.dust > 0 && fog > 0.15 && <Dust engine={engine} count={quality.dust} fog={fog} />}
    </group>
    <OrbitControls makeDefault enableDamping dampingFactor={0.085} enableZoom zoomToCursor zoomSpeed={0.8} rotateSpeed={0.55} panSpeed={0.7}
      screenSpacePanning={false} minPolarAngle={0.001} maxPolarAngle={Math.PI / 2.65} />
    <CameraRig engine={engine} />
  </>;
}

export function SceneRoot() {
  const qualityName = useSim((s) => s.settings.quality);
  const quality = QUALITY[qualityName];
  return <Canvas orthographic shadows={quality.shadows ? 'soft' : false} dpr={quality.dpr}
    gl={{ antialias: true, powerPreference: 'high-performance', toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1.05 }}
    camera={{ near: 0.1, far: 1000, position: [0, 165, 97.5], zoom: 12 }}>
    <Scene />
  </Canvas>;
}
