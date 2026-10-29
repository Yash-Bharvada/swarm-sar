import { useEffect } from 'react';
import { simClock, useSim } from '../store/simStore';
import { useAudio } from './audioStore';
import { EventSoundTracker } from './eventSounds';
import { soundscape } from './Soundscape';

/** One presentation-only observer. Neither audio nor its clocks write to the engine. */
export function AudioBridge() {
  useEffect(() => {
    const tracker = new EventSoundTracker();
    let previous = useSim.getState();
    const robotCue = (name: string | null, focus: boolean) => {
      const robot = useSim.getState().engine.robots.find((unit) => unit.name === name);
      if (robot) soundscape.play(robot.type === 'drone' ? focus ? 'focusDrone' : 'selectDrone' : focus ? 'focusRover' : 'selectRover');
    };
    const sample = () => {
      const state = useSim.getState();
      const time = performance.now() / 1000;
      const cues = tracker.read(state.engine, state.selected, time);
      if (state.engine !== previous.engine) {
        const oldCount = previous.engine.scenario.victims.length;
        const count = state.engine.scenario.victims.length;
        if (state.editingSurvivors && count !== oldCount) soundscape.play(count > oldCount ? 'place' : 'remove');
        else if (previous.status !== 'ready') soundscape.play('reset');
      } else if (state.status !== previous.status) {
        if (state.status === 'running') soundscape.play(previous.status === 'paused' ? 'resume' : 'launch');
        else if (state.status === 'paused') soundscape.play('pause');
      }
      if (state.encounter !== previous.encounter) {
        if (state.encounter && !state.encounter.automatic) soundscape.play('open');
        else if (!state.encounter && previous.encounter) soundscape.play('close');
      }
      if (state.focus && state.focus !== previous.focus) robotCue(state.focus.robot, true);
      else if (state.selected !== previous.selected && state.selected) robotCue(state.selected, state.following);
      else if (state.following && !previous.following) robotCue(state.selected, true);
      if (state.cameraRequest !== previous.cameraRequest && state.cameraRequest) soundscape.play(state.cameraRequest.action === 'zoomIn' || state.cameraRequest.action === 'zoomOut' ? 'zoom' : 'open');
      cues.forEach((cue, index) => soundscape.play(cue, index * 0.65));
      const { engine } = state;
      soundscape.updateVehicles(engine, engine.robots, engine.prevPositions, simClock.alpha, engine.scenario.width, engine.scenario.height, state.status === 'running', state.selected, state.following);
      soundscape.tickMusic();
      previous = state;
    };
    const uiClick = (event: MouseEvent) => {
      if (!(event.target instanceof Element)) return;
      if (event.target.closest('[data-audio="none"]')) return;
      const button = event.target.closest('button, summary');
      if (!button || button.matches(':disabled') || button.closest('.launch-button, .reset-wrap, .focus-button, .follow-button, .camera-tools, .fleet-card, .feed-event-button')) return;
      if (button.tagName === 'SUMMARY') soundscape.play(button.closest('details')?.open ? 'close' : 'open');
      else if (button.getAttribute('aria-label')?.startsWith('Close') || button.textContent?.includes('Done placing')) soundscape.play('close');
      else soundscape.play('ui');
    };
    const uiChange = (event: Event) => {
      if (!(event.target instanceof Element) || event.target.closest('[data-audio="none"]')) return;
      if (event.target.matches('select, input[type="checkbox"], input[type="range"]')) soundscape.play('toggle');
    };
    const visibility = () => {
      // Drain events while hidden so returning never unleashes a notification backlog.
      tracker.read(useSim.getState().engine, useSim.getState().selected, performance.now() / 1000);
      soundscape.visibility(document.hidden);
    };
    const unsubscribe = useAudio.subscribe(() => soundscape.applyLevels());
    const timer = window.setInterval(sample, 90);
    document.addEventListener('click', uiClick, true);
    document.addEventListener('change', uiChange, true);
    document.addEventListener('visibilitychange', visibility);
    sample();
    return () => {
      clearInterval(timer); unsubscribe();
      document.removeEventListener('click', uiClick, true);
      document.removeEventListener('change', uiChange, true);
      document.removeEventListener('visibilitychange', visibility);
      soundscape.dispose();
    };
  }, []);
  return null;
}
