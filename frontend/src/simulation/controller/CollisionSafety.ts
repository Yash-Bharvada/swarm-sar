/**
 * Collision-safe simultaneous movement.
 *
 * `safetyFilter` ports DisasterResponseParallelEnv._safety_filter_movements: a
 * one-step local shield applied below goal selection (autonomous AND manual).
 * `applyMovements` ports sim/engine.py apply_movements: the physics resolver.
 * Together they guarantee: no two robots in one cell, no head-on swaps, and
 * convoys may advance through one-cell corridors when every robot ahead leaves.
 */
import type { Rng } from '../core/Rng';
import { MOVE_DELTAS } from '../core/types';
import { GridMap, RUBBLE, WALL } from '../world/GridMap';
import type { RobotState } from '../robots/RobotState';

export type MoveMap = Map<number, number>;

export interface SafetyReport {
  filtered: MoveMap;
  /** Robots whose requested move was cancelled by the shield. */
  held: number[];
  /** Robots pushed along by the convoy/yield rule. */
  yielded: number[][];
}

const pk = (x: number, y: number) => y * 100000 + x;

function cellAllows(grid: GridMap, robot: RobotState, x: number, y: number): boolean {
  if (!grid.inBounds(x, y)) return false;
  const cell = grid.get(x, y);
  if (cell === WALL && !robot.config.canCrossWalls) return false;
  if (cell === RUBBLE && !robot.config.canCrossRubble) return false;
  return true;
}

export function safetyFilter(robots: RobotState[], requested: MoveMap, grid: GridMap, stepCount: number): SafetyReport {
  const alive = new Map<number, RobotState>();
  for (const r of robots) if (r.alive) alive.set(r.id, r);
  const filtered: MoveMap = new Map(requested);
  const occupant = new Map<number, number>();
  for (const [id, r] of alive) occupant.set(pk(r.x, r.y), id);
  const yielded: number[][] = [];

  // Narrow-passage traffic rule: if a priority robot's step points through a
  // contiguous line of peers to a free cell, that line yields in the same
  // direction for one tick. Priority rotates with the step counter.
  const locked = new Set<number>();
  const ids = [...alive.keys()].sort((a, b) => a - b);
  const offset = ids.length ? stepCount % ids.length : 0;
  const priority = [...ids.slice(offset), ...ids.slice(0, offset)];
  for (const id of priority) {
    const action = filtered.get(id) ?? 0;
    if (!action || locked.has(id)) continue;
    const [dx, dy] = MOVE_DELTAS[action];
    const chain = [id];
    let cx = alive.get(id)!.x + dx;
    let cy = alive.get(id)!.y + dy;
    while (occupant.has(pk(cx, cy)) && !chain.includes(occupant.get(pk(cx, cy))!)) {
      const other = occupant.get(pk(cx, cy))!;
      chain.push(other);
      cx = alive.get(other)!.x + dx;
      cy = alive.get(other)!.y + dy;
    }
    if (chain.length < 2 || occupant.has(pk(cx, cy)) || chain.some((c) => locked.has(c))) continue;
    const traversable = chain.every((c) => {
      const r = alive.get(c)!;
      return cellAllows(grid, r, r.x + dx, r.y + dy);
    });
    if (traversable) {
      for (const c of chain) filtered.set(c, action);
      chain.forEach((c) => locked.add(c));
      yielded.push(chain);
    }
  }

  const targets = new Map<number, [number, number]>();
  for (const [id, action] of filtered) {
    const r = alive.get(id);
    if (!r) continue;
    const [dx, dy] = MOVE_DELTAS[action];
    // Browser addition: cancel steps into impassable cells here rather than
    // letting physics reject them (A* never plans such steps; operators might).
    if (action && !cellAllows(grid, r, r.x + dx, r.y + dy)) {
      filtered.set(id, 0);
      targets.set(id, [r.x, r.y]);
      continue;
    }
    targets.set(id, [r.x + dx, r.y + dy]);
  }

  // Same-cell claims: one deterministic winner per contested cell.
  const claims = new Map<number, number[]>();
  for (const [id, [tx, ty]] of targets) {
    const r = alive.get(id)!;
    if (tx !== r.x || ty !== r.y) {
      const key = pk(tx, ty);
      if (!claims.has(key)) claims.set(key, []);
      claims.get(key)!.push(id);
    }
  }
  for (const claimants of claims.values()) {
    if (claimants.length < 2) continue;
    claimants.sort((a, b) => a - b);
    const winner = claimants[stepCount % claimants.length];
    for (const id of claimants)
      if (id !== winner) {
        filtered.set(id, 0);
        const r = alive.get(id)!;
        targets.set(id, [r.x, r.y]);
      }
  }

  // A convoy may advance when every robot ahead is leaving its cell. Cycles
  // (including head-on swaps) and chains ending at a stationary robot stay blocked.
  const memo = new Map<number, boolean>();
  const canMove = (id: number, visiting: Set<number>): boolean => {
    if (memo.has(id)) return memo.get(id)!;
    if ((filtered.get(id) ?? 0) === 0) {
      memo.set(id, false);
      return false;
    }
    const [tx, ty] = targets.get(id)!;
    const other = occupant.get(pk(tx, ty));
    if (other === undefined) {
      memo.set(id, true);
      return true;
    }
    if (visiting.has(other)) {
      memo.set(id, false);
      return false;
    }
    const allowed = canMove(other, new Set([...visiting, other]));
    memo.set(id, allowed);
    return allowed;
  };
  const held: number[] = [];
  for (const id of [...filtered.keys()].sort((a, b) => a - b)) {
    if (!alive.has(id)) continue;
    if (filtered.get(id) && !canMove(id, new Set([id]))) {
      filtered.set(id, 0);
      held.push(id);
    }
  }
  for (const [id, action] of requested) if (action && filtered.get(id) === 0 && !held.includes(id)) held.push(id);
  return { filtered, held, yielded };
}

/**
 * Resolve and apply simultaneous intents (physics). Returns the number of
 * collisions, i.e. moves rejected at this layer (zero when the shield ran first).
 */
export function applyMovements(robots: RobotState[], actions: MoveMap, grid: GridMap, rng: Rng): number {
  const alive = new Map<number, RobotState>();
  for (const r of robots) if (r.alive) alive.set(r.id, r);
  const occupant = new Map<number, number>();
  for (const [id, r] of alive) occupant.set(pk(r.x, r.y), id);
  const targets = new Map<number, [number, number]>();
  const eligible = new Set<number>();

  for (const r of robots) {
    r.collided = false;
    r.lastAction = actions.get(r.id) ?? 0;
    if (!r.alive) continue;
    const [dx, dy] = MOVE_DELTAS[r.lastAction];
    const t: [number, number] = [r.x + dx, r.y + dy];
    targets.set(r.id, t);
    if (r.lastAction && cellAllows(grid, r, t[0], t[1])) eligible.add(r.id);
  }

  const claims = new Map<number, number[]>();
  for (const id of [...eligible].sort((a, b) => a - b)) {
    const key = pk(...targets.get(id)!);
    if (!claims.has(key)) claims.set(key, []);
    claims.get(key)!.push(id);
  }
  for (const claimants of claims.values()) {
    if (claimants.length > 1) {
      const winner = claimants[rng.integers(claimants.length)];
      for (const id of claimants) if (id !== winner) eligible.delete(id);
    }
  }

  const memo = new Map<number, boolean>();
  const canMove = (id: number, visiting: Set<number>): boolean => {
    if (memo.has(id)) return memo.get(id)!;
    const other = occupant.get(pk(...targets.get(id)!));
    if (other === undefined) {
      memo.set(id, true);
      return true;
    }
    if (!eligible.has(other) || visiting.has(other)) {
      memo.set(id, false);
      return false;
    }
    const allowed = canMove(other, new Set([...visiting, other]));
    memo.set(id, allowed);
    return allowed;
  };
  const accepted = new Set([...eligible].filter((id) => canMove(id, new Set([id]))));

  let collisions = 0;
  for (const r of robots) {
    if (!r.alive) continue;
    const moving = r.lastAction !== 0;
    let cost: number;
    if (moving && !accepted.has(r.id)) {
      r.collided = true;
      collisions++;
      cost = r.config.idleCost;
    } else if (!moving) {
      cost = r.config.idleCost;
    } else {
      const [dx, dy] = MOVE_DELTAS[r.lastAction];
      [r.x, r.y] = targets.get(r.id)!;
      r.visited[r.y * grid.width + r.x] = 1;
      r.distanceTravelled++;
      r.heading = Math.atan2(dx, dy);
      r.odomX += dx + rng.normal(0, r.config.odometryDriftStd);
      r.odomY += dy + rng.normal(0, r.config.odometryDriftStd);
      r.odomUncertainty += r.config.odometryUncertaintyGrowth;
      cost = grid.get(r.x, r.y) === RUBBLE ? r.config.rubbleCost : r.config.moveCost;
    }
    r.battery = Math.max(0, r.battery - cost);
    if (r.battery <= 0) r.alive = false;
  }
  return collisions;
}
