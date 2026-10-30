#!/usr/bin/env python3
"""Live ROS smoke evidence. Never invents a PASS from static/local checks."""
import argparse
import json
import math
from pathlib import Path
import time
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data, QoSProfile, DurabilityPolicy
from nav_msgs.msg import OccupancyGrid, Odometry
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--agents',nargs='+',default=['rover_0','rover_1'])
    parser.add_argument('--seconds',type=float,default=120.)
    parser.add_argument('--wall-timeout',type=float,default=600.)
    parser.add_argument('--output',default='artifacts/slam_runtime.json')
    args=parser.parse_args()
    rclpy.init(); node=Node('slam_runtime_probe')
    result=dict(kind='live_ros_probe',agents={},tf_edges={},events={},network=None,failures=[],sim_elapsed=0.)
    for agent in args.agents:result['agents'][agent]=dict(scans=0,wheel=0,estimated=0,maps=0,known=[],positions=[],frames={},health=None)
    current=[None]; start=[None]; reset=[False]
    def clock(msg):
        value=msg.clock.sec+msg.clock.nanosec/1e9
        if current[0] is not None and value<current[0]:reset[0]=True
        current[0]=value
        if start[0] is None:start[0]=value
    subs=[node.create_subscription(Clock,'/clock',clock,qos_profile_sensor_data)]
    def tf(msg):
        for t in msg.transforms:
            key=t.header.frame_id+' -> '+t.child_frame_id
            result['tf_edges'][key]=result['tf_edges'].get(key,0)+1
    subs.append(node.create_subscription(TFMessage,'/tf',tf,100))
    def event(msg):
        try:
            key=json.loads(msg.data)['event']; result['events'][key]=result['events'].get(key,0)+1
        except (ValueError,KeyError):pass
    def stats(msg):
        try:result['network']=json.loads(msg.data)
        except ValueError:pass
    subs += [node.create_subscription(String,'/swarm/network/events',event,100),node.create_subscription(String,'/swarm/network/stats',stats,10)]
    for agent in args.agents:
        record=result['agents'][agent]
        def scan(msg,r=record):r['scans']+=1
        def wheel(msg,r=record):
            r['wheel']+=1; r['frames']['wheel']=msg.header.frame_id
        def estimated(msg,r=record):
            r['estimated']+=1; r['frames']['estimated']=msg.header.frame_id
            if len(r['positions'])<10000:r['positions'].append([msg.pose.pose.position.x,msg.pose.pose.position.y])
        def grid(msg,r=record):
            r['maps']+=1; r['frames']['map']=msg.header.frame_id
            r['known'].append(sum(v>=0 for v in msg.data)); r['known']=r['known'][-500:]
        def health(msg,r=record):
            try:r['health']=json.loads(msg.data)
            except ValueError:pass
        subs += [node.create_subscription(LaserScan,f'/{agent}/scan',scan,qos_profile_sensor_data),
                 node.create_subscription(Odometry,f'/{agent}/wheel_odom',wheel,qos_profile_sensor_data),
                 node.create_subscription(Odometry,f'/{agent}/estimated_odom',estimated,10),
                 node.create_subscription(OccupancyGrid,f'/{agent}/slam_map',grid,QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL)),
                 node.create_subscription(String,f'/{agent}/slam_health',health,10)]
    deadline=time.monotonic()+args.wall_timeout
    try:
        while rclpy.ok() and time.monotonic()<deadline:
            rclpy.spin_once(node,timeout_sec=.2)
            if start[0] is not None and current[0]-start[0]>=args.seconds:break
    except KeyboardInterrupt:result['failures'].append('interrupted')
    result['sim_elapsed']=0. if start[0] is None else current[0]-start[0]
    if result['sim_elapsed']<args.seconds:result['failures'].append('insufficient simulation time / wall timeout')
    if reset[0]:result['failures'].append('clock rewind: restart full SLAM launch')
    for agent,r in result['agents'].items():
        positions=r.pop('positions'); r['displacement_span_m']=max((math.dist(positions[0],p) for p in positions),default=0.)
        conditions=dict(scans=r['scans']>=10,wheel=r['wheel']>=10,estimated=r['estimated']>=10,
            scan_maps=r['maps']>=3,observed=max(r['known'],default=0)>100,moving=r['displacement_span_m']>.5,
            wheel_frame=r['frames'].get('wheel')==agent+'/odom',estimated_frame=r['frames'].get('estimated')=='map',
            local_map_frame=r['frames'].get('map')==agent+'/map',tracking=(r['health'] or {}).get('state')=='tracking',
            slam_tf=result['tf_edges'].get(agent+'/map -> '+agent+'/odom',0)>0,
            wheel_tf=result['tf_edges'].get(agent+'/odom -> '+agent+'/base_footprint',0)>0,
            no_truth_tf=not any(key.endswith(' -> '+agent+'/ground_truth_base') for key in result['tf_edges']))
        r['checks']=conditions
        result['failures'] += [agent+': '+name for name,ok in conditions.items() if not ok]
    if len(args.agents)>1 and result['events'].get('receiver_applied',0)==0:result['failures'].append('no peer snapshot applied')
    result['passed']=not result['failures']
    result['limits']='Smoke test only; does not prove PPO loading, loop closure success, map accuracy, isolated recovery or unique TF publishers. Validate those separately.'
    output=Path(args.output); output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=result['passed'],failures=result['failures'],output=str(output)),indent=2))
    node.destroy_node(); rclpy.try_shutdown()
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
