/**
 * TypeScript port of the Step 4 decentralized frontier controller
 * (Python baselines/decentralized.py DecentralizedFrontierController).
 *
 * Every robot runs its own `AgentBrain`. A brain receives a `LocalView` built
 * exclusively from that robot's own state (private belief map, own sensors,
 * battery, own cell/odometry) and the peer messages that have actually been
 * delivered to its inbox. There is no reservation table, no central
 * allocator, and no access to the truth grid or survivor list.
 */
import type { ControllerConfig } from '../core/config';
import { hashString } from '../core/Rng';
import { HOLD, INVESTIGATE, manhattan, type Point, type RobotType } from '../core/types';
import type { GridMap } from '../world/GridMap';
import { astarPath } from '../planning/AStar';
import { frontierCandidates, type FrontierCandidate } from '../planning/FrontierPlanner';
import { goalPoint, type PeerMessage } from '../network/PeerMessage';
import type { Sectors } from '../sensing/SensorModel';

/** Everything an autonomous robot is allowed to know when deciding. */
export interface LocalView {
  name: string;
  id: number;
  type: RobotType;
  position: Point;
  odom: Point;
  belief: GridMap;
  canCrossRubble: boolean;
  batteryFraction: number;
  thermal: Sectors;
  acoustic: number;
  /** Latest unexpired message per peer that has actually been delivered. */
  peerMessages: PeerMessage[];
  networkEnabled: boolean;
  step: number;
}

export type Decision =
  | {
      action: number; // frontier slot index 0–4 (always 0 here: the active goal is slot 0)
      kind: 'explore';
      goal: Point;
      path: Point[];
      newGoal: boolean;
      owned: boolean;
      followingPeerEvidence: boolean;
      releasedGoal: Point | null;
      peerClaimsSeen: number;
    }
  | { action: typeof INVESTIGATE; kind: 'investigate'; thermal: number; acoustic: number }
  | { action: typeof HOLD; kind: 'hold'; reason: 'no-frontier' | 'all-claimed' };

/**
 * Rendezvous (highest-random-weight) branch owner. Coarse 8×8 spatial keys keep
 * ownership stable as a frontier advances; only branches owned by a peer that
 * joins or disappears move. Hash: FNV-1a + avalanche (Python uses blake2s).
 */
export function branchOwner(position: Point, participants: readonly string[]): string {
  const key = `${Math.floor(position.x / 8)}:${Math.floor(position.y / 8)}`;
  let best = participants[0];
  let bestHash = -1;
  for (const name of participants) {
    const h = hashString(`${key}:${name}`);
    if (h > bestHash || (h === bestHash && name > best)) {
      best = name;
      bestHash = h;
    }
  }
  return best;
}

export function shouldInvestigate(thermal: Sectors, acoustic: number, config: ControllerConfig): boolean {
  const t = Math.max(...thermal);
  return (
    t >= config.thermalInvestigateThreshold ||
    (t >= config.thermalCorroborationThreshold && acoustic >= config.acousticInterestThreshold)
  );
}

export class AgentBrain {
  /** This robot's own claimed goal. Never shared except through its broadcasts. */
  localGoal: Point | null = null;

  constructor(
    readonly name: string,
    readonly config: ControllerConfig,
  ) {}

  /** Candidates from the robot's own belief; the active goal (if reachable) is slot 0. */
  candidates(view: LocalView): FrontierCandidate[] {
    const list = frontierCandidates(
      view.belief,
      view.position,
      this.config.maxFrontiers,
      this.config.frontierSamplesPerCluster,
      view.canCrossRubble,
    );
    const goal = this.localGoal;
    if (goal && (goal.x !== view.position.x || goal.y !== view.position.y)) {
      const path = astarPath(view.belief, view.position, goal, { canCrossRubble: view.canCrossRubble });
      if (path.length) {
        return [
          { position: goal, clusterSize: 1, path, distance: path.length - 1, activeGoal: true },
          ...list.filter((c) => c.position.x !== goal.x || c.position.y !== goal.y),
        ].slice(0, this.config.maxFrontiers);
      }
    }
    return list;
  }

  private claimsBySender(view: LocalView): Map<string, Point> {
    const claims = new Map<string, Point>();
    if (!view.networkEnabled) return claims;
    for (const m of view.peerMessages) {
      const g = goalPoint(m.claimedGoal);
      if (g) claims.set(m.senderId, g);
    }
    return claims;
  }

  private peerEvidencePositions(view: LocalView): Point[] {
    if (!view.networkEnabled) return [];
    const out: Point[] = [];
    for (const m of view.peerMessages) {
      if (m.evidence.position && m.evidence.thermal >= this.config.peerEvidenceThreshold)
        out.push({ x: m.evidence.position[0], y: m.evidence.position[1] });
    }
    return out;
  }

  private participants(view: LocalView): string[] {
    if (!view.networkEnabled) return [view.name];
    const set = new Set(view.peerMessages.map((m) => m.senderId));
    set.add(view.name);
    return [...set].sort();
  }

  decide(view: LocalView): Decision {
    const thermal = Math.max(...view.thermal);
    if (shouldInvestigate(view.thermal, view.acoustic, this.config)) {
      this.localGoal = null;
      return { action: INVESTIGATE, kind: 'investigate', thermal, acoustic: view.acoustic };
    }

    const candidates = this.candidates(view);
    const claims = this.claimsBySender(view);
    const goal = this.localGoal;
    if (goal) {
      const current = candidates.find((c) => c.position.x === goal.x && c.position.y === goal.y);
      if (current) {
        // Deterministic tie-break on identical claims: lexicographically smaller name keeps it.
        let lowerPriority = false;
        for (const [sender, g] of claims) if (g.x === goal.x && g.y === goal.y && sender < view.name) lowerPriority = true;
        if (!lowerPriority)
          return {
            action: 0,
            kind: 'explore',
            goal,
            path: current.path,
            newGoal: false,
            owned: true,
            followingPeerEvidence: false,
            releasedGoal: null,
            peerClaimsSeen: claims.size,
          };
      }
    }
    const released = this.localGoal;
    this.localGoal = null;
    if (!candidates.length) return { action: HOLD, kind: 'hold', reason: 'no-frontier' };

    const peerClaims = [...claims.values()];
    const sep = this.config.goalSeparationCells;
    let available = candidates.filter((c) => peerClaims.every((p) => manhattan(c.position, p) > sep));
    if (!available.length)
      available = candidates.filter((c) => !peerClaims.some((p) => p.x === c.position.x && p.y === c.position.y));
    if (!available.length) return { action: HOLD, kind: 'hold', reason: 'all-claimed' };

    const evidence = this.peerEvidencePositions(view);
    const acousticWeight = view.acoustic >= this.config.acousticInterestThreshold ? 0.15 : 0.05;
    const scored = available.map((c) => ({
      c,
      key: [
        evidence.length ? Math.min(...evidence.map((p) => manhattan(c.position, p))) : 0,
        c.distance - acousticWeight * c.clusterSize,
        c.distance,
        c.position.x,
        c.position.y,
      ],
    }));
    scored.sort((a, b) => {
      for (let i = 0; i < a.key.length; i++) if (a.key[i] !== b.key[i]) return a.key[i] - b.key[i];
      return 0;
    });
    const ranked = scored.map((s) => s.c);

    let chosen: FrontierCandidate;
    let owned = false;
    if (evidence.length) {
      chosen = ranked[0];
    } else {
      const participants = this.participants(view);
      const mine = ranked.filter((c) => branchOwner(c.position, participants) === view.name);
      if (mine.length) {
        chosen = mine[0];
        owned = true;
      } else {
        chosen = ranked[view.id % ranked.length];
      }
    }
    this.localGoal = { ...chosen.position };
    const path = astarPath(view.belief, view.position, chosen.position, { canCrossRubble: view.canCrossRubble });
    return {
      action: 0,
      kind: 'explore',
      goal: this.localGoal,
      path: path.length ? path : chosen.path,
      newGoal: true,
      owned,
      followingPeerEvidence: evidence.length > 0,
      releasedGoal: released,
      peerClaimsSeen: claims.size,
    };
  }

  /** Called by the robot itself when it reaches its goal cell. */
  goalReached(position: Point): void {
    if (this.localGoal && this.localGoal.x === position.x && this.localGoal.y === position.y) this.localGoal = null;
  }

  reset(): void {
    this.localGoal = null;
  }
}

/**
 * Thin per-tick orchestrator: asks each robot's brain to decide from its own
 * LocalView. Holds no shared assignment state.
 */
export class DecentralizedController {
  readonly brains = new Map<string, AgentBrain>();

  constructor(readonly config: ControllerConfig) {}

  brain(name: string): AgentBrain {
    let b = this.brains.get(name);
    if (!b) {
      b = new AgentBrain(name, this.config);
      this.brains.set(name, b);
    }
    return b;
  }

  decide(view: LocalView): Decision {
    return this.brain(view.name).decide(view);
  }
}
