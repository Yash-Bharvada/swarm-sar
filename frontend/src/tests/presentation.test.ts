import { useSim } from '../store/simStore';

const initialState = useSim.getState();

// Camera tests share the application store, so each case starts and ends with
// the same untouched engine and presentation state.
beforeEach(() => useSim.setState(initialState, true));
afterEach(() => useSim.setState(initialState, true));

describe('Simulation presentation', () => {
  it('opens with readable robot labels and unobstructed terrain', () => {
    const { overlays, settings, cameraView, cameraZoom, following } = useSim.getState();
    expect(overlays.labels).toBe(true);
    expect(overlays.coverage).toBe(false);
    expect(overlays.truth).toBe(false);
    expect(overlays.links || overlays.graph || overlays.packets || overlays.ranges || overlays.paths || overlays.evidence).toBe(false);
    expect(settings.fog).toBeLessThan(0.2);
    expect(cameraView).toBe('isometric');
    expect(cameraZoom).toBe(100);
    expect(following).toBe(false);
  });

  it('delivers every repeated zoom click as a distinct camera request', () => {
    const { moveCamera } = useSim.getState();
    moveCamera('zoomIn');
    const first = useSim.getState().cameraRequest!;
    moveCamera('zoomIn');
    const second = useSim.getState().cameraRequest!;
    moveCamera('zoomOut');
    const third = useSim.getState().cameraRequest!;
    expect(first.action).toBe('zoomIn');
    expect(second.action).toBe('zoomIn');
    expect(second.nonce).toBeGreaterThan(first.nonce);
    expect(third.action).toBe('zoomOut');
    expect(third.nonce).toBeGreaterThan(second.nonce);
  });

  it('switches between overhead and isometric views and restores isometric on reset', () => {
    const { moveCamera } = useSim.getState();
    moveCamera('top');
    expect(useSim.getState().cameraView).toBe('top');
    moveCamera('isometric');
    expect(useSim.getState().cameraView).toBe('isometric');
    moveCamera('top');
    moveCamera('reset');
    expect(useSim.getState().cameraView).toBe('isometric');
    expect(useSim.getState().cameraRequest?.action).toBe('reset');
  });

  it('lets an operator start and stop following the selected robot', () => {
    const state = useSim.getState();
    state.select(state.engine.robots[0].name);
    state.moveCamera('follow');
    expect(useSim.getState().following).toBe(true);
    state.moveCamera('follow');
    expect(useSim.getState().following).toBe(false);
  });

  it.each(['zoomIn', 'zoomOut', 'top', 'isometric', 'reset'] as const)('%s releases the robot-follow camera', (action) => {
    const state = useSim.getState();
    state.select(state.engine.robots[0].name);
    state.moveCamera('follow');
    state.moveCamera(action);
    expect(useSim.getState().following).toBe(false);
  });

  it('stops following when the selection changes or is cleared', () => {
    const state = useSim.getState();
    const [first, second] = state.engine.robots;
    state.select(first.name);
    state.moveCamera('follow');
    state.select(second.name);
    expect(useSim.getState().selected).toBe(second.name);
    expect(useSim.getState().following).toBe(false);
    state.moveCamera('follow');
    state.select(null);
    expect(useSim.getState().selected).toBeNull();
    expect(useSim.getState().following).toBe(false);
  });

  it('focuses a robot again after repeated clicks without enabling follow', () => {
    const state = useSim.getState();
    const robot = state.engine.robots[0].name;
    state.select(robot);
    state.moveCamera('follow');
    state.focusOn(robot);
    const first = useSim.getState().focus!;
    expect(useSim.getState().following).toBe(false);
    state.focusOn(robot);
    const second = useSim.getState().focus!;
    expect(second.robot).toBe(robot);
    expect(second.nonce).toBeGreaterThan(first.nonce);
    expect(useSim.getState().selected).toBe(robot);
  });

  it('updates the zoom readout without interrupting follow unless interaction cancels it', () => {
    const state = useSim.getState();
    state.select(state.engine.robots[0].name);
    state.moveCamera('follow');
    state.updateCamera(175);
    expect(useSim.getState().cameraZoom).toBe(175);
    expect(useSim.getState().following).toBe(true);
    state.updateCamera(180, false);
    expect(useSim.getState().cameraZoom).toBe(180);
    expect(useSim.getState().following).toBe(false);
  });

  it('clears robot camera targets when a mission is reset', () => {
    const state = useSim.getState();
    const robot = state.engine.robots[0].name;
    state.moveCamera('top');
    state.select(robot);
    state.focusOn(robot);
    state.moveCamera('follow');
    state.launch();
    state.reset();
    const resetState = useSim.getState();
    expect(resetState.status).toBe('ready');
    expect(resetState.selected).toBeNull();
    expect(resetState.focus).toBeNull();
    expect(resetState.cameraRequest).toBeNull();
    expect(resetState.following).toBe(false);
    expect(resetState.engine).not.toBe(state.engine);
  });

  it('does not enable robot follow without a selected robot', () => {
    const state = useSim.getState();
    expect(state.selected).toBeNull();
    state.moveCamera('follow');
    expect(useSim.getState().following).toBe(false);
  });

  it('clears camera targets when scenario settings regenerate the world', () => {
    const state = useSim.getState();
    const robot = state.engine.robots[0].name;
    state.moveCamera('top');
    state.select(robot);
    state.focusOn(robot);
    state.moveCamera('follow');
    state.setSetting('seed', state.settings.seed + 1);
    const next = useSim.getState();
    expect(next.engine).not.toBe(state.engine);
    expect(next.selected).toBeNull();
    expect(next.focus).toBeNull();
    expect(next.cameraRequest).toBeNull();
    expect(next.following).toBe(false);
  });

  it('clears camera targets when loading the validation scenario', () => {
    const state = useSim.getState();
    const robot = state.engine.robots[0].name;
    state.moveCamera('top');
    state.select(robot);
    state.focusOn(robot);
    state.moveCamera('follow');
    state.loadDemo();
    const next = useSim.getState();
    expect(next.demo).toBe(true);
    expect(next.engine).not.toBe(state.engine);
    expect(next.selected).toBeNull();
    expect(next.focus).toBeNull();
    expect(next.cameraRequest).toBeNull();
    expect(next.following).toBe(false);
  });

  it('keeps camera changes separate from deterministic mission state', () => {
    const state = useSim.getState();
    const before = state.engine.stateHash();
    const robot = state.engine.robots[0].name;
    state.select(robot);
    state.focusOn(robot);
    state.moveCamera('follow');
    state.moveCamera('zoomIn');
    state.moveCamera('top');
    state.updateCamera(130, false);
    expect(useSim.getState().engine).toBe(state.engine);
    expect(state.engine.stateHash()).toBe(before);
    expect(state.engine.commandLog).toHaveLength(0);
    expect(state.engine.step).toBe(0);
  });
});
