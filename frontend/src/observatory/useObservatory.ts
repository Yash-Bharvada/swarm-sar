/** Presentation-only adapters. They never publish goals, maps or velocity commands. */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSim } from '../store/simStore';
import { RosConnection, validGrid } from '../ros/transport';
import type { ObservatoryAgent, ObservatoryGrid, ObservatoryLink, ObservatoryPacket, ObservatorySnapshot } from './types';

const COLORS = ['#688b68', '#d58b51', '#499a96', '#9b89b4', '#b58d48', '#748fa7', '#be8091', '#7d9d83'];
const ROS_AGENTS = ['rover_0', 'rover_1', 'drone_0', 'drone_1'];
const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const point = (v: unknown): v is { x: number; y: number } => record(v) && finite(v.x) && finite(v.y);
const number = (v: unknown) => finite(v) && v >= 0 ? v : 0;
export function telemetryFresh(now: number, received: number, maximumAge = 3000): boolean {
  return received > 0 && now >= received && now - received <= maximumAge;
}
export function clockProgressTime(previous: number | null, next: number, receipt: number, lastAdvanced: number): number {
  return previous === null || next > previous ? receipt : lastAdvanced;
}
export function rosObservatoryGrid(value: unknown): ObservatoryGrid | null {
  if (!validGrid(value)) return null;
  const q = value.info.origin.orientation;
  return {
    width: value.info.width, height: value.info.height, resolution: value.info.resolution,
    originX: value.info.origin.position.x, originY: value.info.origin.position.y,
    yaw: Math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z)),
    cells: value.data.map(v => v < 0 || (v > 0 && v < 65) ? -1 : v >= 65 ? 1 : 0),
  };
}

export function useBrowserObservatory(): ObservatorySnapshot {
  const version = useSim(s => s.version);
  const engine = useSim(s => s.engine);
  const status = useSim(s => s.status);
  const mode = useSim(s => s.controllerMode);
  const phase = useSim(s => s.ppoPhase);
  const runtime = useRef<{ engine: typeof engine | null; epoch: number; step: number; at: number; receipts: Map<string, number>; paths: Map<string, { x: number; y: number }[]> }>({ engine: null, epoch: 0, step: -1, at: 0, receipts: new Map(), paths: new Map() });
  const [wall, setWall] = useState(Date.now());
  useEffect(() => { const timer = setInterval(() => setWall(Date.now()), 500); return () => clearInterval(timer); }, []);
  return useMemo(() => {
    const now = Date.now(), run = runtime.current;
    if (run.engine !== engine || engine.step < run.step) {
      run.engine = engine; run.epoch++; run.receipts.clear(); run.paths.clear(); run.step = -1;
    }
    if (engine.step !== run.step) {
      run.at = now; run.step = engine.step;
      for (const robot of engine.robots) {
        const path = run.paths.get(robot.name) || [], last = path[path.length - 1];
        if (!last || last.x !== robot.x + .5 || last.y !== robot.y + .5) path.push({ x: robot.x + .5, y: robot.y + .5 });
        run.paths.set(robot.name, path.slice(-1000));
      }
    }
    const fresh = mode !== 'ppo' || (phase === 'ready' && (status !== 'running' || telemetryFresh(now, run.at, 4000)));
    const agents: ObservatoryAgent[] = engine.robots.map((robot, i) => ({
      id: robot.name, type: robot.type, position: { x: robot.x + .5, y: robot.y + .5 }, yaw: robot.heading,
      color: COLORS[i % COLORS.length], battery: Math.max(0, Math.min(1, robot.battery / robot.maxBattery)),
      state: robot.objective.kind, fresh: fresh && robot.alive,
      knownCells: robot.belief.cells.reduce((n, v) => n + (v >= 0 ? 1 : 0), 0), peerCells: 0,
      goal: robot.activeGoal ? { x: robot.activeGoal.x + .5, y: robot.activeGoal.y + .5 } : null,
      path: run.paths.get(robot.name) || [],
      grid: { width: robot.belief.width, height: robot.belief.height, resolution: 1, originX: 0, originY: 0, yaw: 0, cells: Array.from(robot.belief.cells) },
      peerGrid: null, frontiers: [],
    }));
    // Delivered graph deltas are real communicated frontier representatives.
    for (const agent of agents) {
      const graphs = engine.network.latestBySender.get(agent.id);
      if (graphs) agent.frontiers = [...graphs.values()].filter(m => engine.step <= m.expiresStep).flatMap(m => m.graphDelta.map(n => ({ x: n.position[0] + .5, y: n.position[1] + .5 }))).slice(0, 64);
    }
    const packets: ObservatoryPacket[] = engine.network.log.slice(-200).map(entry => {
      const id = `${run.epoch}:${entry.id}:${entry.state}`;
      if (!run.receipts.has(id)) run.receipts.set(id, status === 'running' && engine.step - entry.step <= 2 ? now : now - 10000);
      return {
        id, source: entry.senderId, target: entry.recipientId, kind: entry.isSnapshot ? 'map snapshot' : entry.hasEvidence ? 'survivor evidence' : entry.kind,
        state: entry.state === 'in-flight' ? 'queued' : entry.state === 'delivered' ? 'delivered' : 'dropped',
        reason: entry.reason || (entry.state === 'duplicate' ? 'duplicate' : ''), time: entry.step,
        receivedAt: run.receipts.get(id)!, cells: entry.mapDeltaSize, sequence: entry.sequence,
      };
    });
    if (run.receipts.size > 1000) { const keep = new Set(packets.map(p => p.id)); for (const key of run.receipts.keys()) if (!keep.has(key)) run.receipts.delete(key); }
    const metrics = engine.network.metrics;
    return {
      source: 'browser', sourceLabel: mode === 'ppo' ? 'Python PPO mapping · simulated poses' : 'Browser mapping · simulated poses',
      time: engine.step, running: status === 'running', fresh, agents, packets,
      links: engine.network.enabled ? [...engine.network.links.values()].filter(link => engine.step - link.step <= 8).map(link => ({ source: link.a, target: link.b, state: link.health })) : [],
      metrics: { sent: metrics.transmissionAttempts, delivered: metrics.messagesDelivered,
        dropped: metrics.droppedLoss + metrics.droppedRange + metrics.droppedWall + metrics.droppedPartition + metrics.droppedBandwidth + metrics.droppedStale,
        bytes: metrics.bytesDelivered, applied: engine.mapCellsMerged }, epoch: `browser-${run.epoch}`,
    };
  }, [version, engine, status, mode, phase, wall]);
}

type Timed<T> = { value: T; at: number };
interface Health { run: string; state: string; source: string; local_known: number; peer_known: number; map_age: number | null; pose_age: number | null; claims: Record<string, { goal: [number, number]; expires_at: number }> }
interface Pose { x: number; y: number; yaw: number }
interface RosState {
  epoch: number; clock: Timed<number> | null; clockAdvancedAt: number;
  pose: Record<string, Timed<Pose>>; health: Record<string, Timed<Health>>;
  grids: Record<string, Record<string, Timed<ObservatoryGrid>>>;
  paths: Record<string, { x: number; y: number }[]>; frontiers: Record<string, { x: number; y: number }[]>;
  packets: ObservatoryPacket[]; links: Record<string, ObservatoryLink & { at: number }>;
  metrics: ObservatorySnapshot['metrics']; statsAt: number; applied: number; isolated: string[];
}
const emptyRos = (epoch = 0): RosState => ({ epoch, clock: null, clockAdvancedAt: 0, pose: {}, health: {}, grids: {}, paths: {}, frontiers: {}, packets: [], links: {}, metrics: { sent: 0, delivered: 0, dropped: 0, bytes: 0, applied: null }, statsAt: 0, applied: 0, isolated: [] });
const parseRosString = (msg: unknown): Record<string, unknown> | null => {
  if (!record(msg) || typeof msg.data !== 'string' || msg.data.length > 1_000_000) return null;
  try { const parsed: unknown = JSON.parse(msg.data); return record(parsed) ? parsed : null; } catch { return null; }
};
export function useRosObservatory(): { snapshot: ObservatorySnapshot; connection: string; connect: (url: string) => void; disconnect: () => void; isolate: (agent: string, isolated: boolean) => Promise<unknown>; isolated: string[]; radioStatusFresh: boolean } {
  const data = useRef<RosState>(emptyRos());
  const client = useRef<RosConnection | null>(null);
  const [connection, setConnection] = useState('disconnected');
  const [revision, setRevision] = useState(0);
  const [wall, setWall] = useState(Date.now());
  const pending = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Coalesce bursty ROS packet callbacks; the renderer still animates at display rate.
  const emit = () => {
    if (pending.current !== null) return;
    pending.current = setTimeout(() => { pending.current = null; setRevision(v => v + 1); }, 50);
  };
  const reset = () => { data.current = emptyRos(data.current.epoch + 1); emit(); };
  useEffect(() => {
    const ros = new RosConnection(setConnection); client.current = ros;
    ros.subscribe('/clock', 'rosgraph_msgs/msg/Clock', msg => {
      if (!record(msg) || !record(msg.clock) || !finite(msg.clock.sec) || !finite(msg.clock.nanosec)) return;
      const now = msg.clock.sec + msg.clock.nanosec / 1e9;
      if (data.current.clock && now < data.current.clock.value - .01) reset();
      data.current.clockAdvancedAt = clockProgressTime(data.current.clock?.value ?? null, now, Date.now(), data.current.clockAdvancedAt);
      data.current.clock = { value: now, at: Date.now() }; emit();
    });
    for (const agent of ROS_AGENTS) {
      for (const layer of ['local_slam_map', 'peer_map']) ros.subscribe(`/${agent}/${layer}`, 'nav_msgs/msg/OccupancyGrid', msg => {
        const grid = rosObservatoryGrid(msg); if (!grid) return;
        data.current.grids[agent] = { ...data.current.grids[agent], [layer]: { value: grid, at: Date.now() } }; emit();
      }, 1000);
      ros.subscribe(`/${agent}/estimated_odom`, 'nav_msgs/msg/Odometry', msg => {
        if (!record(msg) || !record(msg.header) || msg.header.frame_id !== 'map' || !record(msg.pose) || !record(msg.pose.pose)) return;
        const pose = msg.pose.pose; if (!point(pose.position) || !record(pose.orientation) || !finite(pose.orientation.z) || !finite(pose.orientation.w)) return;
        data.current.pose[agent] = { value: { x: pose.position.x, y: pose.position.y, yaw: Math.atan2(2 * pose.orientation.z * pose.orientation.w, 1 - 2 * pose.orientation.z ** 2) }, at: Date.now() }; emit();
      });
      ros.subscribe(`/${agent}/slam_health`, 'std_msgs/msg/String', msg => {
        const h = parseRosString(msg);
        if (!h || h.agent !== agent || typeof h.run !== 'string' || typeof h.state !== 'string' || typeof h.source !== 'string') return;
        const d = data.current;
        if (d.health[agent] && d.health[agent].value.run !== h.run) {
          delete d.pose[agent]; delete d.grids[agent]; delete d.paths[agent]; delete d.frontiers[agent];
          d.packets = d.packets.filter(p => p.source !== agent && p.target !== agent);
          for (const key of Object.keys(d.links)) if (d.links[key].source === agent || d.links[key].target === agent) delete d.links[key];
          d.epoch++;
        }
        const claims: Health['claims'] = {};
        if (record(h.claims)) for (const [name, value] of Object.entries(h.claims)) {
          if (record(value) && Array.isArray(value.goal) && value.goal.length === 2 && value.goal.every(finite) && finite(value.expires_at)) claims[name] = { goal: value.goal as [number, number], expires_at: value.expires_at };
        }
        d.health[agent] = { value: { run: h.run, state: h.state, source: h.source,
          local_known: number(h.local_known), peer_known: number(h.peer_known), map_age: finite(h.map_age) ? h.map_age : null, pose_age: finite(h.pose_age) ? h.pose_age : null, claims }, at: Date.now() }; emit();
      }, 1000);
      ros.subscribe(`/${agent}/estimated_path`, 'nav_msgs/msg/Path', msg => {
        if (!record(msg) || !record(msg.header) || msg.header.frame_id !== 'map' || !Array.isArray(msg.poses)) return;
        data.current.paths[agent] = msg.poses.slice(-1000).flatMap(p => record(p) && record(p.pose) && point(p.pose.position) ? [{ x: p.pose.position.x, y: p.pose.position.y }] : []); emit();
      }, 1000);
      ros.subscribe(`/${agent}/topology`, 'std_msgs/msg/String', msg => {
        const t = parseRosString(msg); if (!t || t.frame !== 'map' || !Array.isArray(t.local)) return;
        data.current.frontiers[agent] = t.local.filter(point).slice(0, 64).map(p => ({ x: p.x, y: p.y })); emit();
      }, 1000);
    }
    ros.subscribe('/swarm/network/events', 'std_msgs/msg/String', msg => {
      const e = parseRosString(msg);
      if (!e || typeof e.event !== 'string' || typeof e.source !== 'string' || typeof e.target !== 'string' || !finite(e.sequence) || !finite(e.sim_time)) return;
      const state: ObservatoryPacket['state'] | null = e.event === 'queued' ? 'queued' : e.event === 'transport_delivered' ? 'delivered' : e.event === 'receiver_applied' ? 'applied' : e.event.startsWith('dropped_') ? 'dropped' : null;
      if (!state) return;
      const d = data.current, id = `${d.epoch}:${e.channel}:${e.source}:${e.target}:${e.sequence}:${e.event}:${e.sim_time}`;
      if (d.packets.some(p => p.id === id)) return;
      d.packets.push({ id, source: e.source, target: e.target, sequence: e.sequence, kind: typeof e.channel === 'string' ? e.channel : 'peer', state, reason: state === 'dropped' ? e.event.replace('dropped_', '') : '', time: e.sim_time, receivedAt: Date.now(), cells: null });
      d.packets = d.packets.slice(-200);
      if (state === 'applied') { d.applied++; d.metrics = { ...d.metrics, applied: d.applied }; }
      if (e.target) d.links[[e.source, e.target].sort().join(':')] = { source: e.source, target: e.target, state: state === 'dropped' ? (e.event === 'dropped_loss' ? 'weak' : 'down') : 'healthy', at: Date.now() };
      emit();
    }, 0);
    ros.subscribe('/swarm/network/stats', 'std_msgs/msg/String', msg => {
      const s = parseRosString(msg); if (!s || !record(s.metrics)) return;
      const m = s.metrics, d = data.current;
      if (Array.isArray(s.isolated)) d.isolated = s.isolated.filter((name): name is string => typeof name === 'string');
      d.metrics = { sent: number(m.attempted), delivered: number(m.delivered), dropped: Object.entries(m).filter(([key]) => key.startsWith('dropped_')).reduce((n, [, v]) => n + number(v), 0), bytes: number(m.bytes_sent), applied: d.applied };
      d.statsAt = Date.now(); emit();
    }, 1000);
    const timer = setInterval(() => setWall(Date.now()), 500);
    return () => { clearInterval(timer); if (pending.current !== null) clearTimeout(pending.current); pending.current = null; ros.close(); client.current = null; };
  }, []);
  const connect = useCallback((url: string) => { data.current = emptyRos(data.current.epoch + 1); setRevision(v => v + 1); client.current?.connect(url); }, []);
  const disconnect = useCallback(() => { client.current?.close(); }, []);
  const isolate = useCallback((agent: string, isolated: boolean) => {
    if (!client.current) return Promise.reject(new Error('ROS connection is unavailable'));
    return client.current.isolate(agent, isolated);
  }, []);
  const snapshot = useMemo<ObservatorySnapshot>(() => {
    const d = data.current, now = Date.now(), live = connection === 'connected' && !!d.clock && telemetryFresh(now, d.clock.at);
    const agents: ObservatoryAgent[] = ROS_AGENTS.map((id, i) => {
      const pose = d.pose[id], health = d.health[id], h = health?.value;
      const fresh = live && !!pose && telemetryFresh(now, pose.at) && !!health && telemetryFresh(now, health.at, 3500) && h?.state === 'tracking' && h.map_age !== null && h.map_age < 5 && h.pose_age !== null && h.pose_age < 1;
      const claim = h?.claims[id];
      return { id, type: id.startsWith('drone') ? 'drone' : 'rover', color: COLORS[i], position: pose ? { x: pose.value.x, y: pose.value.y } : null,
        yaw: pose?.value.yaw || 0, battery: null, state: !health ? 'waiting for telemetry' : fresh ? h!.source === 'slam_toolbox' ? 'SLAM tracking' : 'simulator localization' : h!.state === 'restart_required' ? 'restart required' : 'stale',
        fresh, knownCells: h?.local_known || 0, peerCells: h?.peer_known || 0,
        goal: fresh && claim && d.clock && claim.expires_at > d.clock.value ? { x: claim.goal[0], y: claim.goal[1] } : null,
        path: d.paths[id] || [], grid: d.grids[id]?.local_slam_map?.value || null, peerGrid: d.grids[id]?.peer_map?.value || null, frontiers: d.frontiers[id] || [] };
    });
    // Claim telemetry belongs to the receiver: surface a sender's current goal
    // only from delivered, still leased claims; no inferred controller intent.
    if (live && d.clock) for (const health of Object.values(d.health)) {
      if (!telemetryFresh(now, health.at, 3500) || health.value.state !== 'tracking') continue;
      for (const [sender, claim] of Object.entries(health.value.claims)) {
        const agent = agents.find(a => a.id === sender);
        if (agent && !agent.goal && claim.expires_at > d.clock.value) agent.goal = { x: claim.goal[0], y: claim.goal[1] };
      }
    }
    return { source: 'ros', sourceLabel: 'ROS 2 · rover SLAM / drone simulated poses', time: d.clock?.value || 0,
      running: live && telemetryFresh(now, d.clockAdvancedAt, 1200) && agents.some(a => a.fresh), fresh: live && agents.some(a => a.fresh), agents, packets: d.packets,
      links: Object.values(d.links).filter(link => telemetryFresh(now, link.at, 8000)).map(({ source, target, state }) => ({ source, target, state })), metrics: d.metrics, epoch: `ros-${d.epoch}` };
  }, [connection, revision, wall]);
  return { snapshot, connection, connect, disconnect, isolate, isolated: data.current.isolated, radioStatusFresh: connection === 'connected' && telemetryFresh(Date.now(), data.current.statsAt, 3500) };
}
