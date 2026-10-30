import { useEffect, useRef } from 'react';
import { useSim } from '../store/simStore';
import { survivorStory } from '../presentation/survivorStories';

export function SurvivorEncounter() {
  const encounter = useSim((s) => s.encounter);
  const engine = useSim((s) => s.engine);
  const continueExploration = useSim((s) => s.continueExploration);
  const button = useRef<HTMLButtonElement>(null);
  useEffect(() => { if (encounter) button.current?.focus(); }, [encounter]);
  if (!encounter) return null;
  const victim = engine.discoveredSurvivors().find((v) => v.id === encounter.id);
  if (!victim) return null;
  const story = survivorStory(engine.scenario.seed, victim.id);
  return <div className="encounter-stage" onKeyDown={(event) => {
    if (event.key === 'Tab') { event.preventDefault(); button.current?.focus(); }
    if (event.key === 'Escape') event.stopPropagation();
  }}>
    <section className="encounter-card" role="dialog" aria-modal="true" aria-labelledby="encounter-heading" aria-describedby="encounter-story" data-audio="none">
      <div className="encounter-eyebrow" role="status">{encounter.automatic ? '✓ Survivor found' : 'A moment with a survivor'}<span>{engine.done ? 'Mission complete' : 'Exploration paused'}</span></div>
      <h2 id="encounter-heading">Meet {story.name} <small>Survivor {victim.id + 1}</small></h2>
      <p id="encounter-story">“{story.text}”</p>
      <div className="encounter-footer"><span>Location confirmed · ({victim.x}, {victim.y})<small>A little fictional conversation</small></span>
        <button ref={button} className="btn primary" onClick={continueExploration}>{engine.done && !useSim.getState().encounterQueue.length ? 'View mission report' : 'Continue exploration'} <span aria-hidden>→</span></button>
      </div>
    </section>
  </div>;
}
