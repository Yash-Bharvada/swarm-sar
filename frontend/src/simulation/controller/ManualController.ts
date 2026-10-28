/**
 * Operator control for a selected robot. Produces movement *intents* only; the
 * engine passes them through the same CollisionSafety shield and physics as
 * autonomous intents, so manual driving cannot cause overlap, swaps or wall
 * crossing.
 */
import { MOVE_DELTAS, movementAction, type Point } from '../core/types';
import { astarPath } from '../planning/AStar';
import type { RobotState } from '../robots/RobotState';
import { RUBBLE, WALL } from '../world/GridMap';

export interface ManualIntent {
  move: number;
  scan: boolean;
  path: Point[];
  goal: Point | null;
}

export class ManualController {
  private pendingStep = new Map<string, number>();
  private waypoints = new Map<string, Point>();
  private scans = new Set<string>();

  queueStep(robot: string, direction: number): void {
    this.waypoints.delete(robot);
    this.pendingStep.set(robot, direction);
  }

  setWaypoint(robot: string, target: Point): void {
    this.pendingStep.delete(robot);
    this.waypoints.set(robot, { ...target });
  }

  stop(robot: string): void {
    this.pendingStep.delete(robot);
    this.waypoints.delete(robot);
  }

  scan(robot: string): void {
    this.scans.add(robot);
  }

  waypoint(robot: string): Point | null {
    return this.waypoints.get(robot) ?? null;
  }

  /** Uses the robot's own belief map; unknown cells are optimistically passable. */
  intent(robot: RobotState): ManualIntent {
    const scan = this.scans.delete(robot.name);
    const step = this.pendingStep.get(robot.name);
    if (step !== undefined) {
      this.pendingStep.delete(robot.name);
      const [dx, dy] = MOVE_DELTAS[step];
      const target = { x: robot.x + dx, y: robot.y + dy };
      // Refuse steps into cells the robot itself has seen to be impassable.
      const known = robot.belief.inBounds(target.x, target.y) ? robot.belief.get(target.x, target.y) : WALL;
      if (known === WALL || (known === RUBBLE && !robot.config.canCrossRubble)) return { move: 0, scan, path: [], goal: null };
      return { move: step, scan, path: [{ x: robot.x, y: robot.y }, target], goal: null };
    }
    const goal = this.waypoints.get(robot.name);
    if (!goal) return { move: 0, scan, path: [], goal: null };
    if (goal.x === robot.x && goal.y === robot.y) {
      this.waypoints.delete(robot.name);
      return { move: 0, scan, path: [], goal: null };
    }
    const path = astarPath(robot.belief, robot, goal, {
      canCrossRubble: robot.config.canCrossRubble,
      optimisticUnknown: true,
    });
    if (path.length < 2) {
      this.waypoints.delete(robot.name);
      return { move: 0, scan, path: [], goal: null };
    }
    return { move: movementAction(robot, path[1]), scan, path, goal };
  }

  clear(): void {
    this.pendingStep.clear();
    this.waypoints.clear();
    this.scans.clear();
  }
}
