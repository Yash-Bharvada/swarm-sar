import { useEffect, useRef, useState } from 'react';
import { useAudio, type AudioChannel } from '../audio/audioStore';
import { soundscape } from '../audio/Soundscape';
import { Icon } from './Icon';

const CHANNELS: { key: AudioChannel; label: string; detail: string }[] = [
  { key: 'master', label: 'Master volume', detail: 'Your overall listening level' },
  { key: 'music', label: 'Ambient music', detail: 'Slow chords and a gentle melody' },
  { key: 'vehicles', label: 'Fleet sounds', detail: 'Rotors, motors and wheels' },
  { key: 'effects', label: 'Event sounds', detail: 'Discoveries, focus and controls' },
];

export function SoundControls() {
  const { enabled, muted, levels, error, setVolume } = useAudio();
  const [open, setOpen] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const outside = (event: PointerEvent) => { if (!wrapper.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.code === 'Escape') setOpen(false); };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape); };
  }, []);
  const audible = enabled && !muted;
  return <div className="sound-wrap" ref={wrapper} data-audio="none">
    <div className={`sound-buttons ${audible ? 'sound-on' : ''}`}>
      <button className="sound-toggle" aria-label={!enabled ? 'Enable audio' : muted ? 'Unmute audio' : 'Mute audio'} aria-pressed={audible} title={audible ? 'Mute sound (M)' : 'Enable sound (M)'} onClick={() => { soundscape.toggleMute(); if (!enabled) setOpen(true); }}><Icon name={audible ? 'volume' : 'muted'} size={17} /></button>
      <button className={`sound-settings ${open ? 'active' : ''}`} aria-label="Sound settings" aria-expanded={open} aria-controls="sound-settings-panel" title="Sound settings" onClick={() => setOpen(!open)}><Icon name="settings" size={13} /></button>
    </div>
    {open && <section className="sound-panel" id="sound-settings-panel" aria-label="Sound settings">
      <div className="popover-heading"><Icon name="music" size={17} /> Meadow radio<span>A calmer soundtrack for a busy little world.</span></div>
      <button className={`sound-enable ${audible ? 'enabled' : ''}`} onClick={() => soundscape.toggleMute()} aria-pressed={audible}><span className="status-dot" />{audible ? 'Sound on' : enabled ? 'Sound muted' : 'Enable sound'}<kbd>M</kbd></button>
      {CHANNELS.map(({ key, label, detail }) => <label className="sound-channel" key={key}>
        <span className="sound-channel-label"><strong>{label}</strong><span className="mono">{Math.round(levels[key] * 100)}%</span></span>
        <input type="range" min={0} max={100} value={Math.round(levels[key] * 100)} aria-label={label} style={{ background: `linear-gradient(to right, #819b68 ${levels[key] * 100}%, #e5ebd9 ${levels[key] * 100}%)` }} onChange={(event) => setVolume(key, Number(event.target.value) / 100)} />
        <small>{detail}</small>
      </label>)}
      <p className="sound-note">Focus on a robot to hear it more clearly. Music softens for important discoveries.</p>
      {error && <p className="sound-error" role="status">{error}</p>}
    </section>}
  </div>;
}
