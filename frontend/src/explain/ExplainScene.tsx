import { useRef } from 'react';
import { Html, Line } from '@react-three/drei';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { useSim } from '../store/simStore';
import type { SimulationEngine } from '../simulation/core/SimulationEngine';
import { robotRenderPosition } from '../scene/common';
import { STORY, useExplain } from './story';

function SensorSpotlight({ engine, name }: { engine: SimulationEngine; name: string }) {
  const group = useRef<THREE.Group>(null);
  const sweep = useRef<THREE.Group>(null);
  const robot = engine.robots.find((r) => r.name === name);
  const still = typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;
  useFrame((_, delta) => {
    if (!robot || !group.current) return;
    robotRenderPosition(engine, robot.id, group.current.position);
    group.current.position.y = 0.16;
    if (sweep.current && !still && useSim.getState().status === 'running') sweep.current.rotation.y += delta * 0.8;
  });
  if (!robot) return null;
  const radius = robot.config.visionRadius;
  const circle = Array.from({ length: 65 }, (_, i) => new THREE.Vector3(Math.cos(i / 64 * Math.PI * 2) * radius, 0, Math.sin(i / 64 * Math.PI * 2) * radius));
  return <group ref={group} name="explain-sensor-spotlight">
    <Line points={circle} color="#277c73" lineWidth={1.5} dashed dashSize={0.3} gapSize={0.3} transparent opacity={0.7} />
    <group ref={sweep}><Line points={[[0, 0.01, 0], [radius, 0.01, 0]]} color="#277c73" lineWidth={1.5} transparent opacity={0.45} /></group>
    <Html position={[0, 2.5, 0]} center zIndexRange={[12, 0]} style={{ pointerEvents: 'none' }}><div className="ex-robot-caption"><span />{robot.type === 'rover' ? 'Our careful ground explorer' : 'Our wider-looking scout'}</div></Html>
  </group>;
}

export function ExplainScene({ engine }: { engine: SimulationEngine }) {
  const active = useSim((s) => s.explainActive);
  const selected = useSim((s) => s.selected);
  const beat = useExplain((s) => s.beat);
  const part = useExplain((s) => s.systemPart);
  const cue = STORY[beat].cue;
  if (!active || !selected || !(['rover', 'drone'].includes(cue) || (cue === 'system' && part === 0))) return null;
  return <SensorSpotlight engine={engine} name={selected} />;
}
