/**
 * Noisy thermal/acoustic sensing and survivor confirmation (Python sensing/victim_sensor.py).
 *
 * These functions are the simulator's *sensor emulation*: they read the truth
 * survivor list to produce noisy readings. The controller only ever sees the
 * resulting numbers stored on the robot, never the survivor list.
 */
import type { Rng } from '../core/Rng';
import type { RobotTypeConfig } from '../core/config';
import type { Point } from '../core/types';
import type { GridMap } from '../world/GridMap';
import type { Victim } from '../world/ScenarioGenerator';
import type { RobotState } from '../robots/RobotState';
import { hasLineOfSight } from './Vision';

export type Sectors = [number, number, number, number];

/** Return thermal signal in up, right, down, left sectors. */
export function thermalReading(
  robot: RobotState,
  victims: Victim[],
  grid: GridMap,
  config: RobotTypeConfig,
  rng: Rng,
): Sectors {
  const values: Sectors = [0, 0, 0, 0];
  for (const victim of victims) {
    if (victim.found) continue;
    const dx = victim.x - robot.x;
    const dy = victim.y - robot.y;
    const distance = Math.hypot(dx, dy);
    if (distance > config.thermalRadius || !hasLineOfSight(grid, robot, victim)) continue;
    if (rng.random() > config.thermalDetectionProbability) continue;
    let sector: number;
    if (Math.abs(dy) >= Math.abs(dx)) sector = dy <= 0 ? 0 : 2;
    else sector = dx > 0 ? 1 : 3;
    values[sector] += Math.exp(-distance / config.thermalDecay);
  }
  if (rng.random() < config.thermalFalsePositiveRate) values[rng.integers(4)] += rng.uniform(0.1, 0.4);
  for (let i = 0; i < 4; i++) values[i] = Math.max(0, values[i] + rng.normal(0, config.thermalNoise));
  return values;
}

/** One omnidirectional acoustic value; walls attenuate rather than block. */
export function acousticReading(
  robot: RobotState,
  victims: Victim[],
  grid: GridMap,
  config: RobotTypeConfig,
  rng: Rng,
): number {
  let total = 0;
  for (const victim of victims) {
    if (victim.found) continue;
    const distance = Math.hypot(victim.x - robot.x, victim.y - robot.y);
    if (distance > config.acousticRadius) continue;
    if (rng.random() > config.acousticDetectionProbability) continue;
    let signal = Math.exp(-distance / config.acousticDecay);
    if (!hasLineOfSight(grid, robot, victim)) signal *= config.acousticWallFactor;
    total += signal;
  }
  if (rng.random() < config.acousticFalsePositiveRate) total += rng.uniform(0.1, 0.4);
  total += rng.normal(0, config.acousticNoise);
  return Math.max(0, total);
}

export function updateRobotSensors(
  robot: RobotState,
  victims: Victim[],
  grid: GridMap,
  rng: Rng,
  preservePrevious = true,
): void {
  if (preservePrevious) {
    robot.prevThermal = [...robot.thermal] as Sectors;
    robot.prevAcoustic = robot.acoustic;
  }
  robot.thermal = thermalReading(robot, victims, grid, robot.config, rng);
  robot.acoustic = acousticReading(robot, victims, grid, robot.config, rng);
}

/**
 * Truth-side confirmation sensor: an investigating robot within confirm radius
 * and line of sight confirms a survivor (Python confirm_victims).
 */
export function confirmVictims(robots: RobotState[], victims: Victim[], grid: GridMap, step: number): Victim[] {
  const newly: Victim[] = [];
  for (const victim of victims) {
    if (victim.found) continue;
    for (const robot of robots) {
      if (!robot.alive) continue;
      const distance = Math.hypot(victim.x - robot.x, victim.y - robot.y);
      if (distance <= robot.config.confirmRadius && hasLineOfSight(grid, robot, victim)) {
        victim.found = true;
        victim.foundBy = robot.name;
        victim.foundStep = step;
        newly.push(victim);
        break;
      }
    }
  }
  return newly;
}

export const maxThermal = (t: Sectors): number => Math.max(t[0], t[1], t[2], t[3]);

export function argmaxSector(t: Sectors): number {
  let best = 0;
  for (let i = 1; i < 4; i++) if (t[i] > t[best]) best = i;
  return best;
}

/**
 * Estimate where the thermal source is, from the robot's own odometry and its
 * strongest sector (Python env._evidence_position). Uses no truth data.
 */
export function evidencePosition(robot: RobotState): Point | null {
  const strength = maxThermal(robot.thermal);
  if (strength <= 0) return null;
  const sector = argmaxSector(robot.thermal);
  const c = robot.config;
  const distance = Math.min(
    c.thermalRadius,
    Math.max(1, -c.thermalDecay * Math.log(Math.max(1e-4, Math.min(0.999, strength)))),
  );
  const [dx, dy] = ([
    [0, -1],
    [1, 0],
    [0, 1],
    [-1, 0],
  ] as const)[sector];
  return { x: Math.round(robot.odomX + dx * distance), y: Math.round(robot.odomY + dy * distance) };
}
