import { describe, expect, it } from 'vitest';
import { cellWorld, rosBridgeUrlError, validGrid, type RosGrid } from '../ros/transport';

const grid = (): RosGrid => ({ header: { frame_id: 'map' }, info: { width: 2, height: 1, resolution: 1, origin: { position: { x: 3, y: 1 }, orientation: { x: 0, y: 0, z: Math.SQRT1_2, w: Math.SQRT1_2 } } }, data: [100, 0] });
describe('real ROS occupancy geometry', () => {
  it('honors rotated origins in mission meters', () => {
    const [x, y] = cellWorld(grid(), 1, 0);
    expect(x).toBeCloseTo(2.5); expect(y).toBeCloseTo(2.5);
  });
  it('rejects misaligned frames, malformed shape and impossible occupancy', () => {
    expect(validGrid(grid())).toBe(true);
    expect(validGrid({ ...grid(), header: { frame_id: 'rover_0/map' } })).toBe(false);
    expect(validGrid({ ...grid(), data: [0] })).toBe(false);
    expect(validGrid({ ...grid(), data: [0, 300] })).toBe(false);
    expect(validGrid({ ...grid(), info: { ...grid().info, resolution: NaN } })).toBe(false);
  });
  it('explains invalid, portless, and mixed-content bridge URLs', () => {
    expect(rosBridgeUrlError('localhost:9090', 'http:')).toContain('ws://');
    expect(rosBridgeUrlError('ws://localhost', 'http:')).toContain('port');
    expect(rosBridgeUrlError('ws://localhost:9090', 'https:')).toContain('wss://');
    expect(rosBridgeUrlError('ws://localhost:9090', 'http:')).toBeNull();
    expect(rosBridgeUrlError('wss://robots.example:443', 'https:')).toBeNull();
  });
});
