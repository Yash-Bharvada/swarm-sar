export type RobotType = 'rover' | 'drone';

export interface Point {
  x: number;
  y: number;
}

export const pointKey = (x: number, y: number): string => `${x},${y}`;

export const samePoint = (a: Point | null | undefined, b: Point | null | undefined): boolean =>
  !!a && !!b && a.x === b.x && a.y === b.y;

export const manhattan = (a: Point, b: Point): number => Math.abs(a.x - b.x) + Math.abs(a.y - b.y);

/**
 * Grid movement actions (Python sim/engine.py ACTIONS):
 * 0 stay, 1 up (y-1), 2 down (y+1), 3 left (x-1), 4 right (x+1).
 */
export const MOVE_DELTAS: ReadonlyArray<readonly [number, number]> = [
  [0, 0],
  [0, -1],
  [0, 1],
  [-1, 0],
  [1, 0],
];

export function movementAction(from: Point, to: Point): number {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  for (let action = 0; action < MOVE_DELTAS.length; action++) {
    if (MOVE_DELTAS[action][0] === dx && MOVE_DELTAS[action][1] === dy) return action;
  }
  throw new Error(`Non-adjacent move ${from.x},${from.y} -> ${to.x},${to.y}`);
}

/**
 * High-level policy actions (Python sim/env.py):
 * 0–4 frontier slot, 5 investigate strongest thermal sector, 6 hold.
 */
export const FRONTIER_SLOTS = 5;
export const INVESTIGATE = 5;
export const HOLD = 6;

export type OperationMode = 'autonomous' | 'manual' | 'mixed';
export type MissionStatus = 'ready' | 'running' | 'paused' | 'complete';
