export interface ObservatoryPoint { x: number; y: number }
export interface ObservatoryGrid { width: number; height: number; resolution: number; originX: number; originY: number; yaw: number; cells: number[] }
export interface ObservatoryAgent {
  id: string; type: 'rover' | 'drone'; position: ObservatoryPoint | null; yaw: number; color: string;
  battery: number | null; state: string; fresh: boolean; knownCells: number; peerCells: number;
  goal: ObservatoryPoint | null; path: ObservatoryPoint[]; grid: ObservatoryGrid | null; peerGrid: ObservatoryGrid | null;
  frontiers: ObservatoryPoint[];
}
export interface ObservatoryPacket { id: string; source: string; target: string; kind: string; state: 'queued' | 'delivered' | 'applied' | 'dropped'; reason: string; time: number; receivedAt: number; cells: number | null; sequence: number }
export interface ObservatoryLink { source: string; target: string; state: 'healthy' | 'weak' | 'down' }
export interface ObservatorySnapshot {
  source: 'browser' | 'ros'; sourceLabel: string; time: number; running: boolean; fresh: boolean;
  agents: ObservatoryAgent[]; packets: ObservatoryPacket[]; links: ObservatoryLink[];
  metrics: { sent: number; delivered: number; dropped: number; bytes: number; applied: number | null };
  epoch: string;
}
export interface ObservatoryCanvasProps {
  snapshot: ObservatorySnapshot; selected: string | null; onSelect: (id: string) => void;
  view: 'spatial' | 'neural'; showPaths: boolean; showPackets: boolean; showFrontiers: boolean;
  frozen: boolean; zoom: number; cameraAngle?: 'isometric' | 'top';
}
