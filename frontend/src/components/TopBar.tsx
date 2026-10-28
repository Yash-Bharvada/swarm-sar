import { useSim } from '../store/simStore';
import { missionTime, networkHealth, pct } from '../app/format';

export function TopBar() {
  useSim((s) => s.version);
  const engine = useSim((s) => s.engine);
  const status = useSim((s) => s.status);
  const speed = useSim((s) => s.settings.speed);
  const configuredLoss = useSim((s) => s.settings.packetLoss);
  const found = engine.survivorsFound();
  const total = engine.scenario.victims.length;
  const health = networkHealth(engine);
  const alive = engine.robots.filter((r) => r.alive).length;
  const statusLabel =
    status === 'ready' ? 'Ready' : status === 'running' ? 'Running' : status === 'paused' ? 'Paused' : 'Complete';
  const m = engine.network.metrics;
  const measured = engine.measuredLoss();
  const dropped = m.droppedLoss + m.droppedPartition + m.droppedStale + m.droppedBandwidth;

  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark" aria-hidden>
          <span />
        </div>
        <div>
          <div className="brand-title">Swarm Mission Control</div>
          <div className="brand-sub">{engine.scenario.name} · seed {engine.scenario.seed}</div>
        </div>
      </div>
      <div className="chips">
        <div className={`chip status-${status}`}>
          <span className="dot" />
          <div>
            <div className="chip-label">Mission</div>
            <div className="chip-value">{statusLabel}</div>
          </div>
        </div>
        <div className={`chip survivors ${found === total && total ? 'all' : ''}`}>
          <div>
            <div className="chip-label">Survivors</div>
            <div className="chip-value">
              <strong>{found}</strong> of {total} found
            </div>
          </div>
        </div>
        <div className="chip">
          <div>
            <div className="chip-label">Coverage</div>
            <div className="chip-value">{pct(engine.coverage())}</div>
          </div>
        </div>
        <div className="chip">
          <div>
            <div className="chip-label">Elapsed</div>
            <div className="chip-value mono">
              {missionTime(engine.step)}
              <span className="faint"> / {missionTime(engine.maxSteps)}</span>
            </div>
          </div>
        </div>
        <div className="chip">
          <div>
            <div className="chip-label">Active robots</div>
            <div className="chip-value">
              {alive} / {engine.robots.length}
            </div>
          </div>
        </div>
        <div className={`chip net-${health.tone}`} title={health.detail}>
          <span className="dot" />
          <div>
            <div className="chip-label">Network</div>
            <div className="chip-value">{health.label}</div>
          </div>
        </div>
        <div className="chip" title={`Configured ${pct(configuredLoss)} · measured over all in-range packets`}>
          <div>
            <div className="chip-label">Packet loss</div>
            <div className="chip-value">
              {pct(configuredLoss)}{' '}
              <span className="faint">({measured === null ? 'measuring…' : `${pct(measured, 1)} measured`})</span>
            </div>
          </div>
        </div>
        <div className="chip" title="Messages sent / delivered / dropped">
          <div>
            <div className="chip-label">Msgs sent · ok · lost</div>
            <div className="chip-value mono">
              {m.messagesCreated} · <span className="good">{m.messagesDelivered}</span> · <span className="bad">{dropped}</span>
            </div>
          </div>
        </div>
        <div className="chip">
          <div>
            <div className="chip-label">Speed</div>
            <div className="chip-value">{speed}×</div>
          </div>
        </div>
      </div>
    </header>
  );
}
