import { rescueCelebrationProgress, rescueCelebrationStart, RESCUE_CELEBRATION_SECONDS } from '../scene/rescueCelebration';

describe('Rescue celebration lifecycle', () => {
  it('does not restart a survivor celebration when its visual is remounted', () => {
    const mission = {};
    const start = rescueCelebrationStart(mission, 1, 10);
    expect(rescueCelebrationStart(mission, 1, 11)).toBe(start);
    expect(rescueCelebrationStart(mission, 1, 30)).toBe(start);
    expect(rescueCelebrationProgress(start, 30)).toBe(1);
  });

  it('celebrates each newly confirmed survivor independently', () => {
    const mission = {};
    expect(rescueCelebrationStart(mission, 1, 10)).toBe(10);
    expect(rescueCelebrationStart(mission, 2, 11)).toBe(11);
    expect(rescueCelebrationStart(mission, 1, 12)).toBe(10);
  });

  it('allows a fresh mission to celebrate the same survivor id again', () => {
    expect(rescueCelebrationStart({}, 1, 10)).toBe(10);
    expect(rescueCelebrationStart({}, 1, 20)).toBe(20);
  });

  it('expires using wall time even when simulation time is paused', () => {
    const start = rescueCelebrationStart({}, 0, 100);
    expect(rescueCelebrationProgress(start, 100)).toBe(0);
    expect(rescueCelebrationProgress(start, 100 + RESCUE_CELEBRATION_SECONDS / 2)).toBeCloseTo(0.5);
    expect(rescueCelebrationProgress(start, 100 + RESCUE_CELEBRATION_SECONDS + 1)).toBe(1);
  });

  it('keeps progress bounded if a clock sample precedes the start or is long expired', () => {
    expect(rescueCelebrationProgress(10, 9)).toBe(0);
    expect(rescueCelebrationProgress(10, 10000)).toBe(1);
  });
});
