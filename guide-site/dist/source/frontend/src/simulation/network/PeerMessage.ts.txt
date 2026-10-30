/** Wire envelope for the Step 4 peer network (Python network/messages.py PeerMessage + payload). */
import type { Point, RobotType } from '../core/types';

export interface SurvivorEvidence {
  thermal: number;
  acoustic: number;
  /** Sender's own odometry-frame estimate of the heat source, or null. */
  position: [number, number] | null;
}

export interface GraphDeltaItem {
  kind: 'frontier';
  position: [number, number];
}

/** [x, y, cellValue] in the common-entry frame. */
export type MapCell = [number, number, number];

export interface PeerMessage {
  senderId: string;
  sequence: number;
  frameId: string;
  sentStep: number;
  expiresStep: number;
  /** null = neighbourhood broadcast (the only mode used by the Step 4 controller). */
  recipientId: string | null;
  kind: 'state_delta';
  pose: [number, number];
  poseUncertainty: number;
  robotType: RobotType;
  claimedGoal: [number, number] | null;
  evidence: SurvivorEvidence;
  graphDelta: GraphDeltaItem[];
  mapCells: MapCell[];
  isSnapshot: boolean;
  /** Serialized size, computed once at creation. */
  estimatedBytes: number;
}

export const messageId = (m: Pick<PeerMessage, 'senderId' | 'sequence'>): string => `${m.senderId}:${m.sequence}`;

export function estimateBytes(m: Omit<PeerMessage, 'estimatedBytes'>): number {
  return JSON.stringify({ ...m, messageId: messageId(m) }).length;
}

export const goalPoint = (g: [number, number] | null): Point | null => (g ? { x: g[0], y: g[1] } : null);
