import { CONCEPT_STEPS, type ConceptGraph } from './gnnConcept';
import { useState } from 'react';

const name = (id: string) => id.replace('rover_', 'Rover ').replace('drone_', 'Drone ');

export function GNNConceptPanel({ graph, step, score, playing, frozen, onScore, onStep, onPlaying }: {
  graph: ConceptGraph; step: number; score: number; playing: boolean; frozen: boolean;
  onScore: (value: number) => void; onStep: (value: number) => void; onPlaying: (value: boolean) => void;
}) {
  const [compact, setCompact] = useState(() => typeof matchMedia !== 'undefined' && matchMedia('(max-width: 760px)').matches);
  return <aside className={`ob-gnn-panel ${compact ? 'is-compact' : ''}`} aria-label="GNN concept demonstration">
    <div className="ob-gnn-badge">GNN ARCHITECTURE · INTERACTIVE WALKTHROUGH</div>
    <h2>How a GNN connects the swarm</h2>
    <button className="ob-gnn-collapse" aria-expanded={!compact} onClick={() => setCompact(!compact)}>{compact ? 'Show explanation' : 'Hide explanation'}</button>
    {!compact && <>
    <p>Explore message passing, attention, and aggregation using this mission’s robot labels. Connections and scores are examples; live decisions use the selected mission controller.</p>
    <ol className="ob-gnn-steps">{CONCEPT_STEPS.map((phase, i) => <li key={phase.title}><button aria-current={step === i ? 'step' : undefined} onClick={() => onStep(i)}><span>{i + 1}</span>{phase.title}</button></li>)}</ol>
    <div className="ob-gnn-explanation" role="status"><b>{CONCEPT_STEPS[step].title}</b><p>{CONCEPT_STEPS[step].detail}</p></div>
    <div className="ob-gnn-receiver">Example receiver <strong>{graph.receiver ? name(graph.receiver) : 'No agents'}</strong><small>Select another robot to rebuild its local graph.</small></div>
    {step >= 2 && <div className="ob-gnn-weights">
      <label>Example score · {graph.edges[0] ? name(graph.edges[0].source) : 'no peer'}<input aria-label="Example message score" type="range" min="-4" max="4" step=".25" value={score} disabled={!graph.edges.length} onChange={e => onScore(Number(e.target.value))} /></label>
      <span className="ob-gnn-weight-caption">Illustrative attention · includes self</span>
      {[{ source: 'Self', weight: graph.selfWeight }, ...graph.edges].map(edge => <div className="ob-gnn-weight" key={edge.source}><span>{edge.source === 'Self' ? 'Self' : name(edge.source)}</span><meter aria-label={`Example attention ${edge.source}`} min={0} max={1} value={edge.weight} /><b>{(edge.weight * 100).toFixed(1)}%</b></div>)}
      <small>These percentages are calculated from the example scores above.</small>
    </div>}
    </>}
    {compact && <div className="ob-gnn-explanation"><b>{step + 1}. {CONCEPT_STEPS[step].title}</b><p>Explore the architecture with mission robot labels and adjustable example weights.</p></div>}
    <div className="ob-gnn-controls"><button className="ob-outline" disabled={frozen} onClick={() => onPlaying(!playing)}>{playing ? 'Pause illustration' : 'Play illustration'}</button><button className="ob-primary" onClick={() => onStep((step + 1) % CONCEPT_STEPS.length)}>Next step</button></div>
    <small className="ob-gnn-note">Illustration playback is independent of mission playback. Actual packets remain in Messages.</small>
  </aside>;
}
