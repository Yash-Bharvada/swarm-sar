import { useEffect, useState } from 'react';
import { useSim, type Settings } from '../store/simStore';
import { RemoteEngine, type PPOOptions } from '../ppo/RemoteEngine';
import type { Point } from '../simulation/core/types';

let heuristicDraft: { settings: Settings; demo: boolean; customSurvivors: Point[] | null } | null = null;

/** Controller selection and the selected controller's setup live in the drawer. */
export function ControllerControls() {
  const mode = useSim((s) => s.controllerMode);
  const phase = useSim((s) => s.ppoPhase);
  const error = useSim((s) => s.ppoError);
  const engine = useSim((s) => s.engine);
  const savedOptions = useSim((s) => s.ppoOptions);
  const [options, setOptions] = useState<PPOOptions>(() => ({ ...savedOptions }));
  useEffect(() => { setOptions({ ...savedOptions }); }, [savedOptions]);
  const choosePPO = (next: PPOOptions) => {
    const state = useSim.getState();
    if (state.controllerMode === 'heuristic') heuristicDraft = { settings: state.settings, demo: state.demo, customSurvivors: state.customSurvivors };
    useSim.setState({ controllerMode: 'ppo', ppoPhase: 'connecting', ppoError: null, ppoOptions: { ...next }, ppoRevision: state.ppoRevision + 1, status: 'ready', selected: null, following: false, focus: null, encounter: null, encounterQueue: [], announcedSurvivors: [], editingSurvivors: false, cleanView: false });
  };
  const chooseHeuristic = () => {
    if (mode === 'heuristic') return;
    useSim.setState({ controllerMode: 'heuristic', ppoPhase: 'off', ppoError: null, ...(heuristicDraft ?? {}) });
    useSim.getState().reset();
  };
  const validSeed = Number.isInteger(options.seed) && options.seed >= 10000 && options.seed <= 10099;
  const validTeam = Number.isInteger(options.rovers) && Number.isInteger(options.drones) && options.rovers >= 0 && options.drones >= 0 && options.rovers + options.drones >= 1 && options.rovers + options.drones <= 10;
  const change = <K extends keyof PPOOptions>(key: K, value: PPOOptions[K]) => setOptions({ ...options, [key]: value });
  return <section className="controller-settings section" aria-label="Controller settings">
    <label className="field-label">Exploration controller</label>
    <div className="segmented" role="radiogroup" aria-label="Exploration controller">
      <button role="radio" aria-checked={mode === 'heuristic'} className={mode === 'heuristic' ? 'on' : ''} onClick={chooseHeuristic}>Heuristic</button>
      <button role="radio" aria-checked={mode === 'ppo'} className={mode === 'ppo' ? 'on' : ''} onClick={() => { if (mode !== 'ppo') choosePPO(savedOptions); }}>PPO · 754k</button>
    </div>
    <p className="explain">{mode === 'ppo' ? 'Trained neural policies · Python mission service.' : 'Rule-based frontier search · runs in your browser.'} Switching controllers starts a fresh mission and restores that controller’s setup.</p>
    {mode === 'ppo' && <div className="controller-choice ppo-choice chosen">
      <strong>Trained PPO swarm <span className="mono">754k</span></strong>
      <small>Configure your next Python mission.</small>
      <label htmlFor="ppo-seed">Map seed</label>
      <div className="controller-seed-row"><input id="ppo-seed" aria-label="PPO seed" aria-invalid={!validSeed} aria-describedby="ppo-seed-help" type="number" min={10000} max={10099} step={1} value={Number.isNaN(options.seed) ? '' : options.seed} onChange={(e) => change('seed', e.target.value === '' ? NaN : Number(e.target.value))} /><button type="button" className="btn small" aria-label="Choose another PPO seed" onClick={() => { const next = 10000 + Math.floor(Math.random() * 100); change('seed', next === options.seed ? 10000 + (next - 9999) % 100 : next); }}>Shuffle</button></div>
      <p id="ppo-seed-help" className={`controller-seed-help ${validSeed ? '' : 'invalid'}`} role={validSeed ? undefined : 'status'}>{validSeed ? '100 map seeds: 10000–10099. Final-test seeds stay reserved.' : 'Enter a whole number from 10000 to 10099 to launch.'}</p>
      <div className="controller-fields"><label>Map size<select aria-label="PPO map size" value={options.size} onChange={(e) => change('size', Number(e.target.value))}>{[24, 28, 32, 40, 48, 56].map((size) => <option key={size} value={size}>{size} × {size}</option>)}</select></label><label>Site<select aria-label="PPO layout" value={options.layout} onChange={(e) => change('layout', e.target.value as PPOOptions['layout'])}><option value="rooms">Rooms</option><option value="maze">Maze</option><option value="cave">Cave</option></select></label></div>
      <div className="controller-fields"><label>Rovers<input aria-label="PPO rovers" type="number" min={0} max={10} value={options.rovers} onChange={(e) => change('rovers', Number(e.target.value))} /></label><label>Drones<input aria-label="PPO drones" type="number" min={0} max={10} value={options.drones} onChange={(e) => change('drones', Number(e.target.value))} /></label></div>
      {!validTeam && <p className="controller-seed-help invalid" role="status">Choose whole robot counts, with 1–10 robots in total.</p>}
      <label className="controller-radio"><input aria-label="PPO radio" type="checkbox" checked={options.network} onChange={(e) => change('network', e.target.checked)} />Peer-to-peer radio</label>
      <label>Battery mode<select aria-label="PPO battery mode" value={options.batteryLimited === false ? 'unlimited' : 'limited'} onChange={(e) => change('batteryLimited', e.target.value === 'limited')}><option value="limited">Limited</option><option value="unlimited">Unlimited</option></select></label>
      <p className="controller-note">Apply these settings with New PPO mission. This resets current progress; press Launch to begin. Unlimited energy retains the mission time limit.</p>
      <button className="btn primary" disabled={!validSeed || !validTeam || phase === 'connecting'} onClick={() => choosePPO(options)}>{phase === 'connecting' ? 'Connecting…' : 'New PPO mission'}</button>
      <p className="controller-note">Saved checkpoint · CPU inference. Large mazes remain challenging. Manual driving and custom survivor placement are available in heuristic mode.</p>
      {engine instanceof RemoteEngine && phase === 'ready' && <p className="controller-provenance mono">Verified {engine.provenance.checkpointTreeSha256.slice(0, 12)} · 229 observations</p>}
      {error && <p className="sound-error" role="status">{error}</p>}
    </div>}
  </section>;
}
