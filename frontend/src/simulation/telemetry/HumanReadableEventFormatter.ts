/** Converts raw simulation events into plain-language mission feed entries. */

export type SimEvent =
  | { type: 'mission_start'; robots: number; scenario: string }
  | { type: 'goal'; robot: string; owned: boolean; peerEvidence: boolean; distance: number }
  | { type: 'investigate'; robot: string; thermal: number; acoustic: number }
  | { type: 'survivor'; robot: string; victimId: number; found: number; total: number }
  | { type: 'map_shared'; from: string; to: string; cells: number; snapshot: boolean }
  | { type: 'merge_refused'; robot: string; from: string }
  | { type: 'isolated'; robot: string }
  | { type: 'rejoined'; robot: string }
  | { type: 'partition_on'; robots: string[] }
  | { type: 'partition_off'; robots: string[] }
  | { type: 'yield'; robots: string[] }
  | { type: 'blocked'; robot: string }
  | { type: 'no_frontier'; robot: string }
  | { type: 'battery_low'; robot: string }
  | { type: 'battery_depleted'; robot: string }
  | { type: 'manual'; robot: string; action: 'waypoint' | 'step' | 'stop' | 'scan' | 'take' | 'release' }
  | { type: 'complete'; reason: 'all_found' | 'timeout' | 'all_depleted'; found: number; total: number };

export type Tone = 'info' | 'success' | 'warning' | 'danger' | 'network';

export interface FeedItem {
  id: number;
  step: number;
  text: string;
  tone: Tone;
  robots: string[];
}

export function formatEvent(e: SimEvent, label: (name: string) => string): { text: string; tone: Tone; robots: string[] } {
  switch (e.type) {
    case 'mission_start':
      return { text: `Mission launched: ${e.robots} robots deployed into the ${e.scenario.toLowerCase()}.`, tone: 'info', robots: [] };
    case 'goal':
      if (e.peerEvidence)
        return { text: `${label(e.robot)} is heading towards a heat signal reported by a teammate.`, tone: 'info', robots: [e.robot] };
      return {
        text: e.owned
          ? `${label(e.robot)} is scanning an unexplored area it has taken responsibility for.`
          : `${label(e.robot)} is scanning an unexplored room.`,
        tone: 'info',
        robots: [e.robot],
      };
    case 'investigate':
      return {
        text:
          e.thermal >= 0.32
            ? `${label(e.robot)} detected a possible survivor heat signal and is investigating.`
            : `${label(e.robot)} heard faint sounds with a weak heat trace and is investigating.`,
        tone: 'warning',
        robots: [e.robot],
      };
    case 'survivor':
      return {
        text: `Survivor confirmed by ${label(e.robot)}. Rescue location marked (${e.found} of ${e.total}).`,
        tone: 'success',
        robots: [e.robot],
      };
    case 'map_shared':
      return {
        text: e.snapshot
          ? `${label(e.from)} re-sent part of its map so ${label(e.to)} can catch up.`
          : `${label(e.from)} shared a newly mapped safe corridor with ${label(e.to)}.`,
        tone: 'network',
        robots: [e.from, e.to],
      };
    case 'merge_refused':
      return {
        text: `${label(e.robot)} ignored map data from ${label(e.from)} because their positions were too uncertain to align.`,
        tone: 'warning',
        robots: [e.robot, e.from],
      };
    case 'isolated':
      return { text: `${label(e.robot)} temporarily lost network connection and continues on its own.`, tone: 'danger', robots: [e.robot] };
    case 'rejoined':
      return { text: `${label(e.robot)} is back in contact. Network restored; missed map updates are being shared.`, tone: 'network', robots: [e.robot] };
    case 'partition_on':
      return { text: `Radio partition: ${e.robots.map(label).join(', ')} cut off from the team.`, tone: 'danger', robots: e.robots };
    case 'partition_off':
      return { text: `Partition lifted for ${e.robots.map(label).join(', ')}.`, tone: 'network', robots: e.robots };
    case 'yield':
      return {
        text: `${e.robots.map(label).join(' and ')} moved through a narrow passage in single file.`,
        tone: 'info',
        robots: e.robots,
      };
    case 'blocked':
      return { text: `${label(e.robot)} avoided a blocked passage and is re-planning.`, tone: 'warning', robots: [e.robot] };
    case 'no_frontier':
      return { text: `${label(e.robot)} has no unexplored area left in its own map and is holding position.`, tone: 'info', robots: [e.robot] };
    case 'battery_low':
      return { text: `${label(e.robot)} battery below 20%.`, tone: 'warning', robots: [e.robot] };
    case 'battery_depleted':
      return { text: `${label(e.robot)} ran out of battery and has stopped.`, tone: 'danger', robots: [e.robot] };
    case 'manual': {
      const verbs = {
        waypoint: 'is driving to the operator waypoint',
        step: 'moved on operator command',
        stop: 'stopped on operator command',
        scan: 'is taking an extra sensor sample on operator command',
        take: 'is now under manual operator control',
        release: 'returned to autonomous operation',
      } as const;
      return { text: `${label(e.robot)} ${verbs[e.action]}.`, tone: 'info', robots: [e.robot] };
    }
    case 'complete':
      return {
        text:
          e.reason === 'all_found'
            ? `Mission complete. All ${e.total} survivors located.`
            : e.reason === 'timeout'
              ? `Mission time limit reached. ${e.found} of ${e.total} survivors found.`
              : `All robots out of battery. ${e.found} of ${e.total} survivors found.`,
        tone: e.reason === 'all_found' ? 'success' : 'warning',
        robots: [],
      };
  }
}

/** Plain-English description of a robot's current objective for the robot card. */
export function describeObjective(o: import('../robots/RobotState').Objective): string {
  switch (o.kind) {
    case 'idle':
      return 'Waiting for mission start';
    case 'explore':
      if (o.followingPeerEvidence) return 'Heading to a heat signal a teammate reported';
      return o.owned ? 'Exploring an unexplored branch it owns' : 'Exploring the nearest unexplored area';
    case 'investigate':
      return 'Investigating a possible survivor signal';
    case 'manual':
      return o.goal ? 'Driving to operator waypoint' : 'Awaiting operator command';
    case 'hold':
      return o.reason;
    case 'depleted':
      return 'Out of battery';
  }
}
