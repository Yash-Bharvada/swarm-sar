import type { CSSProperties, ReactNode } from 'react';

export type IconName = 'swarm' | 'overview' | 'settings' | 'fleet' | 'activity' | 'help' | 'layers' | 'plus' | 'minus' | 'home' | 'top' | 'orbit' | 'focus' | 'play' | 'pause' | 'reset' | 'close' | 'chevron' | 'signal' | 'person' | 'map' | 'clock' | 'rover' | 'drone' | 'check' | 'mouse' | 'volume' | 'muted' | 'music' | 'book';

const paths: Record<IconName, ReactNode> = {
  swarm: <><path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z" /><path d="m4 7.5 8 4.5 8-4.5M12 12v9M8 5.3l8 4.5" /></>,
  overview: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
  settings: <><path d="M4 7h16M4 17h16" /><circle cx="9" cy="7" r="3" /><circle cx="15" cy="17" r="3" /></>,
  fleet: <><rect x="4" y="7" width="16" height="12" rx="3" /><path d="M12 3v4M8 11h.01M16 11h.01M8 15h8M1 11v4M23 11v4" /></>,
  activity: <><path d="M3 12h4l3-8 4 16 3-8h4" /></>,
  help: <><circle cx="12" cy="12" r="9" /><path d="M9.5 8.5a2.5 2.5 0 1 1 4 2c-1 .6-1.5 1-1.5 2.5M12 17h.01" /></>,
  layers: <><path d="m12 3 10 5-10 5L2 8l10-5ZM2 12l10 5 10-5M2 16l10 5 10-5" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  minus: <path d="M5 12h14" />,
  home: <><path d="m3 10 9-7 9 7M5 9v11h14V9M9 20v-7h6v7" /></>,
  top: <><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M4 10h16M10 4v16" /></>,
  orbit: <><path d="m12 3 9 5-9 5-9-5 9-5ZM3 8v9l9 5 9-5V8M12 13v9" /></>,
  focus: <><path d="M8 3H3v5M16 3h5v5M21 16v5h-5M8 21H3v-5" /><circle cx="12" cy="12" r="3" /></>,
  play: <path d="m8 4 12 8-12 8V4Z" />,
  pause: <><path d="M8 5v14M16 5v14" /></>,
  reset: <><path d="M3 10a9 9 0 1 1 2 8M3 4v6h6" /></>,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  chevron: <path d="m9 5 7 7-7 7" />,
  signal: <><path d="M3 8a14 14 0 0 1 18 0M6 12a9 9 0 0 1 12 0M9 16a4 4 0 0 1 6 0M12 20h.01" /></>,
  person: <><circle cx="12" cy="6" r="3" /><path d="M6 21v-5a6 6 0 0 1 12 0v5M9 21v-4M15 21v-4" /></>,
  map: <><path d="m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2V5ZM9 3v16M15 5v16" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  rover: <><rect x="4" y="7" width="16" height="10" rx="3" /><path d="M7 7V4h7v3M7 11h5M3 17v3M8 17v3M16 17v3M21 17v3" /></>,
  drone: <><path d="m6 6 12 12M18 6 6 18" /><rect x="9" y="9" width="6" height="6" rx="2" /><ellipse cx="5" cy="5" rx="4" ry="2" /><ellipse cx="19" cy="5" rx="4" ry="2" /><ellipse cx="5" cy="19" rx="4" ry="2" /><ellipse cx="19" cy="19" rx="4" ry="2" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  mouse: <><rect x="6" y="2" width="12" height="20" rx="6" /><path d="M12 2v7M6 9h12" /></>,
  volume: <><path d="m11 4-6 5H2v6h3l6 5V4ZM15 8a6 6 0 0 1 0 8M18 4a11 11 0 0 1 0 16" /></>,
  muted: <><path d="m11 4-6 5H2v6h3l6 5V4ZM16 9l6 6M22 9l-6 6" /></>,
  book: <><path d="M12 5c-3-2-6-2-10-1v15c4-1 7-1 10 1 3-2 6-2 10-1V4c-4-1-7-1-10 1ZM12 5v15" /></>,
  music: <><path d="M9 18V5l12-2v13M9 8l12-2" /><ellipse cx="6" cy="18" rx="3" ry="2.5" /><ellipse cx="18" cy="16" rx="3" ry="2.5" /></>,
};

export function Icon({ name, size = 20, style }: { name: IconName; size?: number; style?: CSSProperties }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={style}>{paths[name]}</svg>;
}
