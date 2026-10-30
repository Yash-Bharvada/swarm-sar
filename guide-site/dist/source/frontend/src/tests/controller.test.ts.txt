import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { DEFAULT_CONTROLLER } from '../simulation/core/config';
import { SimulationEngine, defaultOptions } from '../simulation/core/SimulationEngine';
import { AgentBrain, branchOwner, shouldInvestigate } from '../simulation/controller/DecentralizedController';
import { GridMap, FREE, UNKNOWN } from '../simulation/world/GridMap';
import { INVESTIGATE } from '../simulation/core/types';

describe('DecentralizedController', () => {
  it('branch ownership is deterministic and reassigns a missing peer', () => {
    const position = { x: 41, y: 73 };
    const participants = ['drone_2', 'rover_0', 'rover_1'];
    const owner = branchOwner(position, participants);
    expect(branchOwner(position, participants)).toBe(owner);
    expect(branchOwner(position, [...participants].reverse())).toBe(owner);
    const remaining = participants.filter((p) => p !== owner);
    expect(remaining).toContain(branchOwner(position, remaining));
    // Removing a non-owner never moves the branch.
    const nonOwner = remaining[0];
    expect(branchOwner(position, participants.filter((p) => p !== nonOwner))).toBe(owner);
    // Coarse 8x8 keys: nearby frontier cells keep the same owner.
    expect(branchOwner({ x: 40, y: 72 }, participants)).toBe(owner);
    // Ownership spreads across the team rather than collapsing onto one robot.
    const owners = new Set<string>();
    for (let x = 0; x < 80; x += 8) for (let y = 0; y < 80; y += 8) owners.add(branchOwner({ x, y }, participants));
    expect(owners.size).toBe(3);
  });

  it('weak thermal requires independent acoustic corroboration', () => {
    expect(shouldInvestigate([0.18, 0, 0, 0], 0.05, DEFAULT_CONTROLLER)).toBe(false);
    expect(shouldInvestigate([0.18, 0, 0, 0], 0.25, DEFAULT_CONTROLLER)).toBe(true);
    expect(shouldInvestigate([0, 0.4, 0, 0], 0, DEFAULT_CONTROLLER)).toBe(true);
  });

  it('has no reservation table: each brain holds only its own goal', () => {
    const engine = new SimulationEngine(defaultOptions({ seed: 30 }));
    for (let i = 0; i < 5; i++) engine.tick();
    for (const brain of engine.controller.brains.values()) {
      expect(Object.keys(brain).sort()).toEqual(['config', 'localGoal', 'name']);
    }
    expect(engine.controller).not.toHaveProperty('reservations');
  });

  it('a brain decides from its own belief map and inbox only', () => {
    const belief = new GridMap(10, 10, UNKNOWN);
    for (let x = 0; x < 5; x++) belief.set(x, 5, FREE);
    const brain = new AgentBrain('rover_0', DEFAULT_CONTROLLER);
    const view = {
      name: 'rover_0',
      id: 0,
      type: 'rover' as const,
      position: { x: 0, y: 5 },
      odom: { x: 0, y: 5 },
      belief,
      canCrossRubble: true,
      batteryFraction: 1,
      thermal: [0, 0, 0, 0] as [number, number, number, number],
      acoustic: 0,
      peerMessages: [],
      adjacentRobots: [],
      networkEnabled: true,
      step: 0,
    };
    const d = brain.decide(view);
    expect(d.kind).toBe('explore');
    // Strong local heat switches to investigate.
    expect(brain.decide({ ...view, thermal: [0.5, 0, 0, 0] }).action).toBe(INVESTIGATE);
  });

  it('a peer claim with priority makes a robot release a duplicate goal', () => {
    const belief = new GridMap(12, 3, UNKNOWN);
    for (let x = 0; x < 6; x++) belief.set(x, 1, FREE);
    const brain = new AgentBrain('rover_1', DEFAULT_CONTROLLER);
    const base = {
      name: 'rover_1',
      id: 1,
      type: 'rover' as const,
      position: { x: 0, y: 1 },
      odom: { x: 0, y: 1 },
      belief,
      canCrossRubble: true,
      batteryFraction: 1,
      thermal: [0, 0, 0, 0] as [number, number, number, number],
      acoustic: 0,
      peerMessages: [],
      adjacentRobots: [],
      networkEnabled: true,
      step: 1,
    };
    const first = brain.decide(base);
    expect(first.kind).toBe('explore');
    const goal = brain.localGoal!;
    const claim = {
      senderId: 'drone_0',
      sequence: 0,
      frameId: 'common_entry_v1',
      sentStep: 1,
      expiresStep: 9,
      recipientId: null,
      kind: 'state_delta' as const,
      pose: [3, 1] as [number, number],
      poseUncertainty: 0,
      robotType: 'drone' as const,
      claimedGoal: [goal.x, goal.y] as [number, number],
      evidence: { thermal: 0, acoustic: 0, position: null },
      graphDelta: [],
      mapCells: [],
      isSnapshot: false,
      estimatedBytes: 0,
    };
    // 'drone_0' < 'rover_1', so rover_1 yields the identical goal.
    const second = brain.decide({ ...base, peerMessages: [claim] });
    expect(second.kind === 'explore' && second.goal.x === goal.x && second.goal.y === goal.y).toBe(false);
  });

  it('never selects a masked frontier action (next step occupied by a teammate)', () => {
    // Mirrors Python test_controller_never_selects_a_masked_policy_action.
    const engine = new SimulationEngine(defaultOptions({ seed: 33, packetLoss: 0.3 }));
    let checked = 0;
    for (let i = 0; i < 100 && !engine.done; i++) {
      for (const r of engine.robots) {
        if (!r.alive) continue;
        const view = engine.localView(r);
        const decision = new AgentBrain(`probe_${r.name}`, DEFAULT_CONTROLLER);
        decision.localGoal = engine.controller.brain(r.name).localGoal;
        const d = decision.decide({ ...view, name: r.name });
        if (d.kind !== 'explore' || d.path.length < 2) continue;
        const next = d.path[1];
        expect(view.adjacentRobots.some((p) => p.x === next.x && p.y === next.y)).toBe(false);
        expect(d.action).toBeGreaterThanOrEqual(0);
        expect(d.action).toBeLessThan(DEFAULT_CONTROLLER.maxFrontiers);
        checked++;
      }
      engine.tick();
    }
    expect(checked).toBeGreaterThan(100);
  });

  it('controller source never references truth data', () => {
    const path = fileURLToPath(new URL('../simulation/controller/DecentralizedController.ts', import.meta.url));
    const source = readFileSync(path, 'utf8');
    expect(source).not.toMatch(/victim/i);
    expect(source).not.toMatch(/WorldState|ScenarioGenerator|scenario/);
    expect(source).not.toMatch(/thermalReading|acousticReading|confirmVictims/);
  });
});
