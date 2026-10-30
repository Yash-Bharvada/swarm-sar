/** A read-only ROS topic client plus the explicitly requested radio fault service. */
export type RosGrid = { header: { frame_id: string }; info: { width: number; height: number; resolution: number; origin: { position: { x: number; y: number }; orientation: { x: number; y: number; z: number; w: number } } }; data: number[] };
export type RosPose = { header: { frame_id: string }; pose: { pose: { position: { x: number; y: number }; orientation: { z: number; w: number } } } };
export type NetEvent = { event: string; source: string; target: string; sequence: number; channel: string; sim_time: number };
export type Health = { agent: string; run: string; state: string; source: string; sim_time: number; local_known: number; peer_known: number; map_age: number | null; pose_age: number | null; peers: Record<string, { age: number; revision: number }>; claims?: Record<string, { goal: [number, number]; expires_at: number }> };
export type Stats = { sim_time: number; metrics: Record<string, number>; isolated: string[]; queue: number; reset_required: boolean; bytes_per_second: number };

export function validGrid(value: unknown): value is RosGrid {
  const g = value as RosGrid | null;
  if (!g?.info || !g.header || g.header.frame_id !== 'map' || !Array.isArray(g.data)) return false;
  const { width, height, resolution, origin } = g.info;
  return Number.isInteger(width) && width > 0 && Number.isInteger(height) && height > 0 && width * height <= 1048576
    && g.data.length === width * height && Number.isFinite(resolution) && resolution > 0
    && !!origin?.position && !!origin.orientation
    && [origin.position.x, origin.position.y, origin.orientation.x, origin.orientation.y, origin.orientation.z, origin.orientation.w].every(Number.isFinite)
    && g.data.every(v => Number.isInteger(v) && v >= -1 && v <= 100);
}

/** ROS cell center -> mission meters, including nonzero/rotated grid origins. */
export function cellWorld(g: RosGrid, x: number, y: number): [number, number] {
  const o = g.info.origin, q = o.orientation;
  const angle = Math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z));
  const a = (x + .5) * g.info.resolution, b = (y + .5) * g.info.resolution;
  return [o.position.x + Math.cos(angle) * a - Math.sin(angle) * b, o.position.y + Math.sin(angle) * a + Math.cos(angle) * b];
}

type Subscriber = { topic: string; type: string; callback: (msg: unknown) => void; throttle: number };
export class RosConnection {
  private socket: WebSocket | null = null;
  private subscriptions: Subscriber[] = [];
  private pending = new Map<string, { resolve: (v: unknown) => void; reject: (e: Error) => void; timer: ReturnType<typeof setTimeout> }>();
  private nextId = 0;
  constructor(private onState: (state: string) => void) {}
  subscribe(topic: string, type: string, callback: Subscriber['callback'], throttle = 250) {
    this.subscriptions.push({ topic, type, callback, throttle });
  }
  connect(url: string) {
    this.close();
    const parsed = new URL(url);
    if (!['ws:', 'wss:'].includes(parsed.protocol)) throw new Error('Use a ws:// or wss:// rosbridge address');
    this.onState('connecting');
    const socket = new WebSocket(parsed.toString()); this.socket = socket;
    socket.onopen = () => {
      if (this.socket !== socket) return;
      this.onState('connected');
      for (const s of this.subscriptions) socket.send(JSON.stringify({ op: 'subscribe', topic: s.topic, type: s.type, throttle_rate: s.throttle, queue_length: 1 }));
    };
    socket.onmessage = ({ data }) => {
      if (this.socket !== socket || typeof data !== 'string') return;
      try {
        const event = JSON.parse(data);
        if (event.op === 'publish') for (const s of this.subscriptions) if (s.topic === event.topic) s.callback(event.msg);
        if (event.op === 'service_response' && this.pending.has(event.id)) {
          const p = this.pending.get(event.id)!; clearTimeout(p.timer); this.pending.delete(event.id);
          if (event.result === false || event.values?.success === false) p.reject(new Error(event.values?.message || 'ROS service failed'));
          else p.resolve(event.values);
        }
      } catch { /* Ignore malformed telemetry; never convert it into simulated state. */ }
    };
    socket.onerror = () => { if (this.socket === socket) this.onState('connection error'); };
    socket.onclose = () => {
      if (this.socket !== socket) return;
      this.onState('disconnected'); this.rejectPending();
    };
  }
  isolate(agent: string, isolated: boolean) {
    if (!/^\w+$/.test(agent)) return Promise.reject(new Error('Invalid agent'));
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return Promise.reject(new Error('ROS is disconnected'));
    const id = `radio-${++this.nextId}`;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error('ROS service timed out; fault state is unconfirmed')); }, 5000);
      this.pending.set(id, { resolve, reject, timer });
      this.socket!.send(JSON.stringify({ op: 'call_service', service: `/swarm/network/isolate/${agent}`, type: 'std_srvs/srv/SetBool', args: { data: isolated }, id }));
    });
  }
  private rejectPending() {
    for (const p of this.pending.values()) { clearTimeout(p.timer); p.reject(new Error('ROS connection closed')); }
    this.pending.clear();
  }
  close() {
    const socket = this.socket; this.socket = null; socket?.close(); this.rejectPending();
    this.onState('disconnected');
  }
}
