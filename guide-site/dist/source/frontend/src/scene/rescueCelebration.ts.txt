/** Presentation-only clocks never change deterministic mission time. */
export const RESCUE_CELEBRATION_SECONDS = 2.2;

const starts = new WeakMap<object, Map<number, number>>();

/** A given survivor celebrates once, even if its scene component is remounted. */
export function rescueCelebrationStart(mission: object, survivor: number, now: number): number {
  let survivors = starts.get(mission);
  if (!survivors) {
    survivors = new Map();
    starts.set(mission, survivors);
  }
  const existing = survivors.get(survivor);
  if (existing !== undefined) return existing;
  survivors.set(survivor, now);
  return now;
}

export function rescueCelebrationProgress(start: number, now: number): number {
  return Math.min(1, Math.max(0, (now - start) / RESCUE_CELEBRATION_SECONDS));
}
