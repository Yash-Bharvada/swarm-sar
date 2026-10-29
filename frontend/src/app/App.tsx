import { useEffect, useState } from 'react';
import { TopBar } from '../components/TopBar';
import { LeftPanel } from '../components/LeftPanel';
import { RightPanel } from '../components/RightPanel';
import { EventFeed } from '../components/EventFeed';
import { SceneHud } from '../components/SceneHud';
import { SceneRoot } from '../scene/SceneRoot';
import { useSim } from '../store/simStore';
import { Icon, type IconName } from '../components/Icon';

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
      if (e.code === 'Escape') { useSim.getState().select(null); return; }
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      if (target?.closest('input, select, textarea, [contenteditable="true"]')) return;
      if (e.code === 'Space' && target?.closest('button')) return;
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
  useEffect(() => { if (selected) setPanel('fleet'); }, [selected]);
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
    <div className="app">
      <TopBar />
      <nav className="command-rail" aria-label="Workspace">
        <div className="rail-navigation">
          {items.map((item) => <button key={item.label} className={`rail-button ${panel === item.panel ? 'active' : ''}`} onClick={() => setPanel(panel === item.panel ? null : item.panel)} aria-label={item.label === 'World' ? 'World overview' : `Open ${item.label.toLowerCase()} panel`} aria-pressed={panel === item.panel} title={item.label}><Icon name={item.icon} /><span>{item.label}</span></button>)}
        </div>
        <button className={`rail-button ${panel === 'help' ? 'active' : ''}`} onClick={() => setPanel(panel === 'help' ? null : 'help')} aria-label="Open controls guide" aria-pressed={panel === 'help'}><Icon name="help" /><span>Controls</span></button>
        <div className="rail-version">LOCAL</div>
      </nav>
      <main className={`workspace ${panel ? 'has-panel' : ''}`}>
        <section className="stage" aria-label="Interactive simulation world">
          <SceneRoot />
          <SceneHud onOpenPanel={setPanel} />
        </section>
        {panel && <aside className="workspace-drawer" aria-label={`${panel} panel`}>
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
    <dl className="shortcut-list"><dt>Launch / pause</dt><dd><kbd>Space</kbd></dd><dt>Inspect robot</dt><dd>Click a robot</dd><dt>Close / deselect</dt><dd><kbd>Esc</kbd></dd></dl>
    <details className="disclosure"><summary>Manual driving</summary><p className="explain">Choose Manual or Mixed in Mission settings, then select a robot. Click a walkable tile to set a waypoint.</p><dl className="shortcut-list"><dt>Move</dt><dd><kbd>W</kbd><kbd>A</kbd><kbd>S</kbd><kbd>D</kbd> or arrows</dd><dt>Scan</dt><dd><kbd>E</kbd></dd><dt>Stop</dt><dd><kbd>X</kbd></dd></dl></details>
    <p className="guide-note"><Icon name="layers" size={18} />Use Layers to reveal paths, radio links, or the robots’ explored map.</p>
  </div>;
}
