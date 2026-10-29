/** Read-only presentation adapter. Python alone owns PPO actions and physics. */
import { SimulationEngine, defaultOptions } from '../simulation/core/SimulationEngine';
import { GridMap, Material, WALL, bfsDistances } from '../simulation/world/GridMap';
import type { Scenario } from '../simulation/world/ScenarioGenerator';
import { WorldState } from '../simulation/world/WorldState';
import { createRobot } from '../simulation/robots/RobotState';
import { roverConfig } from '../simulation/robots/RoverRobot';
import { droneConfig } from '../simulation/robots/DroneRobot';
import { formatEvent, type SimEvent } from '../simulation/telemetry/HumanReadableEventFormatter';
import type { LinkInfo } from '../simulation/network/PeerNetwork';
import type { PeerMessage } from '../simulation/network/PeerMessage';

export const PPO_CHECKPOINT_SHA = '23696e6cf3b0821b6c01235a3911cb5cb87d0707589efce6ec43cb58b5340040';
export interface PPOOptions { seed: number; rovers: number; drones: number; size: number; layout: 'rooms' | 'maze' | 'cave'; network: boolean; batteryLimited?: boolean }
export const DEFAULT_PPO_OPTIONS: PPOOptions = { seed: 10000, rovers: 2, drones: 2, size: 32, layout: 'rooms', network: true, batteryLimited: true };
export interface PPOProvenance { checkpointStep: number; checkpointTreeSha256: string; policyHashes: Record<string, string>; observationVersion: string; observationSize: number; device: string; finalSeedsUsed: boolean }
interface RemoteRobot { id: number; name: string; type: 'rover' | 'drone'; x: number; y: number; battery: number; maxBattery: number; alive: boolean; belief: number[]; visited: number[]; thermal: [number, number, number, number]; acoustic: number; distanceTravelled: number; lastAction: number; collided: boolean; action: number | null; goal: [number, number] | null; odom_x: number; odom_y: number; odom_uncertainty: number; radii: { vision_radius: number; thermal_radius: number; acoustic_radius: number; comm_radius: number } }
interface RemoteMessage { sender_id: string; seq: number; frame_id: string; sent_step: number; expires_step: number; kind: string; pose: [number, number]; pose_uncertainty: number; estimated_bytes: number; payload: { robot_type: 'rover' | 'drone'; goal?: [number, number] | null; evidence: { thermal: number; acoustic: number; position: [number, number] | null }; graph_delta: PeerMessage['graphDelta']; map_cells: PeerMessage['mapCells']; map_snapshot: boolean } }
export interface PPOSnapshot {
  protocol: number; mission: string; controller: string; provenance: PPOProvenance; options: PPOOptions;
  step: number; done: boolean; doneReason: 'all_found' | 'timeout' | 'all_depleted' | null;
  width: number; height: number; grid: number[]; spawn: [number, number]; spawnSize: number; maxSteps: number;
  victims: Array<{ id: number; x: number; y: number; found: boolean; found_step: number | null; foundBy: string | null }>;
  robots: RemoteRobot[]; links: LinkInfo[]; peers: Record<string, RemoteMessage[]>; packets: SimulationEngine['packets'];
  transport: { packetLoss: number; delay: [number, number]; ttl: number };
  network: Record<string, number | boolean>;
  metrics: { coverage: number; collisions: number; invalid_actions: number; victims_found: number; survivors_total: number };
}

export function validateSnapshot(value: unknown): asserts value is PPOSnapshot {
  const s = value as PPOSnapshot;
  if (!s || s.protocol !== 1 || s.controller !== 'ppo' || !s.mission || s.provenance?.checkpointTreeSha256 !== PPO_CHECKPOINT_SHA || s.provenance?.observationVersion !== 'gpu-v1' || s.provenance?.observationSize !== 229 || s.provenance?.checkpointStep !== 753664 || s.provenance?.finalSeedsUsed !== false) throw new Error('Incompatible PPO service or checkpoint');
  if (!Number.isInteger(s.step) || s.step < 0 || !Number.isInteger(s.width) || s.width < 24 || s.width > 56 || s.height !== s.width || s.grid?.length !== s.width * s.height || !Array.isArray(s.robots) || !s.robots.length || s.robots.length > 10 || !Array.isArray(s.victims) || !s.transport) throw new Error('Invalid Python world snapshot');
  if (!s.options || (s.options.batteryLimited !== undefined && typeof s.options.batteryLimited !== 'boolean')) throw new Error('Invalid Python battery mode');
  if (s.grid.some((v) => ![0, 1, 2].includes(v)) || !Number.isFinite(s.metrics?.coverage) || s.metrics.coverage < 0 || s.metrics.coverage > 1) throw new Error('Invalid Python map or metrics');
  const names = new Set<string>();
  for (const r of s.robots) {
    if (names.has(r.name) || !['rover', 'drone'].includes(r.type) || ![r.x, r.y, r.battery, r.maxBattery, r.acoustic, r.odom_x, r.odom_y].every(Number.isFinite) || r.x < 0 || r.x >= s.width || r.y < 0 || r.y >= s.height || r.belief.length !== s.grid.length || r.visited.length !== s.grid.length || r.thermal.length !== 4 || !r.thermal.every(Number.isFinite) || r.maxBattery <= 0 || !r.radii || r.belief.some((v) => ![-1, 0, 1, 2].includes(v))) throw new Error('Invalid Python robot snapshot');
    names.add(r.name);
  }
}

function message(m: RemoteMessage): PeerMessage {
  return { senderId: m.sender_id, sequence: m.seq, frameId: m.frame_id, sentStep: m.sent_step, expiresStep: m.expires_step, recipientId: null, kind: 'state_delta', pose: m.pose, poseUncertainty: m.pose_uncertainty, robotType: m.payload.robot_type, claimedGoal: m.payload.goal ?? null, evidence: m.payload.evidence, graphDelta: m.payload.graph_delta ?? [], mapCells: m.payload.map_cells ?? [], isSnapshot: m.payload.map_snapshot, estimatedBytes: m.estimated_bytes };
}
const camel = (key: string) => key.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());

export class RemoteEngine extends SimulationEngine {
  readonly mission: string;
  readonly provenance: PPOProvenance;
  private pythonCoverage = 0;
  private seenMessages = new Set<string>();
  constructor(snapshot: PPOSnapshot) {
    validateSnapshot(snapshot);
    super(defaultOptions({ seed: snapshot.options.seed, rovers: snapshot.options.rovers, drones: snapshot.options.drones, networkEnabled: snapshot.options.network, batteryLimited: snapshot.options.batteryLimited !== false, packetLoss: snapshot.transport.packetLoss, delaySteps: snapshot.transport.delay }));
    this.mission = snapshot.mission;
    this.provenance = snapshot.provenance;
    const grid = new GridMap(snapshot.width, snapshot.height, 0, Int8Array.from(snapshot.grid));
    const distances = bfsDistances(grid, snapshot.spawn[0], snapshot.spawn[1]);
    const material = Uint8Array.from(snapshot.grid, (cell) => cell === WALL ? Material.Concrete : Material.None);
    const scenario: Scenario = { preset: 'office', seed: snapshot.options.seed, name: `PPO ${snapshot.options.layout === 'maze' ? 'Maze' : snapshot.options.layout === 'cave' ? 'Cavern' : 'Rescue Site'}`, disaster: 'Python world · trained PPO exploration', width: snapshot.width, height: snapshot.height, grid, material, wallHeight: Float32Array.from(snapshot.grid, (cell) => cell === WALL ? 1 : 0), spawn: { x: snapshot.spawn[0], y: snapshot.spawn[1], size: snapshot.spawnSize }, spawnCenter: { x: snapshot.spawn[0] + 1, y: snapshot.spawn[1] + 1 }, distances, victims: snapshot.victims.map((v) => ({ id: v.id, x: v.x, y: v.y, found: v.found, foundBy: v.foundBy, foundStep: v.found_step })), props: [], emergencyLights: [], openings: [], stairwell: null, maxSteps: snapshot.maxSteps, batteryScale: 1 };
    const indices = { rover: 0, drone: 0 };
    const robots = snapshot.robots.map((r) => createRobot(r.id, r.type, indices[r.type]++, r.x, r.y, r.type === 'rover' ? roverConfig(true) : droneConfig(true), 1, snapshot.width, snapshot.height));
    Object.assign(this, { scenario, world: new WorldState(scenario), robots });
    this.feed = []; this.rawEvents = []; this.coverageHistory = []; this.prevPositions.clear();
    // Discard the local base constructor's transport state. Only Python
    // envelopes and counters may appear in a remote mission.
    this.network.events = []; this.network.log = []; this.network.stepRecords = [];
    this.network.scheduled = []; this.network.outboxes.clear(); this.network.inboxes.clear();
    this.network.latestBySender.clear(); this.network.recentReceived.clear();
    this.network.linkState.clear(); this.network.nextSeq.clear();
    for (const key of Object.keys(this.network.metrics)) Object.assign(this.network.metrics, { [key]: 0 });
    this.applySnapshot(snapshot, true);
  }
  override tick(): void { throw new Error('PPO ticks must come from Python'); }
  override issue(): void { throw new Error('PPO mission is autonomous; browser commands are disabled'); }
  override coverage(): number { return this.pythonCoverage; }
  override connectedRobots(): number { return this.network.enabled ? this.robots.filter((r) => r.alive && this.linksFor(r.name).some((l) => l.health !== 'down')).length : 0; }
  private event(event: SimEvent) {
    this.rawEvents.push({ step: this.step, event });
    this.feed.push({ id: this.rawEvents.length, step: this.step, ...formatEvent(event, (name) => this.label(name)) });
    if (this.feed.length > 200) this.feed.shift();
  }
  applySnapshot(s: PPOSnapshot, initial = false) {
    validateSnapshot(s);
    if (s.mission !== this.mission || (!initial && s.step !== this.step + 1)) throw new Error('PPO mission/step mismatch; reset to reconnect');
    if (s.width !== this.scenario.width || s.height !== this.scenario.height || s.robots.length !== this.robots.length) throw new Error('Python mission geometry changed');
    if (s.grid.some((value, i) => value !== this.scenario.grid.cells[i]) || s.victims.length !== this.scenario.victims.length || s.robots.some((source) => !this.robots.some((r) => r.name === source.name && r.id === source.id)) || s.victims.some((source) => !this.scenario.victims.some((v) => v.id === source.id && v.x === source.x && v.y === source.y))) throw new Error('Python mission identity changed');
    this.step = s.step;
    if (!initial && this.step === 1) this.event({ type: 'mission_start', robots: this.robots.length, scenario: this.scenario.name }); this.done = s.done; this.doneReason = s.doneReason; this.maxSteps = s.maxSteps;
    this.collisions = s.metrics.collisions; this.pythonCoverage = s.metrics.coverage;
    this.investigating.clear();
    for (const r of this.robots) {
      const source = s.robots.find((unit) => unit.name === r.name);
      if (!source) throw new Error('Python robot disappeared');
      this.prevPositions.set(r.id, { x: r.x, y: r.y });
      const oldBattery = r.battery, alive = r.alive;
      r.x = source.x; r.y = source.y; r.battery = source.battery; r.maxBattery = source.maxBattery;
      r.alive = source.alive; r.lastAction = source.lastAction; r.collided = source.collided;
      r.prevThermal = r.thermal; r.prevAcoustic = r.acoustic;
      r.thermal = source.thermal; r.acoustic = source.acoustic;
      r.odomX = source.odom_x; r.odomY = source.odom_y; r.odomUncertainty = source.odom_uncertainty;
      r.distanceTravelled = source.distanceTravelled;
      r.config = { ...r.config, battery: r.maxBattery, visionRadius: source.radii.vision_radius, thermalRadius: source.radii.thermal_radius, acousticRadius: source.radii.acoustic_radius, commRadius: source.radii.comm_radius };
      r.belief.cells.set(source.belief); r.visited.set(source.visited);
      r.activeGoal = source.goal ? { x: source.goal[0], y: source.goal[1] } : null;
      r.path = []; r.manual = false;
      if (r.lastAction) r.heading = [0, Math.PI, 0, -Math.PI / 2, Math.PI / 2][r.lastAction];
      r.objective = !r.alive ? { kind: 'depleted' } : source.action === 5 ? { kind: 'investigate', thermal: Math.max(...r.thermal) } : source.action === 6 ? { kind: 'hold', reason: 'PPO holding position' } : source.action === null ? { kind: 'idle' } : { kind: 'explore', goal: r.activeGoal ?? { x: r.x, y: r.y }, owned: false, followingPeerEvidence: false };
      if (!initial && alive && !r.alive) this.event({ type: 'battery_depleted', robot: r.name });
      if (!initial && oldBattery / r.maxBattery >= .2 && r.battery / r.maxBattery < .2) this.event({ type: 'battery_low', robot: r.name });
      if (source.action === 5) this.investigating.add(r.name);
    }
    for (const v of this.scenario.victims) {
      const source = s.victims.find((person) => person.id === v.id);
      if (!source) throw new Error('Python survivor disappeared');
      const fresh = source.found && !v.found;
      Object.assign(v, { found: source.found, foundBy: source.foundBy, foundStep: source.found_step });
      if (fresh) this.event({ type: 'survivor', robot: v.foundBy ?? '', victimId: v.id, found: s.metrics.victims_found, total: s.metrics.survivors_total });
    }
    this.network.config.enabled = s.options.network;
    this.network.links.clear(); s.links.forEach((link) => this.network.links.set([link.a, link.b].sort().join('|'), link));
    for (const [key, value] of Object.entries(s.network)) {
      const name = camel(key);
      if (name in this.network.metrics && typeof value === 'number') Object.assign(this.network.metrics, { [name]: value });
    }
    this.mapCellsMerged = Number(s.network.map_cells_merged ?? 0);
    this.mapMergesRefused = Number(s.network.map_merges_refused ?? 0);
    this.messagesProcessed = Number(s.network.messages_processed ?? 0);
    for (const r of this.robots) {
      const messages = (s.peers[r.name] ?? []).map(message);
      this.network.latestBySender.set(r.name, new Map(messages.map((m) => [m.senderId, m])));
      this.network.recentReceived.set(r.name, messages.slice(-4));
      for (const m of messages) {
        const id = `${r.name}:${m.senderId}:${m.sequence}`;
        if (!this.seenMessages.has(id)) {
          this.seenMessages.add(id);
          this.network.log.push({ id: this.seenMessages.size, step: this.step, senderId: m.senderId, recipientId: r.name, sequence: m.sequence, kind: 'state_delta', state: 'delivered', reason: null, delay: this.step - m.sentStep, deliverStep: this.step, expiresStep: m.expiresStep, mapDeltaSize: m.mapCells.length, isSnapshot: m.isSnapshot, hasEvidence: m.evidence.thermal >= .35 });

        }
      }
    }
    this.network.log = this.network.log.slice(-600);
    this.packets = s.packets;
    this.coverageHistory.push(this.pythonCoverage);
    if (this.done && !initial) this.event({ type: 'complete', reason: this.doneReason!, found: s.metrics.victims_found, total: s.metrics.survivors_total });
  }
}
