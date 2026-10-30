import { ROBOT_CONFIGS, noiselessConfig } from '../core/config';
import type { RobotTypeConfig } from '../core/config';

/**
 * Drone: 2D aerial proxy (configs/robots.yaml `drone`). Wider vision (7 cells) and
 * radio (10), smaller battery, cheap rubble traversal. Like the Python Step 4
 * simulator it still obeys walls (`canCrossWalls: false`); its altitude is visual only.
 */
export function droneConfig(sensorNoise: boolean): RobotTypeConfig {
  return sensorNoise ? { ...ROBOT_CONFIGS.drone } : noiselessConfig(ROBOT_CONFIGS.drone);
}

export const DRONE_DESCRIPTION =
  'Quadcopter proxy: 7-cell vision, 8-cell thermal, 12-cell acoustic, 10-cell radio. Flies over rubble, never through walls.';
