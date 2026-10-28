import { SimulationEngine, demoOptions } from '../simulation/core/SimulationEngine';

/**
 * The Validation Demo scenario must visibly prove every Step 4 behaviour the
 * UI claims: packet loss, delay, partition, reconnection, map sharing, survivor
 * detection and collision-free narrow-passage traffic.
 */
describe('Validation demo scenario', () => {
  const engine = new SimulationEngine(demoOptions());
  const kinds = new Set<string>();
  let isolatedDuringWindow = false;
  while (!engine.done) {
    engine.tick();
    if (engine.step >= 20 && engine.step <= 60 && engine.network.isolatedAgents(engine.step).has('rover_0')) isolatedDuringWindow = true;
  }
  for (const e of engine.rawEvents) kinds.add(e.event.type);
  const m = engine.network.metrics;

  it('drops packets to loss', () => expect(m.droppedLoss).toBeGreaterThan(0));
  it('delivers delayed packets', () => expect(m.delayedDeliveries).toBeGreaterThan(0));
  it('partitions rover_0 between steps 20 and 60', () => {
    expect(isolatedDuringWindow).toBe(true);
    expect(m.droppedPartition).toBeGreaterThan(0);
    expect(kinds.has('partition_on') && kinds.has('partition_off')).toBe(true);
  });
  it('reconnects after the partition', () => {
    expect(m.reconnections).toBeGreaterThan(0);
    expect(kinds.has('rejoined')).toBe(true);
  });
  it('shares local maps peer to peer', () => {
    expect(engine.mapCellsMerged).toBeGreaterThan(0);
    expect(kinds.has('map_shared')).toBe(true);
  });
  it('detects and confirms survivors', () => {
    expect(kinds.has('investigate')).toBe(true);
    expect(engine.survivorsFound()).toBeGreaterThan(0);
  });
  it('passes the narrow corridor in convoy with zero collisions', () => {
    expect(kinds.has('yield')).toBe(true);
    expect(engine.collisions).toBe(0);
  });
});
