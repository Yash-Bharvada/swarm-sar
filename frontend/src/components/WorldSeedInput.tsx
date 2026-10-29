import { useEffect, useId, useState } from 'react';
import { useSim } from '../store/simStore';
import { isWorldSeed } from '../simulation/core/Rng';

export function WorldSeedInput({ locked }: { locked: boolean }) {
  const seed = useSim((s) => s.settings.seed);
  const preset = useSim((s) => s.settings.preset);
  const [draft, setDraft] = useState(String(seed));
  const id = useId();
  useEffect(() => { setDraft(String(seed)); }, [seed, preset]);
  const value = Number(draft);
  const valid = /^\d+$/.test(draft) && isWorldSeed(value);
  const apply = () => {
    if (locked || !valid) return;
    if (value !== seed) useSim.getState().setSetting('seed', value);
    setDraft(String(value));
  };
  return <>
    <label className="field-label" htmlFor={id}>World seed</label>
    <div className="seed-row world-seed-row">
      <input id={id} type="text" inputMode="numeric" autoComplete="off" spellCheck={false} maxLength={32} value={draft} disabled={locked} aria-invalid={!valid} aria-describedby={`${id}-help`} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); apply(); } }} />
      <button className="btn" onClick={apply} disabled={locked || !valid}>Apply seed</button>
      <button className="btn icon" onClick={() => { const next = (seed + 1 + Math.floor(Math.random() * 99999)) >>> 0; useSim.getState().setSetting('seed', next); setDraft(String(next)); }} disabled={locked} title="Generate another world" aria-label="Randomize world seed">↻</button>
    </div>
    <p id={`${id}-help`} className={`controller-seed-help ${valid ? '' : 'invalid'}`} role={valid ? undefined : 'status'}>{valid ? '0–4,294,967,295. Press Enter or Apply seed to rebuild the world.' : 'Enter a whole number from 0 to 4,294,967,295. The current world has not changed.'}</p>
  </>;
}
