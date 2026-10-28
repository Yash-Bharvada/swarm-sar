import { SimulationEngine, defaultOptions } from '../simulation/core/SimulationEngine';
import { FREE, RUBBLE, UNKNOWN, WALL } from '../simulation/world/GridMap';

describe('Autonomy restrictions', () => {
  it('local robots do not see truth-map survivors', () => {
    const engine = new SimulationEngine(defaultOptions({ preset: 'office', seed: 5 }));
    // Operator view reveals nothing before discovery.
    expect(engine.discoveredSurvivors()).toEqual([]);
    for (const r of engine.robots) {
      // A robot's state has no survivor list and its belief holds only cell types.
      expect(Object.keys(r)).not.toContain('victims');
      const values = new Set(r.belief.cells);
      for (const v of values) expect([UNKNOWN, FREE, WALL, RUBBLE]).toContain(v);
      // Local views passed to the controller carry no truth fields.
      const view = engine.localView(r);
      expect(Object.keys(view).sort()).toEqual(
        ['acoustic', 'batteryFraction', 'belief', 'canCrossRubble', 'id', 'name', 'networkEnabled', 'odom', 'peerMessages', 'position', 'step', 'thermal', 'type'].sort(),
      );
      // The belief map is a private copy, not the truth grid.
      expect(r.belief.cells).not.toBe(engine.scenario.grid.cells);
      expect(r.belief.count(UNKNOWN)).toBeGreaterThan(0);
    }
  });

  it('autonomous robots do not use global survivor positions', () => {
    // Two worlds identical except for where the (undetectable) survivors are.
    const make = () => {
      const e = new SimulationEngine(defaultOptions({ preset: 'random', seed: 8, packetLoss: 0.1 }));
      for (const r of e.robots) {
        r.config = { ...r.config, thermalRadius: -1, acousticRadius: -1, confirmRadius: -1 };
        r.thermal = [0, 0, 0, 0];
        r.acoustic = 0;
      }
      return e;
    };
    const a = make();
    const b = make();
    const free: Array<{ x: number; y: number }> = [];
    const g = b.scenario.grid;
    for (let y = 0; y < g.height; y++) for (let x = 0; x < g.width; x++) if (g.get(x, y) === FREE) free.push({ x, y });
    b.scenario.victims.forEach((v, i) => {
      const p = free[(i * 97 + 13) % free.length];
      v.x = p.x;
      v.y = p.y;
    });
    expect(b.scenario.victims.map((v) => [v.x, v.y])).not.toEqual(a.scenario.victims.map((v) => [v.x, v.y]));
    for (let i = 0; i < 80; i++) {
      a.tick();
      b.tick();
      expect(b.robots.map((r) => [r.x, r.y])).toEqual(a.robots.map((r) => [r.x, r.y]));
    }
    expect(b.stateHash()).toBe(a.stateHash());
  });

  it('robots keep exploring autonomously with the network disabled', () => {
    const engine = new SimulationEngine(defaultOptions({ seed: 32, networkEnabled: false }));
    for (let i = 0; i < 20; i++) engine.tick();
    expect(engine.network.metrics.messagesCreated).toBe(0);
    expect(engine.robots.some((r) => r.distanceTravelled > 5)).toBe(true);
    // Without a network, no robot learns cells it has not sensed itself.
    expect(engine.mapCellsMerged).toBe(0);
  });

  it('map knowledge spreads only through delivered messages', () => {
    const engine = new SimulationEngine(defaultOptions({ seed: 3, packetLoss: 0 }));
    for (let i = 0; i < 30; i++) engine.tick();
    expect(engine.mapCellsMerged).toBeGreaterThan(0);
    expect(engine.mapCellsMerged).toBeLessThanOrEqual(engine.network.metrics.messagesDelivered * 64);
  });
});
