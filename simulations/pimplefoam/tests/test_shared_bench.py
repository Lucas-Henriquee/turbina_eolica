"""Confere as entradas compartilhadas pelos casos padrão."""

from pathlib import Path
import unittest

import yaml

SIMULATIONS = Path(__file__).resolve().parents[2]


class SharedBenchTests(unittest.TestCase):
    def test_default_cases_share_mesh_and_bench(self):
        pimple = SIMULATIONS / "pimplefoam"
        simple = SIMULATIONS / "simplefoam"
        transient = yaml.safe_load((pimple / "config.yaml").read_text())
        steady = yaml.safe_load((simple / "config.yaml").read_text())

        for section in ("mesh", "fluid", "initial", "turbulence"):
            with self.subTest(section=section):
                self.assertEqual(transient[section], steady[section])
        for name, value in transient["bench"].items():
            self.assertEqual(steady["bench"][name], value)
        for name, value in steady["geometry"].items():
            self.assertEqual(transient["geometry"][name], value)

        rotor = Path("constant/triSurface") / steady["geometry"]["rotor_stl"]
        self.assertEqual((pimple / rotor).read_bytes(), (simple / rotor).read_bytes())
