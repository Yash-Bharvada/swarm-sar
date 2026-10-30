"""Dedicated estimated-mapping profile; does not replace the original ROS demo.

Rover TF: map -> rover/map (known start) -> rover/odom (SLAM) ->
rover/base_footprint (wheel odometry). World odometry is evaluation-only.
"""
import atexit
import os
import tempfile
import yaml
from ament_index_python.packages import get_package_share_directory, get_package_prefix
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, IncludeLaunchDescription, RegisterEventHandler, EmitEvent, TimerAction, SetEnvironmentVariable
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.events import matches_action
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, Command, EnvironmentVariable
from launch_ros.actions import Node, LifecycleNode
from launch_ros.events.lifecycle import ChangeState
from launch_ros.event_handlers import OnStateTransition
from launch_ros.parameter_descriptions import ParameterValue
from lifecycle_msgs.msg import Transition
from swarm_sar_control.slam_support import slam_bridges

ROBOTS=(('rover_0','rover',-1.,-17.,0.),('rover_1','rover',-6.,-17.,0.),
        ('drone_0','drone',-5.,-5.,.18),('drone_1','drone',1.,-6.,.18))


def _setup(context):
    arg=lambda name:LaunchConfiguration(name).perform(context)
    robots=ROBOTS if arg('scenario')=='swarm' else ROBOTS[:2] if arg('scenario')=='rovers' else ROBOTS[:1]
    controller=arg('controller'); ppo_executable=arg('ppo_executable')
    if controller=='ppo':
        executable=os.path.join(get_package_prefix('swarm_sar_control'),'lib','swarm_sar_control',ppo_executable)
        if not os.path.isfile(executable) or not os.access(executable,os.X_OK):
            raise RuntimeError(f'PPO executable missing: {executable}. Recover the Linux PPO source and entry point; no heuristic fallback is permitted.')
    desc=get_package_share_directory('swarm_sar_description')
    share=get_package_share_directory('swarm_sar_gazebo')
    world=os.path.join(desc,'worlds','disaster_site.world')
    names=[r[0] for r in robots]; rovers=[r[0] for r in robots if r[1]=='rover']
    truth=[f'/{name}/ground_truth/odom' if kind=='rover' else f'/{name}/odom' for name,kind,*_ in robots]
    with open(os.path.join(share,'config','ros_gz_bridge.yaml')) as f:bridges=slam_bridges(yaml.safe_load(f),names,rovers)
    with tempfile.NamedTemporaryFile('w',prefix='swarm_slam_bridge_',suffix='.yaml',delete=False) as f:
        yaml.safe_dump(bridges,f); bridge_file=f.name
    atexit.register(lambda:os.path.exists(bridge_file) and os.unlink(bridge_file))
    common=dict(use_sim_time=True,agents=names,spawn_positions=[0. for _ in range(2*len(names))],truth_odom_topics=truth)
    actions=[
        SetEnvironmentVariable('LP_NUM_THREADS',EnvironmentVariable('LP_NUM_THREADS',default_value='2')),
        SetEnvironmentVariable('GZ_SIM_RESOURCE_PATH',[EnvironmentVariable('GZ_SIM_RESOURCE_PATH',default_value=''),':',desc,':',os.path.join(desc,'models')]),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(os.path.join(get_package_share_directory('ros_gz_sim'),'launch','gz_sim.launch.py')),
            launch_arguments=dict(gz_args='-r -v 3 '+('-s --headless-rendering ' if arg('headless')=='true' else '')+world,on_exit_shutdown='true').items()),
        Node(package='ros_gz_bridge',executable='parameter_bridge',name='ros_gz_bridge',parameters=[dict(config_file=bridge_file,use_sim_time=True)],output='screen'),
        Node(package='swarm_sar_control',executable='peer_network_bridge',parameters=[common,dict(channels=['peer','slam_peer'],bytes_per_second=32768.)],output='screen'),
        Node(package='swarm_sar_control',executable='survivor_oracle',parameters=[common,dict(world_file=world)],output='screen'),
        Node(package='rosbridge_server',executable='rosbridge_websocket',name='rosbridge_websocket',
                parameters=[dict(port=9090,address=arg('rosbridge_address'),use_sim_time=True)],condition=IfCondition(LaunchConfiguration('rosbridge')),output='screen'),
    ]
    for name,kind,x,y,z in robots:
        command=['xacro ',os.path.join(desc,'urdf',kind+'.urdf.xacro'),' robot_name:=',name,' low_resource:=',arg('low_resource')]
        if kind=='rover':command+=[' slam_mode:=true']
        description=ParameterValue(Command(command),value_type=str)
        actions += [
            Node(package='robot_state_publisher',executable='robot_state_publisher',namespace=name,parameters=[dict(robot_description=description,frame_prefix=name+'/',use_sim_time=True)]),
            Node(package='ros_gz_sim',executable='create',name='spawn_'+name,parameters=[dict(world='disaster_site',name=name,allow_renaming=False,x=x,y=y,z=z,string=description)],output='screen'),
        ]
        if kind=='rover':
            actions.append(Node(package='tf2_ros',executable='static_transform_publisher',name=name+'_known_start',
                arguments=['--x',str(x),'--y',str(y),'--z','0','--yaw','0','--pitch','0','--roll','0','--frame-id','map','--child-frame-id',name+'/map']))
            slam=LifecycleNode(package='slam_toolbox',executable='async_slam_toolbox_node',namespace=name,name='slam_toolbox',output='screen',
                parameters=[os.path.join(share,'config','slam_rover.yaml'),dict(use_sim_time=True,map_name='slam_map',use_map_saver=False,map_frame=name+'/map',odom_frame=name+'/odom',
                base_frame=name+'/base_footprint',scan_topic='/'+name+'/scan')],remappings=[('map','slam_map'),('map_metadata','slam_map_metadata')])
            actions += [slam,RegisterEventHandler(OnStateTransition(target_lifecycle_node=slam,goal_state='inactive',
                entities=[EmitEvent(event=ChangeState(lifecycle_node_matcher=matches_action(slam),transition_id=Transition.TRANSITION_ACTIVATE))])),
                TimerAction(period=2.,actions=[EmitEvent(event=ChangeState(lifecycle_node_matcher=matches_action(slam),transition_id=Transition.TRANSITION_CONFIGURE))])]
        else:
            actions.append(Node(package='tf2_ros',executable='static_transform_publisher',name=name+'_truth_origin',
                arguments=['--frame-id','map','--child-frame-id',name+'/odom']))
        actions.append(Node(package='swarm_sar_control',executable='slam_agent',namespace=name,name='slam_agent',output='screen',parameters=[dict(
            use_sim_time=True,agent_id=name,source_map='slam_map' if kind=='rover' else 'private_map',
            source_kind='slam_toolbox' if kind=='rover' else 'simulator_pose_raycast',publish_estimated_odom=kind=='rover')]))
        if controller!='external':
            params=[dict(use_sim_time=True,agent_id=name,robot_type=kind,initial_x=0.,initial_y=0.,initial_z=0.,
                external_belief_map=kind=='rover',accept_peer_map=False)]
            if controller=='ppo' and arg('ppo_params'):params.insert(0,arg('ppo_params'))
            actions.append(Node(package='swarm_sar_control',executable=ppo_executable if controller=='ppo' else 'waypoint_demo' if controller=='waypoint' else 'decentralized_agent',
                namespace=name,name='search_controller',parameters=params,output='screen'))
    actions.append(Node(package='swarm_sar_control',executable='disaster_scene',parameters=[dict(use_sim_time=True,map_topic='/rover_0/belief_map')],condition=IfCondition(LaunchConfiguration('rviz'))))
    readiness=Node(package='swarm_sar_control',executable='wait_for_simulation',parameters=[dict(scan_topic='/rover_0/scan')],condition=IfCondition(LaunchConfiguration('rviz')),output='screen')
    rviz=Node(package='rviz2',executable='rviz2',arguments=['-d',os.path.join(share,'config','slam_demo.rviz')],parameters=[dict(use_sim_time=True)])
    actions += [RegisterEventHandler(OnProcessExit(target_action=readiness,on_exit=lambda event,context:[rviz] if event.returncode==0 else [])),readiness]
    return actions


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('scenario',default_value='swarm',choices=['swarm','rovers','rover']),
        DeclareLaunchArgument('controller',default_value='external',choices=['external','ppo','waypoint','frontier']),
        DeclareLaunchArgument('ppo_executable',default_value='ppo_agent'),DeclareLaunchArgument('ppo_params',default_value=''),
        DeclareLaunchArgument('headless',default_value='false',choices=['true','false']),
        DeclareLaunchArgument('low_resource',default_value='true',choices=['true','false']),
        DeclareLaunchArgument('rviz',default_value='true',choices=['true','false']),
        DeclareLaunchArgument('rosbridge',default_value='false',choices=['true','false']),
        DeclareLaunchArgument('rosbridge_address',default_value='127.0.0.1'),OpaqueFunction(function=_setup)])
