import { useEffect, useRef, useState } from 'react';
import { useSim, type Settings } from '../store/simStore';
import { RemoteEngine, type PPOOptions } from '../ppo/RemoteEngine';
import { Icon } from './Icon';
import type { Point } from '../simulation/core/types';

let heuristicDraft: { settings: Settings; demo: boolean; customSurvivors: Point[] | null } | null = null;

export function ControllerControls() {
  const mode = useSim((s) => s.controllerMode);
  const phase = useSim((s) => s.ppoPhase);
  const error = useSim((s) => s.ppoError);
  const engine = useSim((s) => s.engine);
  const savedOptions = useSim((s) => s.ppoOptions);
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<PPOOptions>(() => ({ ...useSim.getState().ppoOptions }));
  const wrapper = useRef<HTMLDivElement>(null);
  useEffect(() => { setOptions({ ...savedOptions }); }, [savedOptions]);
  useEffect(() => {
    const close = (event: PointerEvent) => { if (!wrapper.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.code === 'Escape') setOpen(false); };
    document.addEventListener('pointerdown', close); document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', close); document.removeEventListener('keydown', escape); };
  }, []);
  const choosePPO = () => {
    const state = useSim.getState();
    if (state.controllerMode === 'heuristic') heuristicDraft = { settings: state.settings, demo: state.demo, customSurvivors: state.customSurvivors };
    useSim.setState({ controllerMode: 'ppo', ppoPhase: 'connecting', ppoError: null, ppoOptions: options, ppoRevision: state.ppoRevision + 1, status: 'ready', selected: null, following: false, focus: null, encounter: null, encounterQueue: [], announcedSurvivors: [], editingSurvivors: false, cleanView: false });
    setOpen(false);
  };
  const chooseHeuristic = () => {
    if (mode === 'heuristic') { setOpen(false); return; }
    useSim.setState({ controllerMode: 'heuristic', ppoPhase: 'off', ppoError: null, ...(heuristicDraft ?? {}) });
    useSim.getState().reset(); setOpen(false);
  };
  const validSeed = Number.isInteger(options.seed) && options.seed >= 10000 && options.seed <= 10099;
  const valid = validSeed && Number.isInteger(options.rovers) && Number.isInteger(options.drones) && options.rovers >= 0 && options.drones >= 0 && options.rovers + options.drones >= 1 && options.rovers + options.drones <= 10;
  const change = <K extends keyof PPOOptions>(key: K, value: PPOOptions[K]) => setOptions({ ...options, [key]: value });
  return <div className="controller-wrap" ref={wrapper}>
    <button className={`scene-button controller-button ${mode === 'ppo' ? 'active' : ''}`} aria-label="Controller settings" aria-expanded={open} aria-controls="controller-menu" onClick={() => setOpen(!open)}><span className={`status-dot ${phase === 'error' ? 'controller-offline' : ''}`} /><span>{mode === 'ppo' ? 'PPO · 754k' : 'Heuristic'}</span><Icon name="chevron" size={12} /></button>
    {open && <section className="controller-menu" id="controller-menu" aria-label="Controller settings">
      <div className="popover-heading">Who’s exploring?<span>Choose the controller for a new mission.</span></div>
      <button className={`controller-choice ${mode === 'heuristic' ? 'chosen' : ''}`} onClick={chooseHeuristic}><strong>Browser heuristic</strong><small>Local frontier search · custom survivor placement</small></button>
      <div className={`controller-choice ppo-choice ${mode === 'ppo' ? 'chosen' : ''}`}>
        <strong>Trained PPO swarm <span className="mono">754k</span></strong><small>Python mission service · two recurrent policies</small>
        <label>Map seed<div className="controller-seed-row"><input aria-label="PPO seed" aria-invalid={!validSeed} aria-describedby="ppo-seed-help" type="number" min={10000} max={10099} step={1} value={Number.isNaN(options.seed) ? '' : options.seed} onChange={(e) => change('seed', e.target.value === '' ? NaN : Number(e.target.value))} /><button type="button" className="btn small" aria-label="Choose another PPO seed" onClick={() => { const next = 10000 + Math.floor(Math.random() * 100); change('seed', next === options.seed ? 10000 + (next - 9999) % 100 : next); }}>Shuffle</button></div></label>
        <p id="ppo-seed-help" className={`controller-seed-help ${validSeed ? '' : 'invalid'}`} role={validSeed ? undefined : 'status'}>{validSeed ? '100 map seeds: 10000–10099. Final-test seeds stay reserved.' : 'Enter a whole number from 10000 to 10099 to launch.'}</p>
        <div className="controller-fields"><label>Map size<select aria-label="PPO map size" value={options.size} onChange={(e) => change('size', Number(e.target.value))}>{[24, 28, 32, 40, 48, 56].map((size) => <option key={size} value={size}>{size} × {size}</option>)}</select></label><label>Site<select aria-label="PPO layout" value={options.layout} onChange={(e) => change('layout', e.target.value as PPOOptions['layout'])}><option value="rooms">Rooms</option><option value="maze">Maze</option><option value="cave">Cave</option></select></label></div>
        <div className="controller-fields"><label>Rovers<input aria-label="PPO rovers" type="number" min={0} max={10} value={options.rovers} onChange={(e) => change('rovers', Number(e.target.value))} /></label><label>Drones<input aria-label="PPO drones" type="number" min={0} max={10} value={options.drones} onChange={(e) => change('drones', Number(e.target.value))} /></label></div>
        <label className="controller-radio"><input aria-label="PPO radio" type="checkbox" checked={options.network} onChange={(e) => change('network', e.target.checked)} />Peer-to-peer radio</label>
        <label>Battery mode<select aria-label="PPO battery mode" value={options.batteryLimited === false ? 'unlimited' : 'limited'} onChange={(e) => change('batteryLimited', e.target.value === 'limited')}><option value="limited">Limited</option><option value="unlimited">Unlimited</option></select></label>
        <p className="controller-note">Saved GPU-v1 checkpoint · CPU inference. Large mazes remain challenging. Custom survivor editing and manual driving use the heuristic mode.</p>
        <button className="btn primary" disabled={!valid || phase === 'connecting'} onClick={choosePPO}>{phase === 'connecting' ? 'Connecting…' : 'New PPO mission'}</button>
      </div>
      {engine instanceof RemoteEngine && mode === 'ppo' && <p className="controller-provenance mono">Verified {engine.provenance.checkpointTreeSha256.slice(0, 12)} · 229 observations</p>}
      {error && <p className="sound-error" role="status">{error}</p>}
    </section>}
  </div>;
}
