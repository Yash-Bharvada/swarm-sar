import { createPortal } from 'react-dom';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { PerspectiveCamera, View } from '@react-three/drei';
import { Drone, Rover } from '../scene/Robots';
import { QUALITY } from '../scene/common';
import type { SimulationEngine } from '../simulation/core/SimulationEngine';
import type { RobotState } from '../simulation/robots/RobotState';

function useStillPreview() {
  const [still, setStill] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setStill(query.matches);
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);
  return still;
}

/** Views share one renderer for the whole panel, including a ten-unit fleet. */
export function RobotPreview({ engine, robot, large = false }: { engine: SimulationEngine; robot: RobotState; large?: boolean }) {
  const still = useStillPreview();
  const Model = robot.type === 'rover' ? Rover : Drone;
  return <div className={`robot-preview ${robot.type} ${large ? 'large' : ''}`} aria-hidden="true">
    <View className="robot-preview-view">
      <PerspectiveCamera makeDefault position={[0, 1.25, 2.8]} rotation={[-0.42, 0, 0]} fov={36} />
      <ambientLight intensity={1.3} />
      <directionalLight position={[3, 4, 5]} intensity={2.5} color="#fff2d6" />
      <directionalLight position={[-3, 2, -2]} intensity={0.8} color="#b8e6db" />
      <Model engine={engine} robot={robot} quality={QUALITY.low} selected={false} onSelect={() => {}} preview still={still} />
    </View>
    <span className="preview-orbit" />
  </div>;
}

export function FleetPreviewCanvas() {
  const still = useStillPreview();
  const anchor = useRef<HTMLSpanElement>(null);
  const [clip, setClip] = useState('inset(100%)');
  useLayoutEffect(() => {
    const drawer = anchor.current?.parentElement;
    if (!drawer) return;
    const measure = () => {
      const r = drawer.getBoundingClientRect();
      setClip(`inset(${r.top}px ${Math.max(0, innerWidth - r.right)}px ${Math.max(0, innerHeight - r.bottom)}px ${r.left}px round 20px)`);
    };
    const observer = new ResizeObserver(measure);
    observer.observe(drawer);
    window.addEventListener('resize', measure);
    // Measure after the short drawer entrance transform has settled, too.
    const settled = window.setTimeout(measure, 300);
    measure();
    return () => { observer.disconnect(); clearTimeout(settled); window.removeEventListener('resize', measure); };
  }, []);
  return <><span ref={anchor} hidden />{createPortal(<div className="fleet-preview-layer" style={{ clipPath: clip }} aria-hidden="true">
    <Canvas dpr={1} frameloop={still ? 'demand' : 'always'} gl={{ alpha: true, antialias: true }}>
      <View.Port />
    </Canvas>
  </div>, document.body)}</>;
}
