import { useSim } from '../store/simStore';
import { missionTime, pct } from '../app/format';
import { Icon } from './Icon';

export function TopBar({ onOpenObservatory }: { onOpenObservatory?: () => void }) {
  useSim((s) => s.version);
  const engine = useSim((s) => s.engine);
  const mode = useSim((s) => s.controllerMode);
  const status = useSim((s) => s.status);
  const labels = { ready: 'Ready to explore', running: 'Mission live', paused: 'Mission paused', complete: 'Mission complete' };
  return <header className="topbar">
    <div className="brand"><div className="brand-mark"><Icon name="swarm" size={26} /></div><div><div className="brand-title">swarm</div><div className="brand-sub">SEARCH. CONNECT. RESCUE.</div></div></div>
    <div className="workspace-crumb"><span>Workspace</span><Icon name="chevron" size={12} /><strong>{mode === 'ppo' ? 'PPO exploration' : 'Heuristic exploration'}</strong></div>
    <button className="observatory-launch" onClick={onOpenObservatory} title="Open SLAM and peer-message visualization"><span className="ob-launch-spark" /><Icon name="signal" size={15} />Swarm intelligence</button>
    <a className="fieldbook-link" href="https://swarmsar.vercel.app" target="_blank" rel="noopener noreferrer" aria-label="Open the English audio fieldbook" title="Read and listen to the project fieldbook"><Icon name="book" size={16} /><span>Fieldbook</span></a>
    <div className="mission-metrics" aria-label="Mission statistics">
      <div className="metric"><Icon name="person" size={18} /><div><span>Survivors found</span><strong>{engine.survivorsFound()} <small>/ {engine.scenario.victims.length}</small></strong></div></div>
      <div className="metric"><Icon name="map" size={18} /><div><span>Area explored</span><strong>{pct(engine.coverage())}</strong></div><div className="mini-progress"><i style={{ width: pct(engine.coverage()) }} /></div></div>
      <div className="metric metric-time"><Icon name="clock" size={18} /><div><span>Mission time</span><strong className="mono">{missionTime(engine.step)}</strong></div></div>
    </div>
    <div className={`mission-status status-${status}`}><span className="status-dot" />{labels[status]}</div>
  </header>;
}
