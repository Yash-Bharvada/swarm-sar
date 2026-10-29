import { useEffect, useRef } from 'react';
import type { SimulationEngine } from '../simulation/core/SimulationEngine';
import type { RobotState } from '../simulation/robots/RobotState';
import { FREE, RUBBLE, WALL } from '../simulation/world/GridMap';
import { evidencePosition, maxThermal } from '../simulation/sensing/SensorModel';

/**
 * Draws one robot's PRIVATE belief map: what it has sensed itself plus map
 * cells merged from delivered peer messages. Teammates are drawn where their
 * last delivered message said they were, not where they truly are.
 */
export function MiniMap({ engine, robot, version }: { engine: SimulationEngine; robot: RobotState; version: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const offscreen = useRef<HTMLCanvasElement | null>(null);
  const { width, height } = robot.belief;
  const scale = Math.max(2, Math.floor(Math.min(280 / width, 220 / height)));

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;
    const img = ctx.createImageData(width, height);
    for (let i = 0; i < width * height; i++) {
      const v = robot.belief.cells[i];
      const [r, g, b] = v === FREE ? [246, 224, 172] : v === WALL ? [107, 130, 109] : v === RUBBLE ? [190, 137, 91] : [226, 232, 222];
      img.data.set([r, g, b, 255], i * 4);
    }
    // Draw at 1px per cell, then scale up crisply.
    const off = offscreen.current ?? (offscreen.current = document.createElement('canvas'));
    off.width = width;
    off.height = height;
    off.getContext('2d')!.putImageData(img, 0, 0);
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(off, 0, 0, width * scale, height * scale);

    const dot = (x: number, y: number, color: string, radius: number, hollow = false) => {
      ctx.beginPath();
      ctx.arc((x + 0.5) * scale, (y + 0.5) * scale, radius, 0, Math.PI * 2);
      if (hollow) {
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        ctx.stroke();
      } else {
        ctx.fillStyle = color;
        ctx.fill();
      }
    };

    // Path and goal from its own planner.
    if (robot.path.length > 1) {
      ctx.strokeStyle = robot.type === 'rover' ? '#b96c2c' : '#177d83';
      ctx.lineWidth = Math.max(1, scale / 2.5);
      ctx.beginPath();
      robot.path.forEach((p, i) => (i ? ctx.lineTo((p.x + 0.5) * scale, (p.y + 0.5) * scale) : ctx.moveTo((p.x + 0.5) * scale, (p.y + 0.5) * scale)));
      ctx.stroke();
    }
    if (robot.activeGoal) {
      ctx.strokeStyle = '#244e43';
      ctx.lineWidth = 1.5;
      ctx.strokeRect(robot.activeGoal.x * scale - 1, robot.activeGoal.y * scale - 1, scale + 2, scale + 2);
    }
    // Teammates as last reported in delivered messages (odometry frame).
    for (const m of engine.network.enabled ? engine.network.peerMessages(robot.name, engine.step) : []) {
      dot(m.pose[0], m.pose[1], m.robotType === 'rover' ? '#b96c2c' : '#177d83', Math.max(2.5, scale * 0.7), true);
      if (m.evidence.position && m.evidence.thermal >= 0.35) dot(m.evidence.position[0], m.evidence.position[1], '#d97336', Math.max(2, scale * 0.5), true);
    }
    // Own heat estimate.
    if (maxThermal(robot.thermal) >= 0.16) {
      const est = evidencePosition(robot);
      if (est) dot(est.x, est.y, '#d97336', Math.max(2.5, scale * 0.7));
    }
    // Survivors this robot confirmed itself.
    for (const v of engine.discoveredSurvivors()) if (v.foundBy === robot.name) dot(v.x, v.y, '#1e8862', Math.max(3, scale));
    dot(robot.x, robot.y, '#fffdf4', Math.max(4, scale * 1.1));
    dot(robot.x, robot.y, robot.type === 'rover' ? '#b96c2c' : '#177d83', Math.max(2.5, scale * 0.75));
  }, [engine, robot, version, width, height, scale]);

  return <canvas ref={ref} className="minimap" width={width * scale} height={height * scale} role="img" aria-label={`${robot.label}'s local map. Pale areas are unknown, sand is traversable, green marks walls, and brown marks rubble.`} />;
}
