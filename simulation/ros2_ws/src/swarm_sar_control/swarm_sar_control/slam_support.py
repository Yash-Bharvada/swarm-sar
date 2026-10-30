"""ROS-independent SLAM geometry, coherent peer snapshots and bounded transport.

All coordinates are estimated/common-start-frame data. This module never reads
the disaster world, robot truth, model weights or survivor truth.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from collections import deque

import numpy as np


@dataclass(frozen=True)
class GridSpec:
    width: int = 240
    height: int = 240
    resolution: float = 0.2
    origin_x: float = -24.0
    origin_y: float = -24.0
    frame: str = "map"

    def __post_init__(self):
        if type(self.width) is not int or type(self.height) is not int or not 1 <= self.width <= 2048 or not 1 <= self.height <= 2048:
            raise ValueError("Invalid grid dimensions")
        if not all(math.isfinite(v) for v in (self.resolution, self.origin_x, self.origin_y)) or self.resolution <= 0:
            raise ValueError("Invalid grid geometry")
        if not self.frame:
            raise ValueError("A grid frame is required")

    def payload(self):
        return dict(width=self.width, height=self.height, resolution=self.resolution,
                    origin_x=self.origin_x, origin_y=self.origin_y, frame=self.frame)


def project_occupancy(data, width, height, resolution, origin, transform, target: GridSpec):
    """Regrid observed source-cell centers through SE(2), retaining occupied hits.

    origin is (x,y,yaw) in source frame; transform is source->target frame.
    Values 1..64 are uncertain and are excluded; >=65 is occupied. This is a
    conservative knowledge/display layer, not a replacement scan-matching backend.
    """
    if width < 1 or height < 1 or width * height > 4_194_304 or len(data) != width * height:
        raise ValueError("Invalid occupancy shape")
    if resolution <= 0 or not all(math.isfinite(v) for v in (resolution, *origin, *transform)):
        raise ValueError("Invalid occupancy transform")
    source = np.asarray(data, dtype=np.int16).reshape(height, width)
    if np.any((source < -1) | (source > 100)):
        raise ValueError("Invalid occupancy value")
    yy, xx = np.nonzero((source == 0) | (source >= 65))
    x, y = (xx + .5) * resolution, (yy + .5) * resolution
    c, s = math.cos(origin[2]), math.sin(origin[2])
    x, y = origin[0] + c*x - s*y, origin[1] + s*x + c*y
    c, s = math.cos(transform[2]), math.sin(transform[2])
    x, y = transform[0] + c*x - s*y, transform[1] + s*x + c*y
    gx = np.floor((x - target.origin_x) / target.resolution).astype(np.int64)
    gy = np.floor((y - target.origin_y) / target.resolution).astype(np.int64)
    inside = (gx >= 0) & (gy >= 0) & (gx < target.width) & (gy < target.height)
    result = np.full((target.height, target.width), -1, dtype=np.int8)
    # max.at resolves coarse-grid collisions without allowing free to erase wall.
    values = np.where(source[yy, xx] >= 65, 100, 0).astype(np.int8)
    np.maximum.at(result, (gy[inside], gx[inside]), values[inside])
    return result


def observed_cells(grid):
    y, x = np.nonzero(grid >= 0)
    return [[int(xx), int(yy), int(grid[yy, xx])] for xx, yy in zip(x, y)]


def frontier_graph(grid, spec: GridSpec, max_nodes=24):
    """Bounded frontier components from the private estimate, with stable cell IDs."""
    free, unknown = grid == 0, grid == -1
    adjacent = np.zeros_like(free)
    adjacent[1:] |= unknown[:-1]; adjacent[:-1] |= unknown[1:]
    adjacent[:, 1:] |= unknown[:, :-1]; adjacent[:, :-1] |= unknown[:, 1:]
    mask = free & adjacent
    seen = set(); nodes = []
    for yy, xx in np.argwhere(mask):
        key = int(xx), int(yy)
        if key in seen:
            continue
        queue = deque([key]); seen.add(key); component = []
        while queue:
            x, y = queue.popleft(); component.append((x, y))
            for p in ((x-1,y), (x+1,y), (x,y-1), (x,y+1)):
                if 0 <= p[0] < spec.width and 0 <= p[1] < spec.height and mask[p[1],p[0]] and p not in seen:
                    seen.add(p); queue.append(p)
        if len(component) < 3:
            continue
        cx = sum(p[0] for p in component)/len(component)
        cy = sum(p[1] for p in component)/len(component)
        x,y = min(component, key=lambda p: ((p[0]-cx)**2+(p[1]-cy)**2,p))
        nodes.append(dict(id=f"frontier:{x}:{y}", x=spec.origin_x+(x+.5)*spec.resolution,
                          y=spec.origin_y+(y+.5)*spec.resolution, cells=len(component)))
    nodes.sort(key=lambda n: (-n['cells'], n['id']))
    return nodes[:max_nodes]


class PeerKnowledge:
    """Atomic per-sender map snapshots, deduplication, leases and reset isolation."""
    def __init__(self, spec=GridSpec(), max_uncertainty=2.0, assembly_timeout=30.0):
        self.spec = spec; self.max_uncertainty = max_uncertainty
        self.assembly_timeout = assembly_timeout
        self.layers = {}; self.layer_age = {}; self.topologies = {}; self.claims = {}
        self.sessions = {}; self.retired = {}; self.seen = {}; self.pending = {}
        self.revisions = {}; self.claim_sequences = {}

    def expire(self, now):
        self.claims = {k:v for k,v in self.claims.items() if v[1] > now}
        self.pending = {k:v for k,v in self.pending.items() if now-v['started'] <= self.assembly_timeout}

    def accept_claim(self, sender, frame, payload, expires, now, sequence=0):
        """Short lived frontier intent; retained maps and live reservations differ."""
        self.expire(now)
        if expires <= now:return 'expired'
        if frame != self.spec.frame or payload.get('spec') != self.spec.payload():return 'unaligned'
        if self.sessions.get(sender) != payload.get('run'):return 'unknown_session'
        if sequence <= self.claim_sequences.get(sender,-1):return 'duplicate'
        goal=payload.get('goal')
        if goal is not None and (not isinstance(goal,list) or len(goal)!=2 or not all(type(v) in (int,float) and math.isfinite(v) for v in goal)):
            return 'malformed'
        self.claim_sequences[sender]=sequence
        if goal is None:self.claims.pop(sender,None)
        else:self.claims[sender]=(goal,expires)
        return 'claim_applied'

    def accept(self, sender, sequence, expires, frame, payload, now):
        self.expire(now)
        if expires <= now:
            return 'expired'
        if not sender or type(sequence) is not int or sequence < 0 or not isinstance(payload,dict):
            return 'malformed'
        if payload.get('schema') != 1 or not isinstance(payload.get('run'),str) or not payload['run']:
            return 'schema'
        if frame != self.spec.frame or payload.get('spec') != self.spec.payload():
            return 'unaligned'
        uncertainty = payload.get('uncertainty_m')
        if isinstance(uncertainty,bool) or not isinstance(uncertainty,(int,float)) or not math.isfinite(uncertainty) or not 0 <= uncertainty <= self.max_uncertainty:
            return 'uncertain'
        run = payload['run']
        if run in self.retired.get(sender,[]):
            return 'old_session'
        seen = self.seen.get(sender, ()) if self.sessions.get(sender) == run else ()
        if sequence in seen:
            return 'duplicate'
        # Validate all data before admitting the sequence or mutating a map.
        revision, chunk, count = payload.get('revision'), payload.get('chunk'), payload.get('chunks')
        if any(type(v) is not int for v in (revision,chunk,count)) or revision < 1 or not 1 <= count <= 4096 or not 0 <= chunk < count:
            return 'malformed'
        rows = payload.get('cells')
        if not isinstance(rows,list) or len(rows)>1024:
            return 'malformed'
        for row in rows:
            if not isinstance(row,list) or len(row)!=3 or any(type(v) is not int for v in row):
                return 'malformed'
            x,y,value=row
            if not 0<=x<self.spec.width or not 0<=y<self.spec.height or value not in (0,100):
                return 'malformed'
        nodes=payload.get('frontiers',[])
        if not isinstance(nodes,list) or len(nodes)>64:
            return 'malformed'
        for node in nodes:
            if not isinstance(node,dict) or not isinstance(node.get('id'),str) or not all(isinstance(node.get(k),(int,float)) and not isinstance(node[k],bool) and math.isfinite(node[k]) for k in ('x','y')):
                return 'malformed'
        # A malformed packet must never evict an already accepted session.
        if sender in self.sessions and self.sessions[sender] != run:
            self.retired.setdefault(sender,deque(maxlen=16)).append(self.sessions[sender])
            self.layers.pop(sender,None); self.layer_age.pop(sender,None); self.topologies.pop(sender,None)
            self.claims.pop(sender,None); self.pending.pop(sender,None); self.revisions.pop(sender,None)
            self.claim_sequences.pop(sender,None)
            self.seen[sender] = deque(maxlen=2048)
        self.sessions[sender] = run
        seen = self.seen.setdefault(sender,deque(maxlen=2048))
        if revision <= self.revisions.get(sender,0):
            seen.append(sequence); return 'stale_revision'
        state=self.pending.get(sender)
        if state and revision < state['revision']:
            return 'stale_revision'
        if not state or revision > state['revision']:
            state=dict(revision=revision,count=count,parts={},started=now,nodes=nodes)
            self.pending[sender]=state
        if count!=state['count']:
            return 'malformed'
        if chunk == 0:
            state['nodes'] = nodes
        seen.append(sequence); state['parts'][chunk]=rows
        if len(state['parts'])<count:
            return 'buffered'
        layer=np.full((self.spec.height,self.spec.width),-1,dtype=np.int8)
        for part in range(count):
            for x,y,v in state['parts'][part]: layer[y,x]=v
        self.layers[sender]=layer; self.layer_age[sender]=now
        self.topologies[sender]=state['nodes']; self.revisions[sender]=revision
        del self.pending[sender]
        return 'applied'

    def combined(self, local):
        result=local.copy()
        for source in sorted(self.layers):
            layer=self.layers[source]
            mask=(result<0)&(layer>=0); result[mask]=layer[mask]
        return result

    def peer_only(self, local):
        combined=self.combined(local)
        combined[local>=0]=-1
        return combined


class RadioBudget:
    """Token budget in serialized message bytes; zero means unlimited."""
    def __init__(self, bytes_per_second=0, burst_bytes=65536):
        if not all(math.isfinite(v) for v in (bytes_per_second,burst_bytes)) or bytes_per_second < 0 or burst_bytes < 1:
            raise ValueError('Invalid radio budget')
        self.rate=bytes_per_second; self.burst=max(burst_bytes,bytes_per_second)
        self.tokens={}; self.last={}

    def take(self, sender, size, now):
        if size < 0 or not math.isfinite(now):
            raise ValueError('Invalid packet size or time')
        if not self.rate:return True
        previous=self.last.get(sender,now)
        tokens=min(self.burst,self.tokens.get(sender,self.burst)+max(0,now-previous)*self.rate)
        self.last[sender]=max(previous,now)
        if size>tokens:
            self.tokens[sender]=tokens; return False
        self.tokens[sender]=tokens-size; return True


def slim_json(value):
    return json.dumps(value,separators=(',',':'),allow_nan=False)


def slam_bridges(entries, agents, rovers):
    """Keep channel truth for emulation; replace rover TF with wheel TF only."""
    import copy
    result=[]
    for entry in entries:
        topic=entry['gz_topic_name']
        if topic!='/clock' and topic.split('/')[1] not in agents:continue
        item=copy.deepcopy(entry)
        robot=topic.split('/')[1] if topic!='/clock' else ''
        if robot in rovers:
            if topic==f'/{robot}/tf':continue
            if topic==f'/{robot}/odom':item['ros_topic_name']=f'/{robot}/ground_truth/odom'
        result.append(item)
    for robot in rovers:
        result.append(dict(ros_topic_name='/tf',gz_topic_name=f'/{robot}/wheel_tf',
                           ros_type_name='tf2_msgs/msg/TFMessage',gz_type_name='gz.msgs.Pose_V',direction='GZ_TO_ROS'))
    return result
