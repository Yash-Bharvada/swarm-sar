import { useId, useRef, useState } from 'react';
import './evidence-gallery.css';

const PROOF_IMAGES = [
  {
    image: new URL('../../../docs/media/simulation-screenshots/03-gazebo-overview.png', import.meta.url).href,
    title: 'A world with real physics',
    caption: 'Gazebo · Ubuntu / ROS 2 run',
    description: 'The disaster-site world running in Gazebo on Ubuntu. This recorded ROS 2 run used one rover and two drones, with saved-policy inference. Captured 29 October 2026 UTC.',
    alt: 'Original Gazebo screenshot showing the disaster-site walls, rubble and robot simulation.',
  },
  {
    image: new URL('../../../docs/media/simulation-screenshots/10-rviz-progress.png', import.meta.url).href,
    title: 'A growing robot map',
    caption: 'RViz · recorded occupancy map',
    description: 'RViz shows the recorded run’s growing occupancy map: light space, dark obstacles and rover/drone labels. This is an original capture from 29 October 2026 UTC.',
    alt: 'Original RViz screenshot with a black-and-white occupancy map and rover and drone labels.',
  },
  {
    image: new URL('../../../docs/media/updates/observatory-map.png', import.meta.url).href,
    title: 'Each helper has its own view',
    caption: 'Browser · private knowledge',
    description: 'Our working browser observatory shows a selected drone’s private map, its route, battery and goal. This capture uses the browser heuristic and simulated poses. Recorded in the 31 October 2026 edition.',
    alt: 'Browser observatory showing four 3D robots, colored routes and a selected drone’s private map.',
  },
  {
    image: new URL('../../../docs/media/frontend/ppo-completed.png', import.meta.url).href,
    title: 'The learned policy in action',
    caption: 'Python PPO → 3D browser',
    description: 'The actual Python checkpoint drove this browser mission: all 4 people found in 94 steps, with 90.48% of the site explored. Development seed 10000, captured 29 October 2026 UTC. This is one reproduced example mission.',
    alt: 'Completed Python PPO browser mission showing four of four people found and 90 percent area explored.',
  },
];

const PROOF_SOURCES = [
  { title: 'Training review', file: 'ppo_754k_review.json', href: new URL('../../../models/ppo_754k/ppo_754k_review.json', import.meta.url).href },
  { title: 'Practice settings', file: 'training_definition.json', href: new URL('../../../models/ppo_754k/training_definition.json', import.meta.url).href },
  { title: 'Gazebo capture record', file: 'gazebo-capture-manifest.json', href: new URL('../../../docs/media/simulation-screenshots/capture-manifest.json', import.meta.url).href },
  { title: 'Ubuntu launch log', file: 'gazebo-run.log', href: new URL('../../../docs/media/simulation-screenshots/run.log', import.meta.url).href },
  { title: 'Browser capture record', file: 'browser-capture-manifest.json', href: new URL('../../../docs/media/frontend/capture-manifest.json', import.meta.url).href },
  { title: 'Observatory capture record', file: 'observatory-capture-manifest.json', href: new URL('../../../docs/media/updates/capture-manifest.json', import.meta.url).href },
];

type ProofImage = typeof PROOF_IMAGES[number];

export function EvidenceGallery({ compact = false }: { compact?: boolean }) {
  const [selected, setSelected] = useState<ProofImage | null>(null);
  const viewer = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  const images = compact ? PROOF_IMAGES.slice(0, 2) : PROOF_IMAGES;
  const openImage = (item: ProofImage) => {
    setSelected(item);
    if (!viewer.current?.open) viewer.current?.showModal();
  };

  return <section className={`ex-proof${compact ? ' ex-proof-compact' : ''}`} aria-label={compact ? 'Original Gazebo and RViz screenshots' : 'The engineering behind our robot story'}>
    <div className="ex-proof-intro">
      <span className="ex-proof-eyebrow">FROM OUR ACTUAL BUILD</span>
      {!compact && <><h3>A small team. A lot of building.</h3><p>We built the robots, their own little maps, messages that can arrive late or get lost, and a way to train and test them.</p></>}
    </div>
    <div className="ex-proof-grid">
      {images.map(item => <button type="button" className="ex-proof-shot" key={item.title} onClick={() => openImage(item)} aria-label={`Enlarge: ${item.title}`}>
        <span className="ex-proof-image"><img src={item.image} alt={item.alt} loading="lazy" /><span className="ex-proof-enlarge" aria-hidden="true">↗</span></span>
        <span className="ex-proof-shot-title">{item.title}</span><span className="ex-proof-caption">{item.caption}</span>
      </button>)}
    </div>
    {!compact && <>
      <div className="ex-proof-metrics" aria-label="Selected PPO development checkpoint results">
        <div><strong>753,664</strong><span>practice steps</span></div>
        <div><strong>88.8%</strong><span>mean development recall</span></div>
        <div><strong>16</strong><span>parallel practice workers</span></div>
      </div>
      <p className="ex-proof-provenance">Original project captures · Ubuntu / Gazebo / RViz: 29 Oct 2026 · Browser records: 29–31 Oct. Tap any image to see it in full.</p>
      <details className="ex-proof-details">
        <summary>Inside the build <span aria-hidden="true">+</span></summary>
        <div className="ex-proof-detail-content">
          <p>Separate rover and drone brains learn from rewards. Each robot uses its own observations. A Python-to-browser bridge lets us watch the learned policy in our 3D world; a separate ROS 2 workspace provides the physics simulation.</p>
          <dl className="ex-proof-settings">
            <div><dt>Practice batch</dt><dd>16,384 steps</dd></div>
            <div><dt>Learning rate</dt><dd>0.0001</dd></div>
            <div><dt>PPO update limit (clip)</dt><dd>0.2</dd></div>
            <div><dt>Memory size</dt><dd>256</dd></div>
            <div><dt>Mission budget</dt><dd>400 steps</dd></div>
          </dl>
          <p><strong>What 88.8% means:</strong> average survivor recall across the selected model’s development groups. It helps us check progress. Final test worlds are still sealed.</p>
          <p><strong>Still a tough puzzle:</strong> the large-maze group found 5 of 18 people, with 19.15% coverage. We keep this result visible so the next improvements have a clear target.</p>
          <p><strong>The next connection:</strong> the newer SLAM integration awaits Linux runtime validation. These recorded ROS 2 / Gazebo runs are a separate path from the browser’s Python PPO mission; they do not establish that newer integration end to end.</p>
          <div className="ex-proof-source-label">Explore the original records</div>
          <div className="ex-proof-downloads">{PROOF_SOURCES.map(source => <a key={source.file} href={source.href} download={source.file}>{source.title}<span aria-hidden="true"> ↓</span></a>)}</div>
        </div>
      </details>
    </>}
    <dialog ref={viewer} className="ex-proof-viewer" aria-labelledby={titleId} aria-describedby={descriptionId} onClose={() => setSelected(null)} onClick={event => { if (event.target === event.currentTarget) viewer.current?.close(); }}>
      <div className="ex-proof-viewer-content">
        <header><div><span className="ex-proof-eyebrow">ORIGINAL SCREENSHOT</span><h3 id={titleId}>{selected?.title}</h3></div><button type="button" autoFocus onClick={() => viewer.current?.close()} aria-label="Close screenshot">Close <span aria-hidden="true">×</span></button></header>
        {selected && <img src={selected.image} alt={selected.alt} />}
        <p id={descriptionId}>{selected?.description}</p>
      </div>
    </dialog>
  </section>;
}
