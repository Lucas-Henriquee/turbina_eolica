"""Confere o referencial de inércia da rotação restrita ao eixo Y."""

import copy
import math
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from body_corrections import apply_body_corrections, shaft_angular_momentum


def tensor(body):
    axes = np.array(body["orientation"]).reshape(3, 3)
    return axes @ np.diag(body["momentOfInertia"]) @ axes.T


def shaft_inertia(body, centre):
    offset = np.array(body["centreOfMass"]) - centre
    return tensor(body)[1, 1] + body["mass"] * (offset[0]**2 + offset[2]**2)


class BodyAxisTests(unittest.TestCase):
    def setUp(self):
        angle = 1.5e-5
        cosine, sine = math.cos(angle), math.sin(angle)
        self.body = {
            "mass": 0.117451266141,
            "centreOfMass": [0.002, 0.015, -0.003],
            "momentOfInertia": [7.6e-6, 0.0016667373, 0.001668586],
            "orientation": [1, 0, 0, 0, cosine, -sine, 0, sine, cosine],
        }
        self.geometry = {"rotation_centre": [0, 0, 0]}

    def assert_axis_y(self, body):
        axes = np.array(body["orientation"]).reshape(3, 3)
        np.testing.assert_array_equal(axes[:, 1], [0, 1, 0])
        np.testing.assert_allclose(axes.T @ axes, np.eye(3), atol=1e-15)
        self.assertAlmostEqual(np.linalg.det(axes), 1)
        # A restrição projeta momento angular no eixo corporal Y.
        omega = axes @ (np.array([0., 0.02, 0.]) / body["momentOfInertia"])
        self.assertEqual(omega[0], 0)
        self.assertEqual(omega[2], 0)

    def test_removes_tilt_without_magnet_corrections(self):
        original = copy.deepcopy(self.body)
        result = apply_body_corrections(self.body, self.geometry)
        self.assert_axis_y(result)
        self.assertEqual(result["centreOfMass"], self.body["centreOfMass"])
        self.assertEqual(self.body, original)
        self.assertAlmostEqual(shaft_inertia(result, self.geometry["rotation_centre"]),
                               shaft_inertia(self.body, self.geometry["rotation_centre"]), places=15)
        self.assertNotEqual(result["neglected_products_xy_yz_kg_m2"][1], 0)

    def test_keeps_effective_shaft_correction_with_offset_mass(self):
        geometry = dict(self.geometry, mass_correction_kg=0.000733954584,
                        shaft_inertia_correction_kg_m2=4.12849453e-8)
        result = apply_body_corrections(self.body, geometry)
        self.assert_axis_y(result)
        self.assertAlmostEqual(shaft_inertia(result, geometry["rotation_centre"]) -
                               shaft_inertia(self.body, geometry["rotation_centre"]),
                               geometry["shaft_inertia_correction_kg_m2"], places=15)

    def test_preserves_transverse_tensor(self):
        angle = 0.2
        cosine, sine = math.cos(angle), math.sin(angle)
        self.body["orientation"] = [cosine, 0, sine, 0, 1, 0, -sine, 0, cosine]
        result = apply_body_corrections(self.body, self.geometry)
        self.assert_axis_y(result)
        np.testing.assert_allclose(tensor(result), tensor(self.body), atol=1e-18)

    def test_preserves_aligned_body_and_legacy_defaults(self):
        self.body["orientation"] = np.eye(3).ravel().tolist()
        result = apply_body_corrections(self.body, self.geometry)
        self.assert_axis_y(result)
        self.assertEqual(result["momentOfInertia"], self.body["momentOfInertia"])
        self.assertEqual(result["mass"], self.body["mass"])
        self.assertEqual(result["mass_model"], "homogeneous_solid")

    def test_initial_rotation_accounts_for_offset_shaft(self):
        centre = self.geometry["rotation_centre"]
        body = apply_body_corrections(self.body, self.geometry)
        omega_y = -115 * math.pi / 30
        momentum = shaft_angular_momentum(body, centre, omega_y)
        np.testing.assert_allclose(momentum, [0, shaft_inertia(body, centre) * omega_y, 0])


if __name__ == "__main__":
    unittest.main()
