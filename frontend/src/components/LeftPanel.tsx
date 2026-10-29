import { useEffect, useId, useState } from 'react';
import { useSim, type Overlays, type Quality } from '../store/simStore';
import { PRESETS, type PresetId } from '../simulation/world/ScenarioGenerator';
import type { OperationMode } from '../simulation/core/types';

function Segmented<T extends string | number>({ value, options, onChange, label }: {
  value: T;
  options: Array<{ value: T; label: string; title?: string }>;
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={String(o.value)} role="radio" aria-checked={o.value === value} className={o.value === value ? 'on' : ''} title={o.title} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

function Toggle({ label, checked, onChange, disabled, danger, title }: {
  label: string; checked: boolean; onChange: () => void; disabled?: boolean; danger?: boolean; title?: string;
}) {
  return (
    <label className={`toggle ${danger ? 'danger' : ''} ${disabled ? 'disabled' : ''}`} title={title}>
      <input type="checkbox" checked={checked} onChange={onChange} disabled={disabled} />
      <span className="track"><span className="thumb" /></span>
      <span className="toggle-label">{label}</span>
    </label>
  );
}

function Stepper({ label, value, onChange, min, max, disabled, icon }: {
  label: string; value: number; onChange: (v: number) => void; min: number; max: number; disabled?: boolean; icon: string;
}) {
  return (
    <div className={`stepper ${disabled ? 'disabled' : ''}`}>
      <span className={`stepper-icon ${icon}`} aria-hidden />
      <span className="stepper-label">{label}</span>
      <button aria-label={`Fewer ${label.toLowerCase()}`} disabled={disabled || value <= min} onClick={() => onChange(value - 1)}>−</button>
      <span className="stepper-value" aria-live="polite">{value}</span>
      <button aria-label={`More ${label.toLowerCase()}`} disabled={disabled || value >= max} onClick={() => onChange(value + 1)}>+</button>
    </div>
  );
}

export function LeftPanel() {
  const settings = useSim((s) => s.settings);
  const overlays = useSim((s) => s.overlays);
  const status = useSim((s) => s.status);
  const demo = useSim((s) => s.demo);
  const selected = useSim((s) => s.selected);
  const engine = useSim((s) => s.engine);
  const editingSurvivors = useSim((s) => s.editingSurvivors);
  const survivorCapacity = useSim((s) => s.survivorCapacity);
  const survivorMessage = useSim((s) => s.survivorMessage);
  const customSurvivors = useSim((s) => s.customSurvivors);
  const { setSetting, toggleOverlay, reset, randomizeSeed, loadDemo, setSurvivorCount, randomizeSurvivors, setEditingSurvivors, clearSurvivors, useAutomaticSurvivors } = useSim.getState();
  const [survivorCountDraft, setSurvivorCountDraft] = useState(String(settings.survivorCount ?? engine.scenario.victims.length));
  useEffect(() => {
    setSurvivorCountDraft(String(settings.survivorCount ?? engine.scenario.victims.length));
  }, [engine, settings.survivorCount]);
  const applySurvivorCount = () => setSurvivorCount(survivorCountDraft.trim() === '' ? NaN : Number(survivorCountDraft));
  const locked = status !== 'ready';
  const fieldId = useId();
  const partitionTarget = selected ? engine.label(selected) : engine.robots[0]?.label ?? 'robot';
  const overlayToggles: Array<[keyof Overlays, string]> = [
    ['links', 'Radio links'], ['graph', 'Network graph'], ['packets', 'Message pulses'],
    ['ranges', 'Radio range'], ['paths', 'Planned routes'], ['evidence', 'Sensor evidence'],
    ['coverage', 'Unexplored terrain'], ['labels', 'Robot labels'],
  ];

  return (
    <aside className="panel left" aria-label="Mission settings">
      <div className="panel-header">
        <span className="panel-eyebrow">YOUR EXPEDITION</span>
        <h2>Mission setup</h2>
        <p className="panel-intro">Choose the terrain. Build your team.</p>
      </div>
      <section className="section">
        <label className="field-label" htmlFor={`${fieldId}-site`}>Search site {locked && <span className="hint">Reset to change</span>}</label>
        <select id={`${fieldId}-site`} value={demo ? 'demo' : settings.preset} disabled={locked} onChange={(e) => setSetting('preset', e.target.value as PresetId)}>
          {PRESETS.filter((p) => p.id !== 'demo').map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          {demo && <option value="demo">Validation Demo</option>}
        </select>
        <label className="field-label" htmlFor={`${fieldId}-seed`}>World seed</label>
        <div className="seed-row">
          <input id={`${fieldId}-seed`} type="number" min={0} step={1} value={settings.seed} disabled={locked} onChange={(e) => setSetting('seed', Math.max(0, Math.floor(Number(e.target.value) || 0)))} />
          <button className="btn icon" onClick={randomizeSeed} disabled={locked} title="Generate another world" aria-label="Randomize world seed">↻</button>
        </div>
        <label className="field-label">Search team <span className="faint">{settings.rovers + settings.drones} / 10</span></label>
        <Stepper label="Rovers" icon="rover" value={settings.rovers} min={settings.drones ? 0 : 1} max={10 - settings.drones} disabled={locked || demo} onChange={(v) => setSetting('rovers', v)} />
        <Stepper label="Drones" icon="drone" value={settings.drones} min={settings.rovers ? 0 : 1} max={10 - settings.rovers} disabled={locked || demo} onChange={(v) => setSetting('drones', v)} />
      </section>
      <section className="section survivor-setup" aria-label="Survivor setup">
        <label className="field-label" htmlFor={`${fieldId}-survivors`}>
          Survivors <span className="hint">{locked ? 'Reset to edit' : customSurvivors ? 'Custom placement' : settings.survivorCount === null ? 'Automatic · 2–4' : 'Custom count'}</span>
        </label>
        <div className="seed-row survivor-count-row">
          <input
            id={`${fieldId}-survivors`}
            type="number"
            min={0}
            max={survivorCapacity}
            step={1}
            value={survivorCountDraft}
            disabled={locked}
            aria-describedby={`${fieldId}-survivor-help`}
            onChange={(e) => setSurvivorCountDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                applySurvivorCount();
              }
            }}
          />
          <button className="btn" onClick={applySurvivorCount} disabled={locked}>Apply count</button>
        </div>
        <p className="explain" id={`${fieldId}-survivor-help`}>{survivorCapacity.toLocaleString()} available tiles. One survivor per reachable tile outside the staging area.</p>
        <div className="survivor-actions">
          <button className={`btn ${editingSurvivors ? 'primary' : ''}`} disabled={locked} aria-pressed={editingSurvivors} onClick={() => setEditingSurvivors(!editingSurvivors)}>
            {editingSurvivors ? 'Finish placing' : 'Place on map'}
          </button>
          <button className="btn ghost" disabled={locked} onClick={randomizeSurvivors}>Randomize positions</button>
        </div>
        <p className="explain">{locked ? 'Survivor setup is saved for this mission. Reset before changing the count or positions.' : 'Place survivors before launch: click an empty path to add one, or an existing marker to remove it.'}</p>
        {survivorMessage && <p className="explain survivor-editor-message" role="status" aria-live="polite">{survivorMessage}</p>}
        <details className="disclosure survivor-tools">
          <summary>Placement options</summary>
          <div className="survivor-actions">
            <button className="btn ghost" disabled={locked || engine.scenario.victims.length === 0} onClick={clearSurvivors}>Clear survivors</button>
            <button className="btn ghost" disabled={locked} onClick={useAutomaticSurvivors}>Use automatic</button>
          </div>
          <p className="explain">Automatic restores the standard seeded 2–4 survivors. Empty the map to start a custom layout; add at least one survivor before launch.</p>
        </details>
      </section>
      <section className="section">
        <label className="field-label">Control mode</label>
        <Segmented<OperationMode> label="Control mode" value={settings.mode} onChange={(v) => setSetting('mode', v)} options={[
          { value: 'autonomous', label: 'Auto', title: 'Every robot explores independently' },
          { value: 'manual', label: 'Manual', title: 'Drive one robot while the others hold' },
          { value: 'mixed', label: 'Mixed', title: 'Drive one robot while the others explore' },
        ]} />
        <p className="explain">{settings.mode === 'autonomous' ? 'Your team explores independently and shares discoveries.' : settings.mode === 'manual' ? 'Select a robot, then click a path or use WASD to move.' : 'Drive your selected robot while the team keeps exploring.'}</p>
      </section>
      <details className="advanced disclosure">
        <summary>Radio & sensors</summary>
        <p className="explain">Adjust communication conditions to test your team.</p>
        <Toggle label="Peer-to-peer radio" checked={settings.networkEnabled} disabled={locked || demo} onChange={() => setSetting('networkEnabled', !settings.networkEnabled)} />
        <Toggle label="Sensor noise" checked={settings.sensorNoise} disabled={locked} onChange={() => setSetting('sensorNoise', !settings.sensorNoise)} />
        <label className="field-label" htmlFor={`${fieldId}-loss`}>Packet loss <span className="value">{Math.round(settings.packetLoss * 100)}%</span></label>
        <input id={`${fieldId}-loss`} type="range" min={0} max={30} step={1} value={Math.round(settings.packetLoss * 100)} onChange={(e) => setSetting('packetLoss', Number(e.target.value) / 100)} />
        <label className="field-label" htmlFor={`${fieldId}-delay`}>Message delay <span className="value">1–{settings.delayMax} ticks</span></label>
        <input id={`${fieldId}-delay`} type="range" min={1} max={6} step={1} value={settings.delayMax} onChange={(e) => setSetting('delayMax', Number(e.target.value))} />
        <Toggle label={`Isolate ${partitionTarget}`} title="Temporarily disconnect this robot from the team" checked={settings.partition} danger disabled={!settings.networkEnabled} onChange={() => setSetting('partition', !settings.partition)} />
      </details>
      <details className="advanced disclosure">
        <summary>Graphics & overlays</summary>
        <label className="field-label">Graphics quality</label>
        <Segmented<Quality> label="Graphics quality" value={settings.quality} onChange={(v) => setSetting('quality', v)} options={[
          { value: 'low', label: 'Low' }, { value: 'medium', label: 'Balanced' }, { value: 'high', label: 'High' },
        ]} />
        <label className="field-label" htmlFor={`${fieldId}-fog`}>Atmosphere <span className="value">{Math.round(settings.fog * 100)}%</span></label>
        <input id={`${fieldId}-fog`} type="range" min={0} max={100} value={Math.round(settings.fog * 100)} onChange={(e) => setSetting('fog', Number(e.target.value) / 100)} />
        <div className="toggles">{overlayToggles.map(([key, label]) => <Toggle key={key} label={label} checked={overlays[key]} onChange={() => toggleOverlay(key)} />)}</div>
        <Toggle label="Reveal hidden survivors" danger checked={overlays.truth} onChange={() => toggleOverlay('truth')} title="Debug view only. This information is never available to robots." />
      </details>
      <details className="advanced disclosure">
        <summary>Mission tools</summary>
        <p className="explain">A guided scenario demonstrates radio loss and recovery.</p>
        <button className="btn demo" onClick={loadDemo} disabled={locked}>Load validation scenario</button>
        <button className="btn ghost" onClick={reset} disabled={status === 'ready' && engine.step === 0}>Reset mission</button>
      </details>
    </aside>
  );
}
