import { useEffect, useRef, useState } from 'react';
import { useSim, type Overlays, type Speed } from '../store/simStore';
import { missionTime, networkHealth, pct } from '../app/format';
import { NetworkGraph } from './NetworkGraph';
import { Icon } from './Icon';
import { ControllerControls } from './ControllerControls';
import { SoundControls } from './SoundControls';
import type { Panel } from '../app/App';

const layerOptions: { key: keyof Overlays; label: string; detail: string }[] = [
  { key: 'paths', label: 'Planned routes', detail: 'The selected robot’s next steps' },
  { key: 'links', label: 'Radio connections', detail: 'Live links between teammates' },
  { key: 'packets', label: 'Message activity', detail: 'Data travelling across the swarm' },
  { key: 'evidence', label: 'Sensor evidence', detail: 'Thermal and acoustic signals' },
  { key: 'coverage', label: 'Explored map', detail: 'Highlight what robots have sensed' },
  { key: 'labels', label: 'Robot labels', detail: 'Identify your field team' },
];

export function SceneHud({ onOpenPanel }: { onOpenPanel: (panel: Panel) => void }) {
  useSim((s) => s.version);
  const { engine, status, overlays, settings, selected, cameraView, cameraZoom, following, editingSurvivors, survivorMessage, setEditingSurvivors, moveCamera, toggleOverlay, toggleCleanView, launch, pause, resume, reset, setSetting } = useSim();
  const controllerMode = useSim((s) => s.controllerMode);
  const ppoPhase = useSim((s) => s.ppoPhase);
  const ppoError = useSim((s) => s.ppoError);
  const [layersOpen, setLayersOpen] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const layers = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: PointerEvent) => { if (layers.current && !layers.current.contains(e.target as Node)) setLayersOpen(false); };
    const escape = (e: KeyboardEvent) => { if (e.code === 'Escape') { setLayersOpen(false); setConfirmReset(false); } };
    window.addEventListener('pointerdown', close);
    window.addEventListener('keydown', escape);
    return () => { window.removeEventListener('pointerdown', close); window.removeEventListener('keydown', escape); };
  }, []);
  useEffect(() => { if (status === 'ready') setConfirmReset(false); }, [status]);
  const health = networkHealth(engine);
  const selectedRobot = engine.robots.find((r) => r.name === selected);
  const rovers = engine.robots.filter((r) => r.type === 'rover').length;
  const drones = engine.robots.length - rovers;
  const run = () => { if (status === 'ready') launch(); else if (status === 'running') pause(); else if (status === 'paused') resume(); };
  const runLabel = status === 'ready' ? 'Launch mission' : status === 'running' ? 'Pause mission' : status === 'paused' ? 'Resume mission' : 'Mission complete';

  return <div className="hud">
    <div className="world-heading">
      <div className="scene-eyebrow"><span className="tiny-square" />FIELD OPERATIONS <span className="eyebrow-divider">/</span> SANDBOX</div>
      <h1>{engine.scenario.name.replace('Collapsed ', '').replace('Earthquake ', '')}</h1>
      <p>Amber beacons: survivors awaiting discovery.</p>
      <div className="scene-tags"><span><i className={`connection-dot ${health.tone}`} />{!engine.network.enabled ? 'Radio offline' : `Network ${health.label.toLowerCase()}`}</span><span className="mono">SEED {engine.scenario.seed}</span><span>{engine.options.batteryLimited === false ? '∞ Unlimited battery' : 'Limited battery'}</span></div>
    </div>

    <div className="scene-top-right">
      <ControllerControls />
      <SoundControls />
      <button className="scene-button watch-maze" onClick={toggleCleanView} disabled={editingSurvivors} title="Hide interface and overlays (H)"><Icon name="overview" size={17} /><span>Watch maze</span></button>
      <button className="team-pill" onClick={() => onOpenPanel('fleet')} title="Inspect your fleet"><span className="team-icons"><Icon name="rover" size={17} /><Icon name="drone" size={17} /></span><span>{rovers} rovers <b>·</b> {drones} drones</span><Icon name="chevron" size={13} /></button>
      <div className="layers-wrap" ref={layers}>
        <button className={`scene-button ${layersOpen ? 'active' : ''}`} aria-label="Layers" onClick={() => setLayersOpen(!layersOpen)} aria-expanded={layersOpen} aria-controls="layer-menu"><Icon name="layers" size={17} />Layers{layerOptions.some((l) => l.key !== 'labels' && overlays[l.key]) && <span className="layer-count">{layerOptions.filter((l) => l.key !== 'labels' && overlays[l.key]).length}</span>}</button>
        {layersOpen && <div className="layer-menu" id="layer-menu"><div className="popover-heading">Make the invisible visible<span>Choose what you want to see.</span></div>{layerOptions.map((l) => <label className="layer-option" key={l.key}><span><strong>{l.label}</strong><small>{l.detail}</small></span><input type="checkbox" checked={overlays[l.key]} onChange={() => toggleOverlay(l.key)} /></label>)}<button className="text-button" onClick={() => { onOpenPanel('setup'); setLayersOpen(false); }}>More display settings <Icon name="chevron" size={13} /></button></div>}
      </div>
    </div>

    {controllerMode === 'ppo' && ppoPhase !== 'ready' && <div className="ppo-connection" role="status"><strong>{ppoPhase === 'connecting' ? 'Connecting to the PPO swarm…' : 'PPO mission paused'}</strong><p>{ppoError ?? 'Loading the verified checkpoint and Python world.'}</p>{ppoPhase === 'error' && <button className="btn" onClick={reset}>Reset PPO mission</button>}</div>}
    {overlays.truth && <div className="debug-banner">Debug view · Hidden survivor locations revealed to the operator.</div>}
    {overlays.coverage && <div className="map-mode-label"><Icon name="map" size={14} />{selectedRobot ? `${selectedRobot.label}’s private map` : 'Combined explored map'} · Mint: explored / Sand: unseen<button aria-label="Hide explored map" onClick={() => toggleOverlay('coverage')}><Icon name="close" size={13} /></button></div>}
    {overlays.graph && <NetworkGraph />}

    {status === 'ready' && !editingSurvivors && <div className="mission-brief"><span className="brief-index">YOUR MISSION <span>SEARCH & RESCUE</span></span><h2>Send a little help.</h2><p>Your autonomous team is ready. Explore the site, share discoveries, and locate every survivor.</p><button className="brief-configure" onClick={() => onOpenPanel('setup')}><Icon name="settings" size={15} />Configure mission<Icon name="chevron" size={13} /></button></div>}
    {editingSurvivors && <div className="placement-banner" role="status"><div><strong>Place survivors · {engine.scenario.victims.length} placed</strong><span>{survivorMessage ?? 'Click an empty path to add; click a marker to remove.'}</span></div><button className="btn" onClick={() => setEditingSurvivors(false)}>Done placing</button></div>}
    {status === 'complete' && <div className="mission-brief complete-card"><span className="brief-index"><Icon name="check" size={14} />MISSION REPORT</span><h2>{engine.doneReason === 'all_found' ? 'Everyone accounted for.' : 'Mission finished.'}</h2><p>{engine.survivorsFound()} of {engine.scenario.victims.length} survivors found. {pct(engine.coverage())} of the site explored, with {engine.collisions} collisions.</p><button className="brief-configure" onClick={reset}><Icon name="reset" size={15} />Start a new mission</button></div>}

    <div className="camera-tools">
      <div className="camera-view-switch" aria-label="Camera angle"><button className={cameraView === 'isometric' ? 'active' : ''} onClick={() => moveCamera('isometric')} aria-label="Isometric camera" title="Isometric view"><Icon name="orbit" size={18} /></button><button className={cameraView === 'top' ? 'active' : ''} onClick={() => moveCamera('top')} aria-label="Top-down camera" title="Top-down view"><Icon name="top" size={18} /></button></div>
      <div className="zoom-controls"><button aria-label="Zoom in" title="Zoom in (+)" disabled={cameraZoom >= 400} onClick={() => moveCamera('zoomIn')}><Icon name="plus" size={18} /></button><span className="zoom-value mono" aria-live="polite">{cameraZoom}%</span><button aria-label="Zoom out" title="Zoom out (−)" disabled={cameraZoom <= 60} onClick={() => moveCamera('zoomOut')}><Icon name="minus" size={18} /></button><span className="tool-separator" /><button aria-label="Fit world to view" title="Fit world to view (R)" onClick={() => moveCamera('reset')}><Icon name="focus" size={18} /></button></div>
      {selectedRobot && <button className={`follow-button ${following ? 'active' : ''}`} title={`Follow ${selectedRobot.label}`} onClick={() => moveCamera('follow')}><Icon name="focus" size={17} />{following ? 'Following' : 'Follow'}<span>{selectedRobot.label}</span></button>}
    </div>

    {selectedRobot?.manual && status !== 'complete' && <div className="manual-hint"><Icon name={selectedRobot.type === 'drone' ? 'drone' : 'rover'} size={16} />Driving {selectedRobot.label} · Click a path to move · WASD · E to scan</div>}
    <div className="playback">
      <button className={`launch-button ${status === 'running' ? 'running' : ''}`} aria-label={runLabel} onClick={run} disabled={(controllerMode === 'ppo' && ppoPhase !== 'ready') || status === 'complete' || (status === 'ready' && !engine.scenario.victims.length)} title={status === 'ready' && !engine.scenario.victims.length ? 'Place at least one survivor before launching' : `${runLabel} (Space)`}><Icon name={status === 'running' ? 'pause' : status === 'complete' ? 'check' : 'play'} size={18} /><span>{runLabel}</span><kbd>SPACE</kbd></button>
      <div className="playback-divider" />
      <div className="speed-control" aria-label="Simulation speed">{([0.5, 1, 2, 4] as Speed[]).map((speed) => <button key={speed} className={settings.speed === speed ? 'active' : ''} aria-label={`${speed} times speed`} aria-pressed={settings.speed === speed} onClick={() => setSetting('speed', speed)}>{speed}×</button>)}</div>
      <div className="mission-timeline"><div className="timeline-label"><span>{status === 'ready' ? 'Ready when you are' : status === 'running' ? 'Exploring together' : status === 'paused' ? 'Take your time' : 'Exploration complete'}</span><span className="mono">{missionTime(engine.step)} <b>/ {missionTime(engine.maxSteps)}</b></span></div><div className="timeline-track" role="progressbar" aria-label="Mission elapsed time" aria-valuenow={engine.step} aria-valuemin={0} aria-valuemax={engine.maxSteps}><i style={{ width: `${100 * engine.step / engine.maxSteps}%` }} /></div></div>
      <div className="reset-wrap"><button className="reset-button" aria-label="Reset mission" title="Reset mission" onClick={() => status === 'ready' ? reset() : setConfirmReset(!confirmReset)}><Icon name="reset" size={18} /></button>{confirmReset && <div className="reset-popover"><strong>Start this mission again?</strong><p>Your current progress will be cleared.</p><div><button className="btn" onClick={() => setConfirmReset(false)}>Keep exploring</button><button className="btn primary" onClick={() => { reset(); setConfirmReset(false); }}>Reset</button></div></div>}</div>
    </div>
    <div className="scene-footnote"><span><Icon name="mouse" size={12} /><b>Drag</b> to orbit <i>·</i> <b>Right-drag</b> to pan <i>·</i> <b>Scroll</b> to zoom</span><span><span className="status-dot" />BROWSER SIMULATION <span className="footnote-divider">/</span> {engine.scenario.width} × {engine.scenario.height} M</span></div>
  </div>;
}
