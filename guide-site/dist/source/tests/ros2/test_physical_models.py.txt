"""Regression checks for the physical demo; requires sourced ROS/xacro."""
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
import pytest

ROOT = Path(__file__).resolve().parents[2]
DESC = ROOT / "simulation/ros2_ws/src/swarm_sar_description"


def model(kind):
    if not shutil.which("xacro"):
        pytest.skip("source ROS to validate expanded models")
    return ET.fromstring(subprocess.check_output(
        ["xacro", str(DESC / "urdf" / (kind+".urdf.xacro")), "robot_name:="+kind+"_0"], text=True))


def test_drone_has_four_independent_thrust_rotors_and_matching_controller():
    root = model("drone")
    motors = root.findall(".//plugin[@name='gz::sim::systems::MulticopterMotorModel']")
    controller = root.find(".//plugin[@name='gz::sim::systems::MulticopterVelocityControl']")
    assert len(motors) == 4
    assert {int(m.findtext("actuator_number")) for m in motors} == {0, 1, 2, 3}
    rotors = controller.findall("rotorConfiguration/rotor")
    assert sum(int(r.findtext("direction")) for r in rotors) == 0
    for motor, rotor in zip(motors, rotors):
        assert motor.findtext("jointName") == rotor.findtext("jointName")
        assert float(motor.findtext("motorConstant")) == float(rotor.findtext("forceConstant"))
        assert root.find("joint[@name='"+motor.findtext("jointName")+"']").attrib["type"] == "continuous"
    assert root.find(".//plugin[@name='gz::sim::systems::VelocityControl']") is None


def test_rover_wheels_touch_ground_without_initial_penetration():
    root = model("rover")
    base_z = float(root.find("joint[@name='base_joint']/origin").get("xyz").split()[2])
    wheel_z = float(root.find("joint[@name='front_left_wheel_joint']/origin").get("xyz").split()[2])
    radius = float(root.find("link[@name='front_left_wheel_link']/collision/geometry/cylinder").get("radius"))
    world = ET.parse(DESC / "worlds/disaster_site.world")
    floor = world.find(".//model[@name='floor']")
    floor_z = float(floor.findtext("pose").split()[2])
    floor_thickness = float(floor.findtext(".//collision/geometry/box/size").split()[2])
    assert base_z+wheel_z-radius == pytest.approx(floor_z+floor_thickness/2)
    drive = root.find(".//plugin[@name='gz::sim::systems::DiffDrive']")
    assert 0 < float(drive.findtext("max_linear_acceleration")) <= 0.5
    assert drive.findtext("odom_topic") != root.findtext(".//plugin[@name='gz::sim::systems::OdometryPublisher']/odom_topic")


def test_slam_model_labels_truth_separately_and_retains_wheel_tf():
    if not shutil.which("xacro"):
        pytest.skip("xacro required to expand SLAM model")
    root=ET.fromstring(subprocess.check_output(["xacro",str(DESC/'urdf/rover.urdf.xacro'),
        'robot_name:=rover_0','slam_mode:=true'],text=True))
    truth=root.find(".//plugin[@name='gz::sim::systems::OdometryPublisher']")
    wheel=root.find(".//plugin[@name='gz::sim::systems::DiffDrive']")
    assert truth.findtext('odom_frame')=='map'
    assert truth.findtext('robot_base_frame')=='rover_0/ground_truth_base'
    assert wheel.findtext('frame_id')=='rover_0/odom'
    assert wheel.findtext('child_frame_id')=='rover_0/base_footprint'
