import { useEffect, useRef, useState } from 'react';
import { Icon } from '../components/Icon';
import { EvidenceGallery } from './EvidenceGallery';
import type { ObservatoryTourStep } from './observatoryTourSteps';
import './observatory-tour.css';

export function ObservatoryTour({ steps, index, source, hasData, onStep, onClose, onConnect }: {
  steps: ObservatoryTourStep[]; index: number; source: 'browser' | 'ros'; hasData: boolean;
  onStep: (step: number) => void; onClose: () => void; onConnect: () => void;
}) {
  const step = steps[index];
  const heading = useRef<HTMLHeadingElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const [narrate, setNarrate] = useState(false);
  const voice = 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;
  useEffect(() => { heading.current?.focus({ preventScroll: true }); content.current?.scrollTo(0, 0); }, [index]);
  useEffect(() => {
    if (!narrate || !voice) return;
    const message = new SpeechSynthesisUtterance(`${step.title} ${step.story} What we built. ${step.built} ${step.tryIt}`);
    message.rate = .94; message.lang = 'en'; window.speechSynthesis.speak(message);
    return () => window.speechSynthesis.cancel();
  }, [narrate, voice, step]);
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey || document.querySelector('dialog[open], .ob-modal-shade') || (event.target as HTMLElement)?.closest('input, select, textarea')) return;
      if (event.key === 'Escape') { event.preventDefault(); onClose(); }
      else if (event.key === 'ArrowRight') { event.preventDefault(); onStep(Math.min(index + 1, steps.length - 1)); }
      else if (event.key === 'ArrowLeft') { event.preventDefault(); onStep(Math.max(0, index - 1)); }
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  });
  return <aside className="ob-tour-panel" aria-label={`${source === 'ros' ? 'ROS / SLAM' : 'Observatory'} guided tour`}>
    <header><span>EXPLAIN MODE · {source === 'ros' ? 'ROS / SLAM' : 'INTELLIGENCE'}</span><button onClick={onClose} aria-label="Close observatory tour"><Icon name="close" size={17} /></button></header>
    <div className="ob-tour-content" ref={content}>
      <label className="ob-tour-scene-picker"><span>Explore a scene</span><select aria-label="Observatory tour scene" value={index} onChange={event => onStep(Number(event.target.value))}>{steps.map((item, i) => <option value={i} key={item.id}>{String(i + 1).padStart(2, '0')} · {item.title}</option>)}</select></label>
      <article key={step.id}><h2 ref={heading} tabIndex={-1}>{step.title}</h2><p className="ob-tour-story">{step.story}</p><div className="ob-tour-built"><span><Icon name="check" size={13} />WHAT WE BUILT</span><p>{step.built}</p></div><p className="ob-tour-try"><Icon name="mouse" size={15} /><span>{step.tryIt}</span></p></article>
      {source === 'ros' && !hasData && <div className="ob-tour-offline"><Icon name="signal" size={15} /><span>The ROS workspace is waiting for a host. You can still follow this tour and inspect our original recorded captures.</span></div>}
      {step.id === 'connection' && <button className="ob-primary ob-tour-connect" onClick={onConnect}><Icon name="signal" size={15} />Open connection settings</button>}
      {(step.evidence || (source === 'ros' && !hasData && ['map', 'shared-map'].includes(step.id))) && <EvidenceGallery compact />}
      {step.evidence && <a className="ob-tour-other-source" href={`/?mode=${source === 'ros' ? 'observatory' : 'ros'}&explain=1`} target="_blank" rel="noopener noreferrer">Tour {source === 'ros' ? 'the browser mission' : 'ROS / SLAM'} <span aria-hidden="true">↗</span></a>}
    </div>
    <footer><div className="ob-tour-status"><span>{index + 1} / {steps.length}</span><button disabled={!voice} aria-pressed={narrate} onClick={() => setNarrate(!narrate)}><Icon name={narrate ? 'volume' : 'book'} size={13} />{narrate ? 'Voice on' : 'Read aloud'}</button></div><div className="ob-tour-nav"><button className="ob-outline" disabled={index === 0} onClick={() => onStep(index - 1)}>Back</button><button className="ob-primary" onClick={() => index === steps.length - 1 ? onClose() : onStep(index + 1)}>{index === steps.length - 1 ? 'Return to workspace' : 'Continue'}<Icon name="chevron" size={13} /></button></div></footer>
  </aside>;
}
