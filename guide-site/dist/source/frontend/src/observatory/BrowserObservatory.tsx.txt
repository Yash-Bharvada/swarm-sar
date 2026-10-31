import { useEffect } from 'react';
import { useBrowserObservatory } from './useObservatory';
import { ObservatoryPage } from './ObservatoryPage';
import { simClock, TICKS_PER_SECOND, useSim } from '../store/simStore';

/** Runs only while the world canvas/its SimDriver is unmounted. PPO has its own bridge. */
function useObservatoryDriver() {
  const engine = useSim(s => s.engine);
  useEffect(() => {
    let previous = performance.now(), accumulator = 0, frame = 0;
    const tick = (now: number) => {
      const dt = Math.min(.1, Math.max(0, (now - previous) / 1000)); previous = now;
      const s = useSim.getState();
      if (s.controllerMode !== 'ppo' && s.status === 'running') {
        accumulator += dt * s.settings.speed;
        const ticks = Math.min(8, Math.floor(accumulator * TICKS_PER_SECOND));
        if (ticks) { accumulator -= ticks / TICKS_PER_SECOND; s.advance(ticks); }
        if (useSim.getState().encounter) accumulator = 0;
        simClock.alpha = Math.min(1, accumulator * TICKS_PER_SECOND);
      } else { accumulator = 0; simClock.alpha = 1; }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [engine]);
}

export function BrowserObservatory({ onBack }: { onBack: () => void }) {
  const snapshot = useBrowserObservatory();
  const status = useSim(s => s.status), encounter = useSim(s => s.encounter);
  useObservatoryDriver();
  return <ObservatoryPage snapshot={snapshot} onBack={onBack} missionStatus={status} encounter={!!encounter}
    onContinue={() => useSim.getState().continueExploration()}
    onToggleMission={() => { const s = useSim.getState(); if (s.status === 'ready') s.launch(); else if (s.status === 'running') s.pause(); else if (s.status === 'paused') s.resume(); }} />;
}
