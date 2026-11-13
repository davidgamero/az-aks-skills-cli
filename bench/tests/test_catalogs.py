import json
from pathlib import Path
import tempfile
import unittest

from aks_bench.catalogs import freeze, fingerprint, comparison_report
from aks_bench.mock import Simulator
from aks_bench.scenarios import make


def catalog(root, content):
    root.mkdir()
    (root / "skill.md").write_text(content)
    (root / "index.json").write_text(json.dumps({"version": 1, "skills": [{
        "id": "example", "title": "Example", "description": "Example procedure", "tags": ["test"], "path": "skill.md",
    }]}))


class CatalogExperimentTests(unittest.TestCase):
    def test_snapshot_stays_fixed_and_each_simulator_reads_its_own_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog(root / "source", "original instructions\n")
            before = freeze(root / "source", root / "original")
            self.assertEqual(before, fingerprint(root / "source"))
            (root / "source" / "skill.md").write_text("revised instructions\n")
            after = freeze(root / "source", root / "revised")
            self.assertNotEqual(before, after)
            self.assertEqual(before, fingerprint(root / "original"))
            original = Simulator(make("manual-scale"), skills=True, skills_dir=root / "original")
            revised = Simulator(make("manual-scale"), skills=True, skills_dir=root / "revised")
            args = ["aks", "skill", "show", "--name", "example"]
            for simulator, expected in ((original, "original"), (revised, "revised"), (original, "original")):
                result = simulator.call(args)
                self.assertEqual(result["exit_code"], 0, result)
                self.assertEqual(result["stdout"], expected + " instructions\n")

    def test_comparison_does_not_merge_original_and_revised_or_reward_failed_runs(self):
        rows = []
        for seed in (1, 2):
            for condition, elapsed in (("baseline", 5), ("original", 10), ("revised", 3)):
                rows.append({"scenario": "test", "requested_model": "test", "provider": "copilot",
                             "discovery": "passive", "docs_mode": "off", "seed": seed, "condition": condition,
                             "catalog_sha256": None if condition == "baseline" else condition,
                             "success": not (seed == 2 and condition == "revised"), "valid_trial": True,
                             "elapsed_s": elapsed, "skill_reads": int(condition != "baseline")})
        with tempfile.TemporaryDirectory() as directory:
            report = comparison_report(directory, rows)[0]
            self.assertEqual(report["original"]["successes"], 2)
            self.assertEqual(report["revised"]["failures"], 1)
            self.assertEqual(report["revised_minus_original"]["successful_pairs"], 1)
            self.assertEqual(report["revised_minus_original"]["median_delta"]["elapsed_s"], -7)
            self.assertEqual(report["revised_minus_baseline"]["median_delta"]["elapsed_s"], -2)
            with self.assertRaises(ValueError):
                comparison_report(directory, rows + [rows[0]])


if __name__ == "__main__":
    unittest.main()
