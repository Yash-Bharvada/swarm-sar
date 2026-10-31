import { describe, expect, it } from 'vitest';
import { clockProgressTime, rosObservatoryGrid, telemetryFresh } from '../observatory/useObservatory';
import type { RosGrid } from '../ros/transport';

const grid = (): RosGrid => ({ header: { frame_id: 'map' }, info: { width: 3, height: 2, resolution: .2, origin: { position: { x: -5, y: 7 }, orientation: { x: 0, y: 0, z: Math.SQRT1_2, w: Math.SQRT1_2 } } }, data: [-1, 0, 100, 50, 65, 1] });
describe('observatory telemetry boundaries', () => {
  it('converts only confirmed ROS occupancy while retaining exact metric geometry', () => {
    const input = grid(), copy = JSON.stringify(input), result = rosObservatoryGrid(input)!;
    expect(result.cells).toEqual([-1, 0, 1, -1, 1, -1]);
    expect(result.originX).toBe(-5); expect(result.originY).toBe(7);
    expect(result.resolution).toBe(.2); expect(result.yaw).toBeCloseTo(Math.PI / 2);
    expect(JSON.stringify(input)).toBe(copy);
  });
  it('rejects a wrong coordinate frame or impossible grid rather than plotting it', () => {
    expect(rosObservatoryGrid({ ...grid(), header: { frame_id: 'rover_0/map' } })).toBeNull();
    expect(rosObservatoryGrid({ ...grid(), data: [100] })).toBeNull();
    expect(rosObservatoryGrid({ ...grid(), data: [-1, 0, 101, 50, 65, 1] })).toBeNull();
    expect(rosObservatoryGrid(null)).toBeNull();
  });
  it('repeated paused clock heartbeats do not restart mission animation', () => {
    const initial = clockProgressTime(null, 10, 1000, 0);
    const paused = clockProgressTime(10, 10, 5000, initial);
    expect(paused).toBe(1000);
    expect(telemetryFresh(5000, paused, 1200)).toBe(false);
    expect(clockProgressTime(10, 10.1, 5001, paused)).toBe(5001);
  });
  it('does not mark absent, future, or disconnected-age samples as fresh', () => {
    expect(telemetryFresh(10000, 9000)).toBe(true);
    expect(telemetryFresh(10000, 0)).toBe(false);
    expect(telemetryFresh(10000, 10001)).toBe(false);
    expect(telemetryFresh(10000, 6999)).toBe(false);
  });
});
