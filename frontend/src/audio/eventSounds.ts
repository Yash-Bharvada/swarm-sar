import type { SimEvent } from '../simulation/telemetry/HumanReadableEventFormatter';

export type AudioCue = 'ui' | 'open' | 'close' | 'toggle' | 'zoom' | 'selectRover' | 'selectDrone' | 'focusRover' | 'focusDrone' | 'place' | 'remove' | 'launch' | 'pause' | 'resume' | 'reset' | 'survivor' | 'complete' | 'warning' | 'offline' | 'online' | 'scan' | 'waypoint' | 'blocked' | 'map' | 'explore' | 'depleted';

interface CueCandidate { cue: AudioCue; priority: number; cooldown: number }

function candidate(event: SimEvent, selected: string | null): CueCandidate | null {
  switch (event.type) {
    case 'survivor': return { cue: 'survivor', priority: 100, cooldown: 0.8 };
    case 'complete': return { cue: event.reason === 'all_found' ? 'complete' : 'depleted', priority: 95, cooldown: 2 };
    case 'battery_low': return { cue: 'warning', priority: 70, cooldown: 8 };
    case 'battery_depleted': return { cue: 'depleted', priority: 65, cooldown: 5 };
    case 'partition_on': case 'isolated': return { cue: 'offline', priority: 60, cooldown: 5 };
    case 'partition_off': case 'rejoined': return { cue: 'online', priority: 60, cooldown: 5 };
    case 'investigate': return { cue: 'scan', priority: 50, cooldown: 4 };
    case 'manual': return { cue: event.action === 'scan' ? 'scan' : event.action === 'waypoint' ? 'waypoint' : 'ui', priority: 35, cooldown: 0.4 };
    case 'blocked': return event.robot === selected ? { cue: 'blocked', priority: 20, cooldown: 2 } : null;
    case 'map_shared': return !selected || event.to === selected || event.from === selected ? { cue: 'map', priority: 10, cooldown: 6 } : null;
    case 'goal': return event.robot === selected ? { cue: 'explore', priority: 10, cooldown: 7 } : null;
    default: return null;
  }
}

/** Observe actual events once; never replay history when enabling audio or replacing a mission. */
export class EventSoundTracker {
  private engine: object | null = null;
  private cursor = 0;
  private last = new Map<AudioCue, number>();
  private lastBatch = -Infinity;

  read(engine: { rawEvents: Array<{ event: SimEvent }> }, selected: string | null, now: number): AudioCue[] {
    if (engine !== this.engine || engine.rawEvents.length < this.cursor) {
      this.engine = engine;
      this.cursor = engine.rawEvents.length;
      this.last.clear();
      this.lastBatch = -Infinity;
      return [];
    }
    const newest = engine.rawEvents.slice(this.cursor);
    this.cursor = engine.rawEvents.length;
    const choices = newest.map(({ event }) => candidate(event, selected)).filter((cue): cue is CueCandidate => cue !== null).sort((a, b) => b.priority - a.priority);
    const result: AudioCue[] = [];
    for (const choice of choices) {
      if (result.includes(choice.cue)) continue;
      if (now - (this.last.get(choice.cue) ?? -Infinity) < choice.cooldown) continue;
      if (choice.priority < 50 && now - this.lastBatch < 0.7) continue;
      result.push(choice.cue);
      this.last.set(choice.cue, now);
      if (result.length === 2) break;
    }
    if (result.length) this.lastBatch = now;
    return result;
  }
}
