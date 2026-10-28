import { SimulationEngine, defaultOptions, type Command, type EngineOptions } from '../simulation/core/SimulationEngine';

function replay(options: EngineOptions, script: Array<[number, Command]>, steps: number): SimulationEngine {
  const engine = new SimulationEngine(options);
  for (let i = 0; i < steps && !engine.done; i++) {
    for (const [at, command] of script) if (at === engine.step) engine.issue(command);
    engine.tick();
  }
  return engine;
}

describe('Determinism', () => {
  it('same seed and actions give the same simulation outcome', () => {
    const options = defaultOptions({ preset: 'apartment', seed: 21, packetLoss: 0.2, delaySteps: [1, 3] });
    const script: Array<[number, Command]> = [
      [5, { kind: 'setMode', mode: 'mixed', manualRobot: 'drone_2' }],
      [6, { kind: 'manualWaypoint', robot: 'drone_2', target: { x: 10, y: 10 } }],
      [20, { kind: 'setPartition', on: true, robots: ['rover_0'] }],
      [40, { kind: 'setPartition', on: false, robots: ['rover_0'] }],
      [45, { kind: 'setMode', mode: 'autonomous', manualRobot: null }],
      [50, { kind: 'setPacketLoss', value: 0.05 }],
    ];
    const a = replay(options, script, 150);
    const b = replay(options, script, 150);
    expect(a.stateHash()).toBe(b.stateHash());
    expect(a.network.snapshot()).toEqual(b.network.snapshot());
    expect(a.feed.map((f) => f.text)).toEqual(b.feed.map((f) => f.text));
    expect(a.commandLog).toEqual(b.commandLog);
  });

  it('a recorded command log replays to the identical state', () => {
    const options = defaultOptions({ preset: 'mine', seed: 4, packetLoss: 0.1 });
    const original = replay(options, [[3, { kind: 'setPacketLoss', value: 0.3 }]], 100);
    const script = original.commandLog.map((c) => [c.step, c.command] as [number, Command]);
    const again = replay(options, script, 100);
    expect(again.stateHash()).toBe(original.stateHash());
  });

  it('different seeds diverge', () => {
    const a = replay(defaultOptions({ seed: 1 }), [], 40);
    const b = replay(defaultOptions({ seed: 2 }), [], 40);
    expect(a.stateHash()).not.toBe(b.stateHash());
  });
});
