/**
 * Range-, wall-, loss-, delay-, TTL- and partition-aware message transport
 * (Python network/peer.py PeerNetwork). A transport only: it routes messages but
 * never selects robot actions. It also records a transmission log and per-link
 * health purely for visualization.
 */
import { Rng } from '../core/Rng';
import type { NetworkConfig, PartitionWindow, RobotTypeConfig } from '../core/config';
import type { RobotType } from '../core/types';
import type { GridMap } from '../world/GridMap';
import { bresenhamLine } from '../sensing/Vision';
import { WALL } from '../world/GridMap';
import { estimateBytes, messageId, type PeerMessage } from './PeerMessage';

export interface NetNode {
  name: string;
  type: RobotType;
  x: number;
  y: number;
  alive: boolean;
  config: Pick<RobotTypeConfig, 'commRadius'>;
}

export type DropReason = 'loss' | 'range' | 'wall' | 'partition' | 'bandwidth' | 'stale';
export type TransmissionState = 'in-flight' | 'delivered' | 'dropped' | 'duplicate';

export interface TransmissionRecord {
  id: number;
  step: number;
  senderId: string;
  recipientId: string;
  sequence: number;
  kind: string;
  state: TransmissionState;
  reason: DropReason | null;
  delay: number;
  deliverStep: number;
  expiresStep: number;
  mapDeltaSize: number;
  isSnapshot: boolean;
  hasEvidence: boolean;
}

export type LinkHealth = 'healthy' | 'weak' | 'down';

export interface LinkInfo {
  a: string;
  b: string;
  health: LinkHealth;
  reason: DropReason | 'ok';
  step: number;
  distance: number;
  walls: number;
}

export interface NetworkEvent {
  step: number;
  kind: 'reconnect' | 'link_lost';
  a: string;
  b: string;
}

export interface NetworkMetrics {
  messagesCreated: number;
  transmissionAttempts: number;
  messagesDelivered: number;
  droppedLoss: number;
  droppedRange: number;
  droppedWall: number;
  droppedPartition: number;
  droppedBandwidth: number;
  droppedStale: number;
  duplicatesSuppressed: number;
  bytesCreated: number;
  bytesDelivered: number;
  reconnections: number;
  delayedDeliveries: number;
}

interface Scheduled {
  deliverStep: number;
  recipient: string;
  message: PeerMessage;
  record: TransmissionRecord | null;
}

const emptyMetrics = (): NetworkMetrics => ({
  messagesCreated: 0,
  transmissionAttempts: 0,
  messagesDelivered: 0,
  droppedLoss: 0,
  droppedRange: 0,
  droppedWall: 0,
  droppedPartition: 0,
  droppedBandwidth: 0,
  droppedStale: 0,
  duplicatesSuppressed: 0,
  bytesCreated: 0,
  bytesDelivered: 0,
  reconnections: 0,
  delayedDeliveries: 0,
});

const pairKey = (a: string, b: string): string => (a < b ? `${a}|${b}` : `${b}|${a}`);

export type BroadcastFields = Omit<
  PeerMessage,
  'senderId' | 'sequence' | 'sentStep' | 'expiresStep' | 'estimatedBytes' | 'recipientId' | 'kind'
>;

export class PeerNetwork {
  config: NetworkConfig;
  readonly rng: Rng;
  metrics: NetworkMetrics = emptyMetrics();
  readonly outboxes = new Map<string, PeerMessage[]>();
  readonly inboxes = new Map<string, PeerMessage[]>();
  readonly seen = new Map<string, Set<string>>();
  readonly latestBySender = new Map<string, Map<string, PeerMessage>>();
  /** Last delivered message per recipient, kept for operator inspection only. */
  readonly recentReceived = new Map<string, PeerMessage[]>();
  scheduled: Scheduled[] = [];
  readonly nextSeq = new Map<string, number>();
  readonly linkState = new Map<string, boolean>();
  readonly links = new Map<string, LinkInfo>();
  log: TransmissionRecord[] = [];
  /** Records touched during the most recent advance() (for packet animation). */
  stepRecords: TransmissionRecord[] = [];
  events: NetworkEvent[] = [];
  private recordId = 0;
  static readonly LOG_LIMIT = 600;

  constructor(config: NetworkConfig, seed: number) {
    if (config.packetLoss < 0 || config.packetLoss > 1) throw new Error('packetLoss must be between 0 and 1');
    if (config.delaySteps[0] < 0 || config.delaySteps[1] < config.delaySteps[0]) throw new Error('Invalid delaySteps');
    this.config = { ...config, partitionWindows: config.partitionWindows.map((w) => ({ ...w, agents: [...w.agents] })) };
    this.rng = new Rng((seed ^ 0x4e455457) >>> 0);
  }

  get enabled(): boolean {
    return this.config.enabled;
  }

  register(agents: string[]): void {
    for (const a of agents) {
      if (!this.outboxes.has(a)) this.outboxes.set(a, []);
      if (!this.inboxes.has(a)) this.inboxes.set(a, []);
      if (!this.seen.has(a)) this.seen.set(a, new Set());
      if (!this.latestBySender.has(a)) this.latestBySender.set(a, new Map());
      if (!this.recentReceived.has(a)) this.recentReceived.set(a, []);
    }
  }

  broadcast(senderId: string, step: number, fields: BroadcastFields): PeerMessage | null {
    if (!this.enabled) return null;
    const sequence = this.nextSeq.get(senderId) ?? 0;
    this.nextSeq.set(senderId, sequence + 1);
    const base = {
      ...fields,
      senderId,
      sequence,
      sentStep: step,
      expiresStep: step + this.config.messageTtl,
      recipientId: null,
      kind: 'state_delta' as const,
    };
    const message: PeerMessage = { ...base, estimatedBytes: estimateBytes(base) };
    this.outboxes.get(senderId)!.push(message);
    this.metrics.messagesCreated++;
    this.metrics.bytesCreated += message.estimatedBytes;
    return message;
  }

  isPartitioned(sender: string, recipient: string, step: number): boolean {
    for (const w of this.config.partitionWindows) {
      if (w.start <= step && step <= w.end) {
        const isolated = new Set(w.agents);
        if (isolated.has(sender) !== isolated.has(recipient)) return true;
      }
    }
    return false;
  }

  /** Agents isolated by an active partition window at `step`. */
  isolatedAgents(step: number): Set<string> {
    const out = new Set<string>();
    for (const w of this.config.partitionWindows) if (w.start <= step && step <= w.end) w.agents.forEach((a) => out.add(a));
    return out;
  }

  radioLink(sender: NetNode, recipient: NetNode, grid: GridMap): { linked: boolean; reason: DropReason | 'ok'; distance: number; walls: number; margin: number } {
    const radius = Math.min(sender.config.commRadius, recipient.config.commRadius);
    const distance = Math.hypot(sender.x - recipient.x, sender.y - recipient.y);
    if (distance > radius) return { linked: false, reason: 'range', distance, walls: 0, margin: distance / radius };
    const line = bresenhamLine(sender, recipient);
    let walls = 0;
    for (let i = 1; i < line.length - 1; i++) if (grid.get(line[i].x, line[i].y) === WALL) walls++;
    if (this.config.requireLos && walls) return { linked: false, reason: 'wall', distance, walls, margin: 1 };
    const effective = radius * this.config.wallAttenuation ** walls;
    if (distance > effective) return { linked: false, reason: 'wall', distance, walls, margin: distance / effective };
    return { linked: true, reason: 'ok', distance, walls, margin: distance / effective };
  }

  private pushRecord(r: Omit<TransmissionRecord, 'id'>): TransmissionRecord {
    const record = { ...r, id: this.recordId++ };
    this.log.push(record);
    if (this.log.length > PeerNetwork.LOG_LIMIT) this.log.splice(0, this.log.length - PeerNetwork.LOG_LIMIT);
    this.stepRecords.push(record);
    return record;
  }

  private deliver(recipient: string, message: PeerMessage, step: number, record: TransmissionRecord | null): void {
    if (step > message.expiresStep) {
      this.metrics.droppedStale++;
      if (record) {
        record.state = 'dropped';
        record.reason = 'stale';
      }
      return;
    }
    const seen = this.seen.get(recipient)!;
    const id = messageId(message);
    if (seen.has(id)) {
      this.metrics.duplicatesSuppressed++;
      if (record) record.state = 'duplicate';
      return;
    }
    seen.add(id);
    this.inboxes.get(recipient)!.push(message);
    const latest = this.latestBySender.get(recipient)!;
    const current = latest.get(message.senderId);
    if (
      !current ||
      message.sentStep > current.sentStep ||
      (message.sentStep === current.sentStep && message.sequence > current.sequence)
    )
      latest.set(message.senderId, message);
    const recent = this.recentReceived.get(recipient)!;
    recent.push(message);
    if (recent.length > 12) recent.shift();
    this.metrics.messagesDelivered++;
    this.metrics.bytesDelivered += message.estimatedBytes;
    if (step > message.sentStep) this.metrics.delayedDeliveries++;
    if (record) record.state = 'delivered';
  }

  advance(step: number, robots: NetNode[], grid: GridMap): void {
    this.stepRecords = [];
    if (!this.enabled) return;
    const due = this.scheduled.filter((s) => s.deliverStep <= step);
    this.scheduled = this.scheduled.filter((s) => s.deliverStep > step);
    due.sort(
      (a, b) =>
        a.deliverStep - b.deliverStep ||
        (a.recipient < b.recipient ? -1 : a.recipient > b.recipient ? 1 : 0) ||
        (a.message.senderId < b.message.senderId ? -1 : a.message.senderId > b.message.senderId ? 1 : 0) ||
        a.message.sequence - b.message.sequence,
    );
    for (const item of due) {
      this.deliver(item.recipient, item.message, step, item.record);
      if (item.record) this.stepRecords.push(item.record);
    }

    const byName = new Map<string, NetNode>();
    for (const r of robots) if (r.alive) byName.set(r.name, r);
    const recipients = [...byName.keys()].sort();
    const seenPairs = new Set<string>();
    for (const senderName of [...this.outboxes.keys()].sort()) {
      const messages = this.outboxes.get(senderName)!;
      this.outboxes.set(senderName, []);
      const sender = byName.get(senderName);
      if (!sender) continue;
      let remaining = this.config.bandwidthBytes;
      for (const message of messages) {
        if (message.estimatedBytes > remaining) {
          this.metrics.droppedBandwidth++;
          continue;
        }
        remaining -= message.estimatedBytes;
        for (const recipientName of recipients) {
          if (recipientName === senderName) continue;
          const recipient = byName.get(recipientName)!;
          this.metrics.transmissionAttempts++;
          const pair = pairKey(senderName, recipientName);
          const base = {
            step,
            senderId: senderName,
            recipientId: recipientName,
            sequence: message.sequence,
            kind: message.kind,
            expiresStep: message.expiresStep,
            mapDeltaSize: message.mapCells.length,
            isSnapshot: message.isSnapshot,
            hasEvidence: message.evidence.thermal >= 0.3,
          };
          if (this.isPartitioned(senderName, recipientName, step)) {
            this.metrics.droppedPartition++;
            this.setLink(pair, false, step, senderName, recipientName);
            this.updateLinkInfo(pair, senderName, recipientName, 'down', 'partition', step, 0, 0, seenPairs);
            this.pushRecord({ ...base, state: 'dropped', reason: 'partition', delay: 0, deliverStep: step });
            continue;
          }
          const link = this.radioLink(sender, recipient, grid);
          if (!link.linked) {
            const reason = link.reason as DropReason;
            if (reason === 'range') this.metrics.droppedRange++;
            else this.metrics.droppedWall++;
            this.setLink(pair, false, step, senderName, recipientName);
            this.updateLinkInfo(pair, senderName, recipientName, 'down', reason, step, link.distance, link.walls, seenPairs);
            // Range/wall misses are not logged per-attempt: they happen every tick
            // for every distant pair and would drown the log.
            continue;
          }
          this.setLink(pair, true, step, senderName, recipientName);
          if (this.rng.random() < this.config.packetLoss) {
            this.metrics.droppedLoss++;
            this.updateLinkInfo(pair, senderName, recipientName, 'weak', 'loss', step, link.distance, link.walls, seenPairs);
            this.pushRecord({ ...base, state: 'dropped', reason: 'loss', delay: 0, deliverStep: step });
            continue;
          }
          const [lo, hi] = this.config.delaySteps;
          const delay = this.rng.integers(lo, hi + 1);
          const weak = link.margin > 0.75 || delay >= 3 || link.walls > 0;
          this.updateLinkInfo(pair, senderName, recipientName, weak ? 'weak' : 'healthy', 'ok', step, link.distance, link.walls, seenPairs);
          const record = this.pushRecord({ ...base, state: 'in-flight', reason: null, delay, deliverStep: step + delay });
          if (delay === 0) this.deliver(recipientName, message, step, record);
          else this.scheduled.push({ deliverStep: step + delay, recipient: recipientName, message, record });
        }
      }
    }
    // Links to robots that are no longer alive are down.
    for (const info of this.links.values()) if (!byName.has(info.a) || !byName.has(info.b)) info.health = 'down';
  }

  private setLink(pair: string, up: boolean, step: number, a: string, b: string): void {
    const previous = this.linkState.get(pair);
    if (up && previous === false) {
      this.metrics.reconnections++;
      this.events.push({ step, kind: 'reconnect', a, b });
    } else if (!up && previous === true) {
      this.events.push({ step, kind: 'link_lost', a, b });
    }
    this.linkState.set(pair, up);
  }

  /** Both directions of a pair are evaluated per step; keep the healthiest. */
  private updateLinkInfo(
    pair: string,
    a: string,
    b: string,
    health: LinkHealth,
    reason: DropReason | 'ok',
    step: number,
    distance: number,
    walls: number,
    seenPairs: Set<string>,
  ): void {
    const rank = { healthy: 2, weak: 1, down: 0 } as const;
    const existing = this.links.get(pair);
    if (existing && seenPairs.has(pair) && rank[existing.health] >= rank[health]) return;
    seenPairs.add(pair);
    this.links.set(pair, { a: a < b ? a : b, b: a < b ? b : a, health, reason, step, distance, walls });
  }

  drain(recipient: string): PeerMessage[] {
    const inbox = this.inboxes.get(recipient) ?? [];
    this.inboxes.set(recipient, []);
    return inbox;
  }

  /** Latest unexpired message from each peer that has actually reached `recipient`. */
  peerMessages(recipient: string, step: number, maxAge?: number): PeerMessage[] {
    const age = maxAge ?? this.config.messageTtl;
    const latest = this.latestBySender.get(recipient);
    if (!latest) return [];
    return [...latest.values()].filter((m) => step - m.sentStep <= age && step <= m.expiresStep);
  }

  /** Test/debug hook that still passes through expiry and de-duplication. */
  injectDelivery(recipient: string, message: PeerMessage, deliverStep: number): void {
    this.scheduled.push({ deliverStep, recipient, message, record: null });
  }

  setPacketLoss(loss: number): void {
    this.config.packetLoss = Math.max(0, Math.min(1, loss));
  }

  setDelay(delay: [number, number]): void {
    this.config.delaySteps = [Math.max(0, delay[0]), Math.max(delay[0], delay[1])];
  }

  addPartition(window: PartitionWindow): void {
    this.config.partitionWindows.push({ ...window, agents: [...window.agents] });
  }

  /** Close every open-ended partition window at `step`. */
  endPartitions(step: number): void {
    for (const w of this.config.partitionWindows) if (w.end > step && w.start <= step) w.end = step;
    this.config.partitionWindows = this.config.partitionWindows.filter((w) => w.start <= w.end);
  }

  snapshot(): NetworkMetrics & { scheduled: number; deliveryRate: number } {
    const attempts = this.metrics.transmissionAttempts;
    return {
      ...this.metrics,
      scheduled: this.scheduled.length,
      deliveryRate: attempts ? this.metrics.messagesDelivered / attempts : 0,
    };
  }
}
