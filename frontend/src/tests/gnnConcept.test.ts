import { describe, expect, it } from 'vitest';
import { CONCEPT_STEPS, conceptGraph } from '../observatory/gnnConcept';

describe('GNN teaching illustration', () => {
  it('constructs a directed receiver-local example without modifying mission data', () => {
    const ids = ['rover_0', 'rover_1', 'drone_2'];
    const before = JSON.stringify(ids), graph = conceptGraph(ids, 'rover_1');
    expect(graph.receiver).toBe('rover_1');
    expect(graph.edges.map(e => e.source)).toEqual(['rover_0', 'drone_2']);
    expect(graph.edges.every(e => e.target === 'rover_1')).toBe(true);
    expect(JSON.stringify(ids)).toBe(before);
  });
  it('normalizes authored example weights including self and responds to the score control', () => {
    const ids = ['rover_0', 'drone_1', 'drone_2'];
    const low = conceptGraph(ids, null, -4), high = conceptGraph(ids, null, 4);
    expect(high.edges[0].weight).toBeGreaterThan(low.edges[0].weight);
    for (const graph of [low, high]) {
      expect(graph.selfWeight + graph.edges.reduce((sum, e) => sum + e.weight, 0)).toBeCloseTo(1);
      expect(graph.edges.every(e => Number.isFinite(e.weight) && e.weight >= 0)).toBe(true);
    }
  });
  it('handles missing selection, duplicates, empty and solo fleets with a bounded peer count', () => {
    expect(conceptGraph([], null)).toEqual({ receiver: null, selfWeight: 0, edges: [] });
    expect(conceptGraph(['r', 'r'], 'missing')).toEqual({ receiver: 'r', selfWeight: 1, edges: [] });
    expect(conceptGraph(Array.from({ length: 20 }, (_, i) => `r${i}`), 'r0').edges).toHaveLength(8);
    expect(conceptGraph(['r', 'd'], null, NaN)).toEqual(conceptGraph(['r', 'd'], null, 2));
  });
  it('describes the output step as illustrative and issues no actions', () => {
    expect(CONCEPT_STEPS).toHaveLength(4);
    expect(CONCEPT_STEPS[3].detail).toContain('issues no actions');
  });
});
