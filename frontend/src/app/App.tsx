import { useEffect } from 'react';
import { TopBar } from '../components/TopBar';
import { LeftPanel } from '../components/LeftPanel';
import { RightPanel } from '../components/RightPanel';
import { EventFeed } from '../components/EventFeed';
import { SceneHud } from '../components/SceneHud';
import { SceneRoot } from '../scene/SceneRoot';
import { useSim } from '../store/simStore';

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
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'SELECT' || target.tagName === 'TEXTAREA')) return;
      const { status, selected, engine, settings, issue, pause, resume, launch, select } = useSim.getState();
      if (e.code === 'Space') {
        e.preventDefault();
        if (status === 'running') pause();
        else if (status === 'paused') resume();
        else if (status === 'ready') launch();
        return;
      }
      if (e.code === 'Escape') {
        select(null);
        return;
      }
      const robot = selected ? engine.robots.find((r) => r.name === selected) : null;
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
  return (
    <div className="app">
      <TopBar />
      <LeftPanel />
      <main className="stage">
        <SceneRoot />
        <SceneHud />
      </main>
      <RightPanel />
      <EventFeed />
    </div>
  );
}
