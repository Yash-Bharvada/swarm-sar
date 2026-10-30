import { DEFAULT_AUDIO_LEVELS, clampVolume, useAudio } from '../audio/audioStore';
import { EventSoundTracker } from '../audio/eventSounds';
import { Soundscape } from '../audio/Soundscape';
import { useSim } from '../store/simStore';
import type { SimEvent } from '../simulation/telemetry/HumanReadableEventFormatter';

const mission = () => ({ rawEvents: [] as { event: SimEvent }[] });
const found = (id = 0): SimEvent => ({ type: 'survivor', robot: 'rover_0', victimId: id, found: id + 1, total: 4 });
const shared = (to = 'drone_2'): SimEvent => ({ type: 'map_shared', from: 'rover_0', to, cells: 30, snapshot: false });

describe('Audio event routing', () => {
  it('does not play mission history on first observation or after a reset', () => {
    const tracker = new EventSoundTracker();
    const first = mission(); first.rawEvents.push({ event: found() });
    expect(tracker.read(first, null, 1)).toEqual([]);
    first.rawEvents.push({ event: found(1) });
    expect(tracker.read(first, null, 2)).toEqual(['survivor']);
    expect(tracker.read(first, null, 3)).toEqual([]);
    const replacement = mission(); replacement.rawEvents.push({ event: found() });
    expect(tracker.read(replacement, null, 4)).toEqual([]);
  });

  it('prioritizes a real survivor discovery and mission completion over packet chatter', () => {
    const tracker = new EventSoundTracker(), engine = mission();
    tracker.read(engine, null, 0);
    for (let i = 0; i < 100; i++) engine.rawEvents.push({ event: shared() });
    engine.rawEvents.push({ event: found() }, { event: found(1) }, { event: { type: 'complete', reason: 'all_found', found: 4, total: 4 } });
    expect(tracker.read(engine, null, 1)).toEqual(['survivor', 'complete']);
    expect(tracker.read(engine, null, 1.1)).toEqual([]);
  });

  it('coalesces packet traffic and rate-limits it without suppressing important discoveries', () => {
    const tracker = new EventSoundTracker(), engine = mission();
    tracker.read(engine, null, 0);
    engine.rawEvents.push({ event: shared() }, { event: shared() });
    expect(tracker.read(engine, null, 1)).toEqual(['map']);
    engine.rawEvents.push({ event: shared() });
    expect(tracker.read(engine, null, 1.2)).toEqual([]);
    engine.rawEvents.push({ event: found() });
    expect(tracker.read(engine, null, 1.3)).toEqual(['survivor']);
    engine.rawEvents.push({ event: shared() });
    expect(tracker.read(engine, null, 8)).toEqual(['map']);
  });

  it('does not create a backlog of suppressed events', () => {
    const tracker = new EventSoundTracker(), engine = mission();
    tracker.read(engine, null, 0);
    engine.rawEvents.push({ event: found() });
    tracker.read(engine, null, 1);
    engine.rawEvents.push({ event: found(1) });
    expect(tracker.read(engine, null, 1.1)).toEqual([]);
    expect(tracker.read(engine, null, 20)).toEqual([]);
  });

  it('filters distant robots’ routine activity when a unit is selected', () => {
    const tracker = new EventSoundTracker(), engine = mission();
    tracker.read(engine, 'drone_3', 0);
    engine.rawEvents.push({ event: shared() }, { event: { type: 'blocked', robot: 'rover_0' } });
    expect(tracker.read(engine, 'drone_3', 1)).toEqual([]);
    engine.rawEvents.push({ event: shared('drone_3') });
    expect(tracker.read(engine, 'drone_3', 2)).toEqual(['map']);
  });

  it('collapses many low-battery and radio alarms into restrained cues', () => {
    const tracker = new EventSoundTracker(), engine = mission();
    tracker.read(engine, null, 0);
    for (let i = 0; i < 10; i++) engine.rawEvents.push({ event: { type: 'battery_low', robot: `rover_${i}` } }, { event: { type: 'isolated', robot: `rover_${i}` } });
    expect(tracker.read(engine, null, 1)).toEqual(['warning', 'offline']);
    engine.rawEvents.push({ event: { type: 'battery_low', robot: 'rover_0' } });
    expect(tracker.read(engine, null, 2)).toEqual([]);
  });
});

describe('Sound preferences and simulation isolation', () => {
  const initial = useAudio.getState();
  afterEach(() => useAudio.setState(initial, true));

  it('does not construct an AudioContext or start autoplay at import', () => {
    const audio = new Soundscape();
    expect(audio.diagnostics()).toMatchObject({ state: 'not-created', activeVehicles: 0, activeTones: 0, scheduledBeat: 0 });
    expect(useAudio.getState().enabled).toBe(false);
    expect(DEFAULT_AUDIO_LEVELS.master).toBeLessThan(0.7);
  });

  it.each([[0.4, 0.4], [-1, 0], [3, 1], [NaN, 0], [Infinity, 0]])('bounds volume input %s to %s', (input, expected) => {
    expect(clampVolume(input)).toBe(expected);
  });

  it('keeps music, effects and vehicles independently adjustable', () => {
    const state = useAudio.getState();
    state.setVolume('music', 0);
    state.setVolume('vehicles', 0.2);
    expect(useAudio.getState().levels).toMatchObject({ music: 0, vehicles: 0.2, effects: initial.levels.effects, master: initial.levels.master });
  });

  it('leaves the deterministic simulation and command log unchanged', () => {
    const state = useSim.getState();
    const hash = state.engine.stateHash();
    const commands = state.engine.commandLog.slice();
    const audio = new Soundscape();
    useAudio.getState().setVolume('master', 0.3);
    audio.updateSpatial(10, -3, 1, 0, 12);
    audio.play('survivor');
    expect(audio.diagnostics().state).toBe('not-created');
    expect(state.engine.stateHash()).toBe(hash);
    expect(state.engine.commandLog).toEqual(commands);
  });
});
