import { useCallback, memo, useEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Html, Line, OrbitControls, RoundedBox } from '@react-three/drei';
import * as THREE from 'three';
import { GraphicsUnavailable } from './SceneBoundary';
import type { ObservatoryAgent, ObservatoryCanvasProps, ObservatoryGrid, ObservatoryPacket, ObservatoryPoint } from './types';

type V3 = [number, number, number];
type Layout = { scale: number; centerX: number; centerY: number; width: number; depth: number };
type Cell = { x: number; z: number; size: number; kind: number; peer: boolean };
const PAPER = '#eaf0e1';
const shortName = (id: string) => id.replace('rover_', 'Rover ').replace('drone_', 'Drone ');
const point = (p: ObservatoryPoint, layout: Layout, y = 0): V3 => [(p.x - layout.centerX) * layout.scale, y, (p.y - layout.centerY) * layout.scale];

function useReducedMotion() {
  const [reduced, setReduced] = useState(() => matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => { const query = matchMedia('(prefers-reduced-motion: reduce)'); const update = () => setReduced(query.matches); query.addEventListener('change', update); return () => query.removeEventListener('change', update); }, []);
  return reduced;
}

function getLayout(agents: ObservatoryAgent[], chosen: ObservatoryAgent | undefined): Layout {
  const points = agents.flatMap(a => a.position ? [a.position] : []);
  if (chosen?.grid) {
    const g = chosen.grid, c = Math.cos(g.yaw), s = Math.sin(g.yaw);
    for (const [x, y] of [[0, 0], [g.width, 0], [0, g.height], [g.width, g.height]]) points.push({ x: g.originX + (x * c - y * s) * g.resolution, y: g.originY + (x * s + y * c) * g.resolution });
  }
  if (!points.length) return { scale: 1, centerX: 0, centerY: 0, width: 24, depth: 24 };
  const minX = Math.min(...points.map(p => p.x)), maxX = Math.max(...points.map(p => p.x));
  const minY = Math.min(...points.map(p => p.y)), maxY = Math.max(...points.map(p => p.y));
  const width = Math.max(8, maxX - minX), depth = Math.max(8, maxY - minY), scale = 24 / Math.max(width, depth);
  return { scale, centerX: (minX + maxX) / 2, centerY: (minY + maxY) / 2, width: width * scale, depth: depth * scale };
}

/** Each instance represents one measured cell; unknown space remains empty. */
function collectCells(grid: ObservatoryGrid | null, peer: boolean, layout: Layout, cap = 24000): Cell[] {
  if (!grid) return [];
  const cells: Cell[] = [], c = Math.cos(grid.yaw), s = Math.sin(grid.yaw);
  // Keep walls at their exact cell extent. Sampling only omits cells, never inflates occupancy.
  const known = grid.cells.reduce((n, value) => n + (value >= 0 ? 1 : 0), 0);
  const stride = Math.max(1, Math.ceil(known / cap));
  let observed = 0;
  for (let i = 0; i < grid.cells.length; i++) {
    const kind = grid.cells[i]; if (kind < 0) continue;
    if (observed++ % stride !== 0) continue;
    const gx = (i % grid.width + .5) * grid.resolution, gy = (Math.floor(i / grid.width) + .5) * grid.resolution;
    const world = point({ x: grid.originX + gx * c - gy * s, y: grid.originY + gx * s + gy * c }, layout);
    cells.push({ x: world[0], z: world[2], size: grid.resolution * layout.scale, kind, peer });
  }
  return cells;
}

const CellInstances = memo(function CellInstances({ cells, walls, yaw = 0 }: { cells: Cell[]; walls: boolean; yaw?: number }) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  useEffect(() => {
    if (!mesh.current) return;
    const transform = new THREE.Object3D(), color = new THREE.Color();
    cells.forEach((cell, i) => {
      const height = walls ? cell.kind === 2 ? .22 : Math.max(.34, Math.min(.82, cell.size * .78)) : .045;
      transform.position.set(cell.x, walls ? height / 2 + .02 : -.006, cell.z);
      transform.rotation.set(0, -yaw, 0);
      transform.scale.set(cell.size * .96, height, cell.size * .96); transform.updateMatrix();
      mesh.current!.setMatrixAt(i, transform.matrix);
      color.set(cell.peer ? walls ? '#62a79c' : '#a8cebf' : walls ? cell.kind === 2 ? '#b5a078' : '#729775' : '#e3eccc');
      mesh.current!.setColorAt(i, color);
    });
    mesh.current.instanceMatrix.needsUpdate = true;
    if (mesh.current.instanceColor) mesh.current.instanceColor.needsUpdate = true;
    mesh.current.computeBoundingSphere();
  }, [cells, walls, yaw]);
  if (!cells.length) return null;
  return <instancedMesh key={cells.length} ref={mesh} args={[undefined, undefined, cells.length]} castShadow={walls} receiveShadow frustumCulled={false}>
    <boxGeometry /><meshStandardMaterial roughness={.84} metalness={.02} />
  </instancedMesh>;
});

function BeliefMap({ agent, layout }: { agent: ObservatoryAgent; layout: Layout }) {
  const local = useMemo(() => collectCells(agent.grid, false, layout), [agent.grid, layout]);
  const peer = useMemo(() => collectCells(agent.peerGrid, true, layout, 10000), [agent.peerGrid, layout]);
  const localFloor = useMemo(() => local.filter(c => c.kind === 0), [local]);
  const localWalls = useMemo(() => local.filter(c => c.kind > 0), [local]);
  const peerFloor = useMemo(() => peer.filter(c => c.kind === 0), [peer]);
  const peerWalls = useMemo(() => peer.filter(c => c.kind > 0), [peer]);
  return <><CellInstances cells={localFloor} walls={false} yaw={agent.grid?.yaw} /><CellInstances cells={localWalls} walls yaw={agent.grid?.yaw} /><CellInstances cells={peerFloor} walls={false} yaw={agent.peerGrid?.yaw} /><CellInstances cells={peerWalls} walls yaw={agent.peerGrid?.yaw} /></>;
}

function RoverModel({ color }: { color: string }) {
  return <group>
    <RoundedBox args={[.72, .28, .92]} radius={.06} smoothness={2} position={[0, .35, 0]} castShadow><meshStandardMaterial color={color} roughness={.6} /></RoundedBox>
    <RoundedBox args={[.53, .17, .57]} radius={.04} smoothness={2} position={[0, .57, -.06]} castShadow><meshStandardMaterial color="#fff7de" roughness={.7} /></RoundedBox>
    <mesh position={[0, .57, .232]}><boxGeometry args={[.39, .085, .018]} /><meshStandardMaterial color="#355b5a" metalness={.18} roughness={.32} /></mesh>
    {[-.41, .41].flatMap(x => [-.29, .29].map(z => <group key={`${x}-${z}`} position={[x, .2, z]}><mesh rotation-z={Math.PI / 2} castShadow><cylinderGeometry args={[.2, .2, .16, 12]} /><meshStandardMaterial color="#3a5047" roughness={.94} /></mesh><mesh position={[Math.sign(x) * .087, 0, 0]} rotation-z={Math.PI / 2}><cylinderGeometry args={[.105, .105, .018, 10]} /><meshStandardMaterial color="#c9d4b8" /></mesh></group>))}
    <mesh position={[0, .735, -.1]}><cylinderGeometry args={[.12, .12, .12, 16]} /><meshStandardMaterial color="#405c4f" /></mesh>
    <mesh position={[0, .735, -.1]}><cylinderGeometry args={[.124, .124, .033, 16]} /><meshStandardMaterial color="#76c1b0" emissive="#489a8d" emissiveIntensity={.25} /></mesh>
    {[-.23, .23].map(x => <mesh key={x} position={[x, .35, .47]}><boxGeometry args={[.12, .07, .018]} /><meshBasicMaterial color="#fff8db" /></mesh>)}
    <mesh position={[.23, .72, -.28]}><cylinderGeometry args={[.012, .012, .34, 6]} /><meshStandardMaterial color="#496254" /></mesh>
  </group>;
}

function DroneModel({ color, animate }: { color: string; animate: boolean }) {
  const rotors = useRef<THREE.Group>(null);
  useFrame((_, delta) => { if (!animate || !rotors.current) return; rotors.current.children.forEach(rotor => { rotor.rotation.y += Math.min(delta, .05) * 22; }); });
  return <group>
    {[Math.PI / 4, -Math.PI / 4].map(angle => <RoundedBox key={angle} args={[1.28, .075, .12]} radius={.025} smoothness={1} rotation-y={angle} position={[0, .13, 0]} castShadow><meshStandardMaterial color="#51675c" /></RoundedBox>)}
    <RoundedBox args={[.44, .22, .57]} radius={.09} smoothness={2} position={[0, .2, 0]} castShadow><meshStandardMaterial color={color} roughness={.6} /></RoundedBox>
    <mesh position={[0, .03, .16]}><sphereGeometry args={[.11, 12, 8]} /><meshStandardMaterial color="#2f5553" metalness={.2} roughness={.2} /></mesh>
    {[-.46, .46].flatMap(x => [-.46, .46].map(z => <group key={`${x}-${z}`} position={[x, .14, z]}><mesh rotation-x={-Math.PI / 2}><ringGeometry args={[.22, .26, 28]} /><meshStandardMaterial color={color} side={THREE.DoubleSide} /></mesh><mesh><cylinderGeometry args={[.065, .065, .15, 10]} /><meshStandardMaterial color="#435b4e" /></mesh></group>))}
    <group ref={rotors}>{[-.46, .46].flatMap(x => [-.46, .46].map(z => <group key={`${x}-${z}`} position={[x, .24, z]}><mesh><boxGeometry args={[.43, .018, .045]} /><meshStandardMaterial color="#d5dfc4" transparent opacity={.75} /></mesh><mesh rotation-y={Math.PI / 2}><boxGeometry args={[.43, .018, .045]} /><meshStandardMaterial color="#d5dfc4" transparent opacity={.75} /></mesh></group>))}</group>
    {[-.22, .22].map(x => <mesh key={x} position={[x, -.11, 0]}><boxGeometry args={[.035, .22, .4]} /><meshStandardMaterial color="#718771" /></mesh>)}
  </group>;
}

function AgentModel({ agent, position, selected, onSelect, animate, neural }: { agent: ObservatoryAgent; position: V3; selected: boolean; onSelect: (id: string) => void; animate: boolean; neural: boolean }) {
  const group = useRef<THREE.Group>(null);
  const initial = useRef(position);
  const target = useMemo(() => new THREE.Vector3(...position), [position[0], position[1], position[2]]);
  useEffect(() => { if (!animate && group.current) group.current.position.copy(target); }, [animate, target]);
  // Smooth only between received poses; this never drives the simulation or predicts a route.
  useFrame((_, delta) => { if (animate && group.current) group.current.position.lerp(target, 1 - Math.exp(-Math.min(delta, .1) * 15)); });
  const altitude = agent.type === 'drone' ? neural ? .65 : .95 : .04;
  const ringRadius = neural ? 1.05 : .67;
  return <group ref={group} position={initial.current} onClick={event => { event.stopPropagation(); onSelect(agent.id); }}>
    <mesh position={[0, .025, 0]} rotation-x={-Math.PI / 2}><ringGeometry args={[ringRadius, ringRadius + (selected ? .055 : .025), 48]} /><meshBasicMaterial color={agent.color} transparent opacity={agent.fresh ? selected ? .9 : .4 : .18} side={THREE.DoubleSide} /></mesh>
    {neural && <><mesh position={[0, -.08, 0]} receiveShadow><cylinderGeometry args={[1.45, 1.52, .16, 64]} /><meshStandardMaterial color="#edf1df" roughness={.9} /></mesh><mesh position={[0, -.16, 0]}><cylinderGeometry args={[1.55, 1.55, .04, 64]} /><meshStandardMaterial color="#b7cbb2" /></mesh></>}
    <group position={[0, altitude, 0]} rotation-y={-agent.yaw} scale={neural ? 1.25 : .95}>
      {agent.type === 'rover' ? <RoverModel color={agent.fresh ? agent.color : '#a4afa0'} /> : <DroneModel color={agent.fresh ? agent.color : '#a4afa0'} animate={animate && agent.fresh} />}
    </group>
    {(neural || selected) && <Html position={[0, neural ? 2.35 : agent.type === 'drone' ? 1.8 : 1.35, 0]} center zIndexRange={[8, 0]} style={{ pointerEvents: 'none' }}><div className={`ob-scene-label ${selected ? 'selected' : ''}`} style={{ borderColor: agent.color }}>{shortName(agent.id)}<span style={{ display: 'inline-block', width: 4, height: 4, borderRadius: '50%', background: agent.fresh ? agent.color : '#b9bdb2', marginLeft: 7 }} /></div></Html>}
  </group>;
}

function makeCurve(from: V3, to: V3, neural: boolean) {
  return new THREE.QuadraticBezierCurve3(new THREE.Vector3(...from), new THREE.Vector3((from[0] + to[0]) / 2, neural ? 3.5 : Math.min(4, .8 + Math.hypot(to[0] - from[0], to[2] - from[2]) * .13), (from[2] + to[2]) / 2), new THREE.Vector3(...to));
}

function PacketPulse({ packet, curve, animate }: { packet: ObservatoryPacket; curve: THREE.QuadraticBezierCurve3; animate: boolean }) {
  const marker = useRef<THREE.Mesh>(null), tail = useRef<THREE.Mesh>(null), progress = useRef(0);
  const dropped = packet.state === 'dropped', queued = packet.state === 'queued';
  const visibleAtStart = Date.now() - packet.receivedAt < 5000;
  const location = useMemo(() => new THREE.Vector3(), []);
  useFrame((_, delta) => {
    if (!marker.current || !tail.current) return;
    if (animate && visibleAtStart) progress.current += Math.min(delta, .06) * .62;
    const maximum = dropped ? .52 : queued ? .72 : 1;
    const p = Math.min(maximum, progress.current), visible = visibleAtStart && progress.current < (queued ? 3 : 1.5);
    curve.getPoint(p, location); marker.current.position.copy(location); marker.current.visible = visible;
    curve.getPoint(Math.max(0, p - .045), location); tail.current.position.copy(location); tail.current.visible = visible;
    marker.current.scale.setScalar(dropped && p === maximum ? .65 : 1);
  });
  const color = dropped ? '#cf8a69' : '#4caaa0';
  return <><mesh ref={marker} visible={false}><sphereGeometry args={[.085, 10, 8]} /><meshBasicMaterial color={color} toneMapped={false} /></mesh><mesh ref={tail} visible={false}><sphereGeometry args={[.045, 8, 6]} /><meshBasicMaterial color={color} transparent opacity={.42} /></mesh></>;
}

function Communication({ snapshot, positions, neural, showPackets, animate }: { snapshot: ObservatoryCanvasProps['snapshot']; positions: Map<string, V3>; neural: boolean; showPackets: boolean; animate: boolean }) {
  const paths = useMemo(() => snapshot.links.flatMap(link => {
    const start = positions.get(link.source), end = positions.get(link.target); if (!start || !end) return [];
    return [{ ...link, curve: makeCurve([start[0], .65, start[2]], [end[0], .65, end[2]], neural) }];
  }), [snapshot.links, positions, neural]);
  const pulses = useMemo(() => snapshot.packets.slice(-28).flatMap(packet => {
    const start = positions.get(packet.source), end = positions.get(packet.target); if (!start || !end || Date.now() - packet.receivedAt > 5000) return [];
    return [{ packet, curve: makeCurve([start[0], .65, start[2]], [end[0], .65, end[2]], neural) }];
  }), [snapshot.packets, positions, neural]);
  return <>{paths.map(path => <Line key={`${path.source}-${path.target}`} points={path.curve.getPoints(36)} color={path.state === 'down' ? '#bca594' : '#83b6a5'} lineWidth={path.state === 'healthy' ? 1.2 : .8} transparent opacity={!snapshot.fresh ? .15 : path.state === 'down' ? .22 : .55} dashed={path.state !== 'healthy'} dashSize={.18} gapSize={.2} />)}{showPackets && pulses.map(({ packet, curve }) => <PacketPulse key={`${snapshot.epoch}-${packet.id}-${packet.state}`} packet={packet} curve={curve} animate={animate} />)}</>;
}

function CameraRig({ zoom, view, angle }: { zoom: number; view: string; angle: 'isometric' | 'top' }) {
  const { camera, size, invalidate } = useThree();
  useEffect(() => {
    if (!(camera instanceof THREE.OrthographicCamera)) return;
    camera.zoom = Math.min(size.width / 35, size.height / 25) * zoom;
    camera.updateProjectionMatrix(); invalidate();
  }, [camera, size.width, size.height, zoom, view, invalidate]);
  useEffect(() => {
    camera.position.set(...(angle === 'top' ? [0, 38, .01] : [22, 27, 25]) as V3);
    camera.lookAt(0, 0, 0); camera.updateProjectionMatrix(); invalidate();
  }, [angle, view, camera, invalidate]);
  return <OrbitControls key={`${angle}-${view}`} makeDefault enableDamping dampingFactor={.09} minZoom={7} maxZoom={95} minPolarAngle={.001} maxPolarAngle={Math.PI / 2.12} enablePan panSpeed={.75} rotateSpeed={.6} target={[0, 0, 0]} />;
}


function BoardGrid({ width, depth }: { width: number; depth: number }) {
  const geometry = useMemo(() => {
    const points: number[] = [];
    for (let x = -width / 2; x <= width / 2; x += 1.25) points.push(x, -.055, -depth / 2, x, -.055, depth / 2);
    for (let z = -depth / 2; z <= depth / 2; z += 1.25) points.push(-width / 2, -.055, z, width / 2, -.055, z);
    return new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(points, 3));
  }, [width, depth]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return <lineSegments geometry={geometry}><lineBasicMaterial color="#a8bc9c" transparent opacity={.28} /></lineSegments>;
}

function World({ snapshot, selected, onSelect, view, showPaths, showPackets, showFrontiers, frozen, zoom, cameraAngle = 'isometric', reduced }: ObservatoryCanvasProps & { reduced: boolean }) {
  const agents = snapshot.agents.filter(a => a.position !== null);
  const chosen = snapshot.agents.find(a => a.id === selected) || agents.find(a => a.grid !== null) || agents[0];
  const neural = view === 'neural', animate = snapshot.running && snapshot.fresh && !frozen && !reduced;
  const layout = useMemo(() => getLayout(agents, chosen), [agents.map(a => a.id).join(','), chosen?.grid?.width, chosen?.grid?.height, chosen?.grid?.resolution, chosen?.grid?.originX, chosen?.grid?.originY, chosen?.grid?.yaw, chosen?.id, chosen?.grid ? '' : agents.map(a => `${a.position!.x},${a.position!.y}`).join(';')]);
  const positions = useMemo(() => new Map(agents.map((agent, index) => {
    const angle = index / Math.max(1, agents.length) * Math.PI * 2 - Math.PI / 4;
    return [agent.id, neural ? [Math.cos(angle) * 7.7, .12, Math.sin(angle) * 7.7] as V3 : point(agent.position!, layout, .04)];
  })), [snapshot.agents, layout, neural]);
  const width = neural ? 23 : layout.width + 1.1, depth = neural ? 23 : layout.depth + 1.1;
  return <>
    <color attach="background" args={[PAPER]} /><fog attach="fog" args={[PAPER, 62, 110]} />
    <ambientLight intensity={.7} /><hemisphereLight args={['#fffdf0', '#99b395', .85]} />
    <directionalLight position={[-9, 19, 10]} intensity={1.65} castShadow shadow-mapSize={[2048, 2048]} shadow-camera-left={-18} shadow-camera-right={18} shadow-camera-top={18} shadow-camera-bottom={-18} shadow-bias={-.0003} shadow-normalBias={.05} />
    <directionalLight position={[12, 8, -12]} intensity={.45} color="#dbead7" />
    <mesh rotation-x={-Math.PI / 2} position={[0, -.49, 0]} receiveShadow><planeGeometry args={[200, 200]} /><meshStandardMaterial color={PAPER} roughness={1} /></mesh>
    <RoundedBox args={[width, .34, depth]} radius={.18} smoothness={3} position={[0, -.24, 0]} receiveShadow castShadow><meshStandardMaterial color={neural ? '#d9e5ce' : '#bdcfb1'} roughness={.9} /></RoundedBox>
    <mesh position={[0, -.445, 0]}><boxGeometry args={[width - .24, .07, depth - .24]} /><meshStandardMaterial color="#a7bba0" roughness={.9} /></mesh>
    <BoardGrid width={width - .5} depth={depth - .5} />
    {!neural && chosen && <BeliefMap agent={chosen} layout={layout} />}
    {!neural && showPaths && agents.map(agent => agent.path.length > 1 && <Line key={agent.id} points={agent.path.slice(-320).map(p => point(p, layout, .08))} color={agent.color} lineWidth={selected === agent.id ? 2.5 : 1.4} transparent opacity={agent.fresh ? .72 : .26} />)}
    {!neural && chosen && showFrontiers && chosen.frontiers.slice(0, 64).map((p, index) => <mesh key={index} position={point(p, layout, .09)} rotation-x={-Math.PI / 2}><ringGeometry args={[.12, .16, 16]} /><meshBasicMaterial color="#cc9b59" transparent opacity={.75} side={THREE.DoubleSide} /></mesh>)}
    {!neural && chosen?.goal && <group position={point(chosen.goal, layout, .1)}><mesh rotation-x={-Math.PI / 2}><ringGeometry args={[.3, .35, 40]} /><meshBasicMaterial color="#cf9652" side={THREE.DoubleSide} /></mesh><mesh position={[0, .3, 0]}><cylinderGeometry args={[.018, .018, .6, 6]} /><meshStandardMaterial color="#b99562" /></mesh><mesh position={[.13, .56, 0]}><boxGeometry args={[.26, .17, .025]} /><meshStandardMaterial color="#dbad6c" /></mesh></group>}
    <Communication snapshot={snapshot} positions={positions} neural={neural} showPackets={showPackets} animate={animate} />
    {agents.map(agent => <AgentModel key={agent.id} agent={agent} position={positions.get(agent.id)!} selected={selected === agent.id} onSelect={onSelect} animate={animate} neural={neural} />)}
    <CameraRig zoom={zoom} view={view} angle={cameraAngle} />
  </>;
}

function RendererHealth({ onLost }: { onLost: () => void }) {
  const canvas = useThree(state => state.gl.domElement);
  useEffect(() => {
    const lost = (event: Event) => { event.preventDefault(); onLost(); };
    canvas.addEventListener('webglcontextlost', lost);
    return () => canvas.removeEventListener('webglcontextlost', lost);
  }, [canvas, onLost]);
  return null;
}

export function ObservatoryScene(props: ObservatoryCanvasProps) {
  const reduced = useReducedMotion();
  const [lost, setLost] = useState(false);
  const onLost = useCallback(() => setLost(true), []);
  if (lost) return <GraphicsUnavailable onRetry={() => setLost(false)} />;
  return <div className="observatory-canvas" role="img" aria-label={props.view === 'spatial' ? 'Interactive 3D map of observed cells, robots and actual peer messages' : 'Interactive 3D communication topology of the active swarm'} style={{ position: 'absolute', inset: 0 }}>
    <Canvas fallback={<GraphicsUnavailable />} shadows orthographic frameloop={props.snapshot.running && props.snapshot.fresh && !props.frozen && !reduced ? 'always' : 'demand'} camera={{ position: [22, 27, 25], zoom: 24, near: .1, far: 200 }} dpr={[1, 1.7]} gl={{ antialias: true, alpha: false, powerPreference: 'high-performance' }} onCreated={({ gl }) => { gl.setClearColor(PAPER); gl.toneMapping = THREE.ACESFilmicToneMapping; gl.toneMappingExposure = 1.05; }}>
      <RendererHealth onLost={onLost} />
      <World {...props} reduced={reduced} />
    </Canvas>
  </div>;
}
