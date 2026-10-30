/**
 * Local frontier detection and candidate selection (Python sim/planning.py
 * frontier_clusters / frontier_candidates, multi-sample branch used by Step 4).
 */
import type { Point } from '../core/types';
import { FREE, GridMap, NEIGHBOURS4, RUBBLE, UNKNOWN } from '../world/GridMap';
import { TupleHeap } from './AStar';

export interface FrontierCandidate {
  position: Point;
  clusterSize: number;
  path: Point[];
  distance: number;
  activeGoal?: boolean;
}

/** Connected known-traversable cells that border unknown space. */
export function frontierClusters(belief: GridMap): Point[][] {
  const { width, height } = belief;
  const frontier = new Uint8Array(width * height);
  for (let y = 0; y < height; y++)
    for (let x = 0; x < width; x++) {
      const v = belief.get(x, y);
      if (v !== FREE && v !== RUBBLE) continue;
      for (const [dx, dy] of NEIGHBOURS4) {
        const nx = x + dx;
        const ny = y + dy;
        if (belief.inBounds(nx, ny) && belief.get(nx, ny) === UNKNOWN) {
          frontier[y * width + x] = 1;
          break;
        }
      }
    }
  const seen = new Uint8Array(width * height);
  const clusters: Point[][] = [];
  // Row-major scan matches numpy argwhere ordering.
  for (let y = 0; y < height; y++)
    for (let x = 0; x < width; x++) {
      const i = y * width + x;
      if (!frontier[i] || seen[i]) continue;
      const cluster: Point[] = [];
      const queue: Point[] = [{ x, y }];
      seen[i] = 1;
      for (let head = 0; head < queue.length; head++) {
        const c = queue[head];
        cluster.push(c);
        for (const [dx, dy] of NEIGHBOURS4) {
          const nx = c.x + dx;
          const ny = c.y + dy;
          if (!belief.inBounds(nx, ny)) continue;
          const ni = ny * width + nx;
          if (frontier[ni] && !seen[ni]) {
            seen[ni] = 1;
            queue.push({ x: nx, y: ny });
          }
        }
      }
      clusters.push(cluster);
    }
  return clusters;
}

const cmpPoint = (a: Point, b: Point): number => a.x - b.x || a.y - b.y;

/**
 * Up to `maxCandidates` reachable frontier representatives, diversified across
 * branches. One Dijkstra pass supplies paths to every sampled frontier.
 */
export function frontierCandidates(
  belief: GridMap,
  start: Point,
  maxCandidates = 5,
  maxPerCluster = 5,
  canCrossRubble = true,
): FrontierCandidate[] {
  const { width } = belief;
  const passable = (x: number, y: number) => belief.isTraversable(x, y, canCrossRubble);
  if (!passable(start.x, start.y)) return [];

  const heap = new TupleHeap();
  const costs = new Map<number, number>();
  const cameFrom = new Map<number, number>();
  const sIndex = start.y * width + start.x;
  heap.push([0, start.x, start.y]);
  costs.set(sIndex, 0);
  cameFrom.set(sIndex, -1);
  while (heap.size) {
    const [cost, x, y] = heap.pop()!;
    if (cost !== costs.get(y * width + x)) continue;
    for (const [dx, dy] of NEIGHBOURS4) {
      const nx = x + dx;
      const ny = y + dy;
      if (!passable(nx, ny)) continue;
      const next = cost + (belief.get(nx, ny) === RUBBLE ? 2 : 1);
      const ni = ny * width + nx;
      if (next < (costs.get(ni) ?? Infinity)) {
        costs.set(ni, next);
        cameFrom.set(ni, y * width + x);
        heap.push([next, nx, ny]);
      }
    }
  }

  const pathTo = (p: Point): Point[] => {
    const path: Point[] = [];
    let cursor = p.y * width + p.x;
    while (cursor !== -1) {
      path.push({ x: cursor % width, y: Math.floor(cursor / width) });
      cursor = cameFrom.get(cursor)!;
    }
    return path.reverse();
  };

  const groups: FrontierCandidate[][] = [];
  for (const cluster of frontierClusters(belief)) {
    // Long boundaries offer several directions so peers can disperse
    // (deterministic farthest-point sampling).
    const count = Math.min(maxCandidates, Math.max(1, maxPerCluster), Math.max(1, Math.floor((cluster.length + 7) / 8)));
    let first = cluster[0];
    for (const p of cluster) {
      const dp = Math.abs(p.x - start.x) + Math.abs(p.y - start.y);
      const df = Math.abs(first.x - start.x) + Math.abs(first.y - start.y);
      if (dp < df || (dp === df && cmpPoint(p, first) < 0)) first = p;
    }
    const reps: Point[] = [first];
    while (reps.length < count) {
      let best: Point | null = null;
      let bestScore = -1;
      for (const p of cluster) {
        if (reps.some((r) => r.x === p.x && r.y === p.y)) continue;
        let score = Infinity;
        for (const r of reps) score = Math.min(score, (p.x - r.x) ** 2 + (p.y - r.y) ** 2);
        // Python tie-break: larger (score, -y, -x) wins.
        if (!best || score > bestScore || (score === bestScore && (p.y < best.y || (p.y === best.y && p.x < best.x)))) {
          best = p;
          bestScore = score;
        }
      }
      if (!best) break;
      reps.push(best);
    }
    const group: FrontierCandidate[] = [];
    for (const rep of reps) {
      if (!cameFrom.has(rep.y * width + rep.x)) continue;
      const path = pathTo(rep);
      group.push({ position: rep, clusterSize: cluster.length, path, distance: Math.max(0, path.length - 1) });
    }
    group.sort((a, b) => a.distance - b.distance || cmpPoint(a.position, b.position));
    if (group.length) groups.push(group);
  }

  groups.sort(
    (a, b) => b[0].clusterSize - a[0].clusterSize || a[0].distance - b[0].distance || cmpPoint(a[0].position, b[0].position),
  );
  // Distinct branches first, then extra directions from large boundaries.
  const selected = groups.slice(0, maxCandidates).map((g) => g[0]);
  if (selected.length < maxCandidates) {
    const extras = groups.flatMap((g) => g.slice(1)).filter((c) => !selected.includes(c));
    extras.sort((a, b) => b.clusterSize - a.clusterSize || a.distance - b.distance || cmpPoint(a.position, b.position));
    selected.push(...extras.slice(0, maxCandidates - selected.length));
  }
  return selected;
}
