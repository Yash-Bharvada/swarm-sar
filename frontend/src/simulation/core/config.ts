/**
 * Default parameters mirrored from the Python reference configuration:
 *   configs/robots.yaml  -> ROBOT_CONFIGS
 *   configs/sim.yaml     -> network_* keys in DEFAULT_NETWORK
 *   configs/network.yaml -> DEFAULT_CONTROLLER
 *   configs/world.yaml   -> DEFAULT_WORLD
 */
import type { RobotType } from './types';

export interface RobotTypeConfig {
  speed: number;
  visionRadius: number;
  thermalRadius: number;
  thermalDecay: number;
  thermalNoise: number;
  thermalDetectionProbability: number;
  thermalFalsePositiveRate: number;
  acousticRadius: number;
  acousticDecay: number;
  acousticNoise: number;
  acousticDetectionProbability: number;
  acousticFalsePositiveRate: number;
  acousticWallFactor: number;
  confirmRadius: number;
  battery: number;
  moveCost: number;
  rubbleCost: number;
  idleCost: number;
  canCrossRubble: boolean;
  canCrossWalls: boolean;
  commRadius: number;
  odometryDriftStd: number;
  odometryUncertaintyGrowth: number;
}

export const ROBOT_CONFIGS: Record<RobotType, RobotTypeConfig> = {
  rover: {
    speed: 1,
    visionRadius: 4,
    thermalRadius: 6,
    thermalDecay: 3.0,
    thermalNoise: 0.05,
    thermalDetectionProbability: 0.88,
    thermalFalsePositiveRate: 0.02,
    acousticRadius: 10,
    acousticDecay: 6.0,
    acousticNoise: 0.1,
    acousticDetectionProbability: 0.9,
    acousticFalsePositiveRate: 0.03,
    acousticWallFactor: 0.4,
    confirmRadius: 2,
    battery: 300,
    moveCost: 1.0,
    rubbleCost: 2.0,
    idleCost: 0.1,
    canCrossRubble: true,
    canCrossWalls: false,
    commRadius: 8,
    odometryDriftStd: 0.035,
    odometryUncertaintyGrowth: 0.01,
  },
  drone: {
    speed: 1,
    visionRadius: 7,
    thermalRadius: 8,
    thermalDecay: 4.0,
    thermalNoise: 0.07,
    thermalDetectionProbability: 0.92,
    thermalFalsePositiveRate: 0.025,
    acousticRadius: 12,
    acousticDecay: 7.0,
    acousticNoise: 0.12,
    acousticDetectionProbability: 0.92,
    acousticFalsePositiveRate: 0.035,
    acousticWallFactor: 0.5,
    confirmRadius: 2,
    battery: 240,
    moveCost: 1.0,
    rubbleCost: 1.0,
    idleCost: 0.1,
    canCrossRubble: true,
    canCrossWalls: false,
    commRadius: 10,
    odometryDriftStd: 0.05,
    odometryUncertaintyGrowth: 0.015,
  },
};

/** A noiseless sensor variant used when the operator disables sensor noise. */
export function noiselessConfig(config: RobotTypeConfig): RobotTypeConfig {
  return {
    ...config,
    thermalNoise: 0,
    thermalDetectionProbability: 1,
    thermalFalsePositiveRate: 0,
    acousticNoise: 0,
    acousticDetectionProbability: 1,
    acousticFalsePositiveRate: 0,
    odometryDriftStd: 0,
    odometryUncertaintyGrowth: 0,
  };
}

export interface PartitionWindow {
  start: number;
  end: number;
  agents: string[];
}

export interface NetworkConfig {
  enabled: boolean;
  packetLoss: number;
  delaySteps: [number, number];
  messageTtl: number;
  bandwidthBytes: number;
  wallAttenuation: number;
  requireLos: boolean;
  snapshotInterval: number;
  mapChunkCells: number;
  transformUncertaintyMax: number;
  partitionWindows: PartitionWindow[];
}

export const DEFAULT_NETWORK: NetworkConfig = {
  enabled: true,
  packetLoss: 0.0,
  delaySteps: [1, 2],
  messageTtl: 8,
  bandwidthBytes: 8192,
  wallAttenuation: 0.7,
  requireLos: false,
  snapshotInterval: 8,
  mapChunkCells: 64,
  transformUncertaintyMax: 4.0,
  partitionWindows: [],
};

export interface ControllerConfig {
  thermalInvestigateThreshold: number;
  thermalCorroborationThreshold: number;
  acousticInterestThreshold: number;
  peerEvidenceThreshold: number;
  goalSeparationCells: number;
  maxFrontiers: number;
  frontierSamplesPerCluster: number;
}

export const DEFAULT_CONTROLLER: ControllerConfig = {
  thermalInvestigateThreshold: 0.32,
  thermalCorroborationThreshold: 0.16,
  acousticInterestThreshold: 0.2,
  peerEvidenceThreshold: 0.35,
  goalSeparationCells: 3,
  maxFrontiers: 5,
  frontierSamplesPerCluster: 5,
};

export const DEFAULT_WORLD = {
  spawnSize: 4,
  victimMinDistFromSpawn: 8,
  victimMinDistBetween: 4,
  numVictims: [2, 4] as [number, number],
  rubblePatches: 5,
  rubblePatchRadius: [1, 3] as [number, number],
  maxGenerationRetries: 40,
};

/** Common-entry frame identifier shared by all agents (Python: "common_entry_v1"). */
export const FRAME_ID = 'common_entry_v1';
