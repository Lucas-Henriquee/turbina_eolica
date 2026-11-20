"""Verifica carga elétrica, balanço de energia e correções do rotor."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "postprocessing")]
from generator_model import resolve_generator
from body_corrections import apply_body_corrections
from config_validation import validate_controls
from simulation_results import analyze, save_analysis
from check_mesh_motion import inspect_motion_log


class GeneratorModelTests(unittest.TestCase):
    def setUp(self):
        self.config = yaml.safe_load((ROOT / "config.yaml").read_text())

    def test_catalog_derivation_and_load_dependence(self):
        model = resolve_generator(self.config)
        self.assertAlmostEqual(model["internal_resistance_ohm"], 18 / 147)
        self.assertAlmostEqual(model["back_emf_constant_V_s_rad"], 0.00770244073484)
        self.assertAlmostEqual(model["electrical_damping_N_m_s_rad"], 5.803657557e-6)
        self.config["generator"]["load_resistance_ohm"] = 20
        self.assertLess(resolve_generator(self.config)["electrical_damping_N_m_s_rad"],
                        model["electrical_damping_N_m_s_rad"])

    def test_motion_check_rejects_invalid_mesh_or_coverage(self):
        valid = "Mesh OK.\nAMI: Patch source sum(weights) min:0.8 max:1.2 average:1\nEnd\n"
        self.assertEqual(inspect_motion_log(valid, 0.1), (0.8, 1.2))
        for invalid in [valid.replace("0.8", "0"), valid + "Failed 1 mesh checks.\n",
                        valid + "FOAM FATAL ERROR\n", "End\n", valid.replace("End", "")]:
            with self.assertRaises(ValueError):
                inspect_motion_log(invalid, 0.1)

    def test_invalid_parameters(self):
        for key, value in [("no_load_speed_rpm", 0), ("no_load_current_A", 148),
                           ("load_resistance_ohm", -1), ("shunt_resistance_ohm", -1),
                           ("nominal_voltage_V", float("nan")), ("stall_current_A", True)]:
            config = copy.deepcopy(self.config)
            config["generator"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                resolve_generator(config)

    def test_viscous_losses_match_catalog_point_only(self):
        model = resolve_generator(self.config)
        self.assertGreater(model["mechanical_damping_N_m_s_rad"], 0)
        self.assertAlmostEqual(model["mechanical_damping_N_m_s_rad"] * model["catalog_no_load_omega_rad_s"],
                               model["torque_constant_N_m_A"] * self.config["generator"]["no_load_current_A"])
        self.config["generator"]["mechanical_loss_model"] = "none"
        self.assertEqual(resolve_generator(self.config)["mechanical_damping_N_m_s_rad"], 0)
        del self.config["generator"]["mechanical_loss_model"]
        self.assertEqual(resolve_generator(self.config)["mechanical_damping_N_m_s_rad"], 0)
        self.config["generator"]["mechanical_loss_model"] = "invalid"
        with self.assertRaises(ValueError):
            resolve_generator(self.config)

    def test_legacy_config(self):
        del self.config["generator"]
        del self.config["motion"]["initial_rpm"]
        for key in ["mass_correction_kg", "shaft_inertia_correction_kg_m2"]:
            del self.config["geometry"][key]
        validate_controls(self.config, ROOT / "config/templates")
        self.assertFalse(resolve_generator(self.config)["enabled"])
        self.assertEqual(self.config["motion"]["initial_rpm"], 0.0)

    def test_mass_and_shaft_inertia_corrections(self):
        body = {"mass": 0.117451266141, "centreOfMass": [0.002, 0.015, -0.003],
                "momentOfInertia": [7.6e-6, 0.0016667373, 0.001668586],
                "orientation": np.eye(3).ravel().tolist()}
        original = copy.deepcopy(body)
        corrected = apply_body_corrections(body, self.config["geometry"])
        def inertia(value):
            axes = np.array(value["orientation"]).reshape(3, 3)
            com = value["centreOfMass"]
            return (axes @ np.diag(value["momentOfInertia"]) @ axes.T)[1, 1] + value["mass"] * (com[0]**2 + com[2]**2)
        self.assertEqual(body, original)
        self.assertAlmostEqual(corrected["mass"], 0.118185220725)
        self.assertAlmostEqual(inertia(corrected) - inertia(body), 4.12849453e-8, places=14)
        invalid = dict(self.config["geometry"], mass_correction_kg=-1)
        with self.assertRaises(ValueError):
            apply_body_corrections(body, invalid)

    def test_postprocessing_torque_sign_and_power_balance(self):
        for enabled in [False, True]:
            for omega in [-12.0, 0.0, 12.0]:
                with self.subTest(enabled=enabled, omega=omega), tempfile.TemporaryDirectory() as temp:
                    case = Path(temp)
                    config = copy.deepcopy(self.config)
                    config["motion"]["prescribed_rpm"] = None
                    config["generator"]["enabled"] = enabled
                    config["motion"]["shaft_damping"] = 1e-5
                    model = resolve_generator(config)
                    torque = (config["motion"]["shaft_damping"] + model["electrical_damping_N_m_s_rad"] + model["mechanical_damping_N_m_s_rad"]) * omega
                    body = {"mass": 0.118, "volume": 9.25e-5, "radius": 0.226,
                            "swept_area": np.pi * 0.226**2, "centreOfMass": [0, 0, 0],
                            "momentOfInertia": [1e-5, 0.001667, 0.001668],
                            "orientation": np.eye(3).ravel().tolist()}
                    (case / "metadata").mkdir()
                    (case / "metadata/resolved_config.json").write_text(json.dumps({"config": config, "body": body}))
                    (case / "logs").mkdir()
                    log = "".join(f"Time = {t}\nCentre of rotation: (0 0 0)\nCentre of mass: (0 0 0)\nLinear velocity: (0 0 0)\nAngular velocity: (0 {omega} 0)\n" for t in [0, 1, 2])
                    (case / "logs/log.pimpleFoam").write_text(log)
                    forces = case / "postProcessing/forcesRotor/0"
                    forces.mkdir(parents=True)
                    (forces / "moment.dat").write_text("# time total pressure\n" + "".join(f"{t} (0 {torque} 0) (0 0 0)\n" for t in [0, 1, 2]))
                    (forces / "force.dat").write_text("# time total pressure\n" + "".join(f"{t} (0 0 0) (0 0 0)\n" for t in [0, 1, 2]))
                    data, columns, _, summary = analyze(case)
                    result = dict(zip(columns, data.T))
                    self.assertAlmostEqual(summary["energy_balance_residual_J"], 0, places=12)
                    balance = summary["free_torque_balance"]
                    if omega:
                        self.assertAlmostEqual(balance["mean_aero_drive_torque_N_m"], abs(torque))
                        self.assertAlmostEqual(balance["balance_residual_N_m"], 0, places=12)
                    else:
                        self.assertIsNone(balance)
                    if enabled:
                        np.testing.assert_allclose(result["generator_load_power_W"] + result["generator_internal_loss_W"] + result["generator_shunt_loss_W"],
                                                   -result["generator_torque_y_N_m"] * omega, atol=1e-14)
                        self.assertTrue(np.all(result["generator_torque_y_N_m"] * omega <= 0))
                        if omega > 0:
                            save_analysis(case)
                            self.assertIn("generator_load_power_W", (case / "results/timeseries.csv").read_text().splitlines()[0])
                            saved = json.loads((case / "results/summary.json").read_text())
                            self.assertGreater(saved["generator_load_energy_J"], 0)
                    else:
                        self.assertTrue(np.isnan(result["generator_load_power_W"]).all())
                        self.assertIsNone(summary["generator_load_energy_J"])

    def test_prescribed_speed_reports_torque_components_without_motion_log(self):
        config = copy.deepcopy(self.config)
        config["motion"]["prescribed_rpm"] = -115.0
        body = {
            "mass": 0.118, "volume": 9.25e-5, "radius": 0.226,
            "swept_area": np.pi * 0.226**2, "centreOfMass": [0, 0, 0],
            "momentOfInertia": [1e-5, 0.001667, 0.001668],
            "orientation": np.eye(3).ravel().tolist(),
        }
        with tempfile.TemporaryDirectory() as temp:
            case = Path(temp)
            (case / "metadata").mkdir()
            (case / "metadata/resolved_config.json").write_text(
                json.dumps({"config": config, "body": body})
            )
            forces = case / "postProcessing/forcesRotor/0"
            forces.mkdir(parents=True)
            zero = "(0 0 0) (0 0 0) (0 0 0)"
            (forces / "force.dat").write_text(
                f"# time total pressure viscous\n0.1 {zero}\n4 {zero}\n"
            )
            for header, sample in [
                ("total pressure viscous", "(0 -0.0004 0) (0 -0.0005 0) (0 0.0001 0)"),
                ("pressure viscous porous", "(0 -0.0005 0) (0 0.0001 0) (0 0 0)"),
            ]:
                with self.subTest(header=header):
                    moment = "# time " + header + "\n"
                    moment += f"0.1 {sample}\n4 {sample}\n"
                    (forces / "moment.dat").write_text(moment)
                    _, _, motion, summary = analyze(case)
                    self.assertAlmostEqual(summary["final_rpm_y"], -115)
                    self.assertAlmostEqual(motion[-1, 11], -115 * np.pi / 30)
                    self.assertIsNone(summary["energy_balance_residual_J"])
                    balance = summary["prescribed_torque_balance"]
                    self.assertEqual(balance["complete_revolutions"], 3)
                    self.assertAlmostEqual(balance["window_start_s"], 4 - 3 * 60 / 115)
                    self.assertAlmostEqual(balance["mean_aero_drive_torque_N_m"], 0.0004)
                    self.assertAlmostEqual(balance["mean_pressure_drive_torque_N_m"], 0.0005)
                    self.assertAlmostEqual(balance["mean_viscous_drive_torque_N_m"], -0.0001)
                    self.assertAlmostEqual(
                        balance["net_drive_torque_N_m"], 0.0004 - balance["model_total_brake_N_m"]
                    )


if __name__ == "__main__":
    unittest.main()
