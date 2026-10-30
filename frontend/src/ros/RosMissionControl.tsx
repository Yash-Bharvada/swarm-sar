import { useEffect, useRef, useState } from 'react';
import { cellWorld, validGrid, RosConnection, type RosGrid, type RosPose, type NetEvent, type Health, type Stats } from './transport';
import './ros.css';

const AGENTS = ['rover_0', 'rover_1', 'drone_0', 'drone_1'];
const COLORS = ['#fbbf24', '#fb923c', '#a78bfa', '#f472b6'];
type Sample<T> = { value: T; wall: number };
type Layers = Record<string, Record<string, Sample<RosGrid>>>;
type Topology = { local: { id: string; x: number; y: number }[]; peers: Record<string, { id: string; x: number; y: number }[]> };
const parseString = <T,>(msg: unknown): T => JSON.parse((msg as { data: string }).data) as T;

export function RosMissionControl() {
  const [address, setAddress] = useState(new URLSearchParams(location.search).get('bridge') || 'ws://localhost:9090');
  const [connection, setConnection] = useState('disconnected');
  const [selected, setSelected] = useState('rover_0');
  const [layers, setLayers] = useState<Layers>({});
  const [poses, setPoses] = useState<Record<string, Sample<RosPose>>>({});
  const [health, setHealth] = useState<Record<string, Sample<Health>>>({});
  const [stats, setStats] = useState<Sample<Stats> | null>(null);
  const [events, setEvents] = useState<NetEvent[]>([]);
  const [topologies, setTopologies] = useState<Record<string, Topology>>({});
  const [paths, setPaths] = useState<Record<string, [number, number][]>>({});
  const [clock, setClock] = useState<Sample<number> | null>(null);
  const [showPeers, setShowPeers] = useState(true);
  const [feedback, setFeedback] = useState('');
  const [busy, setBusy] = useState(false);
  const [wall, setWall] = useState(Date.now());
  const client = useRef<RosConnection | null>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const previousClock = useRef(0);
  const runs = useRef<Record<string, string>>({});
  const clear = () => { setLayers({}); setPoses({}); setHealth({}); setStats(null); setEvents([]); setPaths({}); setTopologies({}); runs.current = {}; };

  useEffect(() => {
    const ros = new RosConnection(setConnection); client.current = ros;
    ros.subscribe('/clock', 'rosgraph_msgs/msg/Clock', msg => {
      const c = (msg as { clock: { sec: number; nanosec: number } }).clock;
      const t = c.sec + c.nanosec / 1e9;
      if (!Number.isFinite(t)) return;
      if (t < previousClock.current - .01) { clear(); setFeedback('Simulation clock reset: restart the SLAM launch before driving.'); }
      previousClock.current = t; setClock({ value: t, wall: Date.now() });
    });
    for (const agent of AGENTS) {
      for (const layer of ['local_slam_map', 'belief_map', 'peer_map']) ros.subscribe(`/${agent}/${layer}`, 'nav_msgs/msg/OccupancyGrid', msg => {
        if (validGrid(msg)) setLayers(prev => ({ ...prev, [agent]: { ...prev[agent], [layer]: { value: msg, wall: Date.now() } } }));
      }, 1000);
      ros.subscribe(`/${agent}/estimated_odom`, 'nav_msgs/msg/Odometry', msg => {
        const p = msg as RosPose;
        if (p?.header?.frame_id === 'map' && [p.pose?.pose?.position?.x, p.pose?.pose?.position?.y].every(Number.isFinite))
          setPoses(prev => ({ ...prev, [agent]: { value: p, wall: Date.now() } }));
      });
      ros.subscribe(`/${agent}/slam_health`, 'std_msgs/msg/String', msg => {
        const h = parseString<Health>(msg);
        if (h.agent !== agent || typeof h.run !== 'string' || !Number.isFinite(h.sim_time)) return;
        if (runs.current[agent] && runs.current[agent] !== h.run) {
          setLayers(p => { const next = { ...p }; delete next[agent]; return next; });
          setPaths(p => ({ ...p, [agent]: [] }));
        }
        runs.current[agent] = h.run; setHealth(prev => ({ ...prev, [agent]: { value: h, wall: Date.now() } }));
      }, 1000);
      ros.subscribe(`/${agent}/topology`, 'std_msgs/msg/String', msg => {
        const t = parseString<Topology>(msg);
        if (Array.isArray(t.local)) setTopologies(prev => ({ ...prev, [agent]: t }));
      }, 1000);
      ros.subscribe(`/${agent}/estimated_path`, 'nav_msgs/msg/Path', msg => {
        const p = msg as { header: { frame_id: string }; poses: { pose: { position: { x: number; y: number } } }[] };
        if (p?.header?.frame_id !== 'map' || !Array.isArray(p.poses)) return;
        setPaths(prev => ({ ...prev, [agent]: p.poses.slice(-2000).map(p => [p.pose.position.x, p.pose.position.y]).filter(p => p.every(Number.isFinite)) as [number, number][] }));
      }, 1000);
    }
    ros.subscribe('/swarm/network/events', 'std_msgs/msg/String', msg => {
      const e = parseString<NetEvent>(msg);
      if (typeof e.event === 'string' && Number.isFinite(e.sim_time)) setEvents(prev => [e, ...prev].slice(0, 100));
    }, 0);
    ros.subscribe('/swarm/network/stats', 'std_msgs/msg/String', msg => {
      const s = parseString<Stats>(msg);
      if (s.metrics && Array.isArray(s.isolated)) setStats({ value: s, wall: Date.now() });
    }, 1000);
    const timer = setInterval(() => setWall(Date.now()), 500);
    return () => { clearInterval(timer); ros.close(); client.current = null; };
  }, []);

  useEffect(() => {
    const c = canvas.current, grid = layers[selected]?.local_slam_map?.value;
    if (!c) return;
    const ctx = c.getContext('2d'); if (!ctx) return;
    ctx.fillStyle = '#101b28'; ctx.fillRect(0, 0, c.width, c.height);
    if (!grid) { ctx.fillStyle = '#a9b9cb'; ctx.font = '20px system-ui'; ctx.fillText('Waiting for real ROS map messages…', 32, 60); return; }
    const corners = [cellWorld(grid, 0, 0), cellWorld(grid, grid.info.width - 1, 0), cellWorld(grid, 0, grid.info.height - 1), cellWorld(grid, grid.info.width - 1, grid.info.height - 1)];
    const minX = Math.min(...corners.map(p => p[0])) - 1, minY = Math.min(...corners.map(p => p[1])) - 1;
    const extent = Math.max(...corners.map(p => p[0])) - minX + 1;
    const height = Math.max(...corners.map(p => p[1])) - minY + 1;
    const scale = Math.min(c.width / extent, c.height / height);
    const point = (x: number, y: number): [number, number] => [(x - minX) * scale, c.height - (y - minY) * scale];
    const draw = (g: RosGrid, peer: boolean) => {
      const q = g.info.origin.orientation;
      const angle = Math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z));
      ctx.save(); ctx.translate(...point(g.info.origin.position.x, g.info.origin.position.y)); ctx.rotate(-angle);
      const size = g.info.resolution * scale;
      for (let y = 0; y < g.info.height; y++) for (let x = 0; x < g.info.width; x++) {
        const v = g.data[y * g.info.width + x]; if (v < 0) continue;
        ctx.fillStyle = peer ? (v >= 65 ? '#22d3ee' : '#164e63') : (v >= 65 ? '#e5e7eb' : '#33465b');
        ctx.fillRect(x * size, -(y + 1) * size, size + .15, size + .15);
      }
      ctx.restore();
    };
    draw(grid, false);
    const peer = layers[selected]?.peer_map?.value; if (showPeers && peer) draw(peer, true);
    const delivered = new Map(events.filter(e => e.event === 'transport_delivered' && clock && clock.value - e.sim_time >= 0 && clock.value - e.sim_time < 1.5).map(e => [`${e.source}:${e.target}`, e]));
    ctx.strokeStyle = '#22d3ee'; ctx.globalAlpha = .45; ctx.setLineDash([5, 6]);
    for (const e of delivered.values()) {
      const a = poses[e.source], b = poses[e.target];
      if (!a || !b || connection !== 'connected' || wall - a.wall > 3000 || wall - b.wall > 3000) continue;
      ctx.beginPath(); ctx.moveTo(...point(a.value.pose.pose.position.x, a.value.pose.pose.position.y));
      ctx.lineTo(...point(b.value.pose.pose.position.x, b.value.pose.pose.position.y)); ctx.stroke();
    }
    ctx.globalAlpha = 1; ctx.setLineDash([]);
    AGENTS.forEach((agent, i) => {
      const path = paths[agent] || []; ctx.strokeStyle = COLORS[i]; ctx.lineWidth = 1.5;
      ctx.beginPath(); path.forEach(([x, y], j) => { const p = point(x, y); if (j === 0) ctx.moveTo(...p); else ctx.lineTo(...p); }); ctx.stroke();
      const sample = poses[agent]; if (!sample) return;
      const p = sample.value.pose.pose.position, [x, y] = point(p.x, p.y);
      ctx.globalAlpha = wall - sample.wall > 3000 || connection !== 'connected' ? .3 : 1;
      ctx.fillStyle = COLORS[i]; ctx.beginPath(); ctx.arc(x, y, agent === selected ? 7 : 5, 0, Math.PI * 2); ctx.fill();
      ctx.font = '13px system-ui'; ctx.fillText(agent, x + 10, y - 8); ctx.globalAlpha = 1;
    });
    ctx.strokeStyle = '#86efac'; ctx.lineWidth = 1;
    for (const node of topologies[selected]?.local || []) {
      if (![node.x, node.y].every(Number.isFinite)) continue;
      const [x, y] = point(node.x, node.y); ctx.strokeRect(x - 3, y - 3, 6, 6);
    }
    ctx.fillStyle = '#cbd5e1'; ctx.font = '13px system-ui'; ctx.fillText(`1 m = ${scale.toFixed(1)} px · mission frame: map`, 14, c.height - 15);
  }, [layers, selected, poses, paths, topologies, showPeers, wall, connection, events, clock]);

  const h = health[selected];
  const stale = connection !== 'connected' || !clock || wall - clock.wall > 3000 || !h || wall - h.wall > 3500 || h.value.state !== 'tracking';
  const isolated = stats?.value.isolated.includes(selected) || false;
  const toggleIsolation = async () => {
    setBusy(true); setFeedback('Requesting radio fault change from ROS…');
    try { await client.current?.isolate(selected, !isolated); setFeedback('ROS acknowledged the request. The isolation state below comes from network telemetry.'); }
    catch (e) { setFeedback(e instanceof Error ? e.message : 'ROS service failed'); }
    finally { setBusy(false); }
  };

  return <main className="ros-live">
    <header><div><span className="ros-eyebrow">SWARM SAR / PHYSICAL SIMULATION</span><h1>Live SLAM & peer communication</h1><p>Gazebo physics → ROS sensors → estimated maps → per-agent knowledge.</p></div><a href="/">Browser simulator</a></header>
    <div className="ros-connect"><label>ROS bridge <input value={address} onChange={e => setAddress(e.target.value)} aria-label="ROS bridge URL" /></label><button onClick={() => { clear(); setClock(null); previousClock.current = 0; try { client.current?.connect(address); } catch (e) { setFeedback(String(e)); } }}>Connect</button><button onClick={() => client.current?.close()}>Disconnect</button><strong className={stale ? 'ros-warning' : 'ros-good'}>{connection} · {stale ? 'WAITING / STALE' : 'LIVE'}</strong><span>Sim {clock?.value.toFixed(1) ?? '—'} s</span></div>
    <div className="ros-layout"><section className="ros-map"><nav>{AGENTS.map(agent => <button className={selected === agent ? 'selected' : ''} key={agent} onClick={() => setSelected(agent)}>{agent}</button>)}<label><input type="checkbox" checked={showPeers} onChange={e => setShowPeers(e.target.checked)} /> Peer overlay</label></nav><canvas ref={canvas} width={960} height={760} aria-label="ROS occupancy map, estimated trajectories, robot positions, and frontier components" /><p>White: local occupied · slate: local free · cyan: peer-only knowledge · green squares: frontier components. Faded robots have stale telemetry. Drones use simulator poses; only rovers run 2D SLAM.</p></section>
    <aside><section><h2>{selected}</h2><strong className={stale ? 'ros-warning' : 'ros-good'}>{h?.value.state || 'No telemetry'}</strong><dl><dt>Pose/map source</dt><dd>{h?.value.source || '—'}</dd><dt>Local observed cells</dt><dd>{h?.value.local_known ?? '—'}</dd><dt>Peer-only cells</dt><dd>{h?.value.peer_known ?? '—'}</dd><dt>Source map age</dt><dd>{h?.value.map_age?.toFixed(1) ?? '—'} s</dd><dt>Pose age</dt><dd>{h?.value.pose_age?.toFixed(1) ?? '—'} s</dd><dt>Alignment</dt><dd>Known starting positions</dd><dt>Pose covariance</dt><dd>Unavailable from TF</dd></dl><p>Peer maps supplement unknown cells. They do not enter the local SLAM pose graph.</p></section>
    <section><h2>Radio fault test</h2><p>Status: {stats && wall - stats.wall < 3500 ? (isolated ? 'ISOLATED' : 'radio enabled') : 'unconfirmed / stale'}</p><button disabled={busy || connection !== 'connected' || !stats || wall - stats.wall > 3500} onClick={toggleIsolation}>{isolated ? 'Reconnect' : 'Isolate'} {selected}</button><p role="status">{feedback}</p><p>Leave isolated for 15 simulation seconds. Local mapping should continue; shared knowledge should stop updating. Reconnect and watch received snapshots apply.</p></section>
    <section><h2>Transport evidence</h2><dl>{Object.entries(stats?.value.metrics || {}).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{value}</dd></div>)}</dl><p>Budget: {stats?.value.bytes_per_second ?? '—'} bytes/s per sender; queue: {stats?.value.queue ?? '—'}. Transport delivery and receiver application are separate events.</p></section>
    <section><h2>Received peer snapshots</h2>{Object.entries(h?.value.peers || {}).map(([name, peer]) => <p key={name}>{name}: revision {peer.revision}, applied {peer.age.toFixed(1)} s ago</p>)}<h2>Leased frontier intent</h2>{Object.entries(h?.value.claims || {}).map(([name, claim]) => <p key={name}>{name}: ({claim.goal[0].toFixed(1)}, {claim.goal[1].toFixed(1)}) m · expires at {claim.expires_at.toFixed(1)} s</p>)}<p>Dashed cyan lines show recently delivered packets between displayed ROS poses.</p></section></aside></div>
    <section className="ros-events"><h2>Actual packet events</h2><div className="ros-event-scroll"><table><thead><tr><th>Simulation time</th><th>Sender → receiver</th><th>Channel</th><th>Sequence</th><th>Event</th></tr></thead><tbody>{events.slice(0, 60).map((e, i) => <tr key={i}><td>{e.sim_time.toFixed(2)}</td><td>{e.source} → {e.target || 'broadcast'}</td><td>{e.channel}</td><td>{e.sequence}</td><td>{e.event}</td></tr>)}</tbody></table></div></section>
    <footer>Operator telemetry only. Robot decisions stay in ROS. This page never publishes velocity commands, map updates or goals. Om Rashiya · Yash Bharvada · Purva Shah · Pankti Akbari</footer>
  </main>;
}
