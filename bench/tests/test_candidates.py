"""Reference, adversarial and transport checks for primary candidate fixtures."""

import copy
import json
import unittest

from aks_bench.candidate_fixtures import NAMES, key, obj
from aks_bench.candidate_oracles import verified
from aks_bench.candidate_runtime import World
from aks_bench.candidate_solutions import apply, commands, execute, kube, patch
from aks_bench.mock import Simulator
from aks_bench.scenarios import grade, make


class CandidateTests(unittest.TestCase):
    def simulator(self, name):
        return Simulator(make(name, 19), latency_scale=0)

    def solve(self, sim):
        for action in commands(sim.scenario):
            result = execute(sim, action)
            self.assertEqual(result["exit_code"], action.get("expect_exit", 0) if isinstance(action, dict) else 0, (action, result))
        self.assertTrue(grade(sim.scenario, sim.state)["success"], grade(sim.scenario, sim.state))
        self.assertTrue(verified(sim.scenario, sim.state))

    def test_all_primary_references_and_independent_negative_controls(self):
        # Each successful solution is damaged at a different decisive relationship.
        def damage(name, s):
            c = s["clusters"][0]; w = c["_world"]; r = w["resources"]
            dep = r[key("deployment", "retail", "api")]
            if name == "managed-namespace-adopt-identical": w["managed_namespaces"] = {}
            elif name == "managed-namespace-detach-keep": r[key("persistentvolumeclaim", "retail", "data")]["status"]["dataVersion"] = "lost"
            elif name == "managed-namespace-rbac-plane": w["roles"][-1]["scope"] = c["id"]
            elif name == "managed-namespace-selective-ingress": r[key("networkpolicy", "retail", "managed-ingress")]["spec"]["ingress"] = [{}]
            elif name == "acr-abac-pull-repair": w["roles"][-1].pop("condition")
            elif name == "acr-private-data-endpoint": w["registry"]["publicNetworkAccess"] = "Enabled"
            elif name == "workload-federation-versus-rbac": w["federated_credentials"][0]["subject"] = "wrong"
            elif name == "identity-binding-mixed-audiences": dep["spec"]["template"]["spec"]["volumes"][0]["projected"]["sources"][0]["serviceAccountToken"]["audience"] = "api://AzureADTokenExchange"
            elif name == "nap-capacity-control-plane": r[key("nodepool", "", "workers")]["spec"]["template"]["spec"]["requirements"] = []
            elif name == "nap-image-pickup-versus-disruption": r[key("poddisruptionbudget", "retail", "api-pdb")]["spec"]["minAvailable"] = 1
            elif name == "automatic-admission-mutation-quota": w["safeguards"]["excludedNamespaces"] = ["retail"]
            elif name == "pdb-preserving-upgrade": w["minimum_ready_seen"] = 1
            elif name == "csi-secret-sync-alias": dep["spec"]["template"]["spec"]["containers"][0]["volumeMounts"] = []
            elif name == "csi-rotation-consumption-mode": w["rotation_interval"] = "1m"
            elif name == "overlay-cidr-exhaustion": c["networkProfile"]["podCidr"] = "10.245.0.0/16"
            elif name == "api-connectivity-stage-repair": c["apiServerAccessProfile"]["authorizedIpRanges"] = ["0.0.0.0/0"]
            elif name == "gateway-api-publish": r[key("httproute", "retail", "api-route")]["spec"]["rules"][0]["matches"][0]["path"]["value"] = "/wrong"
            else: self.fail(name)
        for name in NAMES:
            with self.subTest(name=name):
                sim = self.simulator(name)
                self.assertFalse(grade(sim.scenario, sim.state)["success"])
                self.solve(sim)
                damaged = copy.deepcopy(sim.state)
                damage(name, damaged)
                self.assertFalse(grade(sim.scenario, damaged)["success"])

    def test_temporal_constraints_cannot_be_restored_away(self):
        for name in ("pdb-preserving-upgrade", "nap-image-pickup-versus-disruption"):
            with self.subTest(name=name):
                sim = self.simulator(name)
                self.assertEqual(execute(sim, patch("pdb", "api-pdb", {"spec": {"minAvailable": 1}}))["exit_code"], 0)
                execute(sim, patch("pdb", "api-pdb", {"spec": {"minAvailable": 2}}))
                for action in commands(sim.scenario): execute(sim, action)
                self.assertFalse(grade(sim.scenario, sim.state)["success"])
        sim = self.simulator("pdb-preserving-upgrade")
        execute(sim, kube("scale", "deployment/api", "--replicas=0"))
        for action in commands(sim.scenario): execute(sim, action)
        self.assertFalse(grade(sim.scenario, sim.state)["success"])

    def test_namespace_cascade_and_recreation_do_not_preserve_data(self):
        sim = self.simulator("managed-namespace-detach-keep")
        action = commands(sim.scenario)[1]
        self.assertEqual(execute(sim, action)["exit_code"], 0)
        self.assertFalse(grade(sim.scenario, sim.state)["success"])
        self.assertFalse(World(sim.scenario, sim.state).get("persistentvolumeclaim", "data"))
        execute(sim, apply(obj("Namespace", "retail", "")))
        execute(sim, apply(sim.scenario["expected"]["deployment"]))
        self.assertFalse(grade(sim.scenario, sim.state)["success"])

    def test_registry_boolean_condition_is_not_a_substring_check(self):
        sim = self.simulator("acr-abac-pull-repair")
        action = commands(sim.scenario)[0]
        action[-1] += " OR @Resource[Microsoft.ContainerRegistry/registries/repositories:name] StringEquals 'other/repository'"
        self.assertEqual(execute(sim, action)["exit_code"], 0)
        self.assertFalse(grade(sim.scenario, sim.state)["success"])
        sim.call(["role", "assignment", "delete", "--assignee", "kubelet-principal", "--role", "Container Registry Repository Reader"])
        for action in commands(sim.scenario): execute(sim, action)
        self.assertFalse(grade(sim.scenario, sim.state)["success"])

    def test_policy_union_and_peer_intersection(self):
        sim = self.simulator("managed-namespace-selective-ingress")
        self.solve(sim)
        world = World(sim.scenario, sim.state)
        policy = world.get("networkpolicy", "allow-approved-ingress")
        policy["spec"]["ingress"][0]["from"][0]["podSelector"] = {"matchLabels": {"app": "wrong"}}
        self.assertFalse(world.traffic("ingress"))
        self.assertFalse(grade(sim.scenario, sim.state)["success"])
        policy["spec"]["ingress"] = [{}]
        self.assertTrue(world.traffic("other"))
        self.assertFalse(grade(sim.scenario, sim.state)["success"])

    def test_status_forgery_does_not_make_workload_ready(self):
        sim = self.simulator("acr-abac-pull-repair")
        execute(sim, patch("deployment", "api", {"status": {"readyReplicas": 2}}))
        self.assertEqual(World(sim.scenario, sim.state).get("deployment", "api")["status"]["readyReplicas"], 0)
        self.assertFalse(grade(sim.scenario, sim.state)["success"])

    def test_wrong_gateway_listener_backend_and_path_fail_traffic(self):
        for field in ("listener", "backend", "path", "selector"):
            with self.subTest(field=field):
                sim = self.simulator("gateway-api-publish")
                self.solve(sim)
                world = World(sim.scenario, sim.state)
                if field == "listener": world.get("gateway", "existing-gw")["spec"]["listeners"][0]["port"] = 81
                if field == "backend": world.get("httproute", "api-route")["spec"]["rules"][0]["backendRefs"][0]["port"] = 9999
                if field == "path": world.get("httproute", "api-route")["spec"]["rules"][0]["matches"][0]["path"]["value"] = "/wrong"
                if field == "selector": world.get("service", "api")["spec"]["selector"] = {"app": "absent"}
                world.reconcile()
                self.assertNotEqual(execute(sim, commands(sim.scenario)[-1])["exit_code"], 0)
                self.assertFalse(grade(sim.scenario, sim.state)["success"])

    def test_mutation_invalidates_final_verification(self):
        sim = self.simulator("csi-rotation-consumption-mode")
        self.solve(sim)
        execute(sim, kube("rollout", "restart", "deployment/api"))
        self.assertTrue(grade(sim.scenario, sim.state)["success"])
        self.assertFalse(verified(sim.scenario, sim.state))

    def test_resource_deletion_does_not_crash_grading(self):
        for name in NAMES:
            sim = self.simulator(name)
            self.solve(sim)
            for resource_key in list(sim.state["clusters"][0]["_world"]["resources"]):
                damaged = copy.deepcopy(sim.state)
                damaged["clusters"][0]["_world"]["resources"].pop(resource_key)
                with self.subTest(name=name, resource=resource_key): grade(sim.scenario, damaged)

    def test_unknown_options_and_wrong_scope_are_transactional(self):
        sim = self.simulator("overlay-cidr-exhaustion")
        before = sim.state_hash()
        result = sim.call(["aks", "update", "--pod-cidr", "10.244.0.0/20", "--made-up", "yes"])
        self.assertNotEqual(result["exit_code"], 0)
        self.assertEqual(sim.events[-1]["category"], "coverage_gap")
        self.assertEqual(sim.state_hash(), before)
        result = sim.call(["aks", "update", "-n", "wrong-cluster", "--pod-cidr", "10.244.0.0/20"])
        self.assertNotEqual(result["exit_code"], 0)
        self.assertEqual(sim.state_hash(), before)

    def test_manifest_stdin_and_help_discovery(self):
        sim = self.simulator("gateway-api-publish")
        action = commands(sim.scenario)[0]
        result = sim.call(["apply", "-f", "-"], tool="kubectl", stdin=next(iter(action["files"].values())))
        self.assertEqual(result["exit_code"], 0, result)
        sim.skills = True
        text = sim.call(["aks", "namespace", "add", "--help"])["stdout"]
        self.assertIn("--adoption-policy", text)
        self.assertIn("aks skill", text)
        for candidate in NAMES:
            skill_id = make(candidate, 19)["candidate"]["proposed_skill_id"]
            self.assertEqual(sim.call(["aks", "skill", "show", "--name", skill_id])["exit_code"], 0, skill_id)

    def test_public_application_probes_have_coverage_for_every_candidate(self):
        for name in NAMES:
            with self.subTest(name=name):
                sim = self.simulator(name)
                self.solve(sim)
                result = execute(sim, kube("exec", "deployment/api", "--", "/app/probe", "--all"))
                self.assertEqual(result["exit_code"], 0, result)
                self.assertNotEqual(sim.events[-1]["category"], "coverage_gap")

    def test_dry_run_does_not_mutate_and_template_rollout_refreshes_env(self):
        sim = self.simulator("csi-rotation-consumption-mode")
        document = copy.deepcopy(sim.scenario["expected"]["deployment"])
        document["spec"]["template"]["metadata"]["annotations"] = {"refresh": "approved"}
        before = sim.state_hash()
        result = sim.call(["apply", "--dry-run=client", "-f", "-"], tool="kubectl", stdin=json.dumps(document))
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(before, sim.state_hash())
        execute(sim, apply(document))
        self.assertTrue(grade(sim.scenario, sim.state)["success"])

    def test_invalid_role_scope_is_rejected_without_recording_grant(self):
        sim = self.simulator("acr-abac-pull-repair")
        action = commands(sim.scenario)[0]
        action[action.index("--scope")+1] = "/subscriptions/not-a-subscription/resourceGroups/none"
        before = sim.state_hash()
        self.assertNotEqual(execute(sim, action)["exit_code"], 0)
        self.assertEqual(before, sim.state_hash())
        self.solve(sim)

    def test_readonly_network_inventory_and_authorization_listing(self):
        sim = self.simulator("acr-private-data-endpoint")
        for args in (["network", "private-endpoint", "list", "-g", "network-rg"], ["network", "vnet", "list", "-g", "network-rg"],
                     ["acr", "private-endpoint-connection", "list", "--registry-name", sim.scenario["context"]["registry"]],
                     ["acr", "check-health", "--ignore-errors"]):
            self.assertEqual(sim.call(args)["exit_code"], 0)
        self.assertEqual(execute(sim, kube("auth", "can-i", "--list", "-n", "retail"))["exit_code"], 0)
        self.assertEqual(execute(sim, kube("get", "namespace", "retail", "ingress", "other", "--show-labels"))["exit_code"], 0)

    def test_namespace_reader_cannot_list_cluster_wide(self):
        sim = self.simulator("managed-namespace-rbac-plane")
        self.solve(sim)
        for flag in ("--all-namespaces", "-A"):
            for args in (("auth", "can-i", "list", "pods", flag), ("get", "pods", flag)):
                self.assertEqual(execute(sim, kube(*args))["exit_code"], 1)
        self.assertTrue(grade(sim.scenario, sim.state)["success"])

    def test_fresh_pull_pod_reconciles_and_get_rest_stays_modeled(self):
        sim = self.simulator("acr-abac-pull-repair")
        self.solve(sim)
        execute(sim, kube("run", "fresh-pull", "--image="+sim.scenario["context"]["approved_image"], "--restart=Never"))
        self.assertEqual(execute(sim, kube("wait", "--for=condition=Ready", "pod/fresh-pull"))["exit_code"], 0)
        sim = self.simulator("managed-namespace-selective-ingress")
        url = "https://management.azure.com"+sim.scenario["context"]["approved_namespace_scope"]+"?api-version=2025-07-01"
        self.assertEqual(sim.call(["rest", "--method", "get", "--url", url])["exit_code"], 0)
        self.assertEqual(sim.call(["rest", "--method", "put", "--url", url])["exit_code"], 2)
        self.assertEqual(sim.call(["rest", "--method", "get", "--url", url.replace("/subscriptions/", "/subscriptions/wrong-")])["exit_code"], 1)
        self.assertNotEqual(sim.events[-1]["category"], "coverage_gap")
