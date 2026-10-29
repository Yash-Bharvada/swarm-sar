import { SimulationEngine, defaultOptions } from '../simulation/core/SimulationEngine';
import { generateScenario, PRESETS, survivorPlacementCells } from '../simulation/world/ScenarioGenerator';
import { WALL } from '../simulation/world/GridMap';
import { useSim } from '../store/simStore';

const options = { preset: 'office' as const, seed: 7 };

describe('Operator survivor placement', () => {
  it('keeps a placed survivor through launch and reset, and blocks an empty mission', () => {
    useSim.getState().reset();
    useSim.getState().useAutomaticSurvivors();
    useSim.getState().setSurvivorCount(0);
    expect(useSim.getState().engine.scenario.victims).toHaveLength(0);
    useSim.getState().launch();
    expect(useSim.getState().status).toBe('ready');
    useSim.getState().setEditingSurvivors(true);
    const point = survivorPlacementCells(useSim.getState().engine.scenario)[0];
    useSim.getState().toggleSurvivorAt(point);
    expect(useSim.getState().engine.scenario.victims.map(({ x, y }) => ({ x, y }))).toEqual([point]);
    useSim.getState().launch();
    expect(useSim.getState().status).toBe('running');
    useSim.getState().reset();
    expect(useSim.getState().engine.scenario.victims.map(({ x, y }) => ({ x, y }))).toEqual([point]);
    useSim.getState().useAutomaticSurvivors();
  });

  it('supports an empty draft, 100 survivors, and every eligible tile without an arbitrary count cap', () => {
    const base = generateScenario(options);
    const capacity = survivorPlacementCells(base).length;
    expect(capacity).toBeGreaterThan(100);
    for (const count of [0, 1, 100, capacity]) {
      const scenario = generateScenario({ ...options, survivorTargetCount: count });
      expect(scenario.victims).toHaveLength(count);
      expect(new Set(scenario.victims.map(({ x, y }) => `${x},${y}`)).size).toBe(count);
      expect(scenario.victims.every((v) => !v.found && v.foundBy === null && v.foundStep === null)).toBe(true);
    }
  });

  it('keeps the terrain, spawn and scenery stable when the count or explicit positions change', () => {
    const base = generateScenario(options);
    const positions = survivorPlacementCells(base).slice(10, 15);
    for (const extra of [{ survivorTargetCount: 0 }, { survivorTargetCount: 100 }, { survivorPositions: positions }]) {
      const scenario = generateScenario({ ...options, ...extra });
      expect(scenario.grid.cells).toEqual(base.grid.cells);
      expect(scenario.material).toEqual(base.material);
      expect(scenario.wallHeight).toEqual(base.wallHeight);
      expect(scenario.props).toEqual(base.props);
      expect(scenario.emergencyLights).toEqual(base.emergencyLights);
      expect(scenario.openings).toEqual(base.openings);
      expect(scenario.spawn).toEqual(base.spawn);
      expect(scenario.maxSteps).toBe(base.maxSteps);
      expect(scenario.batteryScale).toBe(base.batteryScale);
    }
  });

  it.each(PRESETS.map(({ id }) => id))('reproduces exact-count placement on %s without moving earlier targets as the count grows', (preset) => {
    const a = generateScenario({ preset, seed: 13, survivorTargetCount: 12 });
    const b = generateScenario({ preset, seed: 13, survivorTargetCount: 13 });
    const replay = generateScenario({ preset, seed: 13, survivorTargetCount: 12 });
    expect(a.victims).toEqual(replay.victims);
    expect(a.victims).toEqual(b.victims.slice(0, 12));
    const eligible = new Set(survivorPlacementCells(a).map(({ x, y }) => `${x},${y}`));
    for (const victim of b.victims) expect(eligible.has(`${victim.x},${victim.y}`)).toBe(true);
  });

  it('uses custom positions in their supplied order, overriding count settings including an empty list', () => {
    const base = generateScenario(options);
    const positions = survivorPlacementCells(base).slice(20, 23).reverse();
    const scenario = generateScenario({ ...options, survivorTargetCount: 100, survivorPositions: positions });
    expect(scenario.victims.map(({ x, y }) => ({ x, y }))).toEqual(positions);
    expect(scenario.victims.map(({ id }) => id)).toEqual([0, 1, 2]);
    expect(generateScenario({ ...options, survivorTargetCount: 100, survivorPositions: [] }).victims).toEqual([]);
  });

  it('reports capacity instead of silently reducing a requested count', () => {
    const capacity = survivorPlacementCells(generateScenario(options)).length;
    expect(() => generateScenario({ ...options, survivorTargetCount: capacity + 1 })).toThrow(`room for ${capacity} survivors`);
  });

  it.each([-1, 2.5, Infinity, NaN])('rejects invalid count %s', (survivorTargetCount) => {
    expect(() => generateScenario({ ...options, survivorTargetCount })).toThrow('non-negative whole number');
  });

  it('rejects duplicates, walls, off-map cells, staging and non-integer coordinates', () => {
    const base = generateScenario(options);
    const point = survivorPlacementCells(base)[0];
    expect(() => generateScenario({ ...options, survivorPositions: [point, point] })).toThrow('Only one survivor');
    expect(base.grid.get(0, 0)).toBe(WALL);
    expect(() => generateScenario({ ...options, survivorPositions: [{ x: 0, y: 0 }] })).toThrow('reachable walkable tile');
    expect(() => generateScenario({ ...options, survivorPositions: [{ x: -1, y: 2 }] })).toThrow('outside the search site');
    expect(() => generateScenario({ ...options, survivorPositions: [{ x: base.spawn.x, y: base.spawn.y }] })).toThrow('staging area');
    expect(() => generateScenario({ ...options, survivorPositions: [{ x: point.x + 0.5, y: point.y }] })).toThrow('whole-number grid coordinates');
  });

  it('does not alias the caller’s position array or coordinate objects in the engine', () => {
    const points = survivorPlacementCells(generateScenario(options)).slice(20, 22);
    const original = points.map((p) => ({ ...p }));
    const engine = new SimulationEngine(defaultOptions({ ...options, survivorPositions: points }));
    points[0].x = -50;
    points.push({ x: -1, y: -1 });
    expect(engine.options.survivorPositions).toEqual(original);
    expect(engine.scenario.victims.map(({ x, y }) => ({ x, y }))).toEqual(original);
    expect(engine.discoveredSurvivors()).toEqual([]);
    for (const robot of engine.robots) {
      const local = engine.localView(robot);
      expect(Object.keys(local)).not.toContain('survivorPositions');
      expect(Object.keys(local)).not.toContain('victims');
    }
  });

  it('replays a custom mission deterministically', () => {
    const points = survivorPlacementCells(generateScenario(options)).slice(-4);
    const a = new SimulationEngine(defaultOptions({ ...options, survivorPositions: points }));
    const b = new SimulationEngine(defaultOptions({ ...options, survivorPositions: points }));
    for (let i = 0; i < 30 && !a.done; i++) {
      a.tick();
      b.tick();
    }
    expect(b.stateHash()).toBe(a.stateHash());
    expect(b.feed).toEqual(a.feed);
  });
});
