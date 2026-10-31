import { SimulationEngine, defaultOptions } from '../simulation/core/SimulationEngine';
import { simClock, useSim, type Overlays } from '../store/simStore';
import { useExplain, type StoryCue } from './story';

export function createStoryEngine() {
  const engine = new SimulationEngine(defaultOptions({ seed: 7, batteryLimited: false, maxSteps: 800 }));
  // A short deterministic head start puts each helper in view, using real sensing and movement.
  for (let i = 0; i < 8 && !engine.done; i++) engine.tick();
  return engine;
}

/** Swap in a separate sandbox; retain the original engine by identity, without ticking it. */
export function beginExplainSession(): (() => void) | null {
  const previous = useSim.getState();
  if (previous.explainActive || previous.editingSurvivors || previous.editingTerrain || (previous.controllerMode === 'ppo' && previous.ppoPhase === 'connecting')) return null;
  const clock = { ...simClock };
  const engine = createStoryEngine();
  useExplain.setState({ beat: 0, systemPart: 0 });
  useSim.setState({
    explainActive: true, engine, status: 'paused', selected: null, focus: null, following: false, cameraRequest: null,
    settings: { ...previous.settings, preset: 'office', seed: 7, rovers: 2, drones: 2, mode: 'autonomous', speed: 1, terrain: null, batteryLimited: false },
    cleanView: false, encounter: null, encounterQueue: [], announcedSurvivors: [], editingSurvivors: false, editingTerrain: false,
    overlays: storyOverlays('problem'), version: previous.version + 1,
  });
  simClock.alpha = 1;
  let restored = false;
  return () => {
    if (restored) return;
    restored = true;
    const version = useSim.getState().version + 1;
    useSim.setState({ ...previous, explainActive: false, version }, true);
    Object.assign(simClock, clock);
  };
}

export function storyOverlays(cue: StoryCue, part = 0): Overlays {
  const network = cue === 'communication' || cue === 'ros' || (cue === 'system' && part === 3);
  return {
    labels: true, truth: false, netLog: false, graph: false,
    paths: cue === 'cooperation' || (cue === 'system' && (part === 2 || part === 4)),
    coverage: cue === 'slam' || (cue === 'system' && part === 1),
    links: network, packets: network,
    ranges: false,
    evidence: cue === 'world' || (cue === 'system' && part === 0),
  };
}
