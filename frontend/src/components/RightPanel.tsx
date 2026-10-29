import { useSim } from '../store/simStore';
import type { SimulationEngine } from '../simulation/core/SimulationEngine';
import type { RobotState } from '../simulation/robots/RobotState';
import { describeObjective } from '../simulation/telemetry/HumanReadableEventFormatter';
import { ROVER_DESCRIPTION } from '../simulation/robots/RoverRobot';
import { DRONE_DESCRIPTION } from '../simulation/robots/DroneRobot';
import { maxThermal } from '../simulation/sensing/SensorModel';
import { UNKNOWN } from '../simulation/world/GridMap';
import { batteryFillStyle, batteryPct, robotConnection } from '../app/format';
import { MiniMap } from './MiniMap';

function Battery({ robot }: { robot: RobotState }) {
  const p = batteryPct(robot);
  return (
    <div className="battery" title={`${p}% battery`}>
      <div className="battery-track" role="progressbar" aria-label={`${robot.label} battery`} aria-valuenow={p} aria-valuemin={0} aria-valuemax={100}>
        <div className="battery-fill" style={batteryFillStyle(p)} />
      </div>
      <span>{p}%</span>
    </div>
  );
}

function FleetCard({ engine, robot }: { engine: SimulationEngine; robot: RobotState }) {
  const select = useSim((s) => s.select);
  const conn = robotConnection(engine, robot);
  return (
    <button className={`fleet-card ${robot.type} ${robot.alive ? '' : 'dead'}`} onClick={() => select(robot.name)} aria-label={`Inspect ${robot.label}: ${describeObjective(robot.objective)}`}>
      <div className="fleet-head">
        <span className={`type-icon ${robot.type}`} aria-hidden />
        <strong>{robot.label}</strong>
        {robot.manual && <span className="pill manual">Manual</span>}
        <span className={`conn-dot ${conn.tone}`} title={conn.label} aria-label={conn.label} />
        <span className="fleet-chevron" aria-hidden>›</span>
      </div>
      <div className="fleet-objective">{robot.alive ? describeObjective(robot.objective) : 'Battery depleted'}</div>
      <Battery robot={robot} />
    </button>
  );
}

function SensorBars({ robot }: { robot: RobotState }) {
  const sectors = ['N', 'E', 'S', 'W'];
  const thermal = maxThermal(robot.thermal);
  return (
    <div className="sensors">
      <div className="sensor-row">
        <span className="sensor-name">Heat</span>
        <div className="sector-bars">
          {robot.thermal.map((v, i) => (
            <div key={i} className="sector" title={`${sectors[i]} ${v.toFixed(2)}`}>
              <div className="sector-fill heat" style={{ height: `${Math.min(100, (v / 0.6) * 100)}%` }} />
              <span>{sectors[i]}</span>
            </div>
          ))}
        </div>
        <span className="sensor-val">{thermal >= 0.32 ? 'Strong' : thermal >= 0.16 ? 'Weak' : 'None'}</span>
      </div>
      <div className="sensor-row">
        <span className="sensor-name">Sound</span>
        <div className="meter"><div className="meter-fill sound" style={{ width: `${Math.min(100, (robot.acoustic / 0.6) * 100)}%` }} /></div>
        <span className="sensor-val">{robot.acoustic >= 0.2 ? 'Heard' : 'Quiet'}</span>
      </div>
    </div>
  );
}

function RobotDetail({ engine, robot, version }: { engine: SimulationEngine; robot: RobotState; version: number }) {
  const select = useSim((s) => s.select);
  const mode = useSim((s) => s.settings.mode);
  const issue = useSim((s) => s.issue);
  const conn = robotConnection(engine, robot);
  const received = [...(engine.network.recentReceived.get(robot.name) ?? [])].reverse().slice(0, 4);
  const links = engine.linksFor(robot.name);
  const known = robot.belief.cells.length - robot.belief.count(UNKNOWN);
  const brain = engine.controller.brains.get(robot.name);
  const remaining = Math.max(0, robot.path.length - 1);
  const canDrive = mode !== 'autonomous' && robot.manual && robot.alive;

  return (
    <div className="robot-detail">
      <button className="btn ghost small fleet-back" onClick={() => select(null)}>← All robots</button>
      <div className="detail-head">
        <span className={`type-icon big ${robot.type}`} aria-hidden />
        <div>
          <h2>{robot.label}</h2>
          <div className="faint">{robot.type === 'rover' ? 'Ground exploration' : 'Aerial reconnaissance'}</div>
        </div>
      </div>
      <div className="objective-card">
        <div className="label">CURRENT OBJECTIVE</div>
        <div className="objective">{describeObjective(robot.objective)}</div>
        {remaining > 0 && <div className="faint small">{remaining} steps to {robot.manual ? 'your waypoint' : 'the next goal'}</div>}
      </div>
      <div className="kv">
        <span>Battery</span><Battery robot={robot} />
        <span>Radio</span><span className={`tone-${conn.tone}`}>{conn.label}</span>
        <span>Local map</span><span>{Math.round(known / robot.belief.cells.length * 100)}% known</span>
      </div>
      <button className="btn focus-button" onClick={() => useSim.getState().focusOn(robot.name)} title="Bring this robot into view">◎ Focus camera</button>
      {canDrive && (
        <div className="drive">
          <div className="label">Drive {robot.label}</div>
          <div className="dpad">
            <button onClick={() => issue({ kind: 'manualStep', robot: robot.name, direction: 1 })} aria-label="Move north">▲</button>
            <button onClick={() => issue({ kind: 'manualStep', robot: robot.name, direction: 3 })} aria-label="Move west">◀</button>
            <button onClick={() => issue({ kind: 'manualStop', robot: robot.name })} aria-label="Stop">■</button>
            <button onClick={() => issue({ kind: 'manualStep', robot: robot.name, direction: 4 })} aria-label="Move east">▶</button>
            <button onClick={() => issue({ kind: 'manualStep', robot: robot.name, direction: 2 })} aria-label="Move south">▼</button>
          </div>
          <button className="btn small" onClick={() => issue({ kind: 'manualScan', robot: robot.name })}>Scan for survivors</button>
          <p className="faint small">Click the terrain for a waypoint. WASD moves · E scans · X stops.</p>
        </div>
      )}
      <details className="advanced disclosure">
        <summary>Local map</summary>
        <p className="explain">What {robot.label} has sensed and learned from delivered messages.</p>
        <MiniMap engine={engine} robot={robot} version={version} />
        <div className="legend-row faint small">
          <span className="sw free" /> Path <span className="sw wall" /> Wall <span className="sw rubble" /> Rubble <span className="sw unk" /> Unknown
        </div>
        <p className="faint small">Outlined markers show teammates at their last reported position.</p>
      </details>
      <details className="advanced disclosure">
        <summary>Sensor readings</summary>
        <p className="explain">Heat and sound are clues. A close scan confirms a survivor.</p>
        <SensorBars robot={robot} />
      </details>
      <details className="advanced disclosure">
        <summary>Team communication</summary>
        {!engine.network.enabled && <p className="faint small">Radio is disabled.</p>}
        <ul className="peers">
          {engine.robots.filter((r) => r.name !== robot.name).map((peer) => {
            const link = links.find((l) => l.a === peer.name || l.b === peer.name);
            const health = link?.health ?? 'down';
            const reason = link && link.health === 'down' ? (link.reason === 'range' ? 'Out of range' : link.reason === 'wall' ? 'Obstructed' : link.reason) : null;
            return (
              <li key={peer.name}>
                <span className={`conn-dot ${health === 'healthy' ? 'good' : health === 'weak' ? 'warn' : 'bad'}`} />
                {peer.label}<span className="faint">{health === 'down' ? reason ?? 'No link' : health === 'weak' ? 'Weak signal' : 'Connected'}</span>
              </li>
            );
          })}
        </ul>
        <div className="block">
          <div className="label">Recent messages</div>
          {!received.length && <p className="faint small">Waiting for the first team update.</p>}
          <ul className="received">
            {received.map((m) => (
              <li key={`${m.senderId}:${m.sequence}`}>
                <strong>{engine.label(m.senderId)}</strong><span className="faint small"> · {engine.step - m.sentStep} s ago</span>
                <div className="small">{m.mapCells.length ? `${m.mapCells.length} map cells shared${m.isSnapshot ? ' · recovery snapshot' : ''}` : 'Position update'}{m.evidence.thermal >= 0.35 && ' · heat detected'}</div>
              </li>
            ))}
          </ul>
        </div>
      </details>
      <details className="advanced disclosure">
        <summary>Technical details</summary>
        <div className="kv mono small">
          <span>Robot ID</span><span>{robot.name}</span>
          <span>Odometry</span><span>({robot.odomX.toFixed(2)}, {robot.odomY.toFixed(2)})</span>
          <span>Uncertainty</span><span>{robot.odomUncertainty.toFixed(3)}</span>
          <span>Local goal</span><span>{brain?.localGoal ? `(${brain.localGoal.x}, ${brain.localGoal.y})` : '—'}</span>
          <span>Message sequence</span><span>{engine.network.nextSeq.get(robot.name) ?? 0}</span>
          <span>Heat N/E/S/W</span><span>{robot.thermal.map((v) => v.toFixed(2)).join(' / ')}</span>
          <span>Acoustic</span><span>{robot.acoustic.toFixed(3)}</span>
          <span>Vision / radio</span><span>{robot.config.visionRadius} / {robot.config.commRadius} cells</span>
          <span>Distance traveled</span><span>{robot.distanceTravelled} cells</span>
          <span>Last action</span><span>{['Hold', 'North', 'South', 'West', 'East'][robot.lastAction]}</span>
        </div>
        <p className="faint small">{robot.type === 'rover' ? ROVER_DESCRIPTION : DRONE_DESCRIPTION}</p>
      </details>
    </div>
  );
}

export function RightPanel() {
  const version = useSim((s) => s.version);
  const engine = useSim((s) => s.engine);
  const selected = useSim((s) => s.selected);
  const robot = selected ? engine.robots.find((r) => r.name === selected) : null;
  return (
    <aside className="panel right" aria-label="Robot fleet">
      {robot ? <RobotDetail key={robot.name} engine={engine} robot={robot} version={version} /> : (
        <>
          <div className="panel-header">
            <span className="panel-eyebrow">BETTER TOGETHER</span>
            <h2>Your fleet <span className="fleet-count">{engine.robots.length}</span></h2>
            <p className="panel-intro">Select a robot to see what it knows.</p>
          </div>
          <div className="fleet-summary"><span className="conn-dot good" />{engine.robots.filter((r) => r.alive).length} robots operational</div>
          <div className="fleet">{engine.robots.map((r) => <FleetCard key={r.name} engine={engine} robot={r} />)}</div>
        </>
      )}
    </aside>
  );
}
