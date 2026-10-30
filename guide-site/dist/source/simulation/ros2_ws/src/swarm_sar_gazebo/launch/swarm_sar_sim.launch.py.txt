"""Launch the disaster world, bridges, four robots, and decentralized stack."""

import atexit
import os
import tempfile
import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, SetEnvironmentVariable, OpaqueFunction, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, EnvironmentVariable, PathJoinSubstitution, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


ROBOTS = (
    ("rover_0", "rover", -16.0, -17.0, 0.0),
    ("rover_1", "rover", -14.0, -17.0, 0.0),
    ("drone_0", "drone", -16.0, -14.0, 2.5),
    ("drone_1", "drone", -13.5, -14.0, 2.5),
)
DEMO_ROBOTS = (
    ("rover_0", "rover", -1.0, -17.0, 0.0),
    ("drone_0", "drone", -5.0, -5.0, 0.18),
    ("drone_1", "drone", 1.0, -6.0, 0.18),
)


def _setup(context):
    scenario = LaunchConfiguration("scenario").perform(context)
    robots = {"demo": DEMO_ROBOTS, "full": ROBOTS, "pair": (ROBOTS[0], ROBOTS[2]), "rover": (ROBOTS[0],), "drone": (ROBOTS[2],)}[scenario]
    controller = "waypoint_demo" if scenario == "demo" else "decentralized_agent"
    headless = LaunchConfiguration("headless").perform(context) == "true"
    low_resource = LaunchConfiguration("low_resource").perform(context)
    shared = {"use_sim_time": True, "agents": [r[0] for r in robots],
              "spawn_positions": [0.0 for r in robots for _ in r[2:4]]}
    description_share = FindPackageShare("swarm_sar_description")
    gazebo_share = FindPackageShare("swarm_sar_gazebo")
    world = PathJoinSubstitution([description_share, "worlds", "disaster_site.world"])
    with open(os.path.join(get_package_share_directory("swarm_sar_gazebo"), "config", "ros_gz_bridge.yaml")) as stream:
        bridges = yaml.safe_load(stream)
    names = {r[0] for r in robots}
    bridges = [b for b in bridges if b["gz_topic_name"] == "/clock" or b["gz_topic_name"].split("/")[1] in names]
    with tempfile.NamedTemporaryFile(mode="w", prefix="swarm_bridge_", suffix=".yaml", delete=False) as stream:
        yaml.safe_dump(bridges, stream)
        bridge_config = stream.name
    atexit.register(lambda: os.path.exists(bridge_config) and os.unlink(bridge_config))
    actions = [
        # Limit Mesa software-renderer worker memory on the validation VM.
        SetEnvironmentVariable("LP_NUM_THREADS", EnvironmentVariable("LP_NUM_THREADS", default_value="2"), condition=IfCondition(LaunchConfiguration("low_resource"))),
        SetEnvironmentVariable(
            "GZ_SIM_RESOURCE_PATH",
            [EnvironmentVariable("GZ_SIM_RESOURCE_PATH", default_value=""), ":", description_share, ":", PathJoinSubstitution([description_share, "models"])],
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(PathJoinSubstitution([FindPackageShare("ros_gz_sim"), "launch", "gz_sim.launch.py"])),
            launch_arguments={"gz_args": ["-r -v 3 " + ("-s --headless-rendering " if headless else ""), world], "on_exit_shutdown": "true"}.items(),
        ),
        Node(package="ros_gz_bridge", executable="parameter_bridge", name="ros_gz_bridge", output="screen", parameters=[{"config_file": bridge_config, "use_sim_time": True}]),
        Node(package="swarm_sar_control", executable="peer_network_bridge", name="peer_network_bridge", output="screen", parameters=[shared]),
        Node(package="swarm_sar_control", executable="survivor_oracle", name="survivor_oracle", output="screen", parameters=[shared, {"world_file": world}]),
    ]
    for name, robot_type, x, y, z in robots:
        # All vehicles now use world-relative OdometryPublisher for simulation feedback.
        ox, oy, oz = 0.0, 0.0, 0.0
        xacro_file = PathJoinSubstitution([description_share, "urdf", f"{robot_type}.urdf.xacro"])
        robot_description = Command(["xacro ", xacro_file, " robot_name:=", name, " low_resource:=", low_resource])
        description_parameter = ParameterValue(robot_description, value_type=str)
        actions.extend(
            [
                Node(package="robot_state_publisher", executable="robot_state_publisher", namespace=name, name="robot_state_publisher", output="screen", parameters=[{"robot_description": description_parameter, "frame_prefix": f"{name}/", "use_sim_time": True}]),
                Node(package="tf2_ros", executable="static_transform_publisher", name=f"map_to_{name}_odom", arguments=["--x", str(ox), "--y", str(oy), "--z", str(oz), "--yaw", "0", "--pitch", "0", "--roll", "0", "--frame-id", "map", "--child-frame-id", f"{name}/odom"]),
                Node(package="ros_gz_sim", executable="create", name=f"spawn_{name}", output="screen", parameters=[{"world": "disaster_site", "name": name, "allow_renaming": False, "x": x, "y": y, "z": z, "string": description_parameter}]),
                Node(package="swarm_sar_control", executable=controller, namespace=name, name="decentralized_agent", output="screen", parameters=[{"agent_id": name, "robot_type": robot_type, "initial_x": ox, "initial_y": oy, "initial_z": oz, "use_sim_time": True}]),
            ]
        )
    actions.append(Node(package="swarm_sar_control", executable="disaster_scene", condition=IfCondition(LaunchConfiguration("rviz"))))
    # Start the second graphics app only after Gazebo has rendered sensor data.
    readiness = Node(package="swarm_sar_control", executable="wait_for_simulation", output="screen", parameters=[{"scan_topic": f"/{robots[0][0]}/scan"}], condition=IfCondition(LaunchConfiguration("rviz")))
    rviz = Node(package="rviz2", executable="rviz2", name="rviz2", output="screen", arguments=["-d", PathJoinSubstitution([gazebo_share, "config", "rviz_config.rviz"])], parameters=[{"use_sim_time": True}])
    actions.append(RegisterEventHandler(OnProcessExit(target_action=readiness, on_exit=lambda event, context: [rviz] if event.returncode == 0 else [])))
    actions.append(readiness)
    actions.append(Node(package="swarm_sar_control", executable="demo_views", name="demo_sensor_views", output="screen", condition=IfCondition(LaunchConfiguration("views"))))
    return actions


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("scenario", default_value="demo", choices=["demo", "full", "pair", "rover", "drone"]),
        DeclareLaunchArgument("headless", default_value="false", choices=["true", "false"]),
        DeclareLaunchArgument("rviz", default_value="true", choices=["true", "false"]),
        DeclareLaunchArgument("views", default_value="false", choices=["true", "false"]),
        DeclareLaunchArgument("low_resource", default_value="true", choices=["true", "false"]),
        OpaqueFunction(function=_setup),
    ])
