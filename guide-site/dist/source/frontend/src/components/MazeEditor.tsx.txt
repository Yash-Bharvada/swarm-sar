import { useEffect, useRef, useState, type PointerEvent } from 'react';
import { useSim } from '../store/simStore';
import { FREE, RUBBLE, WALL } from '../simulation/world/GridMap';
import type { Point } from '../simulation/core/types';

const BRUSHES = [{ value: FREE, label: 'Path' }, { value: WALL, label: 'Wall' }, { value: RUBBLE, label: 'Debris' }];

export function MazeEditor() {
  const engine = useSim((s) => s.engine);
  const message = useSim((s) => s.mapMessage);
  const { width, height, spawn, victims } = engine.scenario;
  const dialog = useRef<HTMLDialogElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [cells, setCells] = useState(() => new Int8Array(engine.scenario.grid.cells));
  const current = useRef(cells);
  const [brush, setBrush] = useState<number>(FREE);
  const [zoom, setZoom] = useState(0);
  const [viewport, setViewport] = useState({ width: window.innerWidth, height: window.innerHeight });
  const fit = Math.max(.1, Math.min(1, (Math.min(960, viewport.width - 32) - 70) / (width * 14), viewport.height * .48 / (height * 14)));
  const scale = zoom || fit;
  const [undo, setUndo] = useState<Int8Array[]>([]);
  const [redo, setRedo] = useState<Int8Array[]>([]);
  const drawing = useRef<Point | null>(null);
  const beforeStroke = useRef<Int8Array | null>(null);
  const survivorCells = new Set(victims.map((v) => v.y * width + v.x));
  const inStart = (x: number, y: number) => x >= spawn.x && y >= spawn.y && x < spawn.x + spawn.size && y < spawn.y + spawn.size;
  const cancel = () => useSim.getState().setEditingTerrain(false);
  const replace = (next: Int8Array) => { current.current = next; setCells(next); };

  useEffect(() => { dialog.current?.showModal(); }, []);
  useEffect(() => {
    const resize = () => setViewport({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);
  useEffect(() => {
    const ctx = canvas.current?.getContext('2d');
    if (!ctx) return;
    const tile = 14;
    for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
      const cell = cells[y * width + x];
      ctx.fillStyle = inStart(x, y) ? '#88b9a2' : cell === WALL ? '#617b49' : cell === RUBBLE ? '#baa27b' : '#f0e6ba';
      ctx.fillRect(x * tile, y * tile, tile, tile);
      ctx.strokeStyle = '#ffffff20'; ctx.strokeRect(x * tile, y * tile, tile, tile);
    }
    for (const victim of victims) {
      ctx.fillStyle = '#eeae43'; ctx.beginPath(); ctx.arc((victim.x + .5) * tile, (victim.y + .5) * tile, 4, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = '#6b512b'; ctx.stroke();
    }
    // Starting area is labelled rather than implied by its colour alone.
    ctx.fillStyle = '#244f43'; ctx.font = 'bold 11px sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText('START', (spawn.x + spawn.size / 2) * tile, (spawn.y + spawn.size / 2) * tile);
  }, [cells, engine]); // geometry and staging are fixed for the editor session

  const point = (event: PointerEvent<HTMLCanvasElement>): Point => {
    const rect = event.currentTarget.getBoundingClientRect();
    return { x: Math.max(0, Math.min(width - 1, Math.floor((event.clientX - rect.left) / rect.width * width))), y: Math.max(0, Math.min(height - 1, Math.floor((event.clientY - rect.top) / rect.height * height))) };
  };
  const paint = (from: Point, to: Point) => {
    const next = new Int8Array(current.current);
    const write = (x: number, y: number) => {
      if (x < 1 || y < 1 || x >= width - 1 || y >= height - 1 || inStart(x, y) || survivorCells.has(y * width + x)) return;
      next[y * width + x] = brush;
    };
    let { x, y } = from; write(x, y);
    while (x !== to.x) { x += Math.sign(to.x - x); write(x, y); }
    while (y !== to.y) { y += Math.sign(to.y - y); write(x, y); }
    replace(next);
  };
  const finishStroke = () => {
    if (beforeStroke.current && beforeStroke.current.some((v, i) => v !== current.current[i])) {
      const previous = beforeStroke.current;
      setUndo((history) => [...history.slice(-29), previous]); setRedo([]);
    }
    drawing.current = null; beforeStroke.current = null;
  };
  const clearWalls = () => {
    setUndo((history) => [...history.slice(-29), new Int8Array(current.current)]); setRedo([]);
    const next = new Int8Array(current.current);
    for (let y = 1; y < height - 1; y++) for (let x = 1; x < width - 1; x++) if (!survivorCells.has(y * width + x)) next[y * width + x] = FREE;
    replace(next);
  };
  return <dialog ref={dialog} className="maze-editor" aria-labelledby="maze-editor-title" onCancel={(e) => { e.preventDefault(); cancel(); }} onKeyDown={(e) => e.stopPropagation()}>
    <div className="maze-editor-head"><div><span className="panel-eyebrow">MAKE IT YOURS</span><h2 id="maze-editor-title">Edit map</h2><p>Drag to draw. Keep paths connected to START.</p></div><button className="btn ghost" onClick={cancel} aria-label="Close map editor">Close</button></div>
    <div className="maze-editor-toolbar">
      <div className="segmented" role="radiogroup" aria-label="Terrain brush">{BRUSHES.map((item) => <button key={item.value} role="radio" aria-checked={brush === item.value} className={brush === item.value ? 'on' : ''} onClick={() => setBrush(item.value)}>{item.label}</button>)}</div>
      <button className="btn small" disabled={!undo.length} onClick={() => { const previous = undo[undo.length - 1]; setRedo((history) => [...history, new Int8Array(current.current)]); setUndo(undo.slice(0, -1)); replace(previous); }}>Undo</button>
      <button className="btn small" disabled={!redo.length} onClick={() => { const next = redo[redo.length - 1]; setUndo((history) => [...history, new Int8Array(current.current)]); setRedo(redo.slice(0, -1)); replace(next); }}>Redo</button>
      <button className="btn small" onClick={clearWalls}>Clear walls</button>
      <label className="maze-editor-zoom">View<select aria-label="Editor zoom" value={zoom} onChange={(e) => setZoom(Number(e.target.value))}><option value={0}>Fit</option><option value={1}>1×</option><option value={2}>2×</option><option value={3}>3×</option></select></label>
    </div>
    <div className="maze-editor-viewport"><canvas ref={canvas} width={width * 14} height={height * 14} style={{ width: width * 14 * scale, height: height * 14 * scale }} aria-label="Map drawing canvas. Choose Path, Wall or Debris, then drag to paint." onPointerDown={(e) => {
      if (e.button !== 0) return; e.preventDefault(); e.currentTarget.setPointerCapture(e.pointerId);
      useSim.setState({ mapMessage: null }); beforeStroke.current = new Int8Array(current.current); drawing.current = point(e); paint(drawing.current, drawing.current);
    }} onPointerMove={(e) => { if (!drawing.current) return; const next = point(e); paint(drawing.current, next); drawing.current = next; }} onPointerUp={finishStroke} onPointerCancel={finishStroke} onLostPointerCapture={finishStroke} /></div>
    <div className="maze-editor-footer"><p className="explain">The boundary, team start and survivor markers stay protected.</p>{message && <p className="maze-editor-error" role="alert">{message}</p>}<div><button className="btn" onClick={cancel}>Cancel</button><button className="btn primary" onClick={() => useSim.getState().applyTerrain(Array.from(current.current))}>Save layout</button></div></div>
  </dialog>;
}
