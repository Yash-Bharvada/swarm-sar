import { useState } from 'react';
import { useSim } from '../store/simStore';
import { missionTime } from '../app/format';
import type { TransmissionRecord } from '../simulation/network/PeerNetwork';

const TONE_ICON = { info: '·', success: '✓', warning: '!', danger: '!', network: '↗' } as const;

function Feed() {
  useSim((s) => s.version);
  const engine = useSim((s) => s.engine);
  const select = useSim((s) => s.select);
  const items = engine.feed.slice(-35).reverse();
  // Peer messages that carried new map cells, keyed so 'network' rows can be matched to them.
  const oldest = items.length ? items[items.length - 1].step : 0;
  const shares = new Set<string>();
  for (let i = engine.rawEvents.length - 1; i >= 0 && engine.rawEvents[i].step >= oldest; i--) {
    const { step, event } = engine.rawEvents[i];
    if (event.type === 'map_shared' && event.cells > 0) shares.add(`${step}|${event.from}|${event.to}`);
  }
  return (
    <ol className="feed" aria-label="Recent mission events">
      {!items.length && <li className="empty-state">Your mission story starts when the team launches.</li>}
      {items.map((f) => (
        <li
          key={f.id}
          className={`tone-${f.tone} ${f.tone === 'network' && shares.has(`${f.step}|${f.robots[0]}|${f.robots[1]}`) ? 'peer-share' : ''}`}
        >
          {f.robots[0] ? (
            <button className="feed-event-button" onClick={() => select(f.robots[0])} title={`Inspect ${engine.label(f.robots[0])}`}>
              <span className="feed-time mono">{missionTime(f.step)}</span>
              <span className="feed-icon" aria-hidden>{TONE_ICON[f.tone]}</span>
              <span className="feed-text">{f.text}</span>
            </button>
          ) : (
            <>
              <span className="feed-time mono">{missionTime(f.step)}</span>
              <span className="feed-icon" aria-hidden>{TONE_ICON[f.tone]}</span>
              <span className="feed-text">{f.text}</span>
            </>
          )}
        </li>
      ))}
    </ol>
  );
}

type Filter = 'all' | 'dropped' | 'delivered' | 'maps';

function NetworkLog() {
  useSim((s) => s.version);
  const engine = useSim((s) => s.engine);
  const isPPO = useSim((s) => s.controllerMode === 'ppo');
  const [filter, setFilter] = useState<Filter>('all');
  const keep = (r: TransmissionRecord) =>
    filter === 'all' || (filter === 'dropped' ? r.state === 'dropped' : filter === 'delivered' ? r.state === 'delivered' : r.mapDeltaSize > 0);
  const rows = engine.network.log.filter(keep).slice(-120).reverse();
  const reconnects = engine.network.events.filter((e) => e.kind === 'reconnect').slice(-6).reverse();
  const m = engine.network.metrics;
  return (
    <div className="netlog">
      {isPPO && <p className="explain">Python delivery snapshots. Drop totals are authoritative; individual drop traces and reconnect events are unavailable in this view.</p>}
      <div className="netlog-bar">
        {(['all', 'delivered', 'dropped', 'maps'] as Filter[]).map((f) => (
          <button key={f} className={filter === f ? 'on' : ''} onClick={() => setFilter(f)}>
            {f === 'maps' ? 'map deltas' : f}
          </button>
        ))}
        <details className="network-counters faint small">
          <summary>{engine.mapCellsMerged.toLocaleString()} map cells shared · {m.reconnections} reconnections</summary>
          <p>Lost {m.droppedLoss} · isolated {m.droppedPartition} · out of range {m.droppedRange} · obstructed {m.droppedWall} · expired {m.droppedStale} · duplicates {m.duplicatesSuppressed} · map merges refused {engine.mapMergesRefused}</p>
        </details>
      </div>
      <div className="netlog-body">
        <table aria-label="Radio transmissions">
          <thead>
            <tr>
              <th>Sent</th>
              <th>Sender</th>
              <th>Recipient</th>
              <th>Seq</th>
              <th>Type</th>
              <th>State</th>
              <th>Delay</th>
              <th>Expires</th>
              <th>Drop reason</th>
              <th>Map Δ</th>
            </tr>
          </thead>
          <tbody>
            {!rows.length && <tr><td colSpan={10} className="empty-state">No transmissions in this view yet.</td></tr>}
            {rows.map((r) => (
              <tr key={r.id} className={`st-${r.state}`}>
                <td className="mono">{r.step}</td>
                <td>{engine.label(r.senderId)}</td>
                <td>{engine.label(r.recipientId)}</td>
                <td className="mono">{r.sequence}</td>
                <td>{r.isSnapshot ? 'snapshot' : r.kind}</td>
                <td>{r.state}</td>
                <td className="mono">{r.state === 'dropped' ? '—' : `${r.delay}`}</td>
                <td className="mono">{r.expiresStep}</td>
                <td>{r.reason ?? ''}</td>
                <td className="mono">{r.mapDeltaSize || ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="reconnects">
          <div className="label">Reconnect events</div>
          {!reconnects.length && <div className="faint small">None yet</div>}
          {reconnects.map((e, i) => (
            <div key={i} className="small">
              <span className="mono faint">{missionTime(e.step)}</span> {engine.label(e.a)} ⇄ {engine.label(e.b)}
            </div>
          ))}
          <p className="faint small">Range/wall misses are counted but not listed per packet.</p>
        </div>
      </div>
    </div>
  );
}

export function EventFeed() {
  const netLog = useSim((s) => s.overlays.netLog);
  const toggle = useSim((s) => s.toggleOverlay);
  return (
    <footer className="bottom" aria-label="Mission activity">
      <div className="bottom-tabs" role="tablist" aria-label="Activity view">
        <button role="tab" aria-selected={!netLog} className={!netLog ? 'on' : ''} onClick={() => netLog && toggle('netLog')}>
          Mission events
        </button>
        <button role="tab" aria-selected={netLog} className={netLog ? 'on' : ''} onClick={() => !netLog && toggle('netLog')}>
          Radio log
        </button>
      </div>
      {netLog ? <NetworkLog /> : <Feed />}
    </footer>
  );
}
