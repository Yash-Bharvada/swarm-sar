import { useEffect, useRef, useState } from 'react';
import { Icon, type IconName } from '../components/Icon';
import { useSim } from '../store/simStore';
import { ConceptVisual } from './ConceptVisual';
import { EvidenceGallery } from './EvidenceGallery';
import { STORY, useExplain } from './story';
import { createStoryEngine, storyOverlays } from './session';
import './observatory-tour.css';

const GAZEBO = new URL('../../../docs/media/simulation-screenshots/03-gazebo-overview.png', import.meta.url).href;
const RVIZ = [
  new URL('../../../docs/media/simulation-screenshots/02-rviz.png', import.meta.url).href,
  new URL('../../../docs/media/simulation-screenshots/04-rviz-progress.png', import.meta.url).href,
  new URL('../../../docs/media/simulation-screenshots/06-rviz-progress.png', import.meta.url).href,
  new URL('../../../docs/media/simulation-screenshots/08-rviz-progress.png', import.meta.url).href,
  new URL('../../../docs/media/simulation-screenshots/10-rviz-progress.png', import.meta.url).href,
];
const SYSTEM: { label: string; icon: IconName; text: string }[] = [
  { label: 'Sense', icon: 'focus', text: 'Our simulated eyes, heat, and sound sensors gather nearby clues.' },
  { label: 'Map', icon: 'map', text: 'Green tiles reveal sensed ground. Each robot keeps its own map.' },
  { label: 'Decide', icon: 'rover', text: 'The selected robot chooses a useful next place. Its route appears in the world.' },
  { label: 'Share', icon: 'signal', text: 'Links and moving packets show real messages in this browser simulation.' },
  { label: 'Search', icon: 'person', text: 'The team keeps exploring. Confirmed locations help people know where to look.' },
];

function RecordedScene({ rviz }: { rviz: boolean }) {
  const [frame, setFrame] = useState(0);
  const viewer = useRef<HTMLDialogElement>(null);
  const source = rviz ? RVIZ[frame] : GAZEBO;
  const title = rviz ? 'A map taking shape' : 'Our physics playground';
  const alt = rviz ? `Original RViz map capture ${frame + 1} of 5 from the recorded Ubuntu session` : 'Original Gazebo capture of our rover and drone disaster-site simulation on Ubuntu';
  return <div className="ex-recorded">
    <div className="ex-window-bar"><span className="ex-window-dots"><i /><i /><i /></span><span>UBUNTU · ROS 2 · {rviz ? 'RVIZ' : 'GAZEBO'}</span><span className="ex-record-label">RECORDED</span></div>
    <button className="ex-recorded-image" onClick={() => viewer.current?.showModal()} aria-label={`Enlarge ${rviz ? 'RViz map' : 'Gazebo screenshot'}`}><img src={source} alt={alt} /><span>Original screenshot <Icon name="plus" size={14} /></span></button>
    <div className="ex-recorded-caption"><strong>{title}</strong><span>1 rover + 2 drones · 29 Oct 2026 UTC</span></div>
    {rviz && <label className="ex-map-timeline"><span>Earlier map</span><input type="range" min="0" max="4" step="1" value={frame} onChange={(e) => setFrame(Number(e.target.value))} aria-label="Recorded RViz map progress" /><span>Later map</span><small>Recorded state {frame + 1} of 5 · drag to compare</small></label>}
    <p>Actual project capture. The ROS physics workflow runs separately from this browser world.</p>
    <dialog ref={viewer} className="ex-proof-viewer" aria-label={title}>
      <div className="ex-proof-viewer-content"><header><h3>{title}</h3><button autoFocus onClick={() => viewer.current?.close()}>Close screenshot <Icon name="close" size={16} /></button></header><img src={source} alt={alt} /><p>Original Ubuntu host capture · 29 October 2026 UTC · one rover and two drones. These are recorded simulator states.</p></div>
    </dialog>
  </div>;
}

export function ExplainMode({ onExit, onOpenObservatory }: { onExit: () => void; onOpenObservatory?: () => void }) {
  const { beat, setBeat, systemPart, setSystemPart } = useExplain();
  const current = STORY[beat];
  const [auto, setAuto] = useState(false);
  const [paused, setPaused] = useState(false);
  const [narrate, setNarrate] = useState(false);
  const [voiceReady, setVoiceReady] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const pane = useRef<HTMLDivElement>(null);
  const chapters = useRef<HTMLDetailsElement>(null);
  const utterance = useRef<SpeechSynthesisUtterance | null>(null);
  const cue = current.cue;
  const recorded = cue === 'gazebo' || cue === 'rviz';
  const last = beat === STORY.length - 1;
  const move = (next: number) => { setBeat(next); chapters.current?.removeAttribute('open'); };

  useEffect(() => {
    const state = useSim.getState();
    if (cue === 'system' || (['world', 'cooperation', 'communication'].includes(cue) && state.engine.done)) {
      useSim.setState({ engine: createStoryEngine(), selected: null, focus: null, following: false, cameraRequest: null });
    }
    const engine = useSim.getState().engine;
    const robot = engine.robots.find((r) => r.type === (cue === 'drone' ? 'drone' : 'rover'));
    useSim.setState({ overlays: storyOverlays(cue), selected: null, focus: null, following: false });
    if (['rover', 'drone', 'slam', 'learning'].includes(cue) && robot) state.focusOn(robot.name);
    else { if (cue === 'cooperation' && robot) state.select(robot.name); state.moveCamera('reset'); }
    pane.current?.scrollTo({ top: 0 });
    heading.current?.focus({ preventScroll: true });
  }, [cue]);

  useEffect(() => {
    const running = ['world', 'cooperation', 'communication', 'system'].includes(cue) && !paused;
    useSim.setState({ status: useSim.getState().engine.done ? 'complete' : running ? 'running' : 'paused' });
  }, [cue, paused]);

  useEffect(() => {
    if (cue !== 'system') return;
    const state = useSim.getState();
    state.select(systemPart === 3 || systemPart === 4 ? null : state.engine.robots[0]?.name ?? null);
    useSim.setState({ overlays: storyOverlays(cue, systemPart) });
    state.moveCamera('reset');
  }, [cue, systemPart]);

  useEffect(() => {
    if (!auto || paused || last) return;
    const timer = window.setTimeout(() => setBeat(beat + 1), 45000);
    return () => window.clearTimeout(timer);
  }, [auto, paused, last, beat, setBeat]);

  useEffect(() => { setVoiceReady('speechSynthesis' in window && 'SpeechSynthesisUtterance' in window); }, []);
  useEffect(() => {
    if (!voiceReady || !narrate) return;
    const spoken = new SpeechSynthesisUtterance(`${current.title} ${current.story} ${current.takeaway} What we built. ${current.built}`);
    spoken.lang = 'en'; spoken.rate = 0.94;
    utterance.current = spoken;
    window.speechSynthesis.speak(spoken);
    return () => { if (utterance.current === spoken) { window.speechSynthesis.cancel(); utterance.current = null; } };
  }, [current, voiceReady, narrate]);
  useEffect(() => {
    if (!voiceReady || !narrate) return;
    if (paused) window.speechSynthesis.pause(); else window.speechSynthesis.resume();
  }, [paused, narrate, voiceReady, current]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || (event.target as HTMLElement)?.closest('input, select, textarea') || document.querySelector('dialog[open]')) return;
      if (event.code === 'Escape') { event.preventDefault(); onExit(); }
      else if (event.code === 'ArrowRight') { event.preventDefault(); move(beat + 1); }
      else if (event.code === 'ArrowLeft') { event.preventDefault(); move(beat - 1); }
      else if (event.code === 'Space' && !(event.target as HTMLElement)?.closest('button, summary')) { event.preventDefault(); setPaused((value) => !value); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  return <section className={`ex-mode ${paused ? 'ex-paused' : ''} ${recorded ? 'ex-has-recording' : ''} ${cue === 'proof' ? 'ex-has-proof' : ''}`} aria-label="Interactive robot story">
    <header className="ex-header">
      <div className="ex-brand"><Icon name="swarm" size={25} /><strong>swarm</strong><span /><small>A little rescue story</small></div>
      <div className="ex-header-actions">
        <button className="ex-icon-control ex-read" disabled={!voiceReady} aria-pressed={narrate} onClick={() => setNarrate(!narrate)} title={voiceReady ? 'Read the story aloud using your browser’s voice' : 'Browser narration is unavailable'}><Icon name={narrate ? 'volume' : 'book'} size={16} /><span>{narrate ? 'Voice on' : 'Read aloud'}</span></button>
        <button className="ex-exit" onClick={onExit}>Back to mission <Icon name="close" size={15} /></button>
      </div>
    </header>

    <div className="ex-story-pane" ref={pane}>
      <details className="ex-chapters" ref={chapters}><summary><span className="ex-chapter-number">{String(current.chapter).padStart(2, '0')}</span><span>{current.chapterName}</span><Icon name="chevron" size={13} /></summary>
        <nav aria-label="Story chapters">{STORY.filter((item, index) => index === 0 || STORY[index - 1].chapter !== item.chapter).map((item) => <button key={item.chapter} aria-current={item.chapter === current.chapter ? 'step' : undefined} onClick={() => move(STORY.indexOf(item))}><span>{String(item.chapter).padStart(2, '0')}</span>{item.chapterName}<Icon name={item.chapter < current.chapter ? 'check' : 'chevron'} size={13} /></button>)}</nav>
      </details>
      <article key={beat} className="ex-story-content">
        <div className="ex-eyebrow">{current.eyebrow}</div>
        <h1 ref={heading} tabIndex={-1}>{current.title}</h1>
        <p className="ex-story">{current.story}</p>
        {cue === 'world' && <details className="ex-tech ex-mission-modes"><summary><Icon name="settings" size={14} /><span>Choose how the team moves</span><Icon name="plus" size={13} /></summary><dl><dt>Auto</dt><dd>Each helper chooses its own next move.</dd><dt>Manual</dt><dd>You drive a selected robot while the others wait.</dd><dt>Mixed</dt><dd>You drive one helper while the others explore.</dd><dt>Saved PPO policy</dt><dd>The Python service runs the trained policy and sends its mission to this 3D view.</dd></dl></details>}
        <div className="ex-takeaway"><span className="ex-takeaway-mark" /><p>{current.takeaway}</p></div>
        {current.visual && <ConceptVisual key={cue} kind={current.visual} />}
        {(cue === 'rover' || cue === 'drone') && <div className="ex-robot-facts"><span><Icon name="focus" size={15} />{cue === 'rover' ? 'Careful close-up explorer' : 'Wider-looking scout'}</span><span><Icon name="activity" size={15} />Heat + sound clues</span><span><i className="ex-battery" />{cue === 'rover' ? '300' : '240'} energy units</span><small>Simulation values · Guided sandbox energy is unlimited so you can take your time.</small></div>}
        {cue === 'ros' && <div className="ex-ros-chain" aria-label="Example ROS message journey">{[{ icon: 'focus', label: 'Sense' }, { icon: 'map', label: 'Make a map' }, { icon: 'rover', label: 'Move' }].map((part, index) => <div key={part.label}><span><Icon name={part.icon as IconName} size={22} />{part.label}</span>{index < 2 && <i aria-hidden="true">→</i>}</div>)}<small>Inside the robot · ROS 2 carries the messages</small></div>}
        {cue === 'system' && <div className="ex-system"><div role="group" aria-label="Reveal a part of the complete system">{SYSTEM.map((part, index) => <button key={part.label} aria-pressed={systemPart === index} onClick={() => setSystemPart(index)}><Icon name={part.icon} size={18} /><span>{part.label}</span></button>)}</div><p aria-live="polite">{SYSTEM[systemPart].text}</p></div>}
        <div className="ex-built"><span><Icon name="check" size={13} />WHAT WE BUILT</span><p>{current.built}</p></div>
        {['world', 'communication', 'gnn', 'system'].includes(cue) && onOpenObservatory && <div className="ex-workspace-tours"><button onClick={onOpenObservatory}>Tour the map, network & GNN workspace <Icon name="chevron" size={13} /></button><a href="/?mode=ros&explain=1" target="_blank" rel="noopener noreferrer">Tour ROS / SLAM <span aria-hidden="true">↗</span></a></div>}
        {['ros', 'slam', 'gazebo', 'rviz'].includes(cue) && <div className="ex-workspace-tours"><a href="/?mode=ros&explain=1" target="_blank" rel="noopener noreferrer">Explore the actual ROS / SLAM workspace <span aria-hidden="true">↗</span></a></div>}
        <details className="ex-tech" key={`tech-${beat}`}><summary><Icon name="layers" size={14} /><span>{current.technology}</span><Icon name="plus" size={13} /></summary><p>{current.technical}</p></details>
      </article>
    </div>

    <div className={`ex-world-note ${recorded || cue === 'proof' ? 'ex-note-recorded' : ''}`}><span className="ex-live-dot" />{recorded ? 'ORIGINAL PROJECT CAPTURE' : cue === 'proof' ? 'THE ENGINEERING BEHIND THE STORY' : 'OUR EXISTING 3D WORLD'}<span className="ex-world-note-sub">{recorded || cue === 'proof' ? 'Evidence you can explore' : 'Live guided sandbox'}</span></div>
    <div className="ex-scene-tools" aria-label="Guided scene controls"><button onClick={() => useSim.getState().moveCamera('reset')} title="See the whole world" aria-label="Fit story world"><Icon name="orbit" size={17} /></button><button onClick={() => useSim.getState().moveCamera('top')} title="Look from above" aria-label="Story top-down view"><Icon name="top" size={17} /></button><button onClick={() => useSim.getState().moveCamera('zoomIn')} title="Look closer" aria-label="Zoom into story world"><Icon name="plus" size={17} /></button></div>

    {recorded && <div className="ex-recorded-stage"><RecordedScene key={cue} rviz={cue === 'rviz'} /></div>}
    {cue === 'proof' && <div className="ex-proof-stage"><EvidenceGallery /></div>}
    <div className="ex-scene-caption"><Icon name={recorded || cue === 'proof' ? 'book' : 'mouse'} size={14} /><span>{current.sceneCaption}</span></div>

    <footer className="ex-footer">
      <div className="ex-play-controls"><button onClick={() => setPaused(!paused)} aria-label={paused ? 'Resume story animations' : 'Pause story animations'} title="Pause or resume (Space)"><Icon name={paused ? 'play' : 'pause'} size={16} /></button><button className="ex-auto" aria-pressed={auto} onClick={() => setAuto(!auto)}>Auto <span className={auto ? 'on' : ''} /></button></div>
      <div className="ex-progress"><div className="ex-progress-heading"><span>{String(beat + 1).padStart(2, '0')} <i>/ {STORY.length}</i></span><small>{paused ? 'Story paused' : auto && !last ? 'Auto · 45 seconds per scene' : 'Take your time. Explore at your own pace.'}</small></div><div className="ex-progress-steps" aria-label="Story progress">{STORY.map((item, index) => <button key={item.cue} aria-label={`Scene ${index + 1}: ${item.technology}`} aria-current={index === beat ? 'step' : undefined} className={index <= beat ? 'visited' : ''} onClick={() => move(index)}><i /></button>)}</div></div>
      <div className="ex-navigation"><button className="ex-back" disabled={beat === 0} onClick={() => move(beat - 1)}><Icon name="chevron" size={14} />Back</button><button className="ex-next" onClick={() => last ? onExit() : move(beat + 1)}>{last ? 'Explore your mission' : beat === 0 ? 'Meet the team' : 'Continue'}<Icon name="chevron" size={15} /></button></div>
    </footer>
  </section>;
}
