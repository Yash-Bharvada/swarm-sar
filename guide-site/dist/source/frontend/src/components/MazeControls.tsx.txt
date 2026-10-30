import { useEffect, useState } from 'react';
import { useSim } from '../store/simStore';
import { MAX_MAP_SIDE, MIN_MAP_SIDE } from '../simulation/world/ScenarioGenerator';

export function MazeControls({ locked }: { locked: boolean }) {
  const settings = useSim((s) => s.settings);
  const message = useSim((s) => s.mapMessage);
  const [width, setWidth] = useState(String(settings.mapWidth));
  const [height, setHeight] = useState(String(settings.mapHeight));
  useEffect(() => { setWidth(String(settings.mapWidth)); setHeight(String(settings.mapHeight)); }, [settings.mapWidth, settings.mapHeight]);
  const custom = settings.preset === 'maze';
  const valid = [width, height].every((v) => /^\d+$/.test(v) && Number(v) >= MIN_MAP_SIDE && Number(v) <= MAX_MAP_SIDE);
  return <div className="maze-controls">
    {custom && <>
      <div className="controller-fields">
        <label className="field-label">Width<input aria-label="Maze width" type="number" min={MIN_MAP_SIDE} max={MAX_MAP_SIDE} value={width} disabled={locked} onChange={(e) => setWidth(e.target.value)} /></label>
        <label className="field-label">Height<input aria-label="Maze height" type="number" min={MIN_MAP_SIDE} max={MAX_MAP_SIDE} value={height} disabled={locked} onChange={(e) => setHeight(e.target.value)} /></label>
      </div>
      {!valid && <p className="controller-seed-help invalid" role="status">Choose 16–96 tiles per side.</p>}
    </>}
    <div className="survivor-actions">
      <button className="btn" disabled={locked || (custom && !valid)} onClick={() => custom ? useSim.getState().configureMaze(Number(width), Number(height)) : useSim.getState().randomizeSeed()}>Generate map</button>
      <button className="btn ghost" disabled={locked} onClick={() => useSim.getState().setEditingTerrain(true)}>Edit layout</button>
    </div>
    <p className="explain">{locked ? 'Reset the mission to change your map.' : custom ? 'Generate at this size, or edit the current map.' : 'Generate a fresh map, or draw your own paths and walls.'}</p>
    {message && <p className="controller-seed-help invalid" role="status">{message}</p>}
  </div>;
}
