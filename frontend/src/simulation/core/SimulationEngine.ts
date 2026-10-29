/**
 * Deterministic fixed-tick simulation engine.
 *
 * Mirrors the Step 4 pipeline (DecentralizedFrontierController.step ->
 * DisasterResponseParallelEnv.step -> SwarmWorld.step):
 *   1. apply queued operator commands (recorded for replay)
 *   2. each robot decides from its own LocalView (or manual intent)
 *   3. collision-safety shield, then simultaneous physics
 *   4. vision + thermal/acoustic sensing into each robot's private state
 *   5. investigate fusion and truth-side confirmation sensor
 *   6. broadcast state deltas, advance the lossy network, merge delivered maps
 * Rendering never mutates the engine; it reads positions and interpolates.
 */
import { DEFAULT_CONTROLLER, DEFAULT_NETWORK, FRAME_ID, type NetworkConfig, type PartitionWindow } from './config';
import { Rng, hashString } from './Rng';
import { HOLD, INVESTIGATE, MOVE_DELTAS, movementAction, type OperationMode, type Point } from './types';
import { generateScenario, type PresetId, type Scenario, type Victim } from '../world/ScenarioGenerator';
import { UNKNOWN } from '../world/GridMap';
import { WorldState } from '../world/WorldState';
import { createRobot, type RobotState } from '../robots/RobotState';
import { roverConfig } from '../robots/RoverRobot';
import { droneConfig } from '../robots/DroneRobot';
import { updateVision } from '../sensing/Vision';
import {
  acousticReading,
  argmaxSector,
  confirmVictims,
  evidencePosition,
  maxThermal,
  thermalReading,
  updateRobotSensors,
  type Sectors,
} from '../sensing/SensorModel';
import { astarPath } from '../planning/AStar';
import { PeerNetwork, type LinkInfo, type TransmissionRecord } from '../network/PeerNetwork';
import type { MapCell } from '../network/PeerMessage';
import { DecentralizedController, type Decision, type LocalView } from '../controller/DecentralizedController';
import { ManualController } from '../controller/ManualController';
import { applyMovements, safetyFilter } from '../controller/CollisionSafety';
import { formatEvent, type FeedItem, type SimEvent } from '../telemetry/HumanReadableEventFormatter';

export interface EngineOptions {
  preset: PresetId;
  seed: number;
  rovers: number;
  drones: number;
  packetLoss: number;
  delaySteps: [number, number];
  networkEnabled: boolean;
  sensorNoise: boolean;
  mode: OperationMode;
  manualRobot?: string | null;
  partitionWindows?: PartitionWindow[];
  survivorCount?: [number, number];
  survivorTargetCount?: number;
  survivorPositions?: Point[];
  messageTtl?: number;
  maxSteps?: number;
}

export type Command =
  | { kind: 'manualStep'; robot: string; direction: number }
  | { kind: 'manualWaypoint'; robot: string; target: Point }
  | { kind: 'manualStop'; robot: string }
  | { kind: 'manualScan'; robot: string }
  | { kind: 'setMode'; mode: OperationMode; manualRobot: string | null }
  | { kind: 'setPacketLoss'; value: number }
  | { kind: 'setDelay'; value: [number, number] }
  | { kind: 'setPartition'; on: boolean; robots: string[] };

export interface LoggedCommand {
  step: number;
  command: Command;
}

export interface PacketVisual {
  id: number;
  from: string;
  to: string;
  sentStep: number;
  arriveStep: number;
  outcome: 'delivered' | 'in-flight' | 'lost' | 'partition' | 'stale' | 'duplicate';
  mapCells: number;
}

export type DoneReason = 'all_found' | 'timeout' | 'all_depleted' | null;

export function defaultOptions(partial: Partial<EngineOptions> = {}): EngineOptions {
  return {
    preset: 'office',
    seed: 7,
    rovers: 2,
    drones: 2,
    packetLoss: 0.05,
    delaySteps: [1, 2],
    networkEnabled: true,
    sensorNoise: true,
    mode: 'autonomous',
    manualRobot: null,
    partitionWindows: [],
    ...partial,
  };
}

/** Validation demo: proves loss, delay, partition, reconnection, sharing, detection, convoy. */
export function demoOptions(seed = 11): EngineOptions {
  return defaultOptions({
    preset: 'demo',
    seed,
    rovers: 2,
    drones: 2,
    packetLoss: 0.15,
    delaySteps: [1, 3],
    partitionWindows: [{ start: 20, end: 60, agents: ['rover_0'] }],
    survivorCount: [3, 3],
  });
}

export class SimulationEngine {
  readonly options: EngineOptions;
  readonly scenario: Scenario;
  readonly world: WorldState;
  readonly rng: Rng;
  readonly robots: RobotState[];
  readonly network: PeerNetwork;
  readonly controller = new DecentralizedController(DEFAULT_CONTROLLER);
  readonly manual = new ManualController();
  mode: OperationMode;
  manualRobot: string | null;
  step = 0;
  done = false;
  doneReason: DoneReason = null;
  collisions = 0;
  maxSteps: number;
  /** Positions at the start of the latest tick, for render interpolation. */
  prevPositions = new Map<number, Point>();
  decisions = new Map<string, Decision | null>();
  investigating = new Set<string>();
  packets: PacketVisual[] = [];
  feed: FeedItem[] = [];
  rawEvents: Array<{ step: number; event: SimEvent }> = [];
  commandLog: LoggedCommand[] = [];
  coverageHistory: number[] = [];
  mapCellsMerged = 0;
  mapMergesRefused = 0;
  messagesProcessed = 0;
  duplicateGoalSteps = 0;
  private pending: Command[] = [];
  private lastBroadcast = new Map<string, Int8Array>();
  private snapshotCursor = new Map<string, number>();
  private connected = new Map<string, boolean>();
  private everConnected = new Set<string>();
  private cooldowns = new Map<string, number>();
  private feedId = 0;
  private lowBattery = new Set<string>();
  private partitionActive = new Set<string>();
  private noFrontier = new Set<string>();

  constructor(options: EngineOptions) {
    this.options = {
      ...options,
      delaySteps: [...options.delaySteps] as [number, number],
      ...(options.survivorPositions !== undefined ? {
        survivorPositions: Array.isArray(options.survivorPositions) ? options.survivorPositions.map((point) => ({ ...point })) : options.survivorPositions,
      } : {}),
    };
    this.mode = options.mode;
    this.manualRobot = options.manualRobot ?? null;
    const count = options.rovers + options.drones;
    if (count < 1 || count > 10) throw new Error('Team size must be between 1 and 10 robots');
    this.scenario = generateScenario({
      preset: options.preset,
      seed: options.seed,
      survivorCount: options.survivorCount,
      survivorTargetCount: options.survivorTargetCount,
      survivorPositions: this.options.survivorPositions,
    });
    this.world = new WorldState(this.scenario);
    this.maxSteps = options.maxSteps ?? this.scenario.maxSteps;
    this.rng = new Rng((options.seed * 2654435761) ^ hashString(`world:${options.preset}`));

    // Spawn: rovers first then drones, ids sequential (Python agent naming).
    const cells = this.world.spawnCells();
    const order = this.rng.permutation(cells.length);
    const types = [...Array(options.rovers).fill('rover'), ...Array(options.drones).fill('drone')] as const;
    let roverIndex = 0;
    let droneIndex = 0;
    this.robots = types.map((type, id) => {
      const cell = cells[order[id]];
      const config = type === 'rover' ? roverConfig(options.sensorNoise) : droneConfig(options.sensorNoise);
      const typeIndex = type === 'rover' ? roverIndex++ : droneIndex++;
      return createRobot(id, type, typeIndex, cell.x, cell.y, config, this.scenario.batteryScale, this.scenario.width, this.scenario.height);
    });

    const netConfig: NetworkConfig = {
      ...DEFAULT_NETWORK,
      enabled: options.networkEnabled,
      packetLoss: options.packetLoss,
      delaySteps: [...options.delaySteps] as [number, number],
      messageTtl: options.messageTtl ?? DEFAULT_NETWORK.messageTtl,
      partitionWindows: options.partitionWindows ?? [],
    };
    this.network = new PeerNetwork(netConfig, options.seed);
    this.network.register(this.robots.map((r) => r.name));
    for (const r of this.robots) {
      this.lastBroadcast.set(r.name, new Int8Array(r.belief.cells.length).fill(UNKNOWN));
      this.snapshotCursor.set(r.name, 0);
      this.prevPositions.set(r.id, { x: r.x, y: r.y });
      r.manual = this.isManual(r.name);
    }

    for (const r of this.robots) {
      r.newlyRevealed = updateVision(r, this.world.grid, r.config.visionRadius);
      updateRobotSensors(r, this.world.victims, this.world.grid, this.rng, false);
    }
    this.broadcastState();
    this.network.advance(0, this.robots, this.world.grid);
    this.processMessages();
    this.trackConnectivity();
    this.coverageHistory.push(this.coverage());
    this.emit({ type: 'mission_start', robots: this.robots.length, scenario: this.scenario.name });
  }

  // ------------------------------------------------------------------ commands

  /** Queue an operator command; it is applied deterministically at the next tick. */
  issue(command: Command): void {
    this.pending.push(command);
  }

  private isManual(name: string): boolean {
    return this.mode === 'manual' || (this.mode === 'mixed' && name === this.manualRobot);
  }

  private applyCommands(): void {
    const commands = this.pending;
    this.pending = [];
    for (const command of commands) {
      this.commandLog.push({ step: this.step, command });
      switch (command.kind) {
        case 'manualStep':
          if (this.isManual(command.robot)) {
            this.manual.queueStep(command.robot, command.direction);
            this.emitThrottled(`manual-step:${command.robot}`, 6, { type: 'manual', robot: command.robot, action: 'step' });
          }
          break;
        case 'manualWaypoint':
          if (this.isManual(command.robot)) {
            this.manual.setWaypoint(command.robot, command.target);
            this.emit({ type: 'manual', robot: command.robot, action: 'waypoint' });
          }
          break;
        case 'manualStop':
          this.manual.stop(command.robot);
          this.emit({ type: 'manual', robot: command.robot, action: 'stop' });
          break;
        case 'manualScan':
          if (this.isManual(command.robot)) {
            this.manual.scan(command.robot);
            this.emit({ type: 'manual', robot: command.robot, action: 'scan' });
          }
          break;
        case 'setMode': {
          const before = new Map(this.robots.map((r) => [r.name, r.manual]));
          this.mode = command.mode;
          this.manualRobot = command.manualRobot;
          for (const r of this.robots) {
            r.manual = this.isManual(r.name);
            if (r.manual && !before.get(r.name)) {
              this.controller.brain(r.name).reset();
              if (command.mode === 'mixed') this.emit({ type: 'manual', robot: r.name, action: 'take' });
            }
            if (!r.manual && before.get(r.name)) {
              this.manual.stop(r.name);
              if (this.mode !== 'manual') this.emit({ type: 'manual', robot: r.name, action: 'release' });
            }
          }
          break;
        }
        case 'setPacketLoss':
          this.network.setPacketLoss(command.value);
          break;
        case 'setDelay':
          this.network.setDelay(command.value);
          break;
        case 'setPartition':
          if (command.on) {
            this.network.addPartition({ start: this.step + 1, end: Number.MAX_SAFE_INTEGER, agents: command.robots });
          } else {
            this.network.endPartitions(this.step);
          }
          break;
      }
    }
  }

  // ------------------------------------------------------------------ local views

  /** Assemble the only information a robot's brain may use. */
  localView(r: RobotState): LocalView {
    return {
      name: r.name,
      id: r.id,
      type: r.type,
      position: { x: r.x, y: r.y },
      odom: { x: r.odomX, y: r.odomY },
      belief: r.belief,
      canCrossRubble: r.config.canCrossRubble,
      batteryFraction: r.battery / r.maxBattery,
      thermal: [...r.thermal] as Sectors,
      acoustic: r.acoustic,
      peerMessages: this.network.enabled ? this.network.peerMessages(r.name, this.step) : [],
      adjacentRobots: this.robots
        .filter((o) => o.alive && o.id !== r.id && Math.abs(o.x - r.x) + Math.abs(o.y - r.y) === 1)
        .map((o) => ({ x: o.x, y: o.y })),
      networkEnabled: this.network.enabled,
      step: this.step,
    };
  }

  // ------------------------------------------------------------------ tick

  tick(): void {
    if (this.done) return;
    this.applyCommands();
    for (const r of this.robots) this.prevPositions.set(r.id, { x: r.x, y: r.y });

    const requested = new Map<number, number>();
    this.investigating = new Set();
    for (const r of this.robots) {
      if (!r.alive) {
        requested.set(r.id, 0);
        this.decisions.set(r.name, null);
        r.objective = { kind: 'depleted' };
        r.path = [];
        continue;
      }
      if (r.manual) {
        const intent = this.manual.intent(r);
        requested.set(r.id, intent.move);
        r.path = intent.path;
        r.activeGoal = intent.goal;
        r.objective = { kind: 'manual', goal: intent.goal };
        if (intent.scan) {
          this.investigating.add(r.name);
          requested.set(r.id, this.investigateMove(r));
        }
        this.decisions.set(r.name, null);
        continue;
      }
      const decision = this.controller.decide(this.localView(r));
      this.decisions.set(r.name, decision);
      requested.set(r.id, this.decisionMove(r, decision));
      this.describeDecision(r, decision);
    }
    const goals = this.robots.filter((r) => r.alive && !r.manual && r.activeGoal).map((r) => `${r.activeGoal!.x},${r.activeGoal!.y}`);
    if (goals.length !== new Set(goals).size) this.duplicateGoalSteps++;

    const shield = safetyFilter(this.robots, requested, this.world.grid, this.step);
    // Narrate convoys only where they matter: inside one-cell-wide passages.
    for (const chain of shield.yielded.filter((c) => c.some((id) => this.isNarrow(this.robots[id]))))
      this.emitThrottled(`yield:${chain.slice().sort().join()}`, 30, { type: 'yield', robots: chain.map((id) => this.robots[id].name) });

    this.step++;
    this.collisions += applyMovements(this.robots, shield.filtered, this.world.grid, this.rng);
    this.narrateConvoys();

    for (const r of this.robots) {
      if (r.alive) {
        r.newlyRevealed = updateVision(r, this.world.grid, r.config.visionRadius);
        updateRobotSensors(r, this.world.victims, this.world.grid, this.rng);
      } else {
        r.newlyRevealed = 0;
      }
      this.controller.brain(r.name).goalReached(r);
      if (r.activeGoal && r.activeGoal.x === r.x && r.activeGoal.y === r.y) r.activeGoal = null;
    }

    // Investigate: fuse an independent second sample without exposing truth.
    for (const name of [...this.investigating].sort()) {
      const r = this.robots.find((x) => x.name === name)!;
      if (!r.alive) continue;
      const t = thermalReading(r, this.world.victims, this.world.grid, r.config, this.rng);
      const a = acousticReading(r, this.world.victims, this.world.grid, r.config, this.rng);
      r.thermal = r.thermal.map((v, i) => (v + t[i]) / 2) as Sectors;
      r.acoustic = (r.acoustic + a) / 2;
    }
    const confirmers = this.robots.filter((r) => r.alive && this.investigating.has(r.name));
    const newly = confirmVictims(confirmers, this.world.victims, this.world.grid, this.step);
    const found = this.world.victims.filter((v) => v.found).length;
    for (const v of newly) this.emit({ type: 'survivor', robot: v.foundBy!, victimId: v.id, found, total: this.world.victims.length });

    this.broadcastState();
    this.network.advance(this.step, this.robots, this.world.grid);
    this.collectPackets();
    this.processMessages();
    this.trackConnectivity();

    for (const r of this.robots) {
      const frac = r.battery / r.maxBattery;
      if (r.alive && frac < 0.2 && !this.lowBattery.has(r.name)) {
        this.lowBattery.add(r.name);
        this.emit({ type: 'battery_low', robot: r.name });
      }
      if (!r.alive && r.objective.kind !== 'depleted') {
        r.objective = { kind: 'depleted' };
        this.emit({ type: 'battery_depleted', robot: r.name });
      }
    }
    this.coverageHistory.push(this.coverage());

    const allFound = found === this.world.victims.length;
    const allDead = !this.robots.some((r) => r.alive);
    const timedOut = this.step >= this.maxSteps;
    if (allFound || allDead || timedOut) {
      this.done = true;
      this.doneReason = allFound ? 'all_found' : allDead ? 'all_depleted' : 'timeout';
      this.emit({ type: 'complete', reason: this.doneReason, found, total: this.world.victims.length });
    }
  }

  /** Telemetry only: adjacent robots that both advanced through narrow cells this tick. */
  private narrateConvoys(): void {
    const movers = this.robots.filter((r) => {
      const prev = this.prevPositions.get(r.id)!;
      return r.alive && (prev.x !== r.x || prev.y !== r.y) && this.isNarrow(r);
    });
    for (let i = 0; i < movers.length; i++)
      for (let j = i + 1; j < movers.length; j++) {
        const a = movers[i];
        const b = movers[j];
        if (Math.abs(a.x - b.x) + Math.abs(a.y - b.y) !== 1) continue;
        const key = [a.name, b.name].sort().join();
        this.emitThrottled(`convoy:${key}`, 30, { type: 'yield', robots: [a.name, b.name] });
      }
  }

  /** Telemetry only: a cell is narrow when it has at most two passable neighbours. */
  private isNarrow(r: RobotState): boolean {
    let open = 0;
    for (const [dx, dy] of MOVE_DELTAS.slice(1)) if (this.world.grid.isTraversable(r.x + dx, r.y + dy)) open++;
    return open <= 2;
  }

  private investigateMove(r: RobotState): number {
    if (maxThermal(r.thermal) <= 0) return 0;
    const move = [1, 4, 2, 3][argmaxSector(r.thermal)];
    const [dx, dy] = MOVE_DELTAS[move];
    const tx = r.x + dx;
    const ty = r.y + dy;
    // Only step where the robot's own map says it is traversable.
    return r.belief.isTraversable(tx, ty, r.config.canCrossRubble) ? move : 0;
  }

  private decisionMove(r: RobotState, d: Decision): number {
    if (d.kind === 'investigate') {
      this.investigating.add(r.name);
      r.activeGoal = null;
      r.path = [];
      return this.investigateMove(r);
    }
    if (d.kind === 'hold') {
      r.activeGoal = null;
      r.path = [];
      return 0;
    }
    r.activeGoal = { ...d.goal };
    r.path = d.path;
    return d.path.length >= 2 ? movementAction(r, d.path[1]) : 0;
  }

  private describeDecision(r: RobotState, d: Decision): void {
    const previous = r.objective.kind;
    if (d.kind === 'investigate') {
      r.objective = { kind: 'investigate', thermal: d.thermal };
      if (previous !== 'investigate')
        this.emitThrottled(`inv:${r.name}`, 12, { type: 'investigate', robot: r.name, thermal: d.thermal, acoustic: d.acoustic });
      this.noFrontier.delete(r.name);
      return;
    }
    if (d.kind === 'hold') {
      r.objective = {
        kind: 'hold',
        reason: d.reason === 'no-frontier' ? 'No unexplored area left in its own map' : 'Every nearby area is claimed by a teammate',
      };
      if (d.reason === 'no-frontier' && !this.noFrontier.has(r.name)) {
        this.noFrontier.add(r.name);
        this.emit({ type: 'no_frontier', robot: r.name });
      }
      return;
    }
    this.noFrontier.delete(r.name);
    r.objective = { kind: 'explore', goal: d.goal, owned: d.owned, followingPeerEvidence: d.followingPeerEvidence };
    if (d.releasedGoal && !astarPath(r.belief, r, d.releasedGoal, { canCrossRubble: r.config.canCrossRubble }).length)
      this.emitThrottled(`blocked:${r.name}`, 25, { type: 'blocked', robot: r.name });
    if (d.newGoal && (previous !== 'explore' || this.cooldownReady(`goal:${r.name}`, 40)))
      this.emitThrottled(`goal:${r.name}`, 40, {
        type: 'goal',
        robot: r.name,
        owned: d.owned,
        peerEvidence: d.followingPeerEvidence,
        distance: d.path.length - 1,
      });
  }

  // ------------------------------------------------------------------ network application layer

  private mapCellsForBroadcast(r: RobotState): { cells: MapCell[]; snapshot: boolean } {
    const limit = DEFAULT_NETWORK.mapChunkCells;
    const previous = this.lastBroadcast.get(r.name)!;
    const { width } = r.belief;
    const cells: MapCell[] = [];
    for (let i = 0; i < r.belief.cells.length && cells.length < limit; i++) {
      const v = r.belief.cells[i];
      if (v >= 0 && v !== previous[i]) {
        cells.push([i % width, Math.floor(i / width), v]);
        previous[i] = v;
      }
    }
    if (cells.length) return { cells, snapshot: false };
    if (this.step % DEFAULT_NETWORK.snapshotInterval !== 0) return { cells, snapshot: false };
    // Periodic bounded snapshot: rotate through known cells so peers recover
    // anything missed during loss or partition.
    const known: number[] = [];
    for (let i = 0; i < r.belief.cells.length; i++) if (r.belief.cells[i] >= 0) known.push(i);
    if (!known.length) return { cells, snapshot: false };
    const cursor = this.snapshotCursor.get(r.name)! % known.length;
    const count = Math.min(limit, known.length);
    for (let k = 0; k < count; k++) {
      const i = known[(cursor + k) % known.length];
      cells.push([i % width, Math.floor(i / width), r.belief.cells[i]]);
    }
    this.snapshotCursor.set(r.name, cursor + count);
    return { cells, snapshot: true };
  }

  private broadcastState(): void {
    if (!this.network.enabled) return;
    for (const r of [...this.robots].sort((a, b) => (a.name < b.name ? -1 : 1))) {
      if (!r.alive) continue;
      const { cells, snapshot } = this.mapCellsForBroadcast(r);
      const ev = evidencePosition(r);
      const brain = this.controller.brain(r.name);
      const goal = r.manual ? r.activeGoal : brain.localGoal;
      const frontiers = r.manual ? [] : brain.candidates(this.localView(r)).slice(0, 5);
      this.network.broadcast(r.name, this.step, {
        frameId: FRAME_ID,
        pose: [r.odomX, r.odomY],
        poseUncertainty: r.odomUncertainty,
        robotType: r.type,
        claimedGoal: goal ? [goal.x, goal.y] : null,
        evidence: { thermal: maxThermal(r.thermal), acoustic: r.acoustic, position: ev ? [ev.x, ev.y] : null },
        graphDelta: frontiers.map((c) => ({ kind: 'frontier' as const, position: [c.position.x, c.position.y] as [number, number] })),
        mapCells: cells,
        isSnapshot: snapshot,
      });
    }
  }

  private processMessages(): void {
    if (!this.network.enabled) return;
    const limit = DEFAULT_NETWORK.transformUncertaintyMax;
    for (const receiver of [...this.robots].sort((a, b) => (a.name < b.name ? -1 : 1))) {
      for (const m of this.network.drain(receiver.name)) {
        this.messagesProcessed++;
        const aligned = m.frameId === FRAME_ID && m.poseUncertainty <= limit && receiver.odomUncertainty <= limit;
        if (m.mapCells.length && !aligned) {
          this.mapMergesRefused++;
          this.emitThrottled(`refuse:${receiver.name}`, 60, { type: 'merge_refused', robot: receiver.name, from: m.senderId });
          continue;
        }
        let merged = 0;
        for (const [x, y, v] of m.mapCells) {
          if (receiver.belief.inBounds(x, y) && receiver.belief.get(x, y) < 0) {
            receiver.belief.set(x, y, v);
            merged++;
          }
        }
        this.mapCellsMerged += merged;
        if (merged >= 10)
          this.emitThrottled(`share:${m.senderId}`, 45, {
            type: 'map_shared',
            from: m.senderId,
            to: receiver.name,
            cells: merged,
            snapshot: m.isSnapshot,
          });
      }
    }
  }

  private collectPackets(): void {
    const outcome = (r: TransmissionRecord): PacketVisual['outcome'] =>
      r.state === 'delivered'
        ? 'delivered'
        : r.state === 'duplicate'
          ? 'duplicate'
          : r.state === 'in-flight'
            ? 'in-flight'
            : r.reason === 'partition'
              ? 'partition'
              : r.reason === 'stale'
                ? 'stale'
                : 'lost';
    this.packets = this.network.stepRecords
      .filter((r) => r.step === this.step)
      .map((r) => ({
        id: r.id,
        from: r.senderId,
        to: r.recipientId,
        sentStep: r.step,
        arriveStep: r.deliverStep,
        outcome: outcome(r),
        mapCells: r.mapDeltaSize,
      }));
  }

  private trackConnectivity(): void {
    if (!this.network.enabled || this.robots.length < 2) return;
    const isolated = this.network.isolatedAgents(this.step);
    for (const name of isolated)
      if (!this.partitionActive.has(name)) {
        this.partitionActive.add(name);
        this.emit({ type: 'partition_on', robots: [name] });
      }
    for (const name of [...this.partitionActive])
      if (!isolated.has(name)) {
        this.partitionActive.delete(name);
        this.emit({ type: 'partition_off', robots: [name] });
      }
    for (const r of this.robots) {
      if (!r.alive) continue;
      const up = this.linksFor(r.name).some((l) => l.health !== 'down');
      const was = this.connected.get(r.name);
      if (up) this.everConnected.add(r.name);
      if (was === true && !up && this.everConnected.has(r.name)) this.emitThrottled(`iso:${r.name}`, 20, { type: 'isolated', robot: r.name });
      if (was === false && up) this.emitThrottled(`rejoin:${r.name}`, 20, { type: 'rejoined', robot: r.name });
      this.connected.set(r.name, up);
    }
  }

  linksFor(name: string): LinkInfo[] {
    return [...this.network.links.values()].filter((l) => (l.a === name || l.b === name) && l.step === this.step);
  }

  // ------------------------------------------------------------------ events

  private cooldownReady(key: string, steps: number): boolean {
    const last = this.cooldowns.get(key);
    return last === undefined || this.step - last >= steps;
  }

  private emitThrottled(key: string, steps: number, event: SimEvent): void {
    if (!this.cooldownReady(key, steps)) return;
    this.cooldowns.set(key, this.step);
    this.emit(event);
  }

  private emit(event: SimEvent): void {
    this.rawEvents.push({ step: this.step, event });
    const f = formatEvent(event, (n) => this.label(n));
    this.feed.push({ id: this.feedId++, step: this.step, ...f });
    if (this.feed.length > 200) this.feed.splice(0, this.feed.length - 200);
  }

  label(name: string): string {
    return this.robots.find((r) => r.name === name)?.label ?? name;
  }

  // ------------------------------------------------------------------ statistics (offline / operator)

  coverage(): number {
    return this.world.coverage(this.robots);
  }

  /** Survivors visible to the operator: only those already confirmed. */
  discoveredSurvivors(): Victim[] {
    return this.world.victims.filter((v) => v.found);
  }

  survivorsFound(): number {
    return this.world.victims.filter((v) => v.found).length;
  }

  connectedRobots(): number {
    return this.robots.filter((r) => r.alive && this.connected.get(r.name)).length;
  }

  /** Measured link-layer loss over in-range attempts; null until the sample is meaningful. */
  measuredLoss(): number | null {
    const m = this.network.metrics;
    const inRange = m.messagesDelivered + m.droppedLoss + m.droppedStale + m.duplicatesSuppressed;
    return inRange >= 30 ? m.droppedLoss / inRange : null;
  }

  /** Deterministic fingerprint of the complete simulation state. */
  stateHash(): string {
    let h = 0x811c9dc5;
    const mix = (n: number) => {
      h = Math.imul(h ^ (n | 0), 0x01000193) >>> 0;
    };
    mix(this.step);
    for (const r of this.robots) {
      mix(r.x);
      mix(r.y);
      mix(Math.round(r.battery * 1000));
      mix(Math.round(r.odomX * 1000));
      mix(Math.round(r.odomY * 1000));
      mix(r.alive ? 1 : 0);
      for (let i = 0; i < r.belief.cells.length; i++) mix(r.belief.cells[i]);
    }
    for (const v of this.world.victims) mix(v.found ? (v.foundStep ?? 0) + 1 : 0);
    const m = this.network.metrics;
    for (const key of Object.keys(m).sort()) mix((m as unknown as Record<string, number>)[key]);
    return h.toString(16);
  }
}

export { HOLD, INVESTIGATE };
