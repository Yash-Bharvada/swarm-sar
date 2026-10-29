import { useAudio } from './audioStore';
import type { AudioCue } from './eventSounds';
import type { RobotState } from '../simulation/robots/RobotState';

const CHORDS = [
  [146.832, 220, 277.183, 329.628],
  [123.471, 185, 246.942, 293.665],
  [97.999, 195.998, 246.942, 293.665],
  [110, 220, 293.665, 329.628],
];
const MELODIES = [[587.33, 659.25, 739.99, 880], [493.88, 587.33, 739.99, 659.25], [587.33, 739.99, 987.77, 880], [659.25, 587.33, 880, 739.99]];
const BEAT = 60 / 68;

function smooth(param: AudioParam, value: number, time: number, fade = 0.12) {
  param.setTargetAtTime(value, time, fade);
}

function noiseBuffer(context: BaseAudioContext, seconds: number, decay = false): AudioBuffer {
  const buffer = context.createBuffer(decay ? 2 : 1, Math.ceil(context.sampleRate * seconds), context.sampleRate);
  let seed = 24891;
  for (let channel = 0; channel < buffer.numberOfChannels; channel++) {
    const data = buffer.getChannelData(channel);
    let previous = 0;
    for (let i = 0; i < data.length; i++) {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
      previous = previous * 0.6 + (seed / 4294967296 * 2 - 1) * 0.4;
      data[i] = previous * (decay ? Math.pow(1 - i / data.length, 2.4) : 1);
    }
  }
  return buffer;
}

class VehicleVoice {
  private main: GainNode;
  private pan: StereoPannerNode;
  private motor: OscillatorNode;
  private harmonic: OscillatorNode;
  private sources: AudioScheduledSourceNode[];
  private nodes: AudioNode[];

  constructor(private context: AudioContext, bus: AudioNode, noise: AudioBuffer, private drone: boolean) {
    const main = context.createGain(); main.gain.value = 0;
    const pan = context.createStereoPanner();
    const filter = context.createBiquadFilter(); filter.type = 'lowpass'; filter.frequency.value = drone ? 950 : 620; filter.Q.value = 0.45;
    const motor = context.createOscillator(); motor.type = drone ? 'sawtooth' : 'triangle'; motor.frequency.value = drone ? 116 : 58;
    const harmonic = context.createOscillator(); harmonic.type = 'sine'; harmonic.frequency.value = drone ? 231 : 87;
    const harmonicGain = context.createGain(); harmonicGain.gain.value = 0.18;
    const air = context.createBufferSource(); air.buffer = noise; air.loop = true;
    const airFilter = context.createBiquadFilter(); airFilter.type = 'bandpass'; airFilter.frequency.value = drone ? 720 : 300; airFilter.Q.value = 0.55;
    const airGain = context.createGain(); airGain.gain.value = drone ? 0.34 : 0.55;
    const rotor = context.createOscillator(); rotor.frequency.value = drone ? 23 : 11;
    const rotorGain = context.createGain(); rotorGain.gain.value = drone ? 7 : 2.5;
    motor.connect(filter); harmonic.connect(harmonicGain).connect(filter);
    air.connect(airFilter).connect(airGain).connect(filter);
    rotor.connect(rotorGain).connect(motor.frequency);
    filter.connect(main).connect(pan).connect(bus);
    this.main = main; this.pan = pan; this.motor = motor; this.harmonic = harmonic;
    this.sources = [motor, harmonic, air, rotor];
    this.nodes = [main, pan, filter, motor, harmonic, harmonicGain, air, airFilter, airGain, rotor, rotorGain];
    this.sources.forEach((source) => source.start());
  }

  update(level: number, pan: number, moving: boolean) {
    const time = this.context.currentTime;
    smooth(this.main.gain, level, time);
    smooth(this.pan.pan, pan, time);
    smooth(this.motor.frequency, this.drone ? moving ? 142 : 116 : moving ? 83 : 49, time, 0.17);
    smooth(this.harmonic.frequency, this.drone ? moving ? 283 : 231 : moving ? 124 : 73.5, time, 0.17);
  }

  dispose() {
    this.main.gain.cancelScheduledValues(this.context.currentTime);
    this.main.gain.setTargetAtTime(0, this.context.currentTime, 0.015);
    const end = this.context.currentTime + 0.08;
    this.sources.forEach((source) => { try { source.stop(end); } catch { /* Already stopped. */ } });
    this.motor.onended = () => this.nodes.forEach((node) => node.disconnect());
  }
}

interface Tone { frequency: number; offset: number; duration: number; volume: number; wave?: OscillatorType; endFrequency?: number }

/** Original synthesized soundtrack and effects: no downloads, external assets or simulation RNG. */
export class Soundscape {
  private context: AudioContext | null = null;
  private master: GainNode | null = null;
  private music: GainNode | null = null;
  private effects: GainNode | null = null;
  private vehicles: GainNode | null = null;
  private analyser: AnalyserNode | null = null;
  private noise: AudioBuffer | null = null;
  private voices = new Map<number, VehicleVoice>();
  private mission: object | null = null;
  private nextBeat = 0;
  private beat = 0;
  private duckUntil = 0;
  private active = new Set<OscillatorNode>();
  private lastCue = new Map<AudioCue, number>();
  private played = new Map<AudioCue, number>();
  private listener = { x: 0, z: 0, rightX: 1, rightZ: 0, radius: 20 };

  async enable(): Promise<void> {
    try {
      if (!this.context) this.initialize();
      if (this.context!.state === 'closed') throw new Error('Audio context closed');
      const context = this.context!;
      await context.resume();
      if (this.context !== context) return;
      useAudio.setState({ enabled: true, muted: false, error: null });
      this.applyLevels();
      this.play('open');
    } catch {
      useAudio.setState({ enabled: false, error: 'Sound is unavailable. Check browser audio permissions and try again.' });
    }
  }

  toggleMute() {
    if (!useAudio.getState().enabled) { void this.enable(); return; }
    useAudio.setState({ muted: !useAudio.getState().muted });
    if (!useAudio.getState().muted && this.context?.state === 'suspended' && !document.hidden) void this.context.resume().catch(() => {});
    this.applyLevels();
  }

  private initialize() {
    const context = new AudioContext({ latencyHint: 'interactive' });
    this.context = context;
    this.master = context.createGain(); this.master.gain.value = 0;
    this.music = context.createGain(); this.music.gain.value = 0;
    this.effects = context.createGain(); this.effects.gain.value = 0;
    this.vehicles = context.createGain(); this.vehicles.gain.value = 0;
    const limiter = context.createDynamicsCompressor();
    limiter.threshold.value = -14; limiter.knee.value = 18; limiter.ratio.value = 6; limiter.attack.value = 0.006; limiter.release.value = 0.25;
    this.analyser = context.createAnalyser(); this.analyser.fftSize = 1024;
    this.master.connect(limiter).connect(this.analyser).connect(context.destination);
    this.music.connect(this.master); this.effects.connect(this.master); this.vehicles.connect(this.master);
    const reverb = context.createConvolver(); reverb.buffer = noiseBuffer(context, 1.8, true);
    const wet = context.createGain(); wet.gain.value = 0.32;
    const musicSend = context.createGain(); musicSend.gain.value = 0.35;
    const effectSend = context.createGain(); effectSend.gain.value = 0.18;
    this.music.connect(musicSend).connect(reverb); this.effects.connect(effectSend).connect(reverb);
    reverb.connect(wet).connect(this.master);
    this.noise = noiseBuffer(context, 2);
    this.nextBeat = context.currentTime + 0.08;
    this.beat = 0;
  }

  applyLevels() {
    const context = this.context;
    if (!context || !this.master || !this.music || !this.effects || !this.vehicles) return;
    const { enabled, muted, levels } = useAudio.getState();
    smooth(this.master.gain, enabled && !muted ? levels.master : 0, context.currentTime, 0.055);
    smooth(this.music.gain, levels.music * (context.currentTime < this.duckUntil ? 0.48 : 1), context.currentTime, 0.22);
    smooth(this.effects.gain, levels.effects, context.currentTime, 0.055);
    smooth(this.vehicles.gain, levels.vehicles, context.currentTime, 0.12);
  }

  private tone(bus: AudioNode, note: Tone, when: number, bell = false) {
    const context = this.context!;
    if (this.active.size >= 96) return;
    const oscillator = context.createOscillator(); oscillator.type = note.wave ?? 'sine';
    oscillator.frequency.setValueAtTime(note.frequency, when);
    if (note.endFrequency) oscillator.frequency.exponentialRampToValueAtTime(note.endFrequency, when + note.duration);
    const envelope = context.createGain();
    const attack = bell ? 0.012 : Math.min(0.025, note.duration * 0.2);
    envelope.gain.setValueAtTime(0, when);
    envelope.gain.linearRampToValueAtTime(note.volume, when + attack);
    envelope.gain.exponentialRampToValueAtTime(0.0001, when + note.duration);
    const filter = context.createBiquadFilter(); filter.type = 'lowpass'; filter.frequency.value = bell ? 3000 : 1700;
    oscillator.connect(envelope).connect(filter).connect(bus);
    oscillator.start(when); oscillator.stop(when + note.duration + 0.03);
    this.active.add(oscillator);
    oscillator.onended = () => { this.active.delete(oscillator); oscillator.disconnect(); envelope.disconnect(); filter.disconnect(); };
  }

  /** Short look-ahead scheduling keeps music independent of visual frame rate. */
  tickMusic() {
    const context = this.context;
    if (!context || context.state !== 'running' || !useAudio.getState().enabled) return;
    if (this.nextBeat < context.currentTime) this.nextBeat = context.currentTime + 0.03;
    while (this.nextBeat < context.currentTime + 0.3) {
      const chordIndex = Math.floor(this.beat / 8) % CHORDS.length;
      if (this.beat % 8 === 0) this.pad(CHORDS[chordIndex], this.nextBeat);
      const phrase = this.beat % 8;
      if (phrase === 1 || phrase === 3 || phrase === 6) {
        const frequency = MELODIES[chordIndex][Math.floor(this.beat / 32 + phrase) % 4];
        this.tone(this.music!, { frequency, offset: 0, duration: 2.1, volume: 0.075 }, this.nextBeat, true);
        this.tone(this.music!, { frequency: frequency * 2, offset: 0, duration: 0.55, volume: 0.006 }, this.nextBeat, true);
      }
      this.beat++;
      this.nextBeat += BEAT;
    }
    this.applyLevels();
  }

  private pad(chord: number[], when: number) {
    const context = this.context!;
    chord.forEach((frequency, index) => {
      for (const detune of [-3, 3]) {
        const oscillator = context.createOscillator(); oscillator.type = index === 0 ? 'sine' : 'triangle';
        oscillator.frequency.value = frequency; oscillator.detune.value = detune;
        const envelope = context.createGain(); envelope.gain.setValueAtTime(0, when);
        envelope.gain.linearRampToValueAtTime(index === 0 ? 0.035 : 0.018, when + 1.5);
        envelope.gain.setValueAtTime(index === 0 ? 0.035 : 0.018, when + BEAT * 6);
        envelope.gain.linearRampToValueAtTime(0, when + BEAT * 8 + 2);
        const filter = context.createBiquadFilter(); filter.type = 'lowpass'; filter.frequency.value = 950;
        const pan = context.createStereoPanner(); pan.pan.value = (index - 1.5) * 0.24;
        oscillator.connect(envelope).connect(filter).connect(pan).connect(this.music!);
        oscillator.start(when); oscillator.stop(when + BEAT * 8 + 2.1);
        this.active.add(oscillator);
        oscillator.onended = () => { this.active.delete(oscillator); oscillator.disconnect(); envelope.disconnect(); filter.disconnect(); pan.disconnect(); };
      }
    });
  }

  play(cue: AudioCue, delay = 0) {
    const context = this.context;
    const state = useAudio.getState();
    if (!context || context.state !== 'running' || !state.enabled || state.muted || document.hidden || state.levels.effects === 0) return;
    const cooldown = cue === 'ui' || cue === 'toggle' || cue === 'zoom' ? 0.14 : 0.24;
    if (context.currentTime - (this.lastCue.get(cue) ?? -Infinity) < cooldown) return;
    this.lastCue.set(cue, context.currentTime);
    this.played.set(cue, (this.played.get(cue) ?? 0) + 1);
    const when = context.currentTime + 0.01 + delay;
    const notes = (frequencies: number[], gap: number, duration: number, volume: number, wave: OscillatorType = 'sine') => frequencies.map((frequency, index): Tone => ({ frequency, offset: index * gap, duration, volume, wave }));
    let score: Tone[];
    switch (cue) {
      case 'survivor': score = notes([587.33, 739.99, 880, 1174.66], 0.12, 0.85, 0.16); break;
      case 'complete': score = [...notes([293.66, 369.99, 440], 0, 1.6, 0.09), ...notes([587.33, 739.99, 880, 1174.66, 1479.98], 0.16, 1.3, 0.12)]; break;
      case 'launch': score = notes([146.83, 220, 293.66, 440], 0.11, 0.45, 0.11, 'triangle'); break;
      case 'resume': score = notes([293.66, 440], 0.08, 0.35, 0.09); break;
      case 'pause': score = notes([440, 293.66], 0.08, 0.4, 0.08); break;
      case 'reset': score = notes([440, 329.63, 220], 0.06, 0.3, 0.08); break;
      case 'selectRover': score = notes([220, 293.66], 0.065, 0.2, 0.07, 'triangle'); break;
      case 'selectDrone': score = notes([659.25, 880], 0.065, 0.25, 0.055); break;
      case 'focusRover': score = notes([110, 164.81, 220, 293.66], 0.06, 0.4, 0.1, 'triangle'); break;
      case 'focusDrone': score = notes([440, 659.25, 880, 1174.66], 0.055, 0.5, 0.075); break;
      case 'scan': score = notes([880, 1174.66, 880], 0.14, 0.28, 0.065); break;
      case 'warning': score = notes([440, 369.99, 440], 0.2, 0.3, 0.085); break;
      case 'depleted': score = notes([293.66, 246.94, 196], 0.14, 0.45, 0.09); break;
      case 'offline': score = notes([587.33, 440, 293.66], 0.1, 0.3, 0.07); break;
      case 'online': score = notes([293.66, 440, 587.33], 0.1, 0.35, 0.07); break;
      case 'waypoint': case 'place': score = notes([440, 659.25], 0.055, 0.3, 0.07); break;
      case 'remove': case 'close': score = notes([440, 329.63], 0.04, 0.16, 0.04); break;
      case 'open': score = notes([440, 587.33], 0.045, 0.22, 0.05); break;
      case 'blocked': score = [{ frequency: 130, endFrequency: 80, offset: 0, duration: 0.12, volume: 0.06, wave: 'triangle' }]; break;
      case 'map': score = notes([1174.66, 1479.98], 0.035, 0.12, 0.024); break;
      case 'explore': score = notes([587.33], 0, 0.32, 0.025); break;
      case 'zoom': score = [{ frequency: 470, endFrequency: 587, offset: 0, duration: 0.09, volume: 0.023 }]; break;
      case 'toggle': score = [{ frequency: 520, endFrequency: 390, offset: 0, duration: 0.085, volume: 0.022 }]; break;
      case 'ui': score = [{ frequency: 420, endFrequency: 285, offset: 0, duration: 0.065, volume: 0.024 }, { frequency: 840, endFrequency: 570, offset: 0.008, duration: 0.04, volume: 0.004 }]; break;
      default: score = notes([587.33], 0, 0.07, 0.03);
    }
    if (cue === 'survivor' || cue === 'complete' || cue === 'warning') this.duckUntil = when + (cue === 'complete' ? 3 : 1.5);
    score.forEach((note) => this.tone(this.effects!, note, when + note.offset, cue === 'survivor' || cue === 'complete'));
    this.applyLevels();
  }

  updateSpatial(x: number, z: number, rightX: number, rightZ: number, radius: number) {
    this.listener.x = x; this.listener.z = z;
    this.listener.rightX = rightX; this.listener.rightZ = rightZ;
    this.listener.radius = Math.max(4, radius);
  }

  updateVehicles(mission: object, robots: RobotState[], previous: Map<number, { x: number; y: number }>, alpha: number, width: number, height: number, running: boolean, selected: string | null, following: boolean) {
    if (!this.context || !this.vehicles || !this.noise) return;
    if (mission !== this.mission) {
      this.voices.forEach((voice) => voice.dispose()); this.voices.clear(); this.mission = mission;
    }
    for (const robot of robots) {
      let voice = this.voices.get(robot.id);
      if (!voice) { voice = new VehicleVoice(this.context, this.vehicles, this.noise, robot.type === 'drone'); this.voices.set(robot.id, voice); }
      const from = previous.get(robot.id) ?? robot;
      const moving = from.x !== robot.x || from.y !== robot.y;
      const x = from.x + (robot.x - from.x) * alpha - width / 2 + 0.5;
      const z = from.y + (robot.y - from.y) * alpha - height / 2 + 0.5;
      const dx = x - this.listener.x, dz = z - this.listener.z;
      const distance = Math.hypot(dx, dz) / this.listener.radius;
      const proximity = 1 / (1 + distance * distance * 2);
      const focused = robot.name === selected;
      const emphasis = focused ? following ? 3.5 : 2.2 : selected && following ? 0.45 : 1;
      const base = robot.type === 'drone' ? moving ? 0.028 : 0.02 : moving ? 0.042 : 0.008;
      const level = running && robot.alive ? base * proximity * emphasis / Math.sqrt(Math.max(1, robots.length / 2)) : 0;
      const pan = Math.max(-0.9, Math.min(0.9, (dx * this.listener.rightX + dz * this.listener.rightZ) / this.listener.radius));
      voice.update(level, pan, moving);
    }
  }

  visibility(hidden: boolean) {
    if (!this.context || !useAudio.getState().enabled) return;
    if (hidden) void this.context.suspend().catch(() => {});
    else void this.context.resume().catch(() => {});
  }

  diagnostics() {
    const data = new Float32Array(this.analyser?.fftSize ?? 0);
    this.analyser?.getFloatTimeDomainData(data);
    return { state: this.context?.state ?? 'not-created', activeVehicles: this.voices.size, activeTones: this.active.size, scheduledBeat: this.beat, played: Object.fromEntries(this.played), rms: data.length ? Math.sqrt(data.reduce((sum, value) => sum + value * value, 0) / data.length) : 0 };
  }

  dispose() {
    this.voices.forEach((voice) => voice.dispose()); this.voices.clear();
    this.active.forEach((oscillator) => { try { oscillator.stop(); } catch { /* Already ended. */ } });
    this.active.clear();
    if (this.context && this.context.state !== 'closed') void this.context.close().catch(() => {});
    this.context = null; this.master = null; this.music = null; this.effects = null; this.vehicles = null; this.analyser = null; this.noise = null; this.mission = null;
    this.lastCue.clear(); this.played.clear();
    useAudio.setState({ enabled: false });
  }
}

export const soundscape = new Soundscape();
