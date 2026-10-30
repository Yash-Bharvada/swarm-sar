import { DEFAULT_NETWORK, FRAME_ID, ROBOT_CONFIGS, type NetworkConfig } from '../simulation/core/config';
import type { RobotType } from '../simulation/core/types';
import { FREE, GridMap, WALL } from '../simulation/world/GridMap';
import { createRobot, type RobotState } from '../simulation/robots/RobotState';
import { PeerNetwork, type NetNode } from '../simulation/network/PeerNetwork';

export function node(name: string, type: RobotType, x: number, y: number): NetNode {
  return { name, type, x, y, alive: true, config: ROBOT_CONFIGS[type] };
}

export function netConfig(updates: Partial<NetworkConfig> = {}): NetworkConfig {
  return {
    ...DEFAULT_NETWORK,
    enabled: true,
    packetLoss: 0,
    delaySteps: [1, 1],
    messageTtl: 4,
    partitionWindows: [],
    ...updates,
  };
}

export function send(network: PeerNetwork, sender = 'rover_0', step = 0) {
  return network.broadcast(sender, step, {
    frameId: FRAME_ID,
    pose: [1, 1],
    poseUncertainty: 0.1,
    robotType: 'rover',
    claimedGoal: null,
    evidence: { thermal: 0, acoustic: 0, position: null },
    graphDelta: [],
    mapCells: [],
    isSnapshot: false,
  })!;
}

export function openGrid(width: number, height: number): GridMap {
  return new GridMap(width, height, FREE);
}

/** A one-cell-wide horizontal corridor along y = 1. */
export function corridor(length: number): GridMap {
  const g = new GridMap(length, 3, WALL);
  for (let x = 0; x < length; x++) g.set(x, 1, FREE);
  return g;
}

export function robotAt(id: number, type: RobotType, x: number, y: number, grid: GridMap): RobotState {
  return createRobot(id, type, id, x, y, { ...ROBOT_CONFIGS[type], odometryDriftStd: 0 }, 1, grid.width, grid.height);
}
