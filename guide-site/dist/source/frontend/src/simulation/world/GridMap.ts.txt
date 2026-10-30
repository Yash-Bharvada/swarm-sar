/** Integer cell values shared by the truth grid and private belief maps (Python world/cells.py). */
export const UNKNOWN = -1;
export const FREE = 0;
export const WALL = 1;
export const RUBBLE = 2;

export type CellValue = typeof UNKNOWN | typeof FREE | typeof WALL | typeof RUBBLE;

/**
 * Render-only material tags. They never influence logic beyond the cell value
 * they sit on (a desk is a WALL cell drawn as a desk).
 */
export const Material = {
  None: 0,
  Concrete: 1,
  BrokenWall: 2,
  Rock: 3,
  Desk: 4,
  Crate: 5,
  Pillar: 6,
  Shelf: 7,
  Collapsed: 8,
} as const;
export type MaterialId = (typeof Material)[keyof typeof Material];

export class GridMap {
  readonly width: number;
  readonly height: number;
  readonly cells: Int8Array;

  constructor(width: number, height: number, fill: number = UNKNOWN, cells?: Int8Array) {
    this.width = width;
    this.height = height;
    this.cells = cells ?? new Int8Array(width * height).fill(fill);
  }

  inBounds(x: number, y: number): boolean {
    return x >= 0 && y >= 0 && x < this.width && y < this.height;
  }

  get(x: number, y: number): number {
    return this.cells[y * this.width + x];
  }

  set(x: number, y: number, value: number): void {
    this.cells[y * this.width + x] = value;
  }

  isTraversable(x: number, y: number, canCrossRubble = true): boolean {
    if (!this.inBounds(x, y)) return false;
    const v = this.get(x, y);
    return v === FREE || (canCrossRubble && v === RUBBLE);
  }

  clone(): GridMap {
    return new GridMap(this.width, this.height, UNKNOWN, new Int8Array(this.cells));
  }

  count(value: number): number {
    let n = 0;
    for (let i = 0; i < this.cells.length; i++) if (this.cells[i] === value) n++;
    return n;
  }
}

export const NEIGHBOURS4: ReadonlyArray<readonly [number, number]> = [
  [0, -1],
  [1, 0],
  [0, 1],
  [-1, 0],
];

/** 4-neighbour BFS distances from start over non-wall cells; -1 when unreachable. */
export function bfsDistances(grid: GridMap, sx: number, sy: number): Int32Array {
  const distances = new Int32Array(grid.width * grid.height).fill(-1);
  if (!grid.inBounds(sx, sy) || grid.get(sx, sy) === WALL) return distances;
  const queue = new Int32Array(grid.width * grid.height);
  let head = 0;
  let tail = 0;
  distances[sy * grid.width + sx] = 0;
  queue[tail++] = sy * grid.width + sx;
  while (head < tail) {
    const index = queue[head++];
    const x = index % grid.width;
    const y = (index - x) / grid.width;
    for (const [dx, dy] of NEIGHBOURS4) {
      const nx = x + dx;
      const ny = y + dy;
      if (!grid.inBounds(nx, ny)) continue;
      const ni = ny * grid.width + nx;
      if (distances[ni] >= 0 || grid.cells[ni] === WALL) continue;
      distances[ni] = distances[index] + 1;
      queue[tail++] = ni;
    }
  }
  return distances;
}

/** Python world/reachability.py close_unreachable: seal pockets unreachable from spawn. */
export function closeUnreachable(grid: GridMap, sx: number, sy: number): Int32Array {
  let distances = bfsDistances(grid, sx, sy);
  for (let i = 0; i < grid.cells.length; i++) {
    if (grid.cells[i] !== WALL && distances[i] < 0) grid.cells[i] = WALL;
  }
  distances = bfsDistances(grid, sx, sy);
  return distances;
}
