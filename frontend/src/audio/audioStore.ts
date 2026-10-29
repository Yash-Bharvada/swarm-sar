import { create } from 'zustand';

export type AudioChannel = 'master' | 'music' | 'effects' | 'vehicles';
export type AudioLevels = Record<AudioChannel, number>;
export const DEFAULT_AUDIO_LEVELS: AudioLevels = { master: 0.55, music: 0.45, effects: 0.65, vehicles: 0.5 };
export const clampVolume = (value: number) => Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0;
const STORAGE_KEY = 'swarm-sound-levels-v1';

function savedLevels(): AudioLevels {
  if (typeof window === 'undefined') return { ...DEFAULT_AUDIO_LEVELS };
  try {
    const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? '{}');
    return Object.fromEntries(Object.entries(DEFAULT_AUDIO_LEVELS).map(([key, fallback]) => [key, typeof saved?.[key] === 'number' ? clampVolume(saved[key]) : fallback])) as AudioLevels;
  } catch { return { ...DEFAULT_AUDIO_LEVELS }; }
}

interface AudioState {
  enabled: boolean;
  muted: boolean;
  levels: AudioLevels;
  error: string | null;
  setVolume: (channel: AudioChannel, value: number) => void;
}

/** Only levels persist. A fresh page always waits for an explicit sound gesture. */
export const useAudio = create<AudioState>((set, get) => ({
  enabled: false,
  muted: false,
  levels: savedLevels(),
  error: null,
  setVolume: (channel, value) => {
    const levels = { ...get().levels, [channel]: clampVolume(value) };
    set({ levels });
    try { if (typeof window !== 'undefined') window.localStorage.setItem(STORAGE_KEY, JSON.stringify(levels)); } catch { /* Storage is optional. */ }
  },
}));
