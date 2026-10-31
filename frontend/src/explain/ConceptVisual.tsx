import { useState } from 'react';
import './concept-visual.css';

export type ConceptKind = 'slam' | 'learning' | 'cooperation' | 'communication' | 'gnn';

function RobotDot({ x, y, label, drone = false }: { x: number; y: number; label: string; drone?: boolean }) {
  return <g className="exv-robot" transform={`translate(${x} ${y})`}>
    {drone ? <path d="M-13-8 13 8M13-8-13 8" /> : <><path d="M-10 8h20M-6-11v-5h6" /><circle cy="-18" r="2" /></>}
    <circle r="9" className="exv-robot-body" /><circle cx="-3" cy="-1" r="1" /><circle cx="3" cy="-1" r="1" />
    <text y="28" textAnchor="middle" className="exv-svg-label">{label}</text>
  </g>;
}

const HOUSE_PATH = [12, 6, 7, 8, 2, 3, 4, 10];

function SlamVisual() {
  const [step, setStep] = useState(0);
  const visited = HOUSE_PATH.slice(0, step + 1);
  const current = HOUSE_PATH[step];
  const visible = (cell: number) => visited.some(previous => Math.abs(previous % 6 - cell % 6) + Math.abs(Math.floor(previous / 6) - Math.floor(cell / 6)) <= 1);
  const point = (cell: number) => `${33 + cell % 6 * 42},${24 + Math.floor(cell / 6) * 34}`;
  return <section className="exv-card" aria-label="Try building a little map">
    <div className="exv-label">TRY IT · A TINY UNKNOWN HOUSE</div>
    <svg viewBox="0 0 300 125" role="img" aria-label={`Robot explored ${visited.length} places, drawing a map as it walks.`}>
      {Array.from({ length: 18 }, (_, cell) => <rect key={cell} x={14 + cell % 6 * 42} y={9 + Math.floor(cell / 6) * 34} width="38" height="29" rx="5" className={visible(cell) ? 'exv-tile exv-tile-known' : 'exv-tile'} />)}
      <polyline points={visited.map(point).join(' ')} className="exv-route" />
      <g transform={`translate(${point(current).replace(',', ' ')})`} className="exv-map-rover"><circle r="10" /><path d="M-4-2h8M-4 3h8" /></g>
      <text x="281" y="99" textAnchor="end" className="exv-svg-label">? = not seen yet</text>
      {[5, 11, 17].filter(cell => !visible(cell)).map(cell => <text key={cell} x={33 + cell % 6 * 42} y={28 + Math.floor(cell / 6) * 34} textAnchor="middle" className="exv-unknown">?</text>)}
    </svg>
    <div className="exv-actions"><button type="button" onClick={() => setStep(Math.min(step + 1, HOUSE_PATH.length - 1))} disabled={step === HOUSE_PATH.length - 1}>Take a step <span aria-hidden="true">→</span></button><button type="button" className="exv-subtle" onClick={() => setStep(0)} disabled={step === 0}>Start over</button></div>
    <p className="exv-status" aria-live="polite">{step === 0 ? 'We can only see the rooms near us. Let’s walk!' : step === HOUSE_PATH.length - 1 ? 'A map and a trail! We learned where we are while drawing the house.' : `Step ${step}: a little more of the house appears. Our trail helps us remember where we are.`}</p>
  </section>;
}

function LearningVisual() {
  const [choice, setChoice] = useState<'new' | 'repeat' | null>(null);
  const [tries, setTries] = useState(0);
  const choose = (next: 'new' | 'repeat') => { setChoice(next); setTries(value => value + 1); };
  return <section className="exv-card" aria-label="Try a little reward game">
    <div className="exv-label">TRY IT · PRACTICE, THEN IMPROVE A LITTLE</div>
    <svg viewBox="0 0 300 115" role="img" aria-label={choice === 'new' ? 'A new route earns an example reward.' : choice === 'repeat' ? 'Repeating an explored route earns no example reward.' : 'Choose between a familiar loop and a new route.'}>
      <path d="M48 59C65 8 139 11 146 43C154 81 67 101 48 59" className={`exv-route exv-route-soft ${choice === 'repeat' ? 'exv-route-active' : ''}`} />
      <path d="M48 59 139 59 194 25 251 25" className={`exv-route exv-route-soft ${choice === 'new' ? 'exv-route-active' : ''}`} />
      <RobotDot x={48} y={59} label="You choose" />
      <text x="119" y="103" className="exv-svg-label" textAnchor="middle">Old loop</text>
      <rect x="225" y="7" width="54" height="38" rx="10" className={`exv-reward ${choice === 'new' ? 'exv-reward-earned' : ''}`} />
      <text x="252" y="32" className="exv-reward-text" textAnchor="middle">{choice === 'new' ? '+1' : '★'}</text>
      <text x="236" y="66" className="exv-svg-label" textAnchor="middle">New place</text>
    </svg>
    <div className="exv-actions"><button type="button" aria-pressed={choice === 'new'} onClick={() => choose('new')}>Explore a new place</button><button type="button" className="exv-subtle" aria-pressed={choice === 'repeat'} onClick={() => choose('repeat')}>Repeat the loop</button></div>
    <p className="exv-status" aria-live="polite">{choice === 'new' ? 'Example reward: +1 for discovering somewhere new. Make this choice a little more likely next time!' : choice === 'repeat' ? 'Example reward: 0. We already know this loop. Another route might help more.' : 'Pick a route. Helpful discoveries earn points in this tiny practice game.'}</p>
    <span className="exv-note">Teaching game · {tries} {tries === 1 ? 'choice' : 'choices'} · PPO makes small learning updates.</span>
  </section>;
}

function CooperationVisual() {
  const [split, setSplit] = useState(false);
  return <section className="exv-card" aria-label="Compare searching together and splitting the search">
    <div className="exv-label">TRY IT · TWO HELPERS, ONE SHARED GOAL</div>
    <svg viewBox="0 0 300 125" role="img" aria-label={split ? 'Two robots search different areas: six rooms explored.' : 'Two robots search the same area: three rooms explored.'}>
      {Array.from({ length: 6 }, (_, cell) => <rect key={cell} x={25 + cell % 3 * 85} y={11 + Math.floor(cell / 3) * 43} width="75" height="33" rx="7" className={`exv-tile ${cell < 3 ? 'exv-tile-known' : split ? 'exv-tile-blue' : ''}`} />)}
      <path d="M39 27H243" className="exv-route" />
      <path d={split ? 'M39 70H243' : 'M39 34H243'} className="exv-route exv-route-blue" />
      <RobotDot x={64} y={26} label="Rover" />
      <RobotDot x={235} y={split ? 70 : 26} label="Drone" drone />
      <text x="152" y="118" textAnchor="middle" className="exv-svg-label">{split ? 'Different jobs. More ground covered.' : 'Both helpers repeat the same search.'}</text>
    </svg>
    <div className="exv-actions"><button type="button" aria-pressed={!split} className={split ? 'exv-subtle' : ''} onClick={() => setSplit(false)}>Same route</button><button type="button" aria-pressed={split} className={split ? '' : 'exv-subtle'} onClick={() => setSplit(true)}>Split the search</button></div>
    <p className="exv-status" aria-live="polite">{split ? '6 rooms in our toy example! The whole team benefits when helpers cover different places.' : '3 rooms in our toy example. Two helpers walked the same route. Can we use their time better?'}</p>
    <span className="exv-note">Teaching illustration · This is not a performance benchmark.</span>
  </section>;
}

function CommunicationVisual() {
  const [connected, setConnected] = useState(true);
  const [sent, setSent] = useState(0);
  return <section className="exv-card" aria-label="Pass a message between nearby robots">
    <div className="exv-label">TRY IT · PASS A LITTLE NOTE</div>
    <svg viewBox="0 0 300 120" role="img" aria-label={connected ? 'A can share a note with B, who can pass it to C.' : 'C is out of reach. A and B can still share.'}>
      <path d="M52 55H146" className="exv-network" /><path d="M154 55H248" className={connected ? 'exv-network' : 'exv-network exv-network-off'} />
      {sent > 0 && <g key={`${sent}-${connected}`}><circle r="4" cy="55" cx="52" className="exv-message exv-message-first" />{connected && <circle r="4" cy="55" cx="154" className="exv-message exv-message-second" />}</g>}
      <RobotDot x={44} y={55} label="A: a clue!" /><RobotDot x={150} y={55} label="B: pass it on" drone />
      <g className={connected ? '' : 'exv-out-of-reach'}><RobotDot x={256} y={55} label={connected ? 'C: got it' : 'C: too far'} drone /></g>
      <text x="150" y="17" textAnchor="middle" className="exv-svg-label">{sent ? connected ? '“Look near the warm room!”' : 'A ↔ B still share their clues' : 'Neighbors help neighbors'}</text>
    </svg>
    <div className="exv-actions"><button type="button" onClick={() => setSent(value => value + 1)}>Send a clue <span aria-hidden="true">↗</span></button><button type="button" className="exv-subtle" aria-pressed={!connected} onClick={() => { setConnected(value => !value); setSent(0); }}>{connected ? 'Move C out of reach' : 'Bring C back'}</button></div>
    <p className="exv-status" aria-live="polite">{sent ? connected ? 'A shared with B. B can relay the clue to C. Useful news travels from neighbor to neighbor.' : 'C cannot get a new note right now. A and B keep helping each other.' : connected ? 'Tap Send. No central tower is needed in this little example.' : 'C is too far away. Try sending a clue between the remaining neighbors.'}</p>
    <span className="exv-note">Message illustration · Real links can delay or lose notes.</span>
  </section>;
}

const HINTS = [
  { label: 'Warm room', short: 'Warmth', x: 46, y: 25 },
  { label: 'Blocked hall', short: 'Wall', x: 46, y: 66 },
  { label: 'Low battery', short: 'Energy', x: 46, y: 107 },
];

function GnnVisual() {
  const [hints, setHints] = useState<number[]>([0]);
  const decision = hints.includes(2) ? 'Save energy. Choose a nearby clue.' : hints.includes(0) && hints.includes(1) ? 'Try another way to the warm room.' : hints.includes(0) ? 'Check the warm room.' : hints.includes(1) ? 'Look for an open route.' : 'Use my own nearby observations.';
  const toggle = (hint: number) => setHints(previous => previous.includes(hint) ? previous.filter(value => value !== hint) : [...previous, hint]);
  return <section className="exv-card" aria-label="Combine nearby teammate hints">
    <div className="exv-label">TRY IT · PUT SMALL CLUES TOGETHER</div>
    <svg viewBox="0 0 300 140" role="img" aria-label={`${hints.length} selected teammate hints feed one robot’s decision.`}>
      {HINTS.map((hint, index) => <g key={hint.short} className={hints.includes(index) ? '' : 'exv-out-of-reach'}>
        <path d={`M80 ${hint.y}Q129 ${hint.y} 150 66`} className="exv-network" />
        <rect x="5" y={hint.y - 13} width="77" height="26" rx="10" className="exv-hint" /><text x="44" y={hint.y + 4} textAnchor="middle" className="exv-svg-label">{hint.short}</text>
      </g>)}
      <circle cx="156" cy="66" r="26" className="exv-combine" /><RobotDot x={156} y={66} label="Combine" />
      <path d="M188 66H236M229 60l8 6-8 6" className="exv-route" />
      <rect x="240" y="47" width="52" height="38" rx="10" className="exv-hint" /><text x="266" y="70" textAnchor="middle" className="exv-svg-label">Decide</text>
    </svg>
    <div className="exv-actions exv-hint-actions">{HINTS.map((hint, index) => <button type="button" key={hint.label} className={hints.includes(index) ? '' : 'exv-subtle'} aria-pressed={hints.includes(index)} onClick={() => toggle(index)}>{hint.label}</button>)}</div>
    <p className="exv-status" aria-live="polite">{decision} <span className="exv-muted">Different clues can suggest a different next step.</span></p>
    <span className="exv-note">Illustration · These are story choices, not checkpoint predictions.</span>
  </section>;
}

export function ConceptVisual({ kind }: { kind: ConceptKind }) {
  switch (kind) {
    case 'slam': return <SlamVisual />;
    case 'learning': return <LearningVisual />;
    case 'cooperation': return <CooperationVisual />;
    case 'communication': return <CommunicationVisual />;
    case 'gnn': return <GnnVisual />;
  }
}
