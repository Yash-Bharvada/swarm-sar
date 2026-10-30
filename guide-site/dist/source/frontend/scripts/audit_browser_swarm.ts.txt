/**
 * Bounded browser-controller audit, without React or WebGL.
 * Run from frontend/: npx --no-install vite-node scripts/audit_browser_swarm.ts
 * Uses vite-node already installed with Vitest; no extra package is required.
 * Writes docs/validation/browser_swarm_audit.json. This is a simulator regression sample,
 * not evidence of physical rescue accuracy or general 100% success.
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { SimulationEngine, defaultOptions } from '../src/simulation/core/SimulationEngine';

const presets = ['office', 'mine', 'apartment', 'random', 'demo'] as const;
const seeds = Array.from({ length: 10 }, (_, index) => 100 + index);
const conditions = [
  { name: 'loss10', packetLoss: 0.1, networkEnabled: true },
  { name: 'loss30', packetLoss: 0.3, networkEnabled: true },
  { name: 'radio_off', packetLoss: 0, networkEnabled: false },
  { name: 'partition', packetLoss: 0.15, networkEnabled: true, partitionWindows: [{ start: 20, end: 60, agents: ['rover_0'] }] },
];

interface Run {
  preset: string;
  seed: number;
  condition: string;
  found: number;
  total: number;
  doneReason: string | null;
  coverage: number;
  collisions: number;
  steps: number;
}

const started = Date.now();
const runs: Run[] = [];
for (const preset of presets) {
  for (const { name, ...networkOptions } of conditions) {
    for (const seed of seeds) {
      // Deliberately use defaultOptions for every preset, including demo.
      // The separate UI validation scenario uses demoOptions and fixes 3 victims.
      const engine = new SimulationEngine(defaultOptions({ preset, seed, rovers: 2, drones: 2, ...networkOptions }));
      while (!engine.done) engine.tick();
      runs.push({
        preset,
        seed,
        condition: name,
        found: engine.survivorsFound(),
        total: engine.scenario.victims.length,
        doneReason: engine.doneReason,
        coverage: engine.coverage(),
        collisions: engine.collisions,
        steps: engine.step,
      });
    }
    const sample = runs.filter((run) => run.preset === preset && run.condition === name);
    console.log(`${preset}/${name}: ${sample.reduce((sum, run) => sum + run.found, 0)}/${sample.reduce((sum, run) => sum + run.total, 0)} survivors; ${sample.filter((run) => run.doneReason === 'all_found').length}/${sample.length} completed`);
  }
}

const found = runs.reduce((sum, run) => sum + run.found, 0);
const total = runs.reduce((sum, run) => sum + run.total, 0);
const packageJson = JSON.parse(readFileSync(new URL('../frontend/package.json', import.meta.url), 'utf8'));
const report = {
  generatedAt: new Date().toISOString(),
  scope: 'Browser heuristic-controller simulation only; no physical robot, learned-policy, ROS, or Gazebo validation.',
  reproduce: 'cd frontend && npx --no-install vite-node scripts/audit_browser_swarm.ts',
  versions: { node: process.version, vitest: packageJson.devDependencies.vitest, vite: packageJson.devDependencies.vite },
  configuration: {
    presets,
    seeds,
    rovers: 2,
    drones: 2,
    sensorNoise: true,
    delaySteps: [1, 2],
    batteryAndMissionLimits: 'defaultOptions, unchanged',
    survivorCount: 'defaultOptions (2–4); demoOptions is not used',
    conditions,
  },
  results: {
    episodes: runs.length,
    distinctPresetSeedMaps: presets.length * seeds.length,
    survivorsFound: found,
    survivorsTotalAcrossRuns: total,
    recall: found / total,
    allFoundEpisodes: runs.filter((run) => run.doneReason === 'all_found').length,
    postShieldPhysicsCollisions: runs.reduce((sum, run) => sum + run.collisions, 0),
    byCondition: conditions.map(({ name }) => {
      const sample = runs.filter((run) => run.condition === name);
      return {
        name,
        episodes: sample.length,
        found: sample.reduce((sum, run) => sum + run.found, 0),
        total: sample.reduce((sum, run) => sum + run.total, 0),
        allFoundEpisodes: sample.filter((run) => run.doneReason === 'all_found').length,
        meanSteps: sample.reduce((sum, run) => sum + run.steps, 0) / sample.length,
      };
    }),
    incompleteEpisodes: runs.filter((run) => run.doneReason !== 'all_found'),
    runtimeSeconds: (Date.now() - started) / 1000,
  },
  interpretation: [
    'The 50 layouts are repeated under four network conditions; this is not 200 independent layouts.',
    'Found means confirmation within radius and line of sight; evacuation and treatment are absent.',
    'Zero collisions is post-safety-shield physics; requests prevented by the shield are not counted as collisions.',
    'Own grid-cell localization is exact and maps use a prealigned common grid; this does not test SLAM registration.',
    'The browser policy is a deterministic frontier heuristic, not PPO, MAPPO, or a GNN.',
    'Aggregate survivor recall does not establish a communication-efficiency advantage over the network-off baseline.',
  ],
  runs,
};

const destination = fileURLToPath(new URL('../../docs/validation/browser_swarm_audit.json', import.meta.url));
writeFileSync(destination, JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report.results, null, 2));
console.log(`Saved ${destination}`);
