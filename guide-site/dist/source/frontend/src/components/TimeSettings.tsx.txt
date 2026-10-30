import { useEffect, useState } from 'react';
import { useSim } from '../store/simStore';

export interface TimeDraft { mode: 'auto' | 'custom' | 'unlimited'; minutes: string }
export const timeDraft = (seconds?: number | null): TimeDraft => ({ mode: seconds === null ? 'unlimited' : seconds === undefined ? 'auto' : 'custom', minutes: seconds ? String(seconds / 60) : '10' });
export function timeSeconds(draft: TimeDraft): number | null | undefined {
  if (draft.mode === 'auto') return undefined;
  if (draft.mode === 'unlimited') return null;
  const seconds = Math.round(Number(draft.minutes) * 60);
  return draft.minutes.trim() && Number.isFinite(seconds) && seconds >= 1 && seconds <= 86400 ? seconds : NaN;
}
export function TimeLimitFields({ draft, onChange, disabled = false }: { draft: TimeDraft; onChange: (draft: TimeDraft) => void; disabled?: boolean }) {
  const valid = !Number.isNaN(timeSeconds(draft));
  return <div className="time-settings">
    <label className="field-label">Time limit<select aria-label="Mission time limit" value={draft.mode} disabled={disabled} onChange={(e) => onChange({ ...draft, mode: e.target.value as TimeDraft['mode'] })}><option value="auto">Automatic</option><option value="custom">Custom</option><option value="unlimited">Unlimited</option></select></label>
    {draft.mode === 'custom' && <label className="field-label">Minutes<input aria-label="Mission duration in minutes" type="number" min={1 / 60} max={1440} step="any" value={draft.minutes} disabled={disabled} aria-invalid={!valid} onChange={(e) => onChange({ ...draft, minutes: e.target.value })} /></label>}
    {!valid && <p className="controller-seed-help invalid" role="status">Choose a duration from 1 second to 24 hours.</p>}
  </div>;
}
export function TimeSettings() {
  const value = useSim((s) => s.settings.timeLimit);
  const [draft, setDraft] = useState(() => timeDraft(value));
  useEffect(() => { setDraft(timeDraft(value)); }, [value]);
  const next = timeSeconds(draft);
  return <section className="section" aria-label="Mission duration">
    <TimeLimitFields draft={draft} onChange={setDraft} />
    <button className="btn small" disabled={Number.isNaN(next) || next === value} onClick={() => useSim.getState().setSetting('timeLimit', next)}>Apply time</button>
    <p className="explain">Changing time restarts the mission. Minutes are simulation time.</p>
  </section>;
}
