import { Rng } from '../simulation/core/Rng';
import { applyMovements, safetyFilter } from '../simulation/controller/CollisionSafety';
import { SimulationEngine, defaultOptions } from '../simulation/core/SimulationEngine';
import { WALL } from '../simulation/world/GridMap';
import { corridor, openGrid, robotAt } from './helpers';

// Movement actions: 1 up, 2 down, 3 left, 4 right.
const RIGHT = 4;
const LEFT = 3;

function run(robots: ReturnType<typeof robotAt>[], actions: Array<[number, number]>, grid = openGrid(10, 10), step = 0) {
  const { filtered, held } = safetyFilter(robots, new Map(actions), grid, step);
  const collisions = applyMovements(robots, filtered, grid, new Rng(1));
  return { filtered, held, collisions };
}

const positions = (robots: ReturnType<typeof robotAt>[]) => robots.map((r) => [r.x, r.y]);

describe('CollisionSafety', () => {
  it('prevents same-cell overlap when two robots claim one cell', () => {
    const grid = openGrid(10, 10);
    const a = robotAt(0, 'rover', 2, 2, grid);
    const b = robotAt(1, 'drone', 4, 2, grid);
    const { collisions } = run([a, b], [[0, RIGHT], [1, LEFT]], grid);
    expect(collisions).toBe(0);
    expect(`${a.x},${a.y}`).not.toBe(`${b.x},${b.y}`);
    // Exactly one of them entered the contested cell.
    expect([a, b].filter((r) => r.x === 3 && r.y === 2)).toHaveLength(1);
  });

  it('blocks head-on swaps', () => {
    // Pocket with no room to yield: a true swap is the only way to satisfy both.
    const grid = corridor(8);
    grid.set(2, 1, WALL);
    grid.set(5, 1, WALL);
    const a = robotAt(0, 'rover', 3, 1, grid);
    const b = robotAt(1, 'rover', 4, 1, grid);
    for (let tick = 0; tick < 4; tick++) {
      const { collisions } = run([a, b], [[0, RIGHT], [1, LEFT]], grid, tick);
      expect(collisions).toBe(0);
      expect(positions([a, b])).toEqual([
        [3, 1],
        [4, 1],
      ]);
    }
  });

  it('opposing intents in an open corridor resolve by yielding, never by swapping', () => {
    const grid = corridor(10);
    const a = robotAt(0, 'rover', 4, 1, grid);
    const b = robotAt(1, 'rover', 5, 1, grid);
    const { collisions } = run([a, b], [[0, RIGHT], [1, LEFT]], grid);
    expect(collisions).toBe(0);
    expect(a.x).toBeLessThan(b.x);
    expect(a.x).not.toBe(b.x);
  });

  it('lets a convoy advance together through a one-cell corridor', () => {
    const grid = corridor(12);
    const team = [robotAt(0, 'rover', 2, 1, grid), robotAt(1, 'drone', 3, 1, grid), robotAt(2, 'rover', 4, 1, grid)];
    for (let tick = 0; tick < 5; tick++) {
      const { collisions } = run(team, [[0, RIGHT], [1, RIGHT], [2, RIGHT]], grid, tick);
      expect(collisions).toBe(0);
    }
    expect(positions(team)).toEqual([
      [7, 1],
      [8, 1],
      [9, 1],
    ]);
  });

  it('a holding robot yields forward instead of deadlocking the corridor', () => {
    const grid = corridor(8);
    const mover = robotAt(0, 'rover', 2, 1, grid);
    const blocker = robotAt(1, 'drone', 3, 1, grid);
    const { filtered } = safetyFilter([mover, blocker], new Map([[0, RIGHT], [1, 0]]), grid, 0);
    expect(filtered.get(1)).toBe(RIGHT);
    applyMovements([mover, blocker], filtered, grid, new Rng(1));
    expect(positions([mover, blocker])).toEqual([
      [3, 1],
      [4, 1],
    ]);
  });

  it('a robot turning out of the way is followed, not pushed (no livelock)', () => {
    const grid = openGrid(6, 6);
    const follower = robotAt(0, 'rover', 1, 1, grid);
    const turner = robotAt(1, 'rover', 2, 1, grid);
    for (const step of [0, 1]) {
      follower.x = 1;
      follower.y = 1;
      turner.x = 2;
      turner.y = 1;
      const { collisions } = run([follower, turner], [[0, RIGHT], [1, 2]], grid, step);
      expect(collisions).toBe(0);
      expect(positions([follower, turner])).toEqual([
        [2, 1],
        [2, 2],
      ]);
    }
  });

  it('a convoy stops at a wall instead of overlapping', () => {
    const grid = corridor(6);
    grid.set(5, 1, WALL);
    const team = [robotAt(0, 'rover', 3, 1, grid), robotAt(1, 'rover', 4, 1, grid)];
    const { collisions } = run(team, [[0, RIGHT], [1, RIGHT]], grid);
    expect(collisions).toBe(0);
    expect(positions(team)).toEqual([
      [3, 1],
      [4, 1],
    ]);
  });

  it('robots never cross walls', () => {
    const grid = openGrid(6, 6);
    grid.set(3, 2, WALL);
    const drone = robotAt(0, 'drone', 2, 2, grid);
    run([drone], [[0, RIGHT]], grid);
    expect([drone.x, drone.y]).toEqual([2, 2]);
  });

  it('manual movement still passes through collision safety', () => {
    const engine = new SimulationEngine(defaultOptions({ preset: 'demo', seed: 11, mode: 'manual', packetLoss: 0 }));
    const [a, b] = engine.robots;
    // Place two robots side by side inside the clear staging area.
    const sx = engine.scenario.spawn.x;
    const sy = engine.scenario.spawn.y;
    engine.robots.forEach((r, i) => {
      r.x = sx + i;
      r.y = sy + 3;
    });
    // Drive a into b, which holds: no overlap.
    engine.issue({ kind: 'setMode', mode: 'manual', manualRobot: a.name });
    engine.issue({ kind: 'manualStep', robot: a.name, direction: RIGHT });
    engine.tick();
    const cells = engine.robots.map((r) => `${r.x},${r.y}`);
    expect(new Set(cells).size).toBe(cells.length);
    expect(engine.collisions).toBe(0);

    // Two manual robots commanded into the same cell: only one enters.
    const target = { x: sx + 1, y: sy + 1 };
    a.x = sx;
    a.y = sy + 1;
    b.x = sx + 2;
    b.y = sy + 1;
    engine.robots.slice(2).forEach((r, i) => {
      r.x = sx + i;
      r.y = sy + 3;
    });
    engine.issue({ kind: 'manualStep', robot: a.name, direction: RIGHT });
    engine.issue({ kind: 'manualStep', robot: b.name, direction: LEFT });
    engine.tick();
    expect([a, b].filter((r) => r.x === target.x && r.y === target.y)).toHaveLength(1);
    expect(engine.collisions).toBe(0);

    // Manual driving into a wall is refused, without registering a collision.
    for (let i = 0; i < 12; i++) {
      engine.issue({ kind: 'manualStep', robot: a.name, direction: 1 });
      engine.tick();
    }
    expect(engine.scenario.grid.get(a.x, a.y)).not.toBe(WALL);
    expect(engine.collisions).toBe(0);
  });
});
