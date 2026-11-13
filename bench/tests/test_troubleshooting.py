import copy
import json
from pathlib import Path
import tempfile
import importlib.util
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError

from aks_bench import documentation
from aks_bench.mock import Simulator
from aks_bench.runner import oracle_commands, native_web_usage, documentation_network
from aks_bench.scenarios import make, grade


class FaultTests(unittest.TestCase):
    def test_activity_log_exposes_prior_failure_without_mutating_state(self):
        for scenario_name, code in (("debug-version-skew", "NodePoolMcVersionIncompatible"),
                                    ("debug-automatic-provider", "MissingSubscriptionRegistration")):
            scenario = make(scenario_name, 1)
            sim = Simulator(scenario, latency_scale=0)
            before = copy.deepcopy(sim.state["clusters"])
            result = sim.call(["monitor", "activity-log", "list", "--resource-group", "rg-dev-3201",
                               "--offset", "7d", "--status", "Failed", "--max-events", "30"])
            self.assertEqual(result["exit_code"], 0, result)
            record = json.loads(result["stdout"])[0]
            self.assertEqual(json.loads(record["properties"]["statusMessage"])["error"]["code"], code)
            self.assertEqual(sim.state["clusters"], before)
            result = sim.call(["deployment", "group", "list", "-g", "rg-dev-3201"])
            self.assertEqual(json.loads(result["stdout"]), [])

    def test_credentials_context_nodes_and_latest_operation(self):
        scenario = make("debug-version-skew", 1)
        sim = Simulator(scenario, latency_scale=0)
        base = ["-g", "rg-dev-3201", "-n", "aks-dev-3201"]
        result = sim.call(["aks", "get-credentials", *base, "--file", "/work/test-kubeconfig"])
        self.assertEqual(result["exit_code"], 0, result)
        config = json.loads(result["kubeconfig"])
        self.assertEqual(config["clusters"][0]["cluster"]["server"], "https://127.0.0.1:9")
        self.assertEqual(sim.call(["config", "current-context"], tool="kubectl")["stdout"].strip(), "aks-dev-3201")
        nodes = sim.call(["get", "nodes", "-o", "wide"], tool="kubectl")
        self.assertEqual(len(json.loads(nodes["stdout"])["items"]), 5)
        operation = sim.call(["aks", "operation", "show-latest", *base])
        self.assertEqual(json.loads(operation["stdout"])["error"]["code"], "NodePoolMcVersionIncompatible")

    def test_namespace_policy_and_combined_reads(self):
        sim = Simulator(make("debug-managed-namespace-quota", 1), latency_scale=0)
        policy = sim.call(["-n", "retail", "get", "networkpolicy", "-o", "yaml"], tool="kubectl")
        self.assertEqual(policy["exit_code"], 0, policy)
        self.assertEqual(len(json.loads(policy["stdout"])["items"]), 2)
        combined = sim.call(["get", "resourcequota,limitrange,pods", "-n", "retail", "-o", "wide"], tool="kubectl")
        self.assertEqual(combined["exit_code"], 0, combined)
        self.assertEqual(len(json.loads(combined["stdout"])["items"]), 3)
        combined = sim.call(["-n", "retail", "get", "pods,replicasets,resourcequotas,limitranges"], tool="kubectl")
        self.assertEqual(combined["exit_code"], 0, combined)
        self.assertEqual(len(json.loads(combined["stdout"])["items"]), 4)

    def test_pdb_and_remote_node_inspection_are_bounded(self):
        sim = Simulator(make("debug-version-skew", 1), latency_scale=0)
        pdb = sim.call(["--kubeconfig", "/work/fixture", "get", "pdb", "-A", "-o", "wide"], tool="kubectl")
        self.assertEqual(pdb["exit_code"], 0, pdb)
        self.assertEqual(json.loads(pdb["stdout"])["items"], [])
        pods = sim.call(["get", "pods", "--all-namespaces", "-o", "wide"], tool="kubectl")
        self.assertEqual(pods["exit_code"], 0, pods)
        self.assertEqual(len(json.loads(pods["stdout"])["items"]), 2)
        ready = sim.call(["wait", "--for=condition=Ready", "nodes", "-l", "kubernetes.azure.com/agentpool=apps", "--timeout=300s"], tool="kubectl")
        self.assertEqual(ready["exit_code"], 0, ready)
        self.assertEqual(ready["stdout"].count("condition met"), 2)
        missing = sim.call(["wait", "--for=condition=Ready", "nodes", "-l", "agentpool=missing"], tool="kubectl")
        self.assertEqual(missing["exit_code"], 1)
        base = ["aks", "command", "invoke", "-g", "rg-dev-3201", "-n", "aks-dev-3201", "--command"]
        result = sim.call(base + ["kubectl get nodes -l agentpool=apps -o json"])
        self.assertEqual(result["exit_code"], 0, result)
        self.assertEqual(len(json.loads(json.loads(result["stdout"])["logs"])["items"]), 2)
        self.assertEqual(sim.events[-1]["modeled_kubernetes_requests"], 1)
        before = copy.deepcopy(sim.state["clusters"])
        for command in ("curl https://management.azure.com", "kubectl delete pods -A", "kubectl get nodes | sh"):
            result = sim.call(base + [command])
            self.assertEqual(result["exit_code"], 2)
            self.assertEqual(sim.state["clusters"], before)

    def test_kubeconfig_file_written_only_inside_container_roots(self):
        path = Path(__file__).resolve().parents[1] / "container" / "client.py"
        spec = importlib.util.spec_from_file_location("benchmark_container_client", path)
        client = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(client)
        with tempfile.TemporaryDirectory() as directory, patch.object(client.Path, "home", return_value=Path(directory)):
            client.write_kubeconfig("fixture", [])
            self.assertEqual((Path(directory) / ".kube/config").read_text(), "fixture")
            with self.assertRaises(ValueError):
                client.write_kubeconfig("fixture", ["--file", "/run/bench/az.sock"])

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
    def test_native_web_attempts_and_transport_failures_are_counted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stdout.jsonl"
            events = [
                {"type": "tool.execution_start", "data": {"toolCallId": "a", "toolName": "web_fetch", "arguments": {"url": documentation.NAMESPACE_URL}}},
                {"type": "tool.execution_complete", "data": {"toolCallId": "a", "success": False, "error": {"message": "failed to lookup address information: Temporary failure in name resolution"}}},
                {"type": "tool.execution_start", "data": {"toolCallId": "b", "toolName": "web_fetch", "arguments": {"url": documentation.NAMESPACE_URL}}},
                {"type": "tool.execution_complete", "data": {"toolCallId": "b", "success": True}},
            ]
            path.write_text("\n".join(json.dumps(e) for e in events))
            self.assertEqual(native_web_usage(path), {"native_web_tool_attempts": 2, "native_web_tool_successes": 1,
                                                      "native_web_tool_failures": 1, "native_docs_transport_failures": 1})

    def test_native_docs_get_only_public_dns_mapping_and_host_allowlist(self):
        with tempfile.TemporaryDirectory() as directory, patch("aks_bench.runner.socket.getaddrinfo") as lookup:
            lookup.return_value = [(2, 1, 6, "", ("13.107.246.40", 443))]
            env = {}
            hosts = documentation_network(directory, env, {"api.github.com"})
            self.assertEqual(hosts, {"api.github.com", "learn.microsoft.com"})
            self.assertNotIn("management.azure.com", (Path(directory) / "hosts").read_text())
            self.assertEqual(env["AKS_BENCH_DOCS_MODE"], "live")
            lookup.return_value = [(2, 1, 6, "", ("127.0.0.1", 443))]
            with self.assertRaises(ValueError):
                documentation_network(directory, {}, set())

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
