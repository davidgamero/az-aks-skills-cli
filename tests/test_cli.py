import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SHIM = ROOT / "bin" / "az"


class ShimTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.fake_dir = self.work / "fake"
        self.fake_dir.mkdir()
        self.fake = self.fake_dir / "az"
        self.fake.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "print(json.dumps({'args': sys.argv[1:], 'cwd': os.getcwd(), "
            "'input': sys.stdin.read(), 'env': os.environ.get('TEST_VALUE')}))\n"
            "print('real az stderr', file=sys.stderr)\n"
            "sys.exit(23)\n",
            encoding="utf-8",
        )
        self.fake.chmod(0o755)
        (self.fake_dir / "python3").symlink_to(sys.executable)
        self.env = {key: value for key, value in os.environ.items() if not (
            key.startswith("AZ_AKS_") or key == "_AZ_AKS_SKILL_SHIMS"
        )}
        self.env["AZ_AKS_REAL_AZ"] = str(self.fake)

    def invoke(self, *args, env=None, input=""):
        return subprocess.run(
            [str(SHIM), *args], env=self.env if env is None else env,
            cwd=self.work, input=input, text=True, capture_output=True, timeout=10,
        )

    def test_list_from_another_directory(self):
        result = self.invoke("aks", "skill", "list", "-o", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = json.loads(result.stdout)
        self.assertEqual([row["id"] for row in rows], [
            "aks-node-pools", "aks-pod-troubleshooting", "aks-upgrade",
        ])
        self.assertEqual(set(rows[0]), {"id", "title", "description", "tags"})
        self.assertEqual(result.stderr, "")

    def test_search_all_terms_case_insensitive(self):
        result = self.invoke("aks", "skill", "search", "NODE capacity", "-o", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([row["id"] for row in json.loads(result.stdout)], ["aks-node-pools"])

    def test_no_matches_is_success(self):
        result = self.invoke("aks", "skill", "search", "unmatched", "-o", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [])

    def test_show_markdown_and_json(self):
        expected = (ROOT / "skills" / "aks-upgrade" / "SKILL.md").read_text()
        result = self.invoke("aks", "skill", "show", "--name", "aks-upgrade")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, expected)
        result = self.invoke("aks", "skill", "show", "--name", "aks-upgrade", "-o", "json")
        self.assertEqual(json.loads(result.stdout)["content"], expected)

    def test_local_errors_do_not_forward(self):
        for args, code in [
            (["show", "--name", "missing"], 1),
            (["search", "   "], 1),
            (["show"], 2),
            (["unknown"], 2),
            (["list", "--subscription", "example"], 2),
        ]:
            with self.subTest(args=args):
                result = self.invoke("aks", "skill", *args)
                self.assertEqual(result.returncode, code)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr)
                self.assertNotIn("real az stderr", result.stderr)

    def test_help_does_not_require_catalog_or_real_az(self):
        self.env["AZ_AKS_SKILLS_DIR"] = str(self.work / "missing")
        self.env["AZ_AKS_REAL_AZ"] = str(self.work / "missing-az")
        for group in ("skill", "skills"):
            for arguments in ([], ["--help"], ["-h"]):
                with self.subTest(group=group, arguments=arguments):
                    result = self.invoke("aks", group, *arguments)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stderr, "")
                    self.assertTrue(result.stdout.startswith("Group\n"))
                    for text in ("Commands:", "Examples", "list", "search", "show",
                                 f"az aks {group} show --name aks-upgrade"):
                        self.assertIn(text, result.stdout)

    def test_subcommand_help_explains_required_syntax(self):
        for group in ("skill", "skills"):
            for command, required in (("show", "--name [Required]"), ("search", "QUERY [Required]"),
                                      ("list", "Default: table.")):
                with self.subTest(group=group, command=command):
                    result = self.invoke("aks", group, command, "--help")
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertTrue(result.stdout.startswith("Command\n"))
                    self.assertIn(required, result.stdout)
                    self.assertIn("Examples", result.stdout)

    def test_plural_alias_returns_the_same_data(self):
        for args in (["list", "-o", "json"], ["search", "upgrade", "-o", "json"],
                     ["show", "--name", "aks-upgrade"]):
            with self.subTest(args=args):
                singular = self.invoke("aks", "skill", *args)
                plural = self.invoke("aks", "skills", *args)
                self.assertEqual(plural.returncode, 0, plural.stderr)
                self.assertEqual(plural.stdout, singular.stdout)

    def test_passthrough_preserves_process_inputs_and_exit_status(self):
        self.env["TEST_VALUE"] = "environment unchanged"
        args = ["aks", "show", "--name", "space and $literal", "--query", "a[?b=='c']"]
        result = self.invoke(*args, input="stdin payload\n")
        self.assertEqual(result.returncode, 23)
        self.assertEqual(json.loads(result.stdout), {
            "args": args, "cwd": str(self.work), "input": "stdin payload\n",
            "env": "environment unchanged",
        })
        self.assertEqual(result.stderr, "real az stderr\n")

    def test_only_exact_prefix_is_owned(self):
        for args in ([], ["--help"], ["aks", "--help"], ["aks", "skillset", "list"],
                     ["account", "show"], ["--debug", "aks", "skill", "list"]):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 23)
                self.assertEqual(json.loads(result.stdout)["args"], args)

    def path_env(self):
        env = self.env.copy()
        env.pop("AZ_AKS_REAL_AZ", None)
        env["PATH"] = os.pathsep.join([str(SHIM.parent), str(self.fake_dir)])
        return env

    def test_path_resolution_skips_shim_and_symlink(self):
        alias_dir = self.work / "alias"
        alias_dir.mkdir()
        (alias_dir / "az").symlink_to(SHIM)
        env = self.path_env()
        env["PATH"] = str(alias_dir) + os.pathsep + env["PATH"]
        result = self.invoke("version", env=env)
        self.assertEqual(result.returncode, 23, result.stderr)

    def test_stacked_worktree_shims_do_not_recurse(self):
        other = self.work / "other-checkout"
        shutil.copytree(ROOT / "src", other / "src")
        (other / "bin").mkdir()
        shutil.copy2(SHIM, other / "bin" / "az")
        env = self.path_env()
        env["PATH"] = os.pathsep.join([
            str(SHIM.parent), str(other / "bin"), str(self.fake_dir),
        ])
        result = self.invoke("version", env=env)
        self.assertEqual(result.returncode, 23, result.stderr)

    def test_bad_explicit_executable_fails_without_fallback(self):
        for path in (str(SHIM), str(self.work / "missing"), "relative/az"):
            with self.subTest(path=path):
                self.env["AZ_AKS_REAL_AZ"] = path
                result = self.invoke("version")
                self.assertEqual(result.returncode, 127)
                self.assertEqual(result.stdout, "")
                self.assertIn("az shim:", result.stderr)

    def test_missing_real_az_does_not_break_local_commands(self):
        self.fake.unlink()
        env = self.path_env()
        result = self.invoke("version", env=env)
        self.assertEqual(result.returncode, 127)
        result = self.invoke("aks", "skill", "list", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)

    def make_catalog(self):
        root = self.work / "catalog"
        root.mkdir()
        (root / "example.md").write_text("# A temporary skill\nFresh content.\n")
        data = {"version": 1, "skills": [{
            "id": "custom", "title": "Custom skill", "description": "Temporary fixture",
            "tags": ["test"], "path": "example.md",
        }]}
        self.env["AZ_AKS_SKILLS_DIR"] = str(root)
        return root, data

    def test_alternate_catalog(self):
        root, data = self.make_catalog()
        (root / "index.json").write_text(json.dumps(data))
        result = self.invoke("aks", "skill", "show", "--name", "custom")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "# A temporary skill\nFresh content.\n")

    def test_invalid_catalogs_report_errors(self):
        root, data = self.make_catalog()
        cases = ["not json", json.dumps({"version": 2, "skills": []}),
                 json.dumps({"version": 1, "skills": [data["skills"][0]] * 2}),
                 json.dumps({"version": 1, "skills": [{"id": "missing-fields"}]})]
        for content in cases:
            with self.subTest(content=content):
                (root / "index.json").write_text(content)
                result = self.invoke("aks", "skill", "list")
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertNotIn("Traceback", result.stderr)

    def test_catalog_rejects_missing_and_escaping_documents(self):
        root, data = self.make_catalog()
        outside = self.work / "outside.md"
        outside.write_text("outside content")
        (root / "link.md").symlink_to(outside)
        for path in ("missing.md", "../outside.md", str(outside), "link.md"):
            with self.subTest(path=path):
                data["skills"][0]["path"] = path
                (root / "index.json").write_text(json.dumps(data))
                result = self.invoke("aks", "skill", "show", "--name", "custom")
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
