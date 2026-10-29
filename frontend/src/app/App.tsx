import { useEffect, useState } from 'react';
import { TopBar } from '../components/TopBar';
import { LeftPanel } from '../components/LeftPanel';
import { RightPanel } from '../components/RightPanel';
import { EventFeed } from '../components/EventFeed';
import { SceneHud } from '../components/SceneHud';
import { SceneRoot } from '../scene/SceneRoot';
import { useSim } from '../store/simStore';
import { Icon, type IconName } from '../components/Icon';
import { SurvivorEncounter } from '../components/SurvivorEncounter';
import { PPOBridge } from '../ppo/PPOBridge';
import { AudioBridge } from '../audio/AudioBridge';
import { soundscape } from '../audio/Soundscape';

export type Panel = 'setup' | 'fleet' | 'activity' | 'help' | null;

const KEY_DIRECTIONS: Record<string, number> = {
  ArrowUp: 1,
  KeyW: 1,
  ArrowDown: 2,
  KeyS: 2,
  ArrowLeft: 3,
  KeyA: 3,
  ArrowRight: 4,
  KeyD: 4,
};

function useKeyboard() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (useSim.getState().encounter && e.code !== 'KeyM') {
        if (e.code === 'Space' && !(e.target as HTMLElement)?.closest('button')) e.preventDefault();
        return;
      }
      if (e.code === 'Escape') {
        const state = useSim.getState();
        if (state.cleanView) state.toggleCleanView();
        else if (state.editingSurvivors) state.setEditingSurvivors(false);
        else state.select(null);
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      if (e.code === 'KeyM' && !target?.closest('input:not([type="range"]):not([type="checkbox"]), select, textarea, [contenteditable="true"]')) {
        e.preventDefault();
        if (!e.repeat) soundscape.toggleMute();
        return;
      }
      if (target?.closest('input, select, textarea, [contenteditable="true"]')) return;
      if (e.code === 'Space' && target?.closest('button')) return;
      if (e.code === 'KeyH') { e.preventDefault(); if (!e.repeat) useSim.getState().toggleCleanView(); return; }
      const { status, selected, engine, settings, issue, pause, resume, launch } = useSim.getState();
      if (e.code === 'Space') {
        e.preventDefault();
        if (e.repeat) return;
        if (status === 'running') pause();
        else if (status === 'paused') resume();
        else if (status === 'ready') launch();
        return;
      }
      const robot = selected ? engine.robots.find((r) => r.name === selected) : null;
      if (e.code === 'Equal' || e.code === 'NumpadAdd') { e.preventDefault(); useSim.getState().moveCamera('zoomIn'); return; }
      if (e.code === 'Minus' || e.code === 'NumpadSubtract') { e.preventDefault(); useSim.getState().moveCamera('zoomOut'); return; }
      if (e.code === 'KeyR') { useSim.getState().moveCamera('reset'); return; }
      if (e.code === 'KeyF' && selected) { useSim.getState().focusOn(selected); return; }
      if (!robot || settings.mode === 'autonomous' || !robot.manual) return;
      const direction = KEY_DIRECTIONS[e.code];
      if (direction) {
        e.preventDefault();
        issue({ kind: 'manualStep', robot: robot.name, direction });
      } else if (e.code === 'KeyE') issue({ kind: 'manualScan', robot: robot.name });
      else if (e.code === 'KeyX') issue({ kind: 'manualStop', robot: robot.name });
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
}

export function App() {
  useKeyboard();
  const [panel, setPanel] = useState<Panel>(null);
  const selected = useSim((s) => s.selected);
  const cleanView = useSim((s) => s.cleanView);
  const encounter = useSim((s) => s.encounter);
  const editingSurvivors = useSim((s) => s.editingSurvivors);
  const toggleCleanView = useSim((s) => s.toggleCleanView);
  useEffect(() => { if (encounter) setPanel(null); }, [encounter]);
  useEffect(() => { if (selected) setPanel('fleet'); }, [selected]);
  useEffect(() => { if (editingSurvivors || cleanView) setPanel(null); }, [editingSurvivors, cleanView]);
  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.code === 'Escape') setPanel(null); };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, []);
  const items: { panel: Panel; label: string; icon: IconName }[] = [
    { panel: null, label: 'World', icon: 'orbit' },
    { panel: 'setup', label: 'Mission', icon: 'settings' },
    { panel: 'fleet', label: 'Fleet', icon: 'fleet' },
    { panel: 'activity', label: 'Activity', icon: 'activity' },
  ];
  return (
    <div className={`app ${cleanView ? 'clean-view' : ''}`}>
      <AudioBridge />
      <PPOBridge />
      {!cleanView && <TopBar />}
      {!cleanView && <nav className="command-rail" aria-label="Workspace">
        <div className="rail-navigation">
          {items.map((item) => <button key={item.label} className={`rail-button ${panel === item.panel ? 'active' : ''}`} onClick={() => setPanel(panel === item.panel ? null : item.panel)} aria-label={item.label === 'World' ? 'World overview' : `Open ${item.label.toLowerCase()} panel`} aria-pressed={panel === item.panel} title={item.label}><Icon name={item.icon} /><span>{item.label}</span></button>)}
        </div>
        <button className={`rail-button ${panel === 'help' ? 'active' : ''}`} onClick={() => setPanel(panel === 'help' ? null : 'help')} aria-label="Open controls guide" aria-pressed={panel === 'help'}><Icon name="help" /><span>Controls</span></button>
        <div className="rail-version">LOCAL</div>
      </nav>}
      <main className={`workspace ${panel && !cleanView ? 'has-panel' : ''}`}>
        <section className="stage" aria-label="Interactive simulation world">
          <SceneRoot />
          <SurvivorEncounter />
          {!cleanView && !encounter && <SceneHud onOpenPanel={setPanel} />}
          {cleanView && <button className="restore-interface" onClick={toggleCleanView} aria-label="Show interface" title="Show interface (H or Esc)"><Icon name="overview" size={17} /><span>Show interface <kbd>H</kbd></span></button>}
        </section>
        {panel && !cleanView && <aside className="workspace-drawer" aria-label={`${panel} panel`}>
          <button className="drawer-close icon-button" aria-label="Close panel" title="Close panel (Esc)" onClick={() => setPanel(null)}><Icon name="close" size={18} /></button>
          {panel === 'setup' && <LeftPanel />}
          {panel === 'fleet' && <RightPanel />}
          {panel === 'activity' && <EventFeed />}
          {panel === 'help' && <ControlsGuide />}
        </aside>}
      </main>
    </div>
  );
}

function ControlsGuide() {
  return <div className="panel controls-guide">
    <div className="panel-eyebrow">MAKE YOURSELF AT HOME</div>
    <h2 className="panel-title">Explore the world</h2>
    <p className="panel-intro">A few simple controls. Everything else is in your hands.</p>
    <div className="guide-illustration"><Icon name="mouse" size={48} /></div>
    <h3>Move your camera</h3>
    <dl className="shortcut-list"><dt>Orbit</dt><dd>Left mouse drag</dd><dt>Pan</dt><dd>Right mouse drag</dd><dt>Zoom at cursor</dt><dd>Scroll or <kbd>+</kbd> <kbd>−</kbd></dd><dt>Overview</dt><dd><kbd>R</kbd></dd><dt>Focus robot</dt><dd>Select, then <kbd>F</kbd></dd></dl>
    <h3>Run your mission</h3>
    <dl className="shortcut-list"><dt>Launch / pause</dt><dd><kbd>Space</kbd></dd><dt>Inspect robot</dt><dd>Click a robot</dd><dt>Mute / enable sound</dt><dd><kbd>M</kbd></dd><dt>Watch maze / UI</dt><dd><kbd>H</kbd></dd><dt>Close / restore</dt><dd><kbd>Esc</kbd></dd></dl>
    <details className="disclosure"><summary>Manual driving</summary><p className="explain">Choose Manual or Mixed in Mission settings, then select a robot. Click a walkable tile to set a waypoint.</p><dl className="shortcut-list"><dt>Move</dt><dd><kbd>W</kbd><kbd>A</kbd><kbd>S</kbd><kbd>D</kbd> or arrows</dd><dt>Scan</dt><dd><kbd>E</kbd></dd><dt>Stop</dt><dd><kbd>X</kbd></dd></dl></details>
    <p className="guide-note"><Icon name="layers" size={18} />Use Layers to reveal paths, radio links, or the robots’ explored map.</p>
  </div>;
}
