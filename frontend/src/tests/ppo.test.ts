import initialPayload from './fixtures/pythonInitial.json';
import { RemoteEngine, validateSnapshot, type PPOSnapshot } from '../ppo/RemoteEngine';
import { applyPythonInitial, applyPythonTick } from '../ppo/PPOBridge';
import { useSim } from '../store/simStore';

const initialStore = useSim.getState();
const snapshot = () => structuredClone(initialPayload) as unknown as PPOSnapshot;
afterEach(() => useSim.setState(initialStore, true));

describe('Python PPO presentation boundary', () => {
  it('shows exact Python preview geometry while blocking launch and local advancement', () => {
    useSim.setState({ controllerMode: 'ppo', ppoPhase: 'preview' });
    const data = snapshot();
    applyPythonInitial(data, 'preview');
    const state = useSim.getState();
    expect([...state.engine.scenario.grid.cells]).toEqual(data.grid);
    expect(state.settings.rovers).toBe(data.options.rovers);
    expect(state.settings.networkEnabled).toBe(data.options.network);
    state.launch(); state.advance(10);
    expect(useSim.getState().status).toBe('ready');
    expect(state.engine.step).toBe(0);
    expect(useSim.getState().ppoPhase).toBe('preview');
  });

  it('ignores a late active-session tick after replacing it with a preview', () => {
    const previous = new RemoteEngine(snapshot());
    useSim.setState({ controllerMode: 'ppo', ppoPhase: 'ready', engine: previous });
    applyPythonInitial(snapshot(), 'preview');
    const preview = useSim.getState().engine;
    const next = snapshot(); next.step = 1;
    applyPythonTick(previous, next);
    expect(useSim.getState().engine).toBe(preview);
    expect(preview.step).toBe(0);
  });

  it('uses the exact Python geometry and initial private observations', () => {
    const data = snapshot(), engine = new RemoteEngine(data);
    expect([...engine.scenario.grid.cells]).toEqual(data.grid);
    expect(engine.coverage()).toBe(data.metrics.coverage);
    expect(engine.robots.map((r) => [r.x, r.y, r.battery])).toEqual(data.robots.map((r) => [r.x, r.y, r.battery]));
    expect([...engine.robots[0].belief.cells]).toEqual(data.robots[0].belief);
    expect(() => engine.tick()).toThrow('Python');
    expect(() => engine.issue()).toThrow('autonomous');
  });

  it.each(['checkpoint', 'shape', 'position', 'nan'])('rejects incompatible or corrupt snapshots: %s', (kind) => {
    const data = snapshot();
    if (kind === 'checkpoint') data.provenance.checkpointTreeSha256 = 'wrong';
    if (kind === 'shape') data.grid = [];
    if (kind === 'position') data.robots[0].x = 999;
    if (kind === 'nan') data.robots[0].battery = NaN;
    expect(() => validateSnapshot(data)).toThrow();
  });

  it('rejects a different session or skipped tick before mutating presentation state', () => {
    const data = snapshot(), engine = new RemoteEngine(data);
    const changed = snapshot(); changed.step = 2;
    expect(() => engine.applySnapshot(changed)).toThrow('mismatch');
    changed.step = 1; changed.mission = 'other-mission';
    expect(() => engine.applySnapshot(changed)).toThrow('mismatch');
    expect(engine.step).toBe(0);
  });

  it('blocks local authoring and advancement while retaining camera/display controls', () => {
    const engine = new RemoteEngine(snapshot());
    useSim.setState({ controllerMode: 'ppo', ppoPhase: 'ready', engine, status: 'running' });
    const state = useSim.getState(), hash = engine.stateHash();
    state.advance(100); state.issue({ kind: 'manualStep', robot: engine.robots[0].name, direction: 1 });
    state.setSetting('packetLoss', .3); state.setSetting('mode', 'manual');
    state.setSurvivorCount(100); state.clearSurvivors(); state.loadDemo();
    expect(useSim.getState().engine).toBe(engine);
    expect(engine.stateHash()).toBe(hash);
    state.setSetting('quality', 'low'); state.moveCamera('zoomIn');
    expect(useSim.getState().settings.quality).toBe('low');
    expect(useSim.getState().cameraRequest?.action).toBe('zoomIn');
  });

  it('pauses for a real discovery and ignores a late response from a replaced mission', () => {
    const data = snapshot(), engine = new RemoteEngine(data);
    useSim.setState({ controllerMode: 'ppo', ppoPhase: 'ready', engine, status: 'running', announcedSurvivors: [] });
    const next = snapshot(); next.step = 1; next.victims[0].found = true; next.victims[0].found_step = 1;
    next.victims[0].foundBy = next.robots[0].name; next.metrics.victims_found = 1;
    applyPythonTick(engine, next);
    expect(useSim.getState().status).toBe('paused');
    expect(useSim.getState().encounter?.id).toBe(next.victims[0].id);
    expect(engine.rawEvents.some((e) => e.event.type === 'survivor')).toBe(true);
    useSim.getState().resume();
    expect(useSim.getState().status).toBe('paused');
    useSim.getState().continueExploration();
    expect(useSim.getState().status).toBe('running');
    const replacement = new RemoteEngine(data);
    useSim.setState({ engine: replacement });
    next.step = 2; applyPythonTick(engine, next);
    expect(replacement.step).toBe(0);
    expect(engine.step).toBe(1);
  });

  it('accepts one already committed tick after pause while staying paused', () => {
    const engine = new RemoteEngine(snapshot()), next = snapshot(); next.step = 1;
    useSim.setState({ controllerMode: 'ppo', ppoPhase: 'ready', engine, status: 'paused', announcedSurvivors: [] });
    applyPythonTick(engine, next);
    expect(engine.step).toBe(1);
    expect(useSim.getState().status).toBe('paused');
  });

  it('reset requests a fresh Python mission without creating a local world', () => {
    const engine = new RemoteEngine(snapshot());
    useSim.setState({ controllerMode: 'ppo', ppoPhase: 'ready', engine, status: 'running' });
    const revision = useSim.getState().ppoRevision;
    useSim.getState().reset();
    expect(useSim.getState().engine).toBe(engine);
    expect(useSim.getState().ppoRevision).toBe(revision + 1);
    expect(useSim.getState().ppoPhase).toBe('connecting');
    useSim.getState().launch();
    expect(useSim.getState().status).toBe('ready');
  });
});
