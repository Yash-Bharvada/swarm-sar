import { beginExplainSession } from '../explain/session';
import { useSim } from '../store/simStore';
import { SimulationEngine, defaultOptions } from '../simulation/core/SimulationEngine';
import { RemoteEngine, type PPOSnapshot } from '../ppo/RemoteEngine';
import initialPayload from './fixtures/pythonInitial.json';

const initial = useSim.getState();
beforeEach(() => useSim.setState(initial, true));
afterEach(() => useSim.setState(initial, true));

describe('Guided story mission isolation', () => {
  it('restores a running mission and its controls after exploring an independent sandbox', () => {
    const engine = new SimulationEngine(defaultOptions({ seed: 91 }));
    engine.tick();
    useSim.setState({ engine, status: 'running', selected: engine.robots[0].name, following: true, focus: { robot: engine.robots[0].name, nonce: 10 } });
    const original = useSim.getState(), hash = engine.stateHash();
    const finish = beginExplainSession()!;
    expect(useSim.getState().engine).not.toBe(engine);
    useSim.setState({ status: 'running' });
    useSim.getState().advance(150);
    expect(useSim.getState().encounter).toBeNull();
    expect(engine.stateHash()).toBe(hash);
    finish();
    const restored = useSim.getState();
    expect(restored.engine).toBe(engine);
    expect(restored.status).toBe('running');
    expect(restored.settings).toBe(original.settings);
    expect(restored.overlays).toBe(original.overlays);
    expect(restored.focus).toEqual(original.focus);
    expect(restored.following).toBe(true);
    expect(restored.explainActive).toBe(false);
  });

  it('allows the browser story during PPO without advancing the saved Python engine', () => {
    const engine = new RemoteEngine(structuredClone(initialPayload) as unknown as PPOSnapshot);
    useSim.setState({ controllerMode: 'ppo', ppoPhase: 'ready', engine, status: 'paused' });
    const hash = engine.stateHash(), finish = beginExplainSession()!;
    useSim.setState({ status: 'running' });
    const sandbox = useSim.getState().engine, step = sandbox.step;
    useSim.getState().advance(2);
    expect(sandbox.step).toBe(step + 2);
    expect(engine.stateHash()).toBe(hash);
    finish();
    expect(useSim.getState().engine).toBe(engine);
    expect(useSim.getState().controllerMode).toBe('ppo');
    expect(useSim.getState().ppoPhase).toBe('ready');
    useSim.setState({ status: 'running' });
    useSim.getState().advance(10);
    expect(engine.stateHash()).toBe(hash);
  });

  it('preserves an open survivor encounter and manual mission on return', () => {
    useSim.setState({ status: 'paused', encounter: { id: 7, automatic: false }, encounterQueue: [8], settings: { ...initial.settings, mode: 'manual' } });
    const finish = beginExplainSession()!;
    expect(useSim.getState().encounter).toBeNull();
    expect(useSim.getState().settings.mode).toBe('autonomous');
    finish();
    expect(useSim.getState().encounter).toEqual({ id: 7, automatic: false });
    expect(useSim.getState().encounterQueue).toEqual([8]);
    expect(useSim.getState().settings.mode).toBe('manual');
  });

  it('guards unfinished edits, connecting missions, duplicate sessions and repeated cleanup', () => {
    useSim.setState({ editingTerrain: true });
    expect(beginExplainSession()).toBeNull();
    useSim.setState({ editingTerrain: false, editingSurvivors: true });
    expect(beginExplainSession()).toBeNull();
    useSim.setState({ editingSurvivors: false, controllerMode: 'ppo', ppoPhase: 'connecting' });
    expect(beginExplainSession()).toBeNull();
    useSim.setState({ controllerMode: 'heuristic' });
    const finish = beginExplainSession()!;
    expect(beginExplainSession()).toBeNull();
    finish();
    useSim.setState({ selected: initial.engine.robots[1].name });
    finish();
    expect(useSim.getState().selected).toBe(initial.engine.robots[1].name);
  });
});
