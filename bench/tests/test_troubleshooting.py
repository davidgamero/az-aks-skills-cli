import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError

from aks_bench import documentation
from aks_bench.mock import Simulator
from aks_bench.runner import oracle_commands
from aks_bench.scenarios import make, grade


class FaultTests(unittest.TestCase):
    def test_registration_fault_persists_until_provider_is_registered(self):
        scenario = make("debug-automatic-provider", 1)
        sim = Simulator(scenario, latency_scale=0)
        registration, create, verify = oracle_commands(scenario)
        for _ in range(2):
            result = sim.call(create)
            self.assertIn("MissingSubscriptionRegistration", result["stderr"])
            self.assertEqual(sim.state["clusters"], [])
        self.assertEqual(sim.call(registration)["exit_code"], 0)
        self.assertEqual(sim.call(create)["exit_code"], 0)
        self.assertIsNone(sim.verified_goal_s)
        self.assertEqual(sim.call(verify)["exit_code"], 0)
        self.assertTrue(grade(scenario, sim.state)["success"])
        self.assertIsNotNone(sim.verified_goal_s)

    def test_failed_registration_output_validation_rolls_back_provider_state(self):
        scenario = make("debug-automatic-provider", 1)
        sim = Simulator(scenario, latency_scale=0)
        registration = oracle_commands(scenario)[0]
        result = sim.call(registration + ["--query", "["])
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(sim.state["providers"]["Microsoft.PolicyInsights"], "NotRegistered")

    def test_version_fault_requires_correct_order_and_preserves_other_pool(self):
        scenario = make("debug-version-skew", 1)
        sim = Simulator(scenario, latency_scale=0)
        commands = oracle_commands(scenario)
        original = copy.deepcopy(sim.state["clusters"])
        for _ in range(2):
            result = sim.call(commands[2])
            self.assertIn("NodePoolMcVersionIncompatible", result["stderr"])
            self.assertEqual(sim.state["clusters"], original)
        for command in commands:
            self.assertEqual(sim.call(command)["exit_code"], 0)
        self.assertTrue(grade(scenario, sim.state)["success"])

    def test_managed_quota_requires_arm_update_and_workload_verification(self):
        scenario = make("debug-managed-namespace-quota", 1)
        sim = Simulator(scenario, latency_scale=0)
        commands = oracle_commands(scenario)
        problem = sim.call(["describe", "deployment", "api", "-n", "retail"], tool="kubectl")
        self.assertIn("exceeded quota", problem["stdout"])
        initial = copy.deepcopy(sim.state["clusters"])
        denied = sim.call(["patch", "resourcequota", "managed-quota", "-n", "retail", "-p", '{}'], tool="kubectl")
        self.assertIn("Forbidden", denied["stderr"])
        self.assertEqual(sim.state["clusters"], initial)
        self.assertEqual(sim.call(commands[1])["exit_code"], 0)
        self.assertTrue(grade(scenario, sim.state)["success"])
        self.assertIsNone(sim.verified_goal_s)
        result = sim.call(commands[2]["argv"], tool="kubectl")
        self.assertEqual(json.loads(result["stdout"])["status"]["readyReplicas"], 4)
        self.assertIsNotNone(sim.verified_goal_s)
        self.assertEqual(sim.events[-1]["modeled_api_requests"], 0)
        self.assertEqual(sim.events[-1]["modeled_kubernetes_requests"], 1)

    def test_oversized_budget_or_weakened_network_policy_fails(self):
        for extra in (["--cpu-request", "8000m"], ["--ingress-policy", "AllowAll"]):
            scenario = make("debug-managed-namespace-quota", 1)
            sim = Simulator(scenario, latency_scale=0)
            update = oracle_commands(scenario)[1]
            self.assertEqual(sim.call(update + extra)["exit_code"], 0)
            self.assertFalse(grade(scenario, sim.state)["success"])

    def test_requested_replicas_are_not_ready_replicas(self):
        sim = Simulator(make("debug-managed-namespace-quota", 1), latency_scale=0)
        self.assertEqual(sim.call(["scale", "deployment/api", "--replicas=4", "-n", "retail"], tool="kubectl")["exit_code"], 0)
        self.assertEqual(sim.call(["rollout", "status", "deployment/api", "-n", "retail"], tool="kubectl")["exit_code"], 1)
        self.assertIsNone(sim.verified_goal_s)


class DocumentationTests(unittest.TestCase):
    def test_only_read_only_learn_paths_are_approved(self):
        self.assertTrue(documentation.approved(documentation.NAMESPACE_URL))
        self.assertTrue(documentation.approved("https://learn.microsoft.com/api/search?search=quota&locale=en-us"))
        for url in ("http://learn.microsoft.com/en-us/azure/aks", "https://management.azure.com/", "https://learn.microsoft.com.evil.test/en-us/azure/aks", "https://user:pass@learn.microsoft.com/en-us/azure/aks", "file:///etc/passwd"):
            self.assertFalse(documentation.approved(url))
        with patch("aks_bench.documentation.build_opener") as opener:
            for args in ([documentation.NAMESPACE_URL, "--data", "payload"], ["https://management.azure.com"]):
                with self.assertRaises(ValueError):
                    documentation.fetch(args)
            opener.assert_not_called()

    def test_redirect_cannot_escape_allowed_origin(self):
        handler = documentation.RestrictedRedirect({})
        with self.assertRaises(ValueError):
            handler.redirect_request(None, None, 302, "", {}, "https://management.azure.com")

    def test_real_request_accounting_and_body_capture(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"public documentation"
        response.status = 200
        with tempfile.TemporaryDirectory() as directory, patch("aks_bench.documentation.build_opener") as opener:
            opener.return_value.open.return_value = response
            text, metadata = documentation.fetch(["-sSL", documentation.NAMESPACE_URL], directory)
            self.assertEqual(text, "public documentation")
            self.assertEqual(metadata["documentation_http_requests"], 1)
            self.assertEqual(len(list(Path(directory).glob("*.txt"))), 1)

    def test_docs_off_and_failed_requests_are_distinguished(self):
        scenario = make("debug-managed-namespace-quota", 1)
        sim = Simulator(scenario, docs_mode="off")
        with patch("aks_bench.documentation.build_opener") as opener:
            self.assertEqual(sim.call([documentation.NAMESPACE_URL], tool="curl")["exit_code"], 22)
            opener.assert_not_called()
        self.assertEqual(sim.events[-1]["documentation_http_requests"], 0)
        sim.docs_mode = "live"
        with patch("aks_bench.documentation.build_opener") as opener:
            opener.return_value.open.side_effect = HTTPError(documentation.NAMESPACE_URL, 503, "unavailable", {}, None)
            self.assertEqual(sim.call([documentation.NAMESPACE_URL], tool="curl")["exit_code"], 22)
        self.assertEqual(sim.events[-1]["documentation_http_requests"], 1)


if __name__ == "__main__":
    unittest.main()
