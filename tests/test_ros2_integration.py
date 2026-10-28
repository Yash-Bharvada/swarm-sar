"""Static gates that run even when ROS 2 is not installed on the dev host."""

import ast
from pathlib import Path
import xml.etree.ElementTree as ET

import yaml


ROOT = Path(__file__).resolve().parents[1]
ROS = ROOT / "ros2_ws" / "src"


def test_ros_packages_and_xml_are_well_formed():
    packages = {
        "swarm_sar_interfaces",
        "swarm_sar_description",
        "swarm_sar_control",
        "swarm_sar_gazebo",
    }
    assert packages == {path.parent.name for path in ROS.glob("*/package.xml")}
    for path in ROS.glob("*/package.xml"):
        root = ET.parse(path).getroot()
        assert root.tag == "package"
        assert root.findtext("name") == path.parent.name
    ET.parse(ROS / "swarm_sar_description/worlds/disaster_site.world")
    ET.parse(ROS / "swarm_sar_description/urdf/rover.urdf.xacro")
    ET.parse(ROS / "swarm_sar_description/urdf/drone.urdf.xacro")


def test_ros_python_sources_parse_without_ros_installed():
    for path in ROS.rglob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_interfaces_preserve_transport_and_evidence_boundaries():
    peer = (ROS / "swarm_sar_interfaces/msg/PeerMessageEnvelope.msg").read_text()
    evidence = (ROS / "swarm_sar_interfaces/msg/SurvivorEvidence.msg").read_text()
    assert all(field in peer for field in ("sender_id", "target_id", "sequence", "expires_at", "payload_json"))
    assert all(field in evidence for field in ("thermal_confidence", "acoustic_confidence", "estimated_pose", "confirmed"))


def test_bridge_maps_all_robot_control_and_sensor_topics():
    config = yaml.safe_load((ROS / "swarm_sar_gazebo/config/ros_gz_bridge.yaml").read_text())
    topics = {entry["ros_topic_name"] for entry in config}
    for agent in ("rover_0", "rover_1", "drone_0", "drone_1"):
        assert f"/{agent}/cmd_vel" in topics
        assert f"/{agent}/odom" in topics
        assert f"/{agent}/scan" in topics
        assert f"/{agent}/imu/data" in topics
    assert "/clock" in topics


def test_master_launch_contains_full_stack():
    launch = (ROS / "swarm_sar_gazebo/launch/swarm_sar_sim.launch.py").read_text()
    for agent in ("rover_0", "rover_1", "drone_0", "drone_1"):
        assert agent in launch
    for executable in ("decentralized_agent", "peer_network_bridge", "survivor_oracle", "parameter_bridge"):
        assert executable in launch
    assert "rviz2" in launch


def test_default_demo_and_full_profile_have_the_documented_robot_counts():
    tree = ast.parse((ROS / "swarm_sar_gazebo/launch/swarm_sar_sim.launch.py").read_text())
    profiles = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"ROBOTS", "DEMO_ROBOTS"}
    }
    assert [robot[1] for robot in profiles["DEMO_ROBOTS"]].count("drone") == 2
    assert [robot[1] for robot in profiles["DEMO_ROBOTS"]].count("rover") == 1
    assert [robot[1] for robot in profiles["ROBOTS"]].count("drone") == 2
    assert [robot[1] for robot in profiles["ROBOTS"]].count("rover") == 2
    scenario_args = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Name) and node.func.id == "DeclareLaunchArgument"
                     and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == "scenario"]
    assert len(scenario_args) == 1
    assert next(keyword.value.value for keyword in scenario_args[0].keywords if keyword.arg == "default_value") == "demo"
