/** A* on a robot's private belief map (Python sim/planning.py astar_path). */
import type { Point } from '../core/types';
import { FREE, GridMap, NEIGHBOURS4, RUBBLE, UNKNOWN } from '../world/GridMap';

/** Binary min-heap over numeric tuples compared lexicographically (like Python heapq). */
export class TupleHeap {
  private items: number[][] = [];

  get size(): number {
    return this.items.length;
  }

  private static less(a: number[], b: number[]): boolean {
    for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] < b[i];
    return false;
  }

  push(item: number[]): void {
    const items = this.items;
    items.push(item);
    let i = items.length - 1;
    while (i > 0) {
      const parent = (i - 1) >> 1;
      if (!TupleHeap.less(items[i], items[parent])) break;
      [items[i], items[parent]] = [items[parent], items[i]];
      i = parent;
    }
  }

  pop(): number[] | undefined {
    const items = this.items;
    if (!items.length) return undefined;
    const top = items[0];
    const last = items.pop()!;
    if (items.length) {
      items[0] = last;
      let i = 0;
      for (;;) {
        const l = 2 * i + 1;
        const r = l + 1;
        let m = i;
        if (l < items.length && TupleHeap.less(items[l], items[m])) m = l;
        if (r < items.length && TupleHeap.less(items[r], items[m])) m = r;
        if (m === i) break;
        [items[i], items[m]] = [items[m], items[i]];
        i = m;
      }
    }
    return top;
  }
}

export interface PlanOptions {
  canCrossRubble?: boolean;
  /** Treat unknown cells as passable (operator waypoints into unexplored space). */
  optimisticUnknown?: boolean;
}

function passable(belief: GridMap, x: number, y: number, opts: PlanOptions): boolean {
  if (!belief.inBounds(x, y)) return false;
  const v = belief.get(x, y);
  if (v === FREE) return true;
  if (v === RUBBLE) return opts.canCrossRubble !== false;
  if (v === UNKNOWN) return !!opts.optimisticUnknown;
  return false;
}

/** Plan only through locally known traversable cells; returns [] when unreachable. */
export function astarPath(belief: GridMap, start: Point, goal: Point, opts: PlanOptions = {}): Point[] {
  const { width } = belief;
  if (!passable(belief, start.x, start.y, opts) && !(opts.optimisticUnknown && belief.inBounds(start.x, start.y))) return [];
  if (!passable(belief, goal.x, goal.y, opts)) return [];
  const heap = new TupleHeap();
  const cameFrom = new Map<number, number>();
  const costs = new Map<number, number>();
  const sIndex = start.y * width + start.x;
  const gIndex = goal.y * width + goal.x;
  heap.push([Math.abs(goal.x - start.x) + Math.abs(goal.y - start.y), 0, start.x, start.y]);
  cameFrom.set(sIndex, -1);
  costs.set(sIndex, 0);
  while (heap.size) {
    const [, cost, x, y] = heap.pop()!;
    const index = y * width + x;
    if (index === gIndex) {
      const path: Point[] = [];
      let cursor = gIndex;
      while (cursor !== -1) {
        path.push({ x: cursor % width, y: Math.floor(cursor / width) });
        cursor = cameFrom.get(cursor)!;
      }
      return path.reverse();
    }
    if (cost !== costs.get(index)) continue;
    for (const [dx, dy] of NEIGHBOURS4) {
      const nx = x + dx;
      const ny = y + dy;
      if (!passable(belief, nx, ny, opts)) continue;
      const next = cost + (belief.get(nx, ny) === RUBBLE ? 2 : 1);
      const ni = ny * width + nx;
      if (next < (costs.get(ni) ?? 1e9)) {
        costs.set(ni, next);
        cameFrom.set(ni, index);
        heap.push([next + Math.abs(goal.x - nx) + Math.abs(goal.y - ny), next, nx, ny]);
      }
    }
  }
  return [];
}
