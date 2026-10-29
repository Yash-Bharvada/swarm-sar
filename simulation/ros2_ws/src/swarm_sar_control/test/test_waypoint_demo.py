import math
import unittest
from swarm_sar_control.waypoint_demo import slew


class SlewTests(unittest.TestCase):
    def test_accelerates_and_brakes_without_overshoot(self):
        value = 0.
        for _ in range(20):
            previous = value
            value = slew(value, 0.65, 0.05)
            self.assertLessEqual(abs(value-previous), 0.050001)
            self.assertLessEqual(value, 0.65)
        self.assertAlmostEqual(value, 0.65)
        for _ in range(20):
            value = slew(value, 0., 0.05)
            self.assertGreaterEqual(value, 0.)
        self.assertEqual(value, 0.)

    def test_reversal_is_bounded(self):
        self.assertAlmostEqual(slew(0.5, -0.5, 0.05), 0.45)
