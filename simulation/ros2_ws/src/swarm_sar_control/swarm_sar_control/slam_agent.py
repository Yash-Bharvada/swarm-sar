"""Estimated-map/pose adapter and RF-mediated peer knowledge. Never drives motors.

slam_toolbox owns scan matching and loop closure. This node owns bounded sharing
and a per-agent belief view; the operator is never a coordination server.
"""
from collections import deque
import json
import math
import uuid

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.duration import Duration
from rclpy.time import Time
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from nav_msgs.msg import OccupancyGrid, Odometry, Path
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String
from tf2_ros import Buffer, TransformListener, TransformException
from swarm_sar_interfaces.msg import PeerMessageEnvelope, AgentStatus
from swarm_sar_control.slam_support import GridSpec, PeerKnowledge, project_occupancy, observed_cells, frontier_graph, slim_json


def yaw(q):
    return math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))


class SlamAgent(Node):
    def __init__(self):
        super().__init__('slam_agent')
        defaults = dict(agent_id=self.get_namespace().strip('/') or 'rover_0',
                        source_map='slam_map', source_kind='slam_toolbox',
                        base_frame='', publish_estimated_odom=True,
                        alignment_uncertainty_m=0.25, map_size=240, map_resolution=0.2,
                        snapshot_seconds=30.0, chunk_cells=256, max_map_age=5.0,
                        max_pose_age=1.0)
        for k,v in defaults.items(): self.declare_parameter(k,v)
        p=lambda k:self.get_parameter(k).value
        self.agent=str(p('agent_id')); self.source_kind=str(p('source_kind'))
        self.base=str(p('base_frame')) or self.agent+'/base_footprint'
        self.spec=GridSpec(int(p('map_size')),int(p('map_size')),float(p('map_resolution')),
                           -int(p('map_size'))*float(p('map_resolution'))/2,
                           -int(p('map_size'))*float(p('map_resolution'))/2)
        self.local=np.full((self.spec.height,self.spec.width),-1,dtype=np.int8)
        self.peers=PeerKnowledge(self.spec,assembly_timeout=90.0)
        self.tf=Buffer(); self.listener=TransformListener(self.tf,self)
        self.run=uuid.uuid4().hex; self.sequence=0; self.revision=0
        self.cached=None; self.map_stamp=0.; self.pose_stamp=0.; self.pose=None
        self.last_time=0.; self.reset_required=False; self.last_snapshot=-1e9
        self.last_repair=-1e9; self.outgoing=deque(); self.repairs=deque(maxlen=256)
        self.history={}; self.path=Path(); self.path.header.frame_id='map'
        self.goal=None; self.goal_stamp=0.
        qos=QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL,reliability=ReliabilityPolicy.RELIABLE)
        self.maps={k:self.create_publisher(OccupancyGrid,k,qos) for k in ('local_slam_map','belief_map','peer_map')}
        self.odom=self.create_publisher(Odometry,'odom',10) if p('publish_estimated_odom') else None
        self.estimate=self.create_publisher(Odometry,'estimated_odom',10)
        self.paths=self.create_publisher(Path,'estimated_path',1)
        self.health=self.create_publisher(String,'slam_health',1)
        self.topology=self.create_publisher(String,'topology',1)
        self.events=self.create_publisher(String,'/swarm/network/events',50)
        self.outbox=self.create_publisher(PeerMessageEnvelope,'slam_peer_outbox',50)
        self.create_subscription(OccupancyGrid,str(p('source_map')),self.receive_map,qos if self.source_kind=='slam_toolbox' else 1)
        self.create_subscription(PeerMessageEnvelope,'slam_peer_inbox',self.receive_peer,50)
        self.create_subscription(AgentStatus,'status',self.receive_status,10)
        self.create_timer(.1,self.tick)
        self.create_timer(1.,self.publish_views)

    def now(self):return self.get_clock().now().nanoseconds/1e9

    def receive_map(self,msg):self.cached=msg

    def receive_status(self,msg):
        if msg.agent_id!=self.agent or msg.header.frame_id!='map':return
        self.goal=[msg.claimed_frontier.x,msg.claimed_frontier.y] if msg.has_claim else None
        self.goal_stamp=self.now()

    def send(self,kind,payload,target=''):
        msg=PeerMessageEnvelope(); msg.header.stamp=self.get_clock().now().to_msg()
        msg.header.frame_id='map'; msg.sender_id=self.agent; msg.target_id=target
        msg.sequence=self.sequence; self.sequence+=1; msg.kind=kind
        msg.expires_at=(self.get_clock().now()+Duration(seconds=8.)).to_msg()
        if self.pose:msg.sender_pose.pose=self.pose.pose.pose
        msg.payload_json=slim_json(payload); self.outbox.publish(msg)

    def receive_peer(self,msg):
        if self.reset_required or msg.sender_id==self.agent:return
        try:
            payload=json.loads(msg.payload_json)
            if not isinstance(payload,dict):return
            if msg.kind=='slam_repair':
                if msg.header.frame_id!='map' or payload.get('run')!=self.run:return
                if msg.expires_at.sec+msg.expires_at.nanosec/1e9<=self.now():return
                rev=payload.get('revision'); missing=payload.get('missing',[])
                if type(rev) is not int or not isinstance(missing,list) or len(missing)>32:return
                chunks=self.history.get(rev,[])
                for index in missing:
                    if type(index) is int and 0<=index<len(chunks):self.repairs.append((msg.sender_id,chunks[index]))
                return
            if msg.kind=='slam_claim':
                result=self.peers.accept_claim(msg.sender_id,msg.header.frame_id,payload,msg.expires_at.sec+msg.expires_at.nanosec/1e9,self.now(),int(msg.sequence))
            elif msg.kind=='slam_snapshot':
                result=self.peers.accept(msg.sender_id,int(msg.sequence),msg.expires_at.sec+msg.expires_at.nanosec/1e9,
                                         msg.header.frame_id,payload,self.now())
            else:return
            self.events.publish(String(data=slim_json(dict(event='receiver_'+result,source=msg.sender_id,
                target=self.agent,sequence=int(msg.sequence),channel='slam_peer',sim_time=self.now()))))
        except (ValueError,TypeError,KeyError,OverflowError):return

    def tick(self):
        now=self.now()
        if now < self.last_time-.01:
            # A clock jump does not reset slam_toolbox's pose graph. Fail closed.
            self.reset_required=True; self.cached=None; self.pose=None
            self.local.fill(-1); self.peers=PeerKnowledge(self.spec)
            self.outgoing.clear(); self.repairs.clear(); self.history.clear()
            self.path.poses.clear()
        self.last_time=now
        if self.reset_required:return
        try:
            t=self.tf.lookup_transform('map',self.base,Time())
            stamp=t.header.stamp.sec+t.header.stamp.nanosec/1e9
            if stamp>0 and 0<=now-stamp<float(self.get_parameter('max_pose_age').value):
                odom=Odometry(); odom.header=t.header; odom.header.frame_id='map'
                odom.child_frame_id=self.base; odom.pose.pose.position.x=t.transform.translation.x
                odom.pose.pose.position.y=t.transform.translation.y
                odom.pose.pose.position.z=t.transform.translation.z
                odom.pose.pose.orientation=t.transform.rotation
                # TF has no pose covariance: do not manufacture certainty.
                odom.pose.covariance[0]=odom.pose.covariance[7]=odom.pose.covariance[35]=-1.
                self.pose=odom; self.pose_stamp=stamp; self.estimate.publish(odom)
                if self.odom:self.odom.publish(odom)
        except TransformException:pass
        if self.cached is not None:
            msg=self.cached; stamp=msg.header.stamp.sec+msg.header.stamp.nanosec/1e9
            if 0<=now-stamp<float(self.get_parameter('max_map_age').value):
                try:
                    t=self.tf.lookup_transform('map',msg.header.frame_id,Time.from_msg(msg.header.stamp))
                    tr=t.transform; o=msg.info.origin
                    self.local=project_occupancy(msg.data,msg.info.width,msg.info.height,msg.info.resolution,
                        (o.position.x,o.position.y,yaw(o.orientation)),(tr.translation.x,tr.translation.y,yaw(tr.rotation)),self.spec)
                    self.map_stamp=stamp; self.cached=None
                except (TransformException,ValueError):pass
        self.peers.expire(now)
        if not self.outgoing and now-self.last_snapshot>=float(self.get_parameter('snapshot_seconds').value) and self.map_stamp and now-self.map_stamp<5.:
            rows=observed_cells(self.local); size=int(self.get_parameter('chunk_cells').value)
            size=max(16,min(1024,size)); self.revision+=1
            chunks=[rows[i:i+size] for i in range(0,len(rows),size)] or [[]]
            nodes=frontier_graph(self.local,self.spec)
            packets=[dict(schema=1,run=self.run,spec=self.spec.payload(),uncertainty_m=float(self.get_parameter('alignment_uncertainty_m').value),
                revision=self.revision,chunk=i,chunks=len(chunks),cells=cells,frontiers=nodes if i==0 else [],
                source_kind=self.source_kind,captured_at=self.map_stamp) for i,cells in enumerate(chunks)]
            self.history[self.revision]=packets
            for rev in sorted(self.history)[:-2]:del self.history[rev]
            self.outgoing.extend(packets); self.last_snapshot=now
        # Repairs share the same modeled radio; alternate so new traffic cannot starve.
        if self.repairs and (not self.outgoing or self.sequence%2==0):
            target,payload=self.repairs.popleft(); self.send('slam_snapshot',payload,target)
        elif self.outgoing:self.send('slam_snapshot',self.outgoing.popleft())
        if now-self.last_repair>=1.:
            for source,state in self.peers.pending.items():
                missing=[i for i in range(state['count']) if i not in state['parts']][:32]
                if missing:self.send('slam_repair',dict(run=self.peers.sessions[source],revision=state['revision'],missing=missing),source)
            self.last_repair=now

    def grid_message(self,grid):
        msg=OccupancyGrid(); msg.header.stamp=self.get_clock().now().to_msg(); msg.header.frame_id='map'
        msg.info.width=self.spec.width; msg.info.height=self.spec.height; msg.info.resolution=self.spec.resolution
        msg.info.origin.position.x=self.spec.origin_x; msg.info.origin.position.y=self.spec.origin_y
        msg.info.origin.orientation.w=1.; msg.data=grid.ravel().astype(int).tolist(); return msg

    def publish_views(self):
        now=self.now()
        self.peers.expire(now)
        if not self.reset_required:
            self.send('slam_claim',dict(schema=1,run=self.run,spec=self.spec.payload(),goal=self.goal if now-self.goal_stamp<3. else None))
        for name,grid in [('local_slam_map',self.local),('belief_map',self.peers.combined(self.local)),('peer_map',self.peers.peer_only(self.local))]:
            self.maps[name].publish(self.grid_message(grid))
        if self.pose and now-self.pose_stamp<1. and not self.reset_required:
            pose=PoseStamped(); pose.header=self.pose.header; pose.pose=self.pose.pose.pose
            self.path.poses.append(pose); self.path.poses=self.path.poses[-2000:]
            self.path.header.stamp=self.pose.header.stamp; self.paths.publish(self.path)
        data=dict(agent=self.agent,run=self.run,source=self.source_kind,sim_time=now,
            state='restart_required' if self.reset_required else ('tracking' if now-self.pose_stamp<1. and now-self.map_stamp<5. and self.map_stamp>0 else 'waiting_or_stale'),
            local_known=int(np.count_nonzero(self.local>=0)),peer_known=int(np.count_nonzero(self.peers.peer_only(self.local)>=0)),
            map_age=now-self.map_stamp if self.map_stamp else None,pose_age=now-self.pose_stamp if self.pose_stamp else None,
            alignment='known_start',alignment_uncertainty_m=float(self.get_parameter('alignment_uncertainty_m').value),
            covariance_available=False,claims={k:dict(goal=v[0],expires_at=v[1]) for k,v in self.peers.claims.items()},
            peers={k:dict(age=now-v,revision=self.peers.revisions[k]) for k,v in self.peers.layer_age.items()})
        self.health.publish(String(data=slim_json(data)))
        self.topology.publish(String(data=slim_json(dict(agent=self.agent,sim_time=now,frame='map',
            local=frontier_graph(self.local,self.spec),peers=self.peers.topologies,
            claims={k:v[0] for k,v in self.peers.claims.items()},
            description='frontier components; no inferred traversability edges'))))


def main(args=None):
    rclpy.init(args=args); node=SlamAgent()
    try:rclpy.spin(node)
    except (KeyboardInterrupt,rclpy.executors.ExternalShutdownException):pass
    finally:node.destroy_node(); rclpy.try_shutdown()
