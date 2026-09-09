import math
import unittest
from solve import fit


class TestFit(unittest.TestCase):
    def test_known_result(self):
        self.assertEqual(fit([0, 1, 2, 3], [1, 3, 5, 7]),
                         {"slope": 2.0, "intercept": 1.0, "sse": 0.0})

    def test_negative_slope(self):
        self.assertEqual(fit([0, 1, 2], [3, 2, 1])["slope"], -1.0)

    def test_length_mismatch(self):
        with self.assertRaises(ValueError):
            fit([0, 1], [1])

    def test_zero_variance(self):
        with self.assertRaises(ValueError):
            fit([1, 1], [2, 3])

    def test_nonfinite(self):
        with self.assertRaises(ValueError):
            fit([0, math.inf], [1, 2])


if __name__ == "__main__":
    unittest.main()
