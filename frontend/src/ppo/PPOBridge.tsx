import { useEffect } from 'react';
import { simClock, TICKS_PER_SECOND, useSim } from '../store/simStore';
import { RemoteEngine, validateSnapshot, type PPOSnapshot } from './RemoteEngine';

export async function ppoRequest(path: string, method = 'GET', data?: unknown, signal?: AbortSignal): Promise<unknown> {
  const abort = new AbortController();
  const stop = () => abort.abort();
  signal?.addEventListener('abort', stop, { once: true });
  if (signal?.aborted) abort.abort();
  const timer = window.setTimeout(stop, 15000);
  try {
    const response = await fetch(`/api/ppo${path}`, { method, signal: abort.signal, headers: data === undefined ? undefined : { 'Content-Type': 'application/json' }, body: data === undefined ? undefined : JSON.stringify(data) });
    const payload = await response.json().catch(() => null);
    if (!response.ok || !payload) throw new Error(payload?.error ?? 'Python PPO service is unavailable. Start tools/ppo_service.py, then reset this mission.');
    return payload;
  } finally { clearTimeout(timer); signal?.removeEventListener('abort', stop); }
}

/** Publish one authoritative Python tick and retain the discovery-pause flow. */
export function applyPythonTick(engine: RemoteEngine, snapshot: PPOSnapshot) {
  const before = useSim.getState();
  if (before.engine !== engine || before.controllerMode !== 'ppo') return;
  engine.applySnapshot(snapshot);
  simClock.lastTickAt = performance.now(); simClock.alpha = 0;
  const fresh = engine.discoveredSurvivors().filter((v) => !before.announcedSurvivors.includes(v.id)).map((v) => v.id);
  if (fresh.length) {
    simClock.alpha = 1;
    useSim.setState({ encounter: { id: fresh[0], automatic: true }, encounterQueue: fresh.slice(1), announcedSurvivors: [...before.announcedSurvivors, ...fresh], encounterReturnStatus: before.status === 'running' ? 'running' : 'paused', following: false, focus: null, cameraRequest: null, status: 'paused', version: before.version + 1 });
  } else {
    // If pause was pressed while a tick was already in flight, accept that
    // one committed tick and stay paused. Never issue the following one.
    useSim.setState({ status: engine.done ? 'complete' : before.status, version: before.version + 1 });
  }
}

export function PPOBridge() {
  const mode = useSim((s) => s.controllerMode);
  const revision = useSim((s) => s.ppoRevision);
  useEffect(() => {
    if (mode !== 'ppo') return;
    const abort = new AbortController();
    let disposed = false, mission: string | null = null, engine: RemoteEngine | null = null, busy = false;
    let previousFrame = performance.now(), elapsed = 0, previousInterval = 0;
    const fail = (error: unknown) => {
      if (disposed) return;
      useSim.setState({ ppoPhase: 'error', ppoError: error instanceof TypeError || (error instanceof DOMException && error.name === 'AbortError') ? 'Connection to Python was lost. Start the PPO service, then reset this mission.' : error instanceof Error ? error.message : 'PPO connection failed', status: 'paused' });
    };
    (async () => {
      try {
        let clientKey: string;
        try {
          clientKey = sessionStorage.getItem('swarm-ppo-client') ?? crypto.randomUUID();
          sessionStorage.setItem('swarm-ppo-client', clientKey);
        } catch { clientKey = crypto.randomUUID(); }
        const payload = await ppoRequest('/missions', 'POST', { ...useSim.getState().ppoOptions, clientKey }, abort.signal);
        validateSnapshot(payload); mission = payload.mission;
        if (disposed) { void ppoRequest(`/missions/${mission}`, 'DELETE').catch(() => {}); return; }
        engine = new RemoteEngine(payload);
        const state = useSim.getState();
        simClock.alpha = 1;
        useSim.setState({ engine, status: 'ready', ppoPhase: 'ready', ppoError: null, version: state.version + 1,
          settings: { ...state.settings, seed: payload.options.seed, rovers: payload.options.rovers, drones: payload.options.drones, mode: 'autonomous', survivorCount: null, packetLoss: payload.transport.packetLoss, delayMax: payload.transport.delay[1], networkEnabled: payload.options.network, batteryLimited: payload.options.batteryLimited !== false, sensorNoise: true },
          selected: null, following: false, focus: null, cameraRequest: null, encounter: null, encounterQueue: [], announcedSurvivors: [], editingSurvivors: false, survivorMessage: null,
        });
        previousFrame = performance.now();
      } catch (error) { fail(error); }
    })();
    const timer = window.setInterval(async () => {
      const now = performance.now(), dt = Math.min(100, now - previousFrame);
      previousFrame = now;
      const state = useSim.getState();
      if (!engine || disposed || state.engine !== engine || state.ppoPhase !== 'ready') return;
      const interval = 1000 / (TICKS_PER_SECOND * state.settings.speed);
      if (interval !== previousInterval) { elapsed = simClock.alpha * interval; previousInterval = interval; }
      elapsed = Math.max(elapsed, simClock.alpha * interval);
      if ((state.status === 'running' || state.status === 'complete') && !document.hidden) { elapsed += dt; simClock.alpha = Math.min(1, elapsed / interval); }
      if (state.status !== 'running' || document.hidden || busy || elapsed < interval) return;
      busy = true;
      const expected = engine.step;
      try {
        let value: unknown;
        try { value = await ppoRequest(`/missions/${mission}/step`, 'POST', { expectedStep: expected }, abort.signal); }
        catch (error) {
          if (disposed) return;
          // The server deduplicates this expected step if only its response was lost.
          value = await ppoRequest(`/missions/${mission}/step`, 'POST', { expectedStep: expected }, abort.signal);
        }
        validateSnapshot(value);
        if (disposed || useSim.getState().engine !== engine) return;
        elapsed = 0;
        applyPythonTick(engine, value);
      } catch (error) { fail(error); }
      finally { busy = false; }
    }, 16);
    return () => {
      disposed = true; abort.abort(); clearInterval(timer);
      if (mission) void ppoRequest(`/missions/${mission}`, 'DELETE').catch(() => {});
    };
  }, [mode, revision]);
  return null;
}
