import concurrent.futures
import copy
import json
from pathlib import Path
import tempfile
import unittest

from aks_bench.error_ladder import FailureGate, metrics, report
from aks_bench.mock import Simulator
from aks_bench.scenarios import make


class ErrorLadderTests(unittest.TestCase):
    def sim(self,kind="arm503",count=2,scenario="manual-scale",skills=True,log=None):
        return Simulator(make(scenario,71),skills=skills,latency_scale=0,hint_policy="help",log_path=log,
                         failure_config={"kind":kind,"failures":count})

    def show(self,sim):
        c=sim.scenario["state"]["clusters"][0]
        return ["aks","show","-g",c["resourceGroup"],"-n",c["name"]]

    def test_exact_consecutive_budgets_and_third_fourth_call_recovery(self):
        for scenario in ("manual-scale","egress-incident-snat","acr-abac-pull-repair"):
            for kind in ("arm503","cli_error"):
                for count in (0,1,2,3,5,8):
                    with self.subTest(scenario=scenario,kind=kind,count=count):
                        sim=self.sim(kind,count,scenario)
                        before=copy.deepcopy(sim.state["clusters"])
                        for _ in range(count):
                            response=sim.call(self.show(sim))
                            self.assertEqual(response["exit_code"],1)
                            self.assertNotIn("skill",response["stderr"].lower())
                            self.assertNotIn("--help",response["stderr"])
                            self.assertEqual(before,sim.state["clusters"])
                        self.assertEqual(sim.call(self.show(sim))["exit_code"],0)
                        result=metrics(sim.events,{"kind":kind,"failures":count})
                        self.assertEqual(result["injected_failures_observed"],count)
                        self.assertEqual(result["first_eligible_success_attempt"],count+1)
                        self.assertIsNone(result["first_skill_read"])
                        self.assertEqual(result["threshold_status"],"not_observed_before_trial_end")

    def test_local_help_skill_and_kubectl_do_not_consume_failure_budget(self):
        sim=self.sim(scenario="egress-incident-snat")
        for argv,tool in ((["aks","show","--help"],"az"),(["account","show"],"az"),(["version"],"az"),
                          (["aks","skills","list"],"az"),(["config","current-context"],"kubectl")):
            self.assertEqual(sim.call(argv,tool=tool)["exit_code"],0)
        self.assertEqual(sim.failure_gate.attempts,0)
        self.assertEqual(sim.call(self.show(sim))["exit_code"],1)
        self.assertTrue(any(e.get("skill_help_exposed") for e in sim.events))
        self.assertFalse(any(e.get("discovery_hint") for e in sim.events))

    def test_budget_is_shared_across_commands_aliases_and_output_flags(self):
        sim=self.sim(count=3)
        c=sim.scenario["state"]["clusters"][0]
        for argv in (self.show(sim),["aks","show","--resource-group",c["resourceGroup"],"--name",c["name"],"-o","yaml"],
                     ["aks","nodepool","list","-g",c["resourceGroup"],"--cluster-name",c["name"]]):
            self.assertEqual(sim.call(argv)["exit_code"],1)
        self.assertEqual(sim.call(self.show(sim))["exit_code"],0)
        sim=self.sim(count=2)
        self.assertEqual(sim.call([*self.show(sim),"--debug"])["exit_code"],1)
        self.assertEqual(sim.call([*self.show(sim),"--verbose"])["exit_code"],1)
        self.assertEqual(sim.call(self.show(sim))["exit_code"],0)

    def test_cli_errors_have_no_modeled_arm_traffic(self):
        for kind,count in (("arm503",1),("cli_error",0)):
            sim=self.sim(kind)
            sim.call(self.show(sim))
            self.assertEqual(sim.events[-1]["modeled_api_requests"],count)
            self.assertEqual(sim.events[-1]["http_status"],503 if kind=="arm503" else None)

    def test_persistent_failures_survive_help_reads_and_never_advance_resource(self):
        sim=self.sim(count=-1)
        before=sim.state_hash()
        for _ in range(12): self.assertEqual(sim.call(self.show(sim))["exit_code"],1)
        sim.call(["aks","show","--help"])
        sim.call(["aks","skill","show","--name","aks-fixed-capacity"])
        self.assertEqual(sim.call(self.show(sim))["exit_code"],1)
        self.assertEqual(sim.state_hash(),before)
        result=metrics(sim.events,{"kind":"arm503","failures":-1})
        self.assertEqual(result["first_skill_read"]["injected_errors_before"],12)
        self.assertTrue(result["skill_fallback_observed"])
        self.assertIsNone(result["first_eligible_success_attempt"])

    def test_concurrent_calls_are_exactly_counted_and_trace_metadata_matches(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"events.jsonl";sim=self.sim(count=3,log=p)
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                results=list(pool.map(lambda _:sim.call(self.show(sim)),range(10)))
            self.assertEqual(sum(r["exit_code"]==1 for r in results),3)
            events=[json.loads(line) for line in p.read_text().splitlines()]
            self.assertEqual(events,sim.events)
            self.assertEqual([e["failure_gate"]["eligible_attempt"] for e in events],list(range(1,11)))

    def test_hints_forbidden_and_coverage_gaps_remain_gaps_after_gate(self):
        with self.assertRaises(ValueError):
            Simulator(make("manual-scale",71),skills=True,hint_policy="contextual",failure_config={"kind":"arm503","failures":2})
        sim=self.sim(count=0)
        sim.call(["some-unmodeled-group","show"])
        self.assertEqual(sim.events[-1]["category"],"coverage_gap")
        self.assertNotIn("failure_gate",sim.events[-1])

    def test_report_does_not_infer_a_threshold_from_unread_skill(self):
        sim=self.sim(count=3)
        for _ in range(4):sim.call(self.show(sim))
        exp=metrics(sim.events,{"kind":"arm503","failures":3})
        row={"scenario":"manual-scale","requested_model":"model","provider":"copilot","condition":"help","seed":71,
             "valid_trial":True,"success":True,"elapsed_s":10,"failure_experiment":exp}
        with tempfile.TemporaryDirectory() as d:
            summary=report(d,[row])[0]
            self.assertEqual(summary["help"]["errors_before_reads"],[])
            self.assertEqual(summary["recovery_eligible_attempt"],4)
            self.assertEqual(summary["help"]["skill_read_trials"],0)
