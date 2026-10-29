import { useSim } from '../store/simStore';

export function BatterySettings() {
  const limited = useSim((s) => s.settings.batteryLimited);
  const connecting = useSim((s) => s.controllerMode === 'ppo' && s.ppoPhase === 'connecting');
  const setSetting = useSim((s) => s.setSetting);
  return <section className="section" aria-label="Battery settings">
    <label className="field-label">Battery mode</label>
    <div className="segmented" role="radiogroup" aria-label="Battery mode">
      <button role="radio" aria-checked={limited} className={limited ? 'on' : ''} disabled={connecting} onClick={() => setSetting('batteryLimited', true)}>Limited</button>
      <button role="radio" aria-checked={!limited} className={!limited ? 'on' : ''} disabled={connecting} onClick={() => setSetting('batteryLimited', false)}>Unlimited</button>
    </div>
    <p className="explain">{limited ? 'Robots stop when energy runs out.' : 'Energy stays full; the mission timer still applies.'} Changing mode restarts the mission.</p>
  </section>;
}
