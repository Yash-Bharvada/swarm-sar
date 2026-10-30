import { PeerNetwork } from '../simulation/network/PeerNetwork';
import { WALL } from '../simulation/world/GridMap';
import { netConfig, node, openGrid, send } from './helpers';

const pair = () => [node('rover_0', 'rover', 2, 2), node('drone_1', 'drone', 3, 2)];

describe('PeerNetwork', () => {
  it('packet loss actually drops messages', () => {
    const net = new PeerNetwork(netConfig({ packetLoss: 1, delaySteps: [0, 0] }), 3);
    const robots = pair();
    net.register(robots.map((r) => r.name));
    send(net);
    net.advance(0, robots, openGrid(10, 10));
    expect(net.drain('drone_1')).toEqual([]);
    expect(net.metrics.droppedLoss).toBe(1);
    expect(net.log.at(-1)).toMatchObject({ state: 'dropped', reason: 'loss' });

    // Partial loss drops some, not all, across many messages.
    const partial = new PeerNetwork(netConfig({ packetLoss: 0.3, delaySteps: [0, 0] }), 5);
    partial.register(robots.map((r) => r.name));
    for (let step = 0; step < 200; step++) {
      send(partial, 'rover_0', step);
      partial.advance(step, robots, openGrid(10, 10));
    }
    expect(partial.metrics.droppedLoss).toBeGreaterThan(30);
    expect(partial.metrics.messagesDelivered).toBeGreaterThan(100);
  });

  it('message delay queues messages until their delivery step', () => {
    const robots = [node('rover_0', 'rover', 2, 2), node('drone_1', 'drone', 5, 2)];
    const net = new PeerNetwork(netConfig({ delaySteps: [2, 2] }), 9);
    net.register(robots.map((r) => r.name));
    send(net);
    net.advance(0, robots, openGrid(20, 20));
    expect(net.drain('drone_1')).toEqual([]);
    expect(net.scheduled.length).toBe(1);
    net.advance(1, robots, openGrid(20, 20));
    expect(net.drain('drone_1')).toEqual([]);
    net.advance(2, robots, openGrid(20, 20));
    expect(net.drain('drone_1')).toHaveLength(1);
    expect(net.metrics.delayedDeliveries).toBe(1);
  });

  it('TTL expiry prevents stale delivery', () => {
    const robots = pair();
    const net = new PeerNetwork(netConfig({ messageTtl: 1 }), 3);
    net.register(robots.map((r) => r.name));
    const message = send(net);
    net.outboxes.set('rover_0', []);
    net.injectDelivery('drone_1', message, 3);
    net.advance(3, robots, openGrid(10, 10));
    expect(net.drain('drone_1')).toEqual([]);
    expect(net.metrics.droppedStale).toBe(1);

    // A delivered message stops counting as live peer state after its TTL.
    const fresh = new PeerNetwork(netConfig({ messageTtl: 2, delaySteps: [0, 0] }), 3);
    fresh.register(robots.map((r) => r.name));
    send(fresh, 'rover_0', 0);
    fresh.advance(0, robots, openGrid(10, 10));
    expect(fresh.peerMessages('drone_1', 2)).toHaveLength(1);
    expect(fresh.peerMessages('drone_1', 3)).toHaveLength(0);
  });

  it('range and wall attenuation prevent invalid delivery', () => {
    const far = [node('rover_0', 'rover', 1, 1), node('drone_1', 'drone', 15, 1)];
    const net = new PeerNetwork(netConfig({ delaySteps: [0, 0] }), 1);
    net.register(far.map((r) => r.name));
    send(net);
    net.advance(0, far, openGrid(20, 20));
    expect(net.drain('drone_1')).toEqual([]);
    expect(net.metrics.droppedRange).toBe(1);

    const near = [node('rover_0', 'rover', 2, 2), node('drone_1', 'drone', 8, 2)];
    const grid = openGrid(20, 20);
    grid.set(5, 2, WALL);
    const walled = new PeerNetwork(netConfig({ delaySteps: [0, 0] }), 1);
    walled.register(near.map((r) => r.name));
    send(walled);
    walled.advance(0, near, grid);
    expect(walled.drain('drone_1')).toEqual([]);
    expect(walled.metrics.droppedWall).toBe(1);

    // Same geometry without the wall delivers.
    const clear = new PeerNetwork(netConfig({ delaySteps: [0, 0] }), 1);
    clear.register(near.map((r) => r.name));
    send(clear);
    clear.advance(0, near, openGrid(20, 20));
    expect(clear.drain('drone_1')).toHaveLength(1);
  });

  it('partition isolates the configured robot in both directions', () => {
    const robots = [...pair(), node('drone_2', 'drone', 4, 2)];
    const net = new PeerNetwork(
      netConfig({ delaySteps: [0, 0], partitionWindows: [{ start: 0, end: 5, agents: ['rover_0'] }] }),
      4,
    );
    net.register(robots.map((r) => r.name));
    send(net, 'rover_0', 1);
    send(net, 'drone_1', 1);
    net.advance(1, robots, openGrid(10, 10));
    expect(net.drain('drone_1')).toEqual([]);
    expect(net.drain('rover_0')).toEqual([]);
    // Robots on the same side of the partition still talk.
    expect(net.drain('drone_2').map((m) => m.senderId)).toEqual(['drone_1']);
    expect(net.metrics.droppedPartition).toBe(3);
    expect(net.isolatedAgents(1)).toEqual(new Set(['rover_0']));
  });

  it('reconnection after a partition allows future messages and is counted', () => {
    const robots = pair();
    const net = new PeerNetwork(
      netConfig({ delaySteps: [0, 0], partitionWindows: [{ start: 0, end: 2, agents: ['rover_0'] }] }),
      4,
    );
    net.register(robots.map((r) => r.name));
    send(net, 'rover_0', 1);
    net.advance(1, robots, openGrid(10, 10));
    expect(net.metrics.droppedPartition).toBe(1);
    send(net, 'rover_0', 3);
    net.advance(3, robots, openGrid(10, 10));
    expect(net.drain('drone_1')).toHaveLength(1);
    expect(net.metrics.reconnections).toBe(1);
    expect(net.events.some((e) => e.kind === 'reconnect')).toBe(true);
  });

  it('operator partition toggle opens and closes a window', () => {
    const robots = pair();
    const net = new PeerNetwork(netConfig({ delaySteps: [0, 0] }), 4);
    net.register(robots.map((r) => r.name));
    net.addPartition({ start: 1, end: Number.MAX_SAFE_INTEGER, agents: ['drone_1'] });
    send(net, 'rover_0', 1);
    net.advance(1, robots, openGrid(10, 10));
    expect(net.drain('drone_1')).toEqual([]);
    net.endPartitions(1);
    send(net, 'rover_0', 2);
    net.advance(2, robots, openGrid(10, 10));
    expect(net.drain('drone_1')).toHaveLength(1);
  });

  it('suppresses duplicates and is deterministic for a seed', () => {
    const robots = pair();
    const net = new PeerNetwork(netConfig(), 3);
    net.register(robots.map((r) => r.name));
    const m = send(net);
    net.outboxes.set('rover_0', []);
    net.injectDelivery('drone_1', m, 0);
    net.injectDelivery('drone_1', m, 0);
    net.advance(0, robots, openGrid(10, 10));
    expect(net.drain('drone_1')).toHaveLength(1);
    expect(net.metrics.duplicatesSuppressed).toBe(1);

    const run = () => {
      const n = new PeerNetwork(netConfig({ packetLoss: 0.25, delaySteps: [1, 3] }), 77);
      n.register(robots.map((r) => r.name));
      for (let step = 0; step < 50; step++) {
        send(n, 'rover_0', step);
        send(n, 'drone_1', step);
        n.advance(step, robots, openGrid(10, 10));
      }
      return n.snapshot();
    };
    expect(run()).toEqual(run());
  });
});
