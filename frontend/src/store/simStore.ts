/**
 * UI state store. The SimulationEngine instance lives here but is mutated only
 * through engine.tick() and engine.issue(); React re-renders on `version`.
 */
import { create } from 'zustand';
import {
  SimulationEngine,
  defaultOptions,
  demoOptions,
  type Command,
  type EngineOptions,
} from '../simulation/core/SimulationEngine';
import type { MissionStatus, OperationMode } from '../simulation/core/types';
import { survivorPlacementCells, type PresetId } from '../simulation/world/ScenarioGenerator';
import type { Point } from '../simulation/core/types';

export type Quality = 'low' | 'medium' | 'high';
export type Speed = 0.5 | 1 | 2 | 4;
export type CameraAction = 'reset' | 'zoomIn' | 'zoomOut' | 'top' | 'isometric' | 'follow';

export interface Settings {
  preset: PresetId;
  seed: number;
  rovers: number;
  drones: number;
  packetLoss: number; // 0..0.3
  delayMax: number; // delay range is [1, delayMax]
  partition: boolean;
  sensorNoise: boolean;
  networkEnabled: boolean;
  fog: number; // 0..1
  quality: Quality;
  speed: Speed;
  mode: OperationMode;
  survivorCount: number | null;
}

export interface Overlays {
  links: boolean;
  graph: boolean;
  packets: boolean;
  ranges: boolean;
  paths: boolean;
  evidence: boolean;
  coverage: boolean;
  truth: boolean;
  netLog: boolean;
  labels: boolean;
}

/** Simulation ticks per second at 1x speed. One tick = one second of mission time. */
export const TICKS_PER_SECOND = 4;

/** Mutable render clock shared with the 3D scene (avoids React re-renders per frame). */
export const simClock = { alpha: 1, lastTickAt: 0 };

interface Store {
  encounter: { id: number; automatic: boolean } | null;
  encounterQueue: number[];
  announcedSurvivors: number[];
  encounterReturnStatus: MissionStatus;
  inspectSurvivor: (id: number) => void;
  continueExploration: () => void;
  settings: Settings;
  overlays: Overlays;
  engine: SimulationEngine;
  status: MissionStatus;
  selected: string | null;
  version: number;
  demo: boolean;
  /** Camera focus request: robot name plus a counter so repeat clicks re-trigger. */
  focus: { robot: string; nonce: number } | null;
  focusOn: (robot: string) => void;
  cameraRequest: { action: CameraAction; nonce: number } | null;
  cameraView: 'isometric' | 'top';
  cameraZoom: number;
  following: boolean;
  cleanView: boolean;
  toggleCleanView: () => void;
  editingSurvivors: boolean;
  survivorCapacity: number;
  survivorMessage: string | null;
  customSurvivors: Point[] | null;
  setSurvivorCount: (count: number) => void;
  randomizeSurvivors: () => void;
  setEditingSurvivors: (editing: boolean) => void;
  toggleSurvivorAt: (point: Point) => void;
  clearSurvivors: () => void;
  useAutomaticSurvivors: () => void;
  moveCamera: (action: CameraAction) => void;
  updateCamera: (zoom: number, following?: boolean) => void;
  setSetting: <K extends keyof Settings>(key: K, value: Settings[K]) => void;
  toggleOverlay: (key: keyof Overlays) => void;
  launch: () => void;
  pause: () => void;
  resume: () => void;
  reset: () => void;
  randomizeSeed: () => void;
  loadDemo: () => void;
  select: (name: string | null) => void;
  issue: (command: Command) => void;
  advance: (ticks: number) => void;
}

const initialSettings: Settings = {
  preset: 'office',
  seed: 7,
  rovers: 2,
  drones: 2,
  packetLoss: 0.05,
  delayMax: 2,
  partition: false,
  sensorNoise: true,
  networkEnabled: true,
  fog: 0.08,
  quality: 'medium',
  speed: 1,
  mode: 'autonomous',
  survivorCount: null,
};

function optionsFrom(s: Settings, demo: boolean, selected: string | null, customSurvivors: Point[] | null = null): EngineOptions {
  const base = demo ? demoOptions(s.seed) : defaultOptions({
    preset: s.preset,
    seed: s.seed,
    rovers: s.rovers,
    drones: s.drones,
    packetLoss: s.packetLoss,
    delaySteps: [1, s.delayMax],
    networkEnabled: s.networkEnabled,
    sensorNoise: s.sensorNoise,
    mode: s.mode,
    manualRobot: selected,
  });
  return {
    ...base,
    ...(demo ? { sensorNoise: s.sensorNoise, mode: s.mode, manualRobot: selected } : {}),
    ...(s.survivorCount !== null ? { survivorTargetCount: s.survivorCount } : {}),
    ...(customSurvivors !== null ? { survivorPositions: customSurvivors } : {}),
  };
}

/** Settings that only take effect on a fresh world. */
const WORLD_KEYS: Array<keyof Settings> = ['preset', 'seed', 'rovers', 'drones', 'sensorNoise', 'networkEnabled'];
const initialEngine = new SimulationEngine(optionsFrom(initialSettings, false, null));
const capacityOf = (engine: SimulationEngine) => survivorPlacementCells(engine.scenario).length;
const clearEncounters = { encounter: null, encounterQueue: [], announcedSurvivors: [], encounterReturnStatus: 'ready' as MissionStatus };
const clearCameraTarget = { ...clearEncounters, selected: null, focus: null, cameraRequest: null, following: false };

export const useSim = create<Store>((set, get) => ({
  ...clearEncounters,
  inspectSurvivor: (id) => {
    const state = get();
    if (state.encounter || !state.engine.discoveredSurvivors().some((v) => v.id === id)) return;
    set({ encounter: { id, automatic: false }, encounterReturnStatus: state.status,
      status: state.status === 'running' ? 'paused' : state.status, focus: null, following: false, cameraRequest: null });
  },
  continueExploration: () => {
    const state = get();
    if (!state.encounter) return;
    const [next, ...rest] = state.encounterQueue;
    if (next !== undefined) {
      set({ encounter: { id: next, automatic: true }, encounterQueue: rest });
      return;
    }
    get().moveCamera('reset');
    set({ encounter: null, status: state.engine.done ? 'complete' : state.encounterReturnStatus });
  },
  settings: initialSettings,
  overlays: {
    links: false,
    graph: false,
    packets: false,
    ranges: false,
    paths: false,
    evidence: false,
    coverage: false,
    truth: false,
    netLog: false,
    labels: true,
  },
  engine: initialEngine,
  status: 'ready',
  selected: null,
  version: 0,
  demo: false,
  focus: null,
  cameraRequest: null,
  cameraView: 'isometric',
  cameraZoom: 100,
  following: false,
  cleanView: false,
  toggleCleanView: () => {
    if (get().editingSurvivors) return;
    set({ cleanView: !get().cleanView });
  },
  editingSurvivors: false,
  survivorCapacity: capacityOf(initialEngine),
  survivorMessage: null,
  customSurvivors: null,
  focusOn: (robot) => {
    if (!get().engine.robots.some((unit) => unit.name === robot)) return;
    get().select(robot);
    set({ focus: { robot, nonce: (get().focus?.nonce ?? 0) + 1 }, cameraRequest: null, following: true });
  },
  moveCamera: (action) => set({
    cameraRequest: { action, nonce: (get().cameraRequest?.nonce ?? 0) + 1 },
    ...(action === 'top' || action === 'isometric' ? { cameraView: action } : {}),
    ...(action === 'reset' ? { cameraView: 'isometric' } : {}),
    following: action === 'follow' && get().selected !== null ? !get().following : false,
    focus: null,
  }),
  updateCamera: (zoom, following) => set({ cameraZoom: zoom, ...(following === undefined ? {} : { following }), ...(following === false ? { focus: null } : {}) }),

  setSurvivorCount: (count) => {
    const state = get();
    if (state.status !== 'ready') return;
    if (!Number.isSafeInteger(count) || count < 0 || count > state.survivorCapacity) {
      set({ survivorMessage: `Enter a whole number from 0 to ${state.survivorCapacity}.` });
      return;
    }
    const settings = { ...state.settings, survivorCount: count };
    set({ ...clearCameraTarget, settings, customSurvivors: null, engine: new SimulationEngine(optionsFrom(settings, state.demo, null)), survivorMessage: null, version: state.version + 1 });
  },
  randomizeSurvivors: () => {
    const state = get();
    if (state.status !== 'ready') return;
    const count = state.settings.survivorCount ?? state.engine.scenario.victims.length;
    const cells = survivorPlacementCells(state.engine.scenario);
    for (let i = cells.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [cells[i], cells[j]] = [cells[j], cells[i]];
    }
    const customSurvivors = cells.slice(0, count);
    const settings = { ...state.settings, survivorCount: count };
    set({ ...clearCameraTarget, settings, customSurvivors, engine: new SimulationEngine(optionsFrom(settings, state.demo, null, customSurvivors)), survivorMessage: null, version: state.version + 1 });
  },
  setEditingSurvivors: (editing) => {
    const state = get();
    if (state.status !== 'ready') return;
    if (!editing) { set({ editingSurvivors: false, survivorMessage: null }); return; }
    const customSurvivors = state.engine.scenario.victims.map(({ x, y }) => ({ x, y }));
    const settings = { ...state.settings, survivorCount: customSurvivors.length };
    set({ ...clearCameraTarget, cleanView: false, settings, customSurvivors, editingSurvivors: true, engine: new SimulationEngine(optionsFrom(settings, state.demo, null, customSurvivors)), survivorMessage: 'Click a reachable tile to add or remove a survivor.', version: state.version + 1 });
  },
  toggleSurvivorAt: (point) => {
    const state = get();
    if (state.status !== 'ready' || !state.editingSurvivors) return;
    const eligible = survivorPlacementCells(state.engine.scenario).some(({ x, y }) => x === point.x && y === point.y);
    if (!eligible) { set({ survivorMessage: 'Choose a reachable tile outside the robot staging area.' }); return; }
    const current = state.customSurvivors ?? state.engine.scenario.victims.map(({ x, y }) => ({ x, y }));
    const present = current.some(({ x, y }) => x === point.x && y === point.y);
    const customSurvivors = present ? current.filter(({ x, y }) => x !== point.x || y !== point.y) : [...current, { ...point }];
    const settings = { ...state.settings, survivorCount: customSurvivors.length };
    set({ ...clearCameraTarget, settings, customSurvivors, engine: new SimulationEngine(optionsFrom(settings, state.demo, null, customSurvivors)), survivorMessage: `${present ? 'Removed' : 'Placed'} survivor at (${point.x}, ${point.y}).`, version: state.version + 1 });
  },
  clearSurvivors: () => {
    const state = get();
    if (state.status !== 'ready') return;
    const settings = { ...state.settings, survivorCount: 0 };
    set({ ...clearCameraTarget, settings, customSurvivors: [], engine: new SimulationEngine(optionsFrom(settings, state.demo, null, [])), survivorMessage: 'Add a survivor before launching.', version: state.version + 1 });
  },
  useAutomaticSurvivors: () => {
    const state = get();
    if (state.status !== 'ready') return;
    const settings = { ...state.settings, survivorCount: null };
    set({ ...clearCameraTarget, settings, customSurvivors: null, editingSurvivors: false, engine: new SimulationEngine(optionsFrom(settings, state.demo, null)), survivorMessage: null, version: state.version + 1 });
  },

  setSetting: (key, value) => {
    if (key === 'survivorCount') {
      if (value === null) get().useAutomaticSurvivors();
      else get().setSurvivorCount(value as number);
      return;
    }
    const { settings, status, engine, selected } = get();
    const next = { ...settings, [key]: value };
    if (key === 'rovers' || key === 'drones') {
      const total = next.rovers + next.drones;
      if (total < 1 || total > 10) return;
    }
    if (WORLD_KEYS.includes(key)) {
      if (status !== 'ready') return;
      const demo = key === 'preset' ? false : get().demo;
      const terrainChanged = key === 'preset' || key === 'seed';
      const nextSettings = terrainChanged ? { ...next, survivorCount: null } : next;
      const customSurvivors = terrainChanged ? null : get().customSurvivors;
      const nextEngine = new SimulationEngine(optionsFrom(nextSettings, demo, null, customSurvivors));
      set({ settings: nextSettings, demo, customSurvivors, editingSurvivors: terrainChanged ? false : get().editingSurvivors, survivorCapacity: capacityOf(nextEngine), survivorMessage: null, engine: nextEngine, selected: null, focus: null, cameraRequest: null, following: false, version: get().version + 1 });
      return;
    }
    set({ settings: next });
    // Live network/mode settings become recorded engine commands.
    if (key === 'packetLoss') engine.issue({ kind: 'setPacketLoss', value: value as number });
    if (key === 'delayMax') engine.issue({ kind: 'setDelay', value: [1, value as number] });
    if (key === 'partition') {
      const target = selected ?? engine.robots[0]?.name;
      engine.issue({ kind: 'setPartition', on: value as boolean, robots: target ? [target] : [] });
    }
    if (key === 'mode') {
      const manualRobot = selected ?? (value === 'autonomous' ? null : engine.robots[0]?.name ?? null);
      if (value !== 'autonomous' && !selected && manualRobot) set({ selected: manualRobot });
      // Before launch the command stays queued and applies on the first tick.
      engine.issue({ kind: 'setMode', mode: value as OperationMode, manualRobot });
    }
    set({ version: get().version + 1 });
  },

  toggleOverlay: (key) => set({ overlays: { ...get().overlays, [key]: !get().overlays[key] } }),

  launch: () => {
    if (get().status === 'ready') {
      if (!get().engine.scenario.victims.length) { set({ survivorMessage: 'Add at least one survivor before launching.' }); return; }
      set({ status: 'running', editingSurvivors: false, survivorMessage: null });
    }
  },
  pause: () => {
    if (get().status === 'running') set({ status: 'paused' });
  },
  resume: () => {
    if (get().status === 'paused' && !get().encounter) set({ status: 'running' });
  },
  reset: () => {
    const { settings, demo, customSurvivors } = get();
    const engine = new SimulationEngine(optionsFrom({ ...settings, partition: false, mode: settings.mode }, demo, null, customSurvivors));
    set({
      ...clearEncounters,
      engine,
      status: 'ready',
      selected: null,
      following: false,
      focus: null,
      cameraRequest: null,
      settings: { ...settings, partition: false },
      survivorCapacity: capacityOf(engine),
      editingSurvivors: false,
      survivorMessage: null,
      version: get().version + 1,
    });
  },
  randomizeSeed: () => {
    if (get().status !== 'ready') return;
    get().setSetting('seed', Math.floor(Math.random() * 100000));
  },
  loadDemo: () => {
    const settings: Settings = {
      ...get().settings,
      preset: 'demo',
      seed: 11,
      rovers: 2,
      drones: 2,
      packetLoss: 0.15,
      delayMax: 3,
      partition: false,
      networkEnabled: true,
      mode: 'autonomous',
      survivorCount: null,
    };
    const engine = new SimulationEngine(optionsFrom(settings, true, null));
    set({
      ...clearEncounters,
      settings,
      demo: true,
      engine,
      customSurvivors: null,
      editingSurvivors: false,
      survivorCapacity: capacityOf(engine),
      survivorMessage: null,
      status: 'ready',
      selected: null,
      version: get().version + 1,
      focus: null,
      following: false,
      cameraRequest: null,
    });
  },
  select: (name) => {
    const { engine, settings, following, focus } = get();
    if (name !== null && !engine.robots.some((robot) => robot.name === name)) return;
    const keepFollowing = following && name !== null;
    set({ selected: name, following: keepFollowing, focus: keepFollowing ? { robot: name, nonce: (focus?.nonce ?? 0) + 1 } : null });
    // In mixed mode the selected robot becomes the manually driven one.
    if (settings.mode === 'mixed' && name) engine.issue({ kind: 'setMode', mode: 'mixed', manualRobot: name });
    if (settings.mode === 'manual' && name) engine.issue({ kind: 'setMode', mode: 'manual', manualRobot: name });
    set({ version: get().version + 1 });
  },
  issue: (command) => {
    get().engine.issue(command);
  },
  advance: (ticks) => {
    const { engine, status } = get();
    if (status !== 'running' || ticks <= 0) return;
    const announced = new Set(get().announcedSurvivors);
    for (let i = 0; i < ticks && !engine.done; i++) {
      engine.tick();
      const fresh = engine.discoveredSurvivors().filter((victim) => !announced.has(victim.id)).map((v) => v.id);
      if (fresh.length) {
        set({ encounter: { id: fresh[0], automatic: true }, encounterQueue: fresh.slice(1),
          announcedSurvivors: [...get().announcedSurvivors, ...fresh], encounterReturnStatus: 'running',
          focus: null, following: false, cameraRequest: null, status: 'paused', version: get().version + 1 });
        simClock.alpha = 1;
        return;
      }
    }
    set({ version: get().version + 1, status: engine.done ? 'complete' : 'running' });
  },
}));
