import { useSim } from '../store/simStore';
import { SimulationEngine } from '../simulation/core/SimulationEngine';
import { coverageColor, survivorStory } from '../presentation/survivorStories';

const initial = useSim.getState();
beforeEach(() => { useSim.setState(initial, true); useSim.getState().reset(); });
afterEach(() => useSim.setState(initial, true));

describe('Survivor encounters', () => {
  it('pauses on every real discovery, blocks ordinary resume, and finishes the same mission', () => {
    const state = useSim.getState();
    const baseline = new SimulationEngine(state.engine.options);
    while (!baseline.done) baseline.tick();
    const ids: number[] = [];
    state.launch();
    for (let guard = 0; guard < 2000 && useSim.getState().status !== 'complete'; guard++) {
      state.advance(8);
      const current = useSim.getState();
      if (!current.encounter) continue;
      ids.push(current.encounter.id);
      expect(current.status).toBe('paused');
      const hash = current.engine.stateHash();
      state.resume(); state.advance(100);
      expect(useSim.getState().status).toBe('paused');
      expect(current.engine.stateHash()).toBe(hash);
      state.continueExploration();
      expect(useSim.getState().cameraRequest?.action).toBe('reset');
    }
    expect(useSim.getState().status).toBe('complete');
    expect(ids).toHaveLength(state.engine.scenario.victims.length);
    expect(new Set(ids).size).toBe(ids.length);
    expect(state.engine.stateHash()).toBe(baseline.stateHash());
  });

  it('queues simultaneous discoveries before resuming', () => {
    const state = useSim.getState();
    state.launch();
    vi.spyOn(state.engine, 'tick').mockImplementationOnce(() => {
      state.engine.scenario.victims.slice(0, 2).forEach((v) => { v.found = true; });
    });
    state.advance(8);
    const first = useSim.getState().encounter!.id;
    expect(useSim.getState().encounterQueue).toHaveLength(1);
    state.continueExploration();
    expect(useSim.getState().encounter!.id).not.toBe(first);
    expect(useSim.getState().status).toBe('paused');
    state.continueExploration();
    expect(useSim.getState().encounter).toBeNull();
    expect(useSim.getState().status).toBe('running');
    state.reset();
    expect(useSim.getState().announcedSurvivors).toEqual([]);
    expect(useSim.getState().encounterQueue).toEqual([]);
  });

  it('only opens confirmed humans and preserves a previously paused or completed mission', () => {
    const state = useSim.getState();
    const victim = state.engine.scenario.victims[0];
    state.inspectSurvivor(victim.id);
    expect(useSim.getState().encounter).toBeNull();
    state.launch(); state.pause();
    victim.found = true;
    for (const status of ['paused', 'complete'] as const) {
      useSim.setState({ status });
      const hash = state.engine.stateHash();
      state.inspectSurvivor(victim.id);
      expect(useSim.getState().encounter).toEqual({ id: victim.id, automatic: false });
      state.continueExploration();
      expect(useSim.getState().status).toBe(status);
      expect(state.engine.stateHash()).toBe(hash);
    }
  });

  it('keeps stories stable, varied and independent of engine randomness', () => {
    const state = useSim.getState();
    const hash = state.engine.stateHash();
    const stories = Array.from({ length: 12 }, (_, id) => survivorStory(7, id));
    expect(new Set(stories.map((s) => s.text)).size).toBe(12);
    expect(survivorStory(7, 0)).toEqual(stories[0]);
    expect(survivorStory(8, 0)).not.toEqual(stories[0]);
    expect(state.engine.stateHash()).toBe(hash);
    expect(coverageColor(true)).toEqual([44, 151, 129, 122]);
    expect(coverageColor(false)).not.toEqual(coverageColor(true));
  });
});
