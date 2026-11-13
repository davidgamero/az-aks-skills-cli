import copy
import json
import unittest

from aks_bench.automatic import AUTO_SCHEDULE, OS_SCHEDULE
from aks_bench.mock import Simulator
from aks_bench.runner import oracle_commands
from aks_bench.scenarios import make, grade


class AutomaticTests(unittest.TestCase):
    def simulator(self, name="automatic-create"):
        scenario = make(name, 1)
        return scenario, Simulator(scenario, skills=True, latency_scale=0)

    def test_create_requires_automatic_sku_not_just_standard_tier(self):
        scenario, sim = self.simulator()
        commands = oracle_commands(scenario)
        wrong = commands[0][:commands[0].index("--sku")] + ["--tier", "standard"]
        self.assertEqual(sim.call(wrong)["exit_code"], 0)
        self.assertFalse(grade(scenario, sim.state)["success"])
        self.assertEqual(sim.state["clusters"][0]["sku"]["name"], "Base")
        scenario, sim = self.simulator()
        self.assertFalse(grade(scenario, sim.state)["success"])
        for command in commands:
            self.assertEqual(sim.call(command)["exit_code"], 0)
        self.assertTrue(grade(scenario, sim.state)["success"])
        self.assertIsNotNone(sim.verified_goal_s)

    def test_automatic_creation_rejects_conflicting_options(self):
        for flags in (["--tier", "free"], ["--node-count", "3"],
                      ["--node-provisioning-mode", "Manual"], ["--auto-upgrade-channel", "none"]):
            with self.subTest(flags=flags):
                scenario, sim = self.simulator()
                result = sim.call(oracle_commands(scenario)[0] + flags)
                self.assertEqual(result["exit_code"], 1, result)
                self.assertEqual(sim.state["clusters"], [])

    def test_hosted_system_is_default_for_new_automatic_clusters(self):
        scenario, sim = self.simulator()
        command = oracle_commands(scenario)[0][:-1]
        self.assertEqual(sim.call(command)["exit_code"], 0)
        self.assertTrue(grade(scenario, sim.state)["success"])
        self.assertIsNone(sim.verified_goal_s)

    def test_automatic_cluster_protects_managed_settings(self):
        scenario, sim = self.simulator("automatic-maintenance")
        t = scenario["target"]
        base = ["-g", t["resourceGroup"], "-n", t["name"]]
        initial = copy.deepcopy(sim.state["clusters"])
        for command in (["aks", "stop", *base],
                        ["aks", "update", *base, "--auto-upgrade-channel", "none"],
                        ["aks", "update", *base, "--node-os-upgrade-channel", "None"],
                        ["aks", "update", *base, "--node-provisioning-mode", "Manual"]):
            with self.subTest(command=command):
                self.assertEqual(sim.call(command)["exit_code"], 1)
                self.assertEqual(sim.state["clusters"], initial)

    def test_cluster_show_does_not_expose_or_verify_child_schedules(self):
        scenario, sim = self.simulator("automatic-maintenance")
        commands = oracle_commands(scenario)
        for command in commands[:-1]:
            self.assertEqual(sim.call(command)["exit_code"], 0)
        result = sim.call(commands[0])
        self.assertNotIn("_maintenanceConfigurations", result["stdout"])
        self.assertNotIn(AUTO_SCHEDULE, result["stdout"])
        self.assertIsNone(sim.verified_goal_s)
        self.assertEqual(sim.call(commands[-1])["exit_code"], 0)
        self.assertIsNotNone(sim.verified_goal_s)
        self.assertTrue(grade(scenario, sim.state)["success"])

    def test_two_individual_reads_verify_the_current_schedule_versions(self):
        scenario, sim = self.simulator("automatic-maintenance")
        commands = oracle_commands(scenario)
        base = commands[1][3:]
        self.assertEqual(sim.call(commands[2])["exit_code"], 0)
        self.assertEqual(sim.call(["aks", "maintenanceconfiguration", "show", *base, "-n", AUTO_SCHEDULE])["exit_code"], 0)
        self.assertEqual(sim.call(commands[3])["exit_code"], 0)
        self.assertIsNone(sim.verified_goal_s)
        self.assertEqual(sim.call(["aks", "maintenanceconfiguration", "show", *base, "-n", OS_SCHEDULE])["exit_code"], 0)
        self.assertIsNotNone(sim.verified_goal_s)

    def test_wrong_window_and_unrelated_mutations_fail_oracle(self):
        scenario, sim = self.simulator("automatic-maintenance")
        commands = oracle_commands(scenario)
        wrong = list(commands[2])
        wrong[wrong.index(AUTO_SCHEDULE)] = "default"
        self.assertEqual(sim.call(wrong)["exit_code"], 0)
        self.assertFalse(grade(scenario, sim.state)["success"])
        for command in commands[2:]:
            self.assertEqual(sim.call(command)["exit_code"], 0)
        self.assertFalse(grade(scenario, sim.state)["success"])
        self.assertFalse(grade(scenario, sim.state)["checks"]["default_unchanged"])

    def test_invalid_window_is_transactional_and_missing_resource_is_404(self):
        scenario, sim = self.simulator("automatic-maintenance")
        command = oracle_commands(scenario)[2]
        initial = copy.deepcopy(sim.state["clusters"])
        for option, value in (("--duration", "2"), ("--start-time", "25:00"), ("--day-of-week", "Funday"), ("--utc-offset", "+99:00")):
            args = list(command)
            args[args.index(option) + 1] = value
            self.assertEqual(sim.call(args)["exit_code"], 1)
            self.assertEqual(sim.state["clusters"], initial)
        args = list(command)
        args[args.index(AUTO_SCHEDULE)] = "missing"
        self.assertEqual(sim.call(args)["exit_code"], 1)
        self.assertEqual(sim.events[-1]["http_status"], 404)

    def test_add_and_delete_maintenance_resources(self):
        scenario, sim = self.simulator("automatic-maintenance")
        command = oracle_commands(scenario)[2]
        base = command[3:command.index("--schedule-type")]
        self.assertEqual(sim.call(["aks", "maintenanceconfiguration", "delete", *base])["exit_code"], 0)
        self.assertEqual(sim.call(command)["exit_code"], 1)
        command[2] = "add"
        self.assertEqual(sim.call(command)["exit_code"], 0)


if __name__ == "__main__":
    unittest.main()
