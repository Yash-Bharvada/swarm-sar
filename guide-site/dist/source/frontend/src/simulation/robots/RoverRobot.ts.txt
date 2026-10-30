import { ROBOT_CONFIGS, noiselessConfig } from '../core/config';
import type { RobotTypeConfig } from '../core/config';

/**
 * Rover: small wheeled ground robot. Shorter vision (4 cells) and comm radius (8),
 * larger battery, pays double energy on rubble (configs/robots.yaml `rover`).
 */
export function roverConfig(sensorNoise: boolean): RobotTypeConfig {
  return sensorNoise ? { ...ROBOT_CONFIGS.rover } : noiselessConfig(ROBOT_CONFIGS.rover);
}

export const ROVER_DESCRIPTION =
  'Ground rover: lidar-style 4-cell vision, 6-cell thermal, 10-cell acoustic, 8-cell radio, slow on rubble.';
