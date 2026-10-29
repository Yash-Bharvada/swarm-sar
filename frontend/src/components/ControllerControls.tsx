import { useEffect, useState } from 'react';
import { useSim, type Settings } from '../store/simStore';
import type { PPOOptions } from '../ppo/RemoteEngine';
import type { Point } from '../simulation/core/types';

let heuristicDraft: { settings: Settings; demo: boolean; customSurvivors: Point[] | null } | null = null;

/** Controller selection and the selected controller's setup live in the drawer. */
export function ControllerControls() {
  const mode = useSim((s) => s.controllerMode);
  const phase = useSim((s) => s.ppoPhase);
  const error = useSim((s) => s.ppoError);
  const savedOptions = useSim((s) => s.ppoOptions);
  const [options, setOptions] = useState<PPOOptions>(() => ({ ...savedOptions }));
  useEffect(() => { setOptions({ ...savedOptions }); }, [savedOptions]);
  const choosePPO = (next: PPOOptions) => {
    const state = useSim.getState();
    if (state.controllerMode === 'heuristic') heuristicDraft = { settings: state.settings, demo: state.demo, customSurvivors: state.customSurvivors };
    useSim.setState({ controllerMode: 'ppo', ppoPhase: 'connecting', ppoError: null, ppoOptions: { ...next }, ppoRevision: state.ppoRevision + 1, status: 'ready', selected: null, following: false, focus: null, encounter: null, encounterQueue: [], announcedSurvivors: [], editingSurvivors: false, editingTerrain: false, cleanView: false });
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
      <button role="radio" aria-checked={mode === 'ppo'} className={mode === 'ppo' ? 'on' : ''} onClick={() => { if (mode !== 'ppo') choosePPO(savedOptions); }}>PPO</button>
    </div>
    <p className="explain">{mode === 'ppo' ? 'Learned swarm coordination.' : 'Rule-based exploration with custom maps.'} Switching starts a fresh mission.</p>
    {mode === 'ppo' && <div className="controller-choice ppo-choice chosen">
      <strong>Your next mission</strong>
      <label>Map<div className="controller-seed-row"><select aria-label="PPO map" value={options.seed} onChange={(e) => change('seed', Number(e.target.value))}>{Array.from({ length: 100 }, (_, i) => <option key={i} value={10000 + i}>Map {String(i + 1).padStart(2, '0')}</option>)}</select><button type="button" className="btn small" aria-label="Choose another PPO map" onClick={() => { const next = 10000 + Math.floor(Math.random() * 100); change('seed', next === options.seed ? 10000 + (next - 9999) % 100 : next); }}>Shuffle</button></div></label>
      <div className="controller-fields"><label>Map size<select aria-label="PPO map size" value={options.size} onChange={(e) => change('size', Number(e.target.value))}>{[24, 28, 32, 40, 48, 56].map((size) => <option key={size} value={size}>{size} × {size}</option>)}</select></label><label>Site<select aria-label="PPO layout" value={options.layout} onChange={(e) => change('layout', e.target.value as PPOOptions['layout'])}><option value="rooms">Rooms</option><option value="maze">Maze</option><option value="cave">Cave</option></select></label></div>
      <div className="controller-fields"><label>Rovers<input aria-label="PPO rovers" type="number" min={0} max={10} value={options.rovers} onChange={(e) => change('rovers', Number(e.target.value))} /></label><label>Drones<input aria-label="PPO drones" type="number" min={0} max={10} value={options.drones} onChange={(e) => change('drones', Number(e.target.value))} /></label></div>
      {!validTeam && <p className="controller-seed-help invalid" role="status">Choose whole robot counts, with 1–10 robots in total.</p>}
      <label className="controller-radio"><input aria-label="PPO radio" type="checkbox" checked={options.network} onChange={(e) => change('network', e.target.checked)} />Peer-to-peer radio</label>
      <label>Battery mode<select aria-label="PPO battery mode" value={options.batteryLimited === false ? 'unlimited' : 'limited'} onChange={(e) => change('batteryLimited', e.target.value === 'limited')}><option value="limited">Limited</option><option value="unlimited">Unlimited</option></select></label>
      <p className="controller-note">Create the mission, then press Launch to explore.</p>
      <button className="btn primary" disabled={!validSeed || !validTeam || phase === 'connecting'} onClick={() => choosePPO(options)}>{phase === 'connecting' ? 'Connecting…' : 'Create mission'}</button>
      {error && <p className="sound-error" role="status">{error}</p>}
    </div>}
  </section>;
}
