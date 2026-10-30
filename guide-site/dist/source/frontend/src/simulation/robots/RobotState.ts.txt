/**
 * Robot state (Python robots/robot.py Robot).
 *
 * The truth position (x, y) is owned by the simulator for physics and sensor
 * simulation. Everything the controller may read lives in `RobotKnowledge`
 * (see DecentralizedController.ts), assembled from this robot's own fields only.
 */
import type { RobotTypeConfig } from '../core/config';
import type { Point, RobotType } from '../core/types';
import { GridMap, UNKNOWN } from '../world/GridMap';

export type Objective =
  | { kind: 'idle' }
  | { kind: 'explore'; goal: Point; owned: boolean; followingPeerEvidence: boolean }
  | { kind: 'investigate'; thermal: number }
  | { kind: 'manual'; goal: Point | null }
  | { kind: 'hold'; reason: string }
  | { kind: 'depleted' };

export interface RobotState {
  id: number;
  /** Python agent name, e.g. "rover_0", "drone_2". Used as network sender id. */
  name: string;
  /** Operator-facing label, e.g. "Rover 1", "Drone 2". */
  label: string;
  type: RobotType;
  config: RobotTypeConfig;
  x: number;
  y: number;
  battery: number;
  maxBattery: number;
  belief: GridMap;
  visited: Uint8Array;
  odomX: number;
  odomY: number;
  odomUncertainty: number;
  alive: boolean;
  lastAction: number;
  collided: boolean;
  distanceTravelled: number;
  /** Thermal intensity per sector: up, right, down, left. */
  thermal: [number, number, number, number];
  acoustic: number;
  prevThermal: [number, number, number, number];
  prevAcoustic: number;
  /** Local controller state. */
  activeGoal: Point | null;
  path: Point[];
  objective: Objective;
  heading: number;
  manual: boolean;
  manualGoal: Point | null;
  manualStep: number;
  newlyRevealed: number;
}

export function createRobot(
  id: number,
  type: RobotType,
  typeIndex: number,
  x: number,
  y: number,
  config: RobotTypeConfig,
  batteryScale: number,
  width: number,
  height: number,
): RobotState {
  const visited = new Uint8Array(width * height);
  visited[y * width + x] = 1;
  const battery = config.battery * batteryScale;
  return {
    id,
    name: `${type}_${id}`,
    label: `${type === 'rover' ? 'Rover' : 'Drone'} ${typeIndex + 1}`,
    type,
    config,
    x,
    y,
    battery,
    maxBattery: battery,
    belief: new GridMap(width, height, UNKNOWN),
    visited,
    odomX: x,
    odomY: y,
    odomUncertainty: 0,
    alive: true,
    lastAction: 0,
    collided: false,
    distanceTravelled: 0,
    thermal: [0, 0, 0, 0],
    acoustic: 0,
    prevThermal: [0, 0, 0, 0],
    prevAcoustic: 0,
    activeGoal: null,
    path: [],
    objective: { kind: 'idle' },
    heading: 0,
    manual: false,
    manualGoal: null,
    manualStep: 0,
    newlyRevealed: 0,
  };
}

export const position = (r: RobotState): Point => ({ x: r.x, y: r.y });

export const batteryFraction = (r: RobotState): number => (r.maxBattery > 0 ? r.battery / r.maxBattery : 0);
