"""Check visible survivor positions and encounter feasibility without fake detections."""
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from swarm_sar_control.peer_network_bridge import _intersects
from swarm_sar_control.survivor_oracle import survivors_from_world
from swarm_sar_control.waypoint_demo import DEMO_ROUTES


def test_visible_and_sensed_survivors_share_positions():
    description = Path(__file__).resolve().parents[2] / "swarm_sar_description"
    positions = survivors_from_world(description / "worlds/disaster_site.world")
    assert len(positions) == 10
    assert positions == [-14., 13., -2., 6., 14., 14., 13., -14., -1., -10.]
    person = ET.parse(description / "models/survivor/model.sdf")
    assert person.find(".//visual[@name='head']") is not None
    assert person.find(".//visual[@name='left_leg']") is not None
    assert person.find(".//collision") is None
    # Existing rover route's northern waypoint is (-1, -11). It can detect
    # the nearby person without crossing the damaged wall at y=-9.
    rover, survivor = (-1., -11.), tuple(positions[-2:])
    assert not _intersects(rover, survivor, (-7.5, -9.), (5.5, -9.))
    distance = math.dist(rover, survivor)
    assert math.exp(-distance/3.) >= .62
    assert math.exp(-distance/6.) >= .28


def test_each_drone_route_visits_a_survivor_without_crossing_the_other_lane():
    assert (-2., 6.) in DEMO_ROUTES["drone_0"]
    assert (13., -14.) in DEMO_ROUTES["drone_1"]
    assert max(x for x, _ in DEMO_ROUTES["drone_0"]) < min(x for x, _ in DEMO_ROUTES["drone_1"])
