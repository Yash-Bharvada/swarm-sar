/** Line-of-sight vision and private fog-of-war updates (Python sensing/vision.py). */
import type { Point } from '../core/types';
import { GridMap, WALL } from '../world/GridMap';
import type { RobotState } from '../robots/RobotState';

export function bresenhamLine(start: Point, end: Point): Point[] {
  let x0 = start.x;
  let y0 = start.y;
  const x1 = end.x;
  const y1 = end.y;
  const points: Point[] = [];
  const dx = Math.abs(x1 - x0);
  const sx = x0 < x1 ? 1 : -1;
  const dy = -Math.abs(y1 - y0);
  const sy = y0 < y1 ? 1 : -1;
  let error = dx + dy;
  for (;;) {
    points.push({ x: x0, y: y0 });
    if (x0 === x1 && y0 === y1) return points;
    const twice = 2 * error;
    if (twice >= dy) {
      error += dy;
      x0 += sx;
    }
    if (twice <= dx) {
      error += dx;
      y0 += sy;
    }
  }
}

interface Ray {
  dx: number;
  dy: number;
  intermediates: Point[];
}

const rayCache = new Map<number, Ray[]>();

export function visionRays(radius: number): Ray[] {
  const cached = rayCache.get(radius);
  if (cached) return cached;
  const rays: Ray[] = [];
  for (let dy = -radius; dy <= radius; dy++)
    for (let dx = -radius; dx <= radius; dx++)
      if (dx * dx + dy * dy <= radius * radius) {
        const line = bresenhamLine({ x: 0, y: 0 }, { x: dx, y: dy });
        rays.push({ dx, dy, intermediates: line.slice(1, -1) });
      }
  rayCache.set(radius, rays);
  return rays;
}

/** Walls strictly between two cells block sight; the end wall itself is visible. */
export function hasLineOfSight(grid: GridMap, start: Point, end: Point): boolean {
  if (!grid.inBounds(end.x, end.y)) return false;
  const line = bresenhamLine(start, end);
  for (let i = 1; i < line.length - 1; i++) {
    const p = line[i];
    if (!grid.inBounds(p.x, p.y) || grid.get(p.x, p.y) === WALL) return false;
  }
  return true;
}

export function countWallsBetween(grid: GridMap, start: Point, end: Point): number {
  const line = bresenhamLine(start, end);
  let walls = 0;
  for (let i = 1; i < line.length - 1; i++) if (grid.get(line[i].x, line[i].y) === WALL) walls++;
  return walls;
}

/** Reveal visible truth cells into one robot's private belief map. Returns newly revealed count. */
export function updateVision(robot: RobotState, grid: GridMap, radius: number): number {
  let revealed = 0;
  for (const ray of visionRays(radius)) {
    const tx = robot.x + ray.dx;
    const ty = robot.y + ray.dy;
    if (!grid.inBounds(tx, ty)) continue;
    let blocked = false;
    for (const p of ray.intermediates) {
      if (grid.get(robot.x + p.x, robot.y + p.y) === WALL) {
        blocked = true;
        break;
      }
    }
    if (blocked) continue;
    if (robot.belief.get(tx, ty) < 0) revealed++;
    robot.belief.set(tx, ty, grid.get(tx, ty));
  }
  return revealed;
}
