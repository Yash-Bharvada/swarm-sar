"""Check occupancy rendering and detection-only survivor markers."""

import numpy as np

from nav_msgs.msg import OccupancyGrid
from visualization_msgs.msg import Marker
from swarm_sar_interfaces.msg import SurvivorEvidence
from swarm_sar_control.disaster_scene import SurvivorDetections, map_tiles


def test_projected_box_and_map_cells():
    grid = OccupancyGrid()
    grid.header.frame_id = "map"
    grid.info.width, grid.info.height, grid.info.resolution = 2, 2, .2
    grid.info.origin.position.x = -24.
    grid.info.origin.orientation.w = 1.
    grid.data = [-1, 0, 100, 50]
    marker = map_tiles(grid).markers[0]
    assert len(marker.points) == 18  # three observed cells, two triangles each
    assert np.allclose([(marker.points[i].x, marker.points[i].y) for i in (0,6,12)], [(.2, 0.), (0., .2), (.2, .2)])
    assert marker.pose.position.x == -24.
    assert marker.colors[0].r > marker.colors[12].r > marker.colors[6].r
    grid.data = [0] * 4
    assert len(map_tiles(grid).markers[0].points) == 12  # two row rectangles, not four cubes
    grid.data = [-1] * 4
    assert map_tiles(grid).markers[0].action == Marker.DELETE


def test_survivor_dots_require_detection_and_deduplicate_agents():
    detections = SurvivorDetections()
    assert detections.markers.markers == []
    evidence = SurvivorEvidence()
    evidence.header.frame_id = "map"
    evidence.source_id = "rover_0"
    evidence.estimated_pose.pose.position.x = 3.
    evidence.estimated_pose.pose.position.y = 4.
    evidence.thermal_confidence, evidence.acoustic_confidence = .2, .1
    assert not detections.observe(evidence)
    evidence.confirmed = True
    assert detections.observe(evidence)
    dot = detections.markers.markers[0]
    assert (dot.color.r, dot.color.g, dot.color.b, dot.color.a) == (0., 1., 0., 1.)
    assert (dot.pose.position.x, dot.pose.position.y) == (3., 4.)
    evidence.source_id = "drone_0"
    evidence.estimated_pose.pose.position.x = 3.2
    assert not detections.observe(evidence)
    evidence.estimated_pose.pose.position.x = 8.
    evidence.confirmed = False
    evidence.thermal_confidence, evidence.acoustic_confidence = .8, .4
    assert detections.observe(evidence)
    assert len(detections.markers.markers) == 2
    evidence.estimated_pose.pose.position.x = float('nan')
    assert not detections.observe(evidence)
