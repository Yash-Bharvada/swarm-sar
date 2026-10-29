from launch import LaunchDescription
from launch.actions import SetEnvironmentVariable
from launch_ros.actions import Node
from launch.substitutions import EnvironmentVariable, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    config = PathJoinSubstitution([FindPackageShare("swarm_sar_gazebo"), "config", "rviz_config.rviz"])
    return LaunchDescription([
        SetEnvironmentVariable("LP_NUM_THREADS", EnvironmentVariable("LP_NUM_THREADS", default_value="2")),
        Node(package="swarm_sar_control", executable="disaster_scene", output="screen"),
        Node(package="rviz2", executable="rviz2", arguments=["-d", config], parameters=[{"use_sim_time": True}], output="screen"),
    ])
