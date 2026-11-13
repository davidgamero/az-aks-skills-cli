import copy
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

from aks_bench.mock import COMMANDS, SEMANTIC, Simulator
from aks_bench.runner import oracle_commands, report, telemetry, provider_environment, container_command
from aks_bench.scenarios import NAMES, make, grade
from aks_bench.services import Services, allowed_authority


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.scenario = make("manual-scale", 42)
        self.sim = Simulator(self.scenario, skills=True, latency_scale=0)
        self.c = self.scenario["state"]["clusters"][0]
        self.pool = ["-g", self.c["resourceGroup"], "--cluster-name", self.c["name"], "-n", "apps"]
        self.cluster = ["-g", self.c["resourceGroup"], "-n", self.c["name"]]

    def call(self, words, *args):
        return self.sim.call([*words.split(), *args])

    def test_seed_pair_is_identical_and_other_seeds_differ(self):
        self.assertEqual(make("manual-scale", 42), self.scenario)
        self.assertNotEqual(make("manual-scale", 43)["prompt"], self.scenario["prompt"])

    def test_each_scenario_reference_sequence_satisfies_oracle(self):
        for name in NAMES:
            with self.subTest(name=name):
                scenario = make(name, 19)
                sim = Simulator(scenario, latency_scale=0)
                self.assertFalse(grade(scenario, sim.state)["success"])
                for args in oracle_commands(scenario):
                    result = sim.call(args)
                    if "TooManyRequests" in result["stderr"]:
                        result = sim.call(args)
                    self.assertEqual(result["exit_code"], 0, result)
                self.assertTrue(grade(scenario, sim.state)["success"])
                self.assertIsNotNone(sim.verified_goal_s)

    def test_autoscaler_conflict_is_transactional(self):
        initial = copy.deepcopy(self.sim.state["clusters"])
        result = self.call("aks nodepool scale", *self.pool, "--node-count", "5")
        self.assertEqual(result["exit_code"], 1)
        self.assertIn("autoscaler", result["stderr"])
        self.assertEqual(initial, self.sim.state["clusters"])
        self.assertEqual(self.sim.events[-1]["modeled_api_requests"], 1)

    def test_query_output_and_argument_aliases(self):
        result = self.call("aks show", *self.cluster, "--query", "agentPoolProfiles[?name=='apps'].count | [0]", "-o", "tsv")
        self.assertEqual(result["stdout"], "2\n")
        result = self.call("aks show", *self.cluster, "--query=name")
        self.assertEqual(json.loads(result["stdout"]), self.c["name"])

    def test_invalid_queries_and_counts_dont_commit_state(self):
        initial = copy.deepcopy(self.sim.state["clusters"])
        result = self.call("aks nodepool update", *self.pool, "--disable-cluster-autoscaler", "--query", "[")
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(initial, self.sim.state["clusters"])
        result = self.call("aks nodepool update", *self.pool, "--update-cluster-autoscaler", "--min-count", "9", "--max-count", "1")
        self.assertNotEqual(result["exit_code"], 0)
        self.assertEqual(initial, self.sim.state["clusters"])

    def test_every_registered_command_accepts_scripted_success_and_failure(self):
        self.assertTrue(SEMANTIC <= set(COMMANDS))
        for command in COMMANDS:
            with self.subTest(command=command):
                scenario = copy.deepcopy(self.scenario)
                scenario["responses"] = [{"command": command, "output": {"fixture": command}}]
                sim = Simulator(scenario, latency_scale=0)
                result = sim.call(command.split())
                self.assertEqual(result["exit_code"], 0, result)
                self.assertEqual(json.loads(result["stdout"]), {"fixture": command})
                scenario["responses"][0]["error"] = {"code": "AuthorizationFailed", "message": "fixture denial", "status": 403}
                sim = Simulator(scenario, latency_scale=0)
                result = sim.call(command.split())
                self.assertEqual(result["exit_code"], 1)
                self.assertEqual(sim.events[-1]["http_status"], 403)

    def test_unimplemented_is_a_coverage_gap_not_a_fake_success(self):
        command = next(c for c in COMMANDS if c not in SEMANTIC)
        result = self.call(command)
        self.assertEqual(result["exit_code"], 2)
        self.assertIn("MockNotImplemented", result["stderr"])
        self.assertEqual(self.sim.events[-1]["category"], "coverage_gap")
        self.assertEqual(self.sim.events[-1]["modeled_api_requests"], 0)

    def test_unknown_commands_and_flags_never_delegate(self):
        for args in (["rest", "--method", "put", "--url", "https://management.azure.com"],
                     ["aks", "invented"], ["aks", "show", *self.cluster, "--invented", "x"]):
            result = self.sim.call(args)
            self.assertEqual(result["exit_code"], 2)

    def test_fault_occurrences_and_scope(self):
        self.sim.scenario["faults"] = [{"command": "aks show", "occurrences": [2],
                                        "code": "ServiceUnavailable", "message": "retry", "status": 503}]
        results = [self.call("aks show", *self.cluster) for _ in range(3)]
        self.assertEqual([r["exit_code"] for r in results], [0, 1, 0])
        self.assertEqual([e["http_status"] for e in self.sim.events], [200, 503, 200])

    def test_control_plane_only_and_negative_control(self):
        scenario = make("control-plane-upgrade", 42)
        self.sim = Simulator(scenario, latency_scale=0)
        self.call("aks upgrade", *self.cluster, "--kubernetes-version", scenario["target_version"])
        self.assertFalse(grade(scenario, self.sim.state)["success"])
        self.sim = Simulator(scenario, latency_scale=0)
        self.call("aks upgrade", *self.cluster, "--kubernetes-version", scenario["target_version"], "--control-plane-only")
        self.assertTrue(grade(scenario, self.sim.state)["success"])

    def test_no_wait_is_pending_until_observed_or_waited(self):
        self.sim.latency_scale = 1
        self.sim.scenario["latency_ms"] = 0
        self.sim.scenario["operation_delay_ms"] = 40
        result = self.call("aks nodepool update", *self.pool, "--disable-cluster-autoscaler", "--no-wait")
        self.assertEqual(result["exit_code"], 0)
        self.assertTrue(self.sim.state["pending"])
        self.assertTrue(self.sim.state["clusters"][0]["agentPoolProfiles"][1]["enableAutoScaling"])
        result = self.call("aks wait", *self.cluster, "--updated")
        self.assertEqual(result["exit_code"], 0, result)
        self.assertFalse(self.sim.state["pending"])
        self.assertFalse(self.sim.state["clusters"][0]["agentPoolProfiles"][1]["enableAutoScaling"])

    def test_wrong_pool_read_does_not_verify_goal(self):
        for args in oracle_commands(self.scenario)[:-1]:
            self.sim.call(args)
        self.assertIsNone(self.sim.verified_goal_s)
        other = self.pool[:-1] + ["system"]
        self.call("aks nodepool show", *other)
        self.assertIsNone(self.sim.verified_goal_s)
        self.call("aks nodepool show", *self.pool)
        self.assertIsNotNone(self.sim.verified_goal_s)

    def test_skills_have_zero_modeled_network_requests(self):
        result = self.call("aks skill show", "--name", "aks-fixed-capacity")
        self.assertIn("disable-cluster-autoscaler", result["stdout"])
        self.assertEqual(self.sim.events[-1]["modeled_api_requests"], 0)
        self.sim.skills = False
        result = self.call("aks skill show", "--name", "aks-fixed-capacity")
        self.assertEqual(result["exit_code"], 2)
        self.assertNotIn("skill", self.call("aks", "--help")["stdout"])

    def test_plural_help_and_reads_use_actual_cli_and_are_tracked(self):
        result = self.call("aks skills")
        self.assertEqual(result["exit_code"], 0, result)
        self.assertTrue(result["stdout"].startswith("Group\n"))
        self.assertEqual(self.sim.events[-1]["category"], "skill")
        result = self.call("aks skills show", "--name", "aks-fixed-capacity")
        self.assertEqual(result["exit_code"], 0, result)
        self.assertEqual(self.sim.events[-1]["command"], "aks skill show")
        self.assertEqual(self.sim.events[-1]["modeled_api_requests"], 0)
        self.sim.skills = False
        self.assertEqual(self.call("aks skills")["exit_code"], 2)

    def test_host_server_preserves_events_under_concurrency(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "trace.jsonl"
            self.sim.log_path = log
            sockets = Path(directory) / "sockets"
            with Services(sockets, self.sim, set(), Path(directory) / "proxy.jsonl"):
                def call():
                    with socket.socket(socket.AF_UNIX) as connection:
                        connection.connect(str(sockets / "az.sock"))
                        connection.sendall(json.dumps({"argv": ["aks", "show", *self.cluster]}).encode() + b"\n")
                        self.assertEqual(json.loads(connection.makefile().readline())["exit_code"], 0)
                threads = [threading.Thread(target=call) for _ in range(8)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()
            events = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual([e["sequence"] for e in events], list(range(1, 9)))
            self.assertTrue(all(e["end_s"] >= e["start_s"] for e in events))


class ReportAndIsolationTests(unittest.TestCase):
    def test_foundry_environment_only_passes_selected_provider_variables(self):
        with patch.dict("os.environ", {"COPILOT_PROVIDER_BASE_URL": "https://example.openai.azure.com",
                                       "COPILOT_PROVIDER_API_KEY": "test-key", "AZURE_CLIENT_SECRET": "must-not-pass",
                                       "COPILOT_PROVIDER_API_KEY_COMMAND": "must-not-run"}, clear=True):
            env, hosts = provider_environment("foundry")
        self.assertEqual(hosts, {"example.openai.azure.com"})
        self.assertEqual(env["COPILOT_PROVIDER_TYPE"], "azure")
        self.assertNotIn("AZURE_CLIENT_SECRET", env)
        self.assertNotIn("COPILOT_PROVIDER_API_KEY_COMMAND", env)
        for endpoint in ("http://example.test", "https://management.azure.com", "https://user:password@example.test"):
            with patch.dict("os.environ", {"COPILOT_PROVIDER_BASE_URL": endpoint}, clear=True):
                with self.assertRaises(ValueError):
                    provider_environment("foundry")

    def test_container_commands_do_not_put_credentials_in_argv(self):
        for engine in ("bwrap", "docker"):
            args = container_command(engine, "/usr/bin/bwrap", Path("/copilot"), Path("/sockets"),
                                     Path("/artifacts"), ["--check"], {"COPILOT_GITHUB_TOKEN": "secret-value"}, "test")
            self.assertNotIn("secret-value", " ".join(args))
            if engine == "docker":
                self.assertEqual(args[args.index("--network") + 1], "none")
                self.assertIn("--read-only", args)
            else:
                self.assertIn("--unshare-all", args)

    def test_proxy_allowlist_blocks_arm_even_when_misconfigured(self):
        allowed = {"api.github.com", "management.azure.com"}
        self.assertTrue(allowed_authority("api.github.com:443", allowed))
        for authority in ("api.github.com:80", "api.github.com.attacker.test:443", "management.azure.com:443", "169.254.169.254:443", "localhost:443"):
            self.assertFalse(allowed_authority(authority, allowed))

    def test_otel_counts_spans_not_metrics_or_duplicate_exports(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "otel.jsonl"
            span = {"spanId": "abc", "name": "chat sol", "attributes": [
                {"key": "gen_ai.usage.input_tokens", "value": {"intValue": "23"}},
                {"key": "gen_ai.usage.output_tokens", "value": {"intValue": "7"}}]}
            path.write_text(json.dumps({"resourceSpans": [{"scopeSpans": [{"spans": [span, span]}]}]}) + "\n")
            result = telemetry(path)
            self.assertEqual(result["llm_requests"], 1)
            self.assertEqual(result["input_tokens"], 23)
            self.assertEqual(result["output_tokens"], 7)

    def test_report_never_counts_replay_as_agent_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trial"
            path.mkdir()
            (path / "result.json").write_text(json.dumps({
                "scenario": "manual-scale", "requested_model": None, "provider": None,
                "discovery": "explicit", "mode": "replay", "skills": True,
                "valid_trial": False, "success": True, "seed": 1,
            }))
            result = report(directory)[0]
            self.assertEqual(result["skills"]["valid_trials"], 0)
            self.assertEqual(result["successful_pairs"], 0)
            self.assertIsNone(result["median_paired_delta_skills_minus_baseline"])


if __name__ == "__main__":
    unittest.main()
