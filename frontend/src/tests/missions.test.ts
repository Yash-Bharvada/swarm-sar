import { SimulationEngine, defaultOptions, demoOptions } from '../simulation/core/SimulationEngine';
import { PRESETS } from '../simulation/world/ScenarioGenerator';

/**
 * End-to-end regression: complete missions on every preset under 10% loss.
 * Mirrors the spirit of the Python Step 4 audit (zero collisions, high recall),
 * on browser-sized maps. Thresholds are regression guards, not accuracy claims.
 */
describe('Full missions', () => {
  const results: Array<{ preset: string; seed: number; found: number; total: number; collisions: number; coverage: number }> = [];
  for (const preset of PRESETS.map((p) => p.id))
    for (const seed of [1, 2, 3]) {
      const engine = new SimulationEngine(preset === 'demo' ? demoOptions(seed) : defaultOptions({ preset, seed, packetLoss: 0.1 }));
      while (!engine.done) engine.tick();
      results.push({
        preset,
        seed,
        found: engine.survivorsFound(),
        total: engine.scenario.victims.length,
        collisions: engine.collisions,
        coverage: engine.coverage(),
      });
    }

  it('never collides on any preset', () => {
    expect(results.filter((r) => r.collisions > 0)).toEqual([]);
  });

  it('finds most survivors overall', () => {
    const found = results.reduce((s, r) => s + r.found, 0);
    const total = results.reduce((s, r) => s + r.total, 0);
    console.log(`recall ${found}/${total} = ${((100 * found) / total).toFixed(1)}%`);
    expect(found / total).toBeGreaterThanOrEqual(0.75);
  });

  it('maps a meaningful share of every site', () => {
    for (const r of results) expect(r.coverage).toBeGreaterThan(0.3);
  });
});
