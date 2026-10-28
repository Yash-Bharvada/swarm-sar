/**
 * Ground-truth world container. Only the engine (physics, sensor emulation,
 * rendering and offline statistics) touches this; controllers never receive it.
 */
import type { Point } from '../core/types';
import type { RobotState } from '../robots/RobotState';
import { UNKNOWN, WALL } from './GridMap';
import type { Scenario, Victim } from './ScenarioGenerator';

export class WorldState {
  readonly reachableCount: number;
  private readonly reachable: Uint8Array;

  constructor(readonly scenario: Scenario) {
    const { grid, distances } = scenario;
    this.reachable = new Uint8Array(grid.cells.length);
    let n = 0;
    for (let i = 0; i < grid.cells.length; i++) {
      if (distances[i] >= 0 && grid.cells[i] !== WALL) {
        this.reachable[i] = 1;
        n++;
      }
    }
    this.reachableCount = n;
  }

  get grid() {
    return this.scenario.grid;
  }

  get victims(): Victim[] {
    return this.scenario.victims;
  }

  /** Spawn staging cells (non-wall) in row-major order. */
  spawnCells(): Point[] {
    const { x, y, size } = this.scenario.spawn;
    const cells: Point[] = [];
    for (let yy = y; yy < y + size; yy++) for (let xx = x; xx < x + size; xx++) if (this.grid.get(xx, yy) !== WALL) cells.push({ x: xx, y: yy });
    return cells;
  }

  /** Offline statistic: fraction of reachable cells known to at least one robot. */
  coverage(robots: RobotState[]): number {
    if (!this.reachableCount) return 0;
    let known = 0;
    for (let i = 0; i < this.reachable.length; i++) {
      if (!this.reachable[i]) continue;
      for (const r of robots)
        if (r.belief.cells[i] !== UNKNOWN) {
          known++;
          break;
        }
    }
    return known / this.reachableCount;
  }
}
