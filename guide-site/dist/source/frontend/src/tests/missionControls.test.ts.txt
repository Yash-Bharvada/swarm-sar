import { useSim } from '../store/simStore';
import { survivorPlacementCells } from '../simulation/world/ScenarioGenerator';

const initial = useSim.getState();
beforeEach(() => { useSim.setState(initial, true); useSim.getState().reset(); });
afterEach(() => useSim.setState(initial, true));

describe('Mission authoring controls', () => {
  it('applies exact counts, reports invalid input, and preserves the map', () => {
    const state = useSim.getState();
    const cells = state.engine.scenario.grid.cells.slice();
    state.setSurvivorCount(100);
    expect(useSim.getState().engine.scenario.victims).toHaveLength(100);
    expect(useSim.getState().engine.scenario.grid.cells).toEqual(cells);
    const validEngine = useSim.getState().engine;
    for (const count of [NaN, -1, 1.5, initial.survivorCapacity + 1]) {
      state.setSurvivorCount(count);
      expect(useSim.getState().engine).toBe(validEngine);
      expect(useSim.getState().survivorMessage).toContain('whole number');
    }
  });

  it('adds and removes exact positions, rejects staging, and hides the editor on launch', () => {
    const state = useSim.getState();
    state.clearSurvivors();
    state.setEditingSurvivors(true);
    const point = survivorPlacementCells(useSim.getState().engine.scenario)[5];
    state.toggleSurvivorAt(point);
    expect(useSim.getState().customSurvivors).toEqual([point]);
    state.toggleSurvivorAt(useSim.getState().engine.scenario.spawn);
    expect(useSim.getState().customSurvivors).toEqual([point]);
    expect(useSim.getState().survivorMessage).toContain('staging');
    state.toggleSurvivorAt(point);
    expect(useSim.getState().customSurvivors).toEqual([]);
    state.launch();
    expect(useSim.getState().status).toBe('ready');
    state.toggleSurvivorAt(point);
    state.launch();
    expect(useSim.getState().status).toBe('running');
    expect(useSim.getState().editingSurvivors).toBe(false);
    const engine = useSim.getState().engine;
    state.clearSurvivors(); state.setSurvivorCount(12); state.randomizeSurvivors(); state.setEditingSurvivors(true);
    expect(useSim.getState().engine).toBe(engine);
    expect(useSim.getState().editingSurvivors).toBe(false);
  });

  it('keeps authored positions through team changes and reset but clears them on terrain changes', () => {
    const state = useSim.getState();
    state.setSurvivorCount(12); state.randomizeSurvivors();
    const positions = useSim.getState().customSurvivors;
    state.setSetting('rovers', 3); state.reset();
    expect(useSim.getState().customSurvivors).toEqual(positions);
    expect(useSim.getState().engine.scenario.victims.map(({ x, y }) => ({ x, y }))).toEqual(positions);
    state.setSetting('seed', 15);
    expect(useSim.getState().customSurvivors).toBeNull();
    expect(useSim.getState().settings.survivorCount).toBeNull();
  });

  it('restores automatic placement and leaves edited truth outside controller observations', () => {
    const state = useSim.getState();
    state.setSurvivorCount(100); state.setEditingSurvivors(true); state.useAutomaticSurvivors();
    const next = useSim.getState();
    expect(next.engine.scenario.victims.length).toBeGreaterThanOrEqual(2);
    expect(next.engine.scenario.victims.length).toBeLessThanOrEqual(4);
    expect(next.customSurvivors).toBeNull();
    expect(next.editingSurvivors).toBe(false);
    expect(Object.keys(next.engine.localView(next.engine.robots[0]))).not.toContain('survivorPositions');
  });
});

describe('Persistent camera focus and clean viewing', () => {
  it('focuses and follows a robot until interaction cancels it', () => {
    const state = useSim.getState();
    const name = state.engine.robots[0].name;
    state.focusOn(name);
    expect(useSim.getState().following).toBe(true);
    expect(useSim.getState().selected).toBe(name);
    state.updateCamera(320);
    expect(useSim.getState().following).toBe(true);
    state.updateCamera(320, false);
    expect(useSim.getState().following).toBe(false);
    expect(useSim.getState().focus).toBeNull();
  });

  it('rejects stale camera targets', () => {
    const state = useSim.getState();
    state.focusOn('missing-robot'); state.select('missing-robot');
    expect(useSim.getState().selected).toBeNull();
    expect(useSim.getState().following).toBe(false);
  });

  it('hides UI without changing settings, overlays, simulation, or camera focus', () => {
    const state = useSim.getState();
    state.focusOn(state.engine.robots[0].name);
    const focused = useSim.getState();
    const hash = focused.engine.stateHash();
    state.toggleCleanView();
    expect(useSim.getState().cleanView).toBe(true);
    expect(useSim.getState().overlays).toBe(focused.overlays);
    expect(useSim.getState().settings).toBe(focused.settings);
    expect(useSim.getState().following).toBe(true);
    expect(useSim.getState().engine.stateHash()).toBe(hash);
    state.toggleCleanView();
    expect(useSim.getState().cleanView).toBe(false);
  });

  it('keeps authoring controls available while placing survivors', () => {
    const state = useSim.getState();
    state.setEditingSurvivors(true); state.toggleCleanView();
    expect(useSim.getState().cleanView).toBe(false);
    state.setEditingSurvivors(false); state.toggleCleanView();
    expect(useSim.getState().cleanView).toBe(true);
  });
});
