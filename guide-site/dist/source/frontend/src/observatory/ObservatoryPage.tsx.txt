import { Suspense, lazy, useEffect, useRef, useState, type CSSProperties } from 'react';
import { Icon } from '../components/Icon';
import type { ObservatorySnapshot } from './types';
import { SceneBoundary } from './SceneBoundary';
import './observatory.css';

const ObservatoryScene = lazy(() => import('./ObservatoryScene').then(module => ({ default: module.ObservatoryScene })));
type Props = {
  snapshot: ObservatorySnapshot; onBack: () => void; missionStatus?: string;
  onToggleMission?: () => void; encounter?: boolean; onContinue?: () => void;
  connection?: string; onConnect?: (url: string) => void; onDisconnect?: () => void;
  onIsolate?: (agent: string, isolated: boolean) => Promise<unknown>; isolated?: string[]; radioStatusFresh?: boolean;
};
const number = (n: number) => n.toLocaleString('en-US');
const shortName = (id: string) => id.replace('rover_', 'R').replace('drone_', 'D');

export function ObservatoryPage({ snapshot, onBack, missionStatus, onToggleMission, encounter, onContinue, connection, onConnect, onDisconnect, onIsolate, isolated = [], radioStatusFresh = false }: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const [view, setView] = useState<'spatial' | 'neural'>('spatial');
  const [paths, setPaths] = useState(true), [packets, setPackets] = useState(true), [frontiers, setFrontiers] = useState(false);
  const [frozen, setFrozen] = useState(false), [zoom, setZoom] = useState(1);
  const [cameraReset, setCameraReset] = useState(0);
  const [cameraAngle, setCameraAngle] = useState<'isometric' | 'top'>('isometric');
  const [stream, setStream] = useState(false), [layers, setLayers] = useState(false);
  const [filter, setFilter] = useState('all');
  const [bridge, setBridge] = useState(new URLSearchParams(location.search).get('bridge') || 'ws://localhost:9090');
  const [feedback, setFeedback] = useState(''), [busy, setBusy] = useState(false);
  const [connectionPanel, setConnectionPanel] = useState(false);
  const last = useRef(snapshot);
  if (!frozen || last.current.epoch !== snapshot.epoch) last.current = snapshot;
  const data = last.current;
  const hasData = data.agents.some(a => a.position !== null);
  const agent = data.agents.find(a => a.id === selected);
  const mapAgent = agent || data.agents.find(a => a.position && a.grid) || data.agents.find(a => a.position);
  const [bridgeFeedback, setBridgeFeedback] = useState('');
  const events = data.packets.filter(p => (!selected || p.source === selected || p.target === selected) && (filter === 'all' || (filter === 'success' ? p.state === 'delivered' || p.state === 'applied' : p.state === 'dropped'))).slice(-20).reverse();
  useEffect(() => { setSelected(null); setFrozen(false); }, [snapshot.epoch]);
  useEffect(() => {
    if (!connectionPanel) return;
    const previous = document.activeElement as HTMLElement | null;
    document.querySelector<HTMLInputElement>('.ob-connection-modal input')?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); setConnectionPanel(false); }
      if (event.key === 'Tab') {
        const controls = [...document.querySelectorAll<HTMLElement>('.ob-connection-modal button, .ob-connection-modal input')];
        if (event.shiftKey && document.activeElement === controls[0]) { event.preventDefault(); controls.at(-1)?.focus(); }
        else if (!event.shiftKey && document.activeElement === controls.at(-1)) { event.preventDefault(); controls[0]?.focus(); }
      }
    };
    document.addEventListener('keydown', keydown);
    return () => { document.removeEventListener('keydown', keydown); previous?.focus(); };
  }, [connectionPanel]);
  const exportTelemetry = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify({ exportedAt: new Date().toISOString(), ...data }, null, 2)], { type: 'application/json' }));
    const a = document.createElement('a'); a.href = url; a.download = `swarm-${data.source}-telemetry-${Math.floor(data.time)}.json`; a.click(); URL.revokeObjectURL(url);
  };
  const changeIsolation = async () => {
    if (!agent || !onIsolate) return;
    setBusy(true); setFeedback('Sending radio request…');
    try { await onIsolate(agent.id, !isolated.includes(agent.id)); setFeedback('Request acknowledged. Status follows ROS telemetry.'); }
    catch (error) { setFeedback(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  };
  return <div className="observatory">
    <header className="ob-header">
      <button className="ob-brand" onClick={onBack} aria-label="Return to simulation home"><span className="ob-brand-icon"><Icon name="swarm" size={25} /></span><span><b>swarm<sup>®</sup></b><small>SEARCH. CONNECT. RESCUE.</small></span></button>
      <div className="ob-breadcrumb"><span>Workspace</span><Icon name="chevron" size={12} /><strong>Swarm intelligence</strong></div>
      <div className="ob-source-picker" aria-label="Telemetry source"><a className={data.source === 'browser' ? 'current' : ''} href="/?mode=observatory" onClick={e => { if (data.source === 'browser') e.preventDefault(); }}>Browser mission</a><a className={data.source === 'ros' ? 'current' : ''} href="/?mode=ros">ROS / SLAM</a></div>
      <button className="ob-back" onClick={onBack}><Icon name="orbit" size={15} /><span>Back to simulation</span></button>
    </header>
    <main className={`ob-stage ${stream ? 'stream-open' : ''} ${hasData ? 'has-data' : 'waiting'}`} aria-label="SLAM and agent communication visualization">
      {hasData ? <SceneBoundary key={cameraReset} onRetry={() => setCameraReset(v => v + 1)}><Suspense fallback={<div className="ob-loading"><span />Preparing the 3D view…</div>}><ObservatoryScene key={cameraReset} snapshot={data} selected={selected} onSelect={id => setSelected(id === selected ? null : id)} view={view} showPaths={paths} showPackets={packets} showFrontiers={frontiers} frozen={frozen} zoom={zoom} cameraAngle={cameraAngle} /></Suspense></SceneBoundary> : <div className="ob-empty-scene" aria-hidden="true"><div /><div /><div /></div>}
      <div className="ob-stage-top"><div className="ob-stage-title"><span className="ob-eyebrow">MISSION OBSERVATORY</span><h1>{data.source === 'ros' ? 'The swarm, in focus.' : 'Intelligence in motion.'}</h1><div className="ob-stamp"><i className={data.fresh && data.running && !frozen ? 'on' : ''} /><span>{frozen ? 'VIEW FROZEN' : !hasData ? 'AWAITING CONNECTION' : !data.fresh ? 'WAITING / STALE' : data.running ? 'LIVE MISSION' : missionStatus === 'ready' ? 'READY TO EXPLORE' : 'MISSION PAUSED'}</span>{hasData && <time>{data.time.toFixed(1)} s</time>}</div></div>
        {hasData && <div className="ob-live-summary"><span><Icon name="fleet" size={15} /><b>{data.agents.filter(a => a.fresh).length}</b> agents</span><i /><span><Icon name="signal" size={15} /><b>{number(data.metrics.delivered)}</b> delivered</span></div>}
      </div>
      {hasData && <><div className="ob-view-switch"><button aria-pressed={view === 'spatial'} className={view === 'spatial' ? 'active' : ''} onClick={() => { setView('spatial'); setZoom(1); }}><Icon name="map" size={15} />3D map</button><button aria-pressed={view === 'neural'} className={view === 'neural' ? 'active' : ''} onClick={() => { setView('neural'); setZoom(1); }}><Icon name="signal" size={15} />Peer network</button></div>
        <nav className="ob-agent-rail" aria-label="Select agent">{data.agents.map(a => <button key={a.id} aria-label={`Inspect ${a.id}`} title={`${a.id} · ${a.fresh ? a.state : 'stale'}`} className={`ob-agent ${selected === a.id ? 'selected' : ''}`} style={{ '--agent-color': a.color } as CSSProperties} onClick={() => { setSelected(selected === a.id ? null : a.id); setFeedback(''); }}><span className="ob-agent-glyph"><Icon name={a.type} size={22} /></span><strong>{shortName(a.id)}</strong><i className={a.fresh ? 'online' : ''} /></button>)}</nav>
        {agent && <aside className="ob-inspector"><header><div><span className="ob-eyebrow">PRIVATE KNOWLEDGE</span><h2><span style={{ background: agent.color }} />{agent.id.replace('_', ' ')}</h2></div><button className="ob-icon" onClick={() => setSelected(null)} aria-label="Clear agent selection"><Icon name="close" size={16} /></button></header><dl><div><dt>Known cells</dt><dd>{number(agent.knownCells)}</dd></div><div><dt>Agent state</dt><dd>{agent.fresh ? agent.state.replaceAll('_', ' ') : 'Waiting / stale'}</dd></div>{data.source === 'ros' && <div><dt>Peer-only cells</dt><dd>{number(agent.peerCells)}</dd></div>}<div><dt>Battery</dt><dd>{agent.battery === null ? 'Not reported' : `${Math.round(agent.battery * 100)}%`}</dd></div><div><dt>Goal</dt><dd>{agent.goal ? `${agent.goal.x.toFixed(1)}, ${agent.goal.y.toFixed(1)}` : 'Not reported'}</dd></div><div><dt>Localization</dt><dd>{data.source === 'browser' ? 'Simulated pose' : agent.type === 'rover' ? 'SLAM estimate' : 'Simulator pose'}</dd></div></dl>{data.source === 'ros' && onIsolate && <div className="ob-radio"><button className="ob-outline" disabled={busy || connection !== 'connected' || !snapshot.fresh || !radioStatusFresh} onClick={changeIsolation}><Icon name="signal" size={14} />{isolated.includes(agent.id) ? 'Reconnect radio' : 'Isolate radio'}</button><small>{feedback || (!radioStatusFresh ? 'Waiting for radio status' : isolated.includes(agent.id) ? 'ROS reports isolated' : 'ROS reports radio enabled')}</small></div>}</aside>}
        <div className="ob-map-tools"><button aria-label={cameraAngle === 'isometric' ? 'Top-down camera' : 'Isometric camera'} title={cameraAngle === 'isometric' ? 'Top-down camera' : 'Isometric camera'} aria-pressed={cameraAngle === 'top'} onClick={() => setCameraAngle(v => v === 'top' ? 'isometric' : 'top')}><Icon name={cameraAngle === 'isometric' ? 'top' : 'orbit'} size={16} /></button><button aria-label="Zoom in" disabled={zoom >= 2.5} onClick={() => setZoom(v => Math.min(2.5, v + .2))}><Icon name="plus" size={16} /></button><button aria-label="Zoom out" disabled={zoom <= .5} onClick={() => setZoom(v => Math.max(.5, v - .2))}><Icon name="minus" size={16} /></button><button aria-label="Reset view" onClick={() => { setZoom(1); setCameraAngle('isometric'); setCameraReset(v => v + 1); }}><Icon name="focus" size={16} /></button></div>
      </>}
      {!hasData && <section className="ob-welcome"><div className="ob-welcome-symbol"><Icon name="signal" size={30} /><i /></div><span className="ob-eyebrow">CONNECT YOUR PHYSICAL SIMULATOR</span><h2>Your swarm.<br />One clear view.</h2><p>Connect ROS to explore estimated maps, robot trajectories and peer communication in real time.</p><button className="ob-primary" onClick={() => setConnectionPanel(true)}><Icon name="signal" size={16} />Connect ROS bridge</button><a href="/?mode=observatory">Explore the browser mission <Icon name="chevron" size={12} /></a></section>}
      <div className="ob-stage-bottom"><div className="ob-source-note"><span>{data.source === 'ros' ? 'ROS 2 · Rover SLAM' : 'Browser mission · Simulated poses'}</span>{hasData && <small>{view === 'spatial' ? `${mapAgent?.id.replace('_', ' ')} · Private map · Blank is unobserved` : 'Peer topology · Actual transport events'}</small>}</div><div className="ob-playback">{hasData && <><button className="ob-icon" aria-label={frozen ? 'Resume visualization' : 'Freeze visualization'} title="Freeze view only" onClick={() => setFrozen(v => !v)}><Icon name={frozen ? 'play' : 'pause'} size={16} /></button><div className="ob-layers-wrap"><button className={`ob-icon ${layers ? 'active' : ''}`} aria-expanded={layers} aria-label="Map layers" onClick={() => setLayers(v => !v)}><Icon name="layers" size={17} /></button>{layers && <div className="ob-layer-popover">{[['Packets', packets, setPackets], ['Paths', paths, setPaths], ['Frontiers', frontiers, setFrontiers]].map(([label, enabled, setter]) => <button key={String(label)} aria-pressed={Boolean(enabled)} onClick={() => (setter as (fn: (v: boolean) => boolean) => void)(v => !v)}><span>{String(label)}</span><i className={enabled ? 'on' : ''} /></button>)}</div>}</div><span className="ob-control-divider" /></>}{data.source === 'browser' ? <button className="ob-primary ob-run" onClick={encounter ? onContinue : onToggleMission} disabled={missionStatus === 'complete'}><Icon name={data.running ? 'pause' : 'play'} size={14} />{encounter ? 'Continue after discovery' : missionStatus === 'ready' ? 'Launch mission' : missionStatus === 'complete' ? 'Mission complete' : data.running ? 'Pause mission' : 'Resume mission'}</button> : <button className="ob-connect-button" onClick={() => setConnectionPanel(true)}><Icon name="signal" size={15} />{connection === 'connected' ? 'ROS connection' : 'Connect ROS'}</button>}</div>{hasData ? <button className={`ob-stream-toggle ${stream ? 'active' : ''}`} onClick={() => setStream(v => !v)} aria-expanded={stream}><span className="ob-stream-pulse" /><span>Messages</span><b>{number(data.metrics.delivered)}</b><Icon name="chevron" size={13} /></button> : <span className="ob-empty-status">{connection === 'connecting' ? 'Connecting…' : 'No active connection'}</span>}</div>
      {stream && hasData && <section className="ob-stream"><header><div><h2>Peer messages</h2><span>Transport events{selected ? ` · ${shortName(selected)}` : ''}</span></div><div><select aria-label="Filter packet stream" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">All messages</option><option value="success">Delivered / applied</option><option value="dropped">Dropped</option></select><button className="ob-icon" onClick={exportTelemetry} aria-label="Export telemetry" title="Export telemetry"><Icon name="layers" size={16} /></button><button className="ob-icon" onClick={() => setStream(false)} aria-label="Close messages"><Icon name="close" size={16} /></button></div></header><div className="ob-stream-table"><div className="ob-table-head"><span>TIME</span><span>ROUTE</span><span>PAYLOAD</span><span>STATUS</span></div>{events.length ? events.map(p => <div className="ob-packet-row" key={p.id}><span className="ob-time">{p.time.toFixed(1)} s</span><span className="ob-route"><strong>{shortName(p.source)}</strong><i>→</i><strong>{p.target ? shortName(p.target) : 'all'}</strong></span><span className="ob-payload">{p.kind.replaceAll('_', ' ')}{p.cells !== null && <small>{p.cells} cells</small>}</span><span className={`ob-packet-state ${p.state}`}>{p.state === 'dropped' ? p.reason || 'dropped' : p.state}<i /></span></div>) : <div className="ob-no-packets">No matching messages yet.</div>}</div></section>}
    </main>
    {connectionPanel && <div className="ob-modal-shade" onClick={() => setConnectionPanel(false)}><section role="dialog" aria-modal="true" aria-label="ROS bridge connection" className="ob-connection-modal" onClick={e => e.stopPropagation()}><button className="ob-icon ob-close-dialog" onClick={() => setConnectionPanel(false)} aria-label="Close ROS connection"><Icon name="close" size={18} /></button><span className="ob-eyebrow">ROS CONNECTION</span><h2>Connect your swarm.</h2><p>Use your ROS bridge address or an existing SSH tunnel.</p><label>WebSocket address<input aria-label="ROS bridge URL" value={bridge} onChange={e => setBridge(e.target.value)} placeholder="ws://localhost:9090" /></label><p className="ob-connection-status" role="status">{bridgeFeedback || connection || 'disconnected'}</p><div><button className="ob-outline" onClick={() => { onDisconnect?.(); setBridgeFeedback(''); }}>Disconnect</button><button className="ob-primary" onClick={() => { try { onConnect?.(bridge); setBridgeFeedback(''); } catch (e) { setBridgeFeedback(e instanceof Error ? e.message : String(e)); } }}>Connect</button></div></section></div>}
  </div>;
}
