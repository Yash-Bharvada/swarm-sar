import unittest

from swarm_sar_control.decentralized_agent import _bresenham, _wrap
from swarm_sar_control.peer_network_bridge import _intersects


class ControlHelperTests(unittest.TestCase):
    def test_bresenham_includes_both_endpoints(self):
        self.assertEqual(
            list(_bresenham(0, 0, 3, 0)),
            [(0, 0), (1, 0), (2, 0), (3, 0)],
        )

    def test_angle_wrap_stays_in_principal_interval(self):
        self.assertLessEqual(-3.14160, _wrap(7.0))
        self.assertLessEqual(_wrap(7.0), 3.14160)

    def test_wall_intersection_detects_crossing_only(self):
        self.assertTrue(
            _intersects((0.0, 0.0), (2.0, 2.0), (0.0, 2.0), (2.0, 0.0))
        )
        self.assertFalse(
            _intersects((0.0, 0.0), (1.0, 0.0), (0.0, 2.0), (1.0, 2.0))
        )
