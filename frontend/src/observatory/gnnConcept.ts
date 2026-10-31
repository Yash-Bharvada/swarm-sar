/** Teaching-only graph. Scores are authored examples, never inference telemetry. */
export const CONCEPT_STEPS = [
  { title: 'Build a local graph', detail: 'One receiver and its example neighbors become graph nodes.' },
  { title: 'Pass messages', detail: 'Feature vectors travel along illustrative incoming edges.' },
  { title: 'Weight and aggregate', detail: 'Softmax normalizes example scores, then messages are combined.' },
  { title: 'Inform a decision', detail: 'The aggregate could inform LSTM/PPO. This demo issues no actions.' },
] as const;

export interface ConceptEdge { source: string; target: string; score: number; weight: number }
export interface ConceptGraph { receiver: string | null; selfWeight: number; edges: ConceptEdge[] }

export function conceptGraph(ids: readonly string[], selected: string | null, exampleScore = 2): ConceptGraph {
  const unique = [...new Set(ids)];
  const receiver = unique.includes(selected ?? '') ? selected : unique[0] ?? null;
  if (!receiver) return { receiver: null, selfWeight: 0, edges: [] };
  const peers = unique.filter(id => id !== receiver).slice(0, 8);
  // The slider edits only the first example edge. These are not learned scores.
  const score = Number.isFinite(exampleScore) ? Math.max(-4, Math.min(4, exampleScore)) : 2;
  const scores = [0, ...peers.map((_, i) => i === 0 ? score : 1 / (i + 1))];
  const maximum = Math.max(...scores), values = scores.map(s => Math.exp(s - maximum));
  const sum = values.reduce((total, value) => total + value, 0);
  return { receiver, selfWeight: values[0] / sum, edges: peers.map((source, i) => ({ source, target: receiver, score: scores[i + 1], weight: values[i + 1] / sum })) };
}
