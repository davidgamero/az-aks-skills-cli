import copy
import json
from pathlib import Path
import tempfile
import unittest

from aks_bench.candidate_solutions import execute
from aks_bench.investigations import NAMES
from aks_bench.investigation_solutions import commands, report
from aks_bench.investigation_report import report as summarize
from aks_bench.mock import Simulator
from aks_bench.scenarios import make, grade


class InvestigationTests(unittest.TestCase):
    def sim(self,name,skills=False,hint="help"):
        return Simulator(make(name,41),skills=skills,hint_policy=hint,latency_scale=0)

    def solve(self,sim):
        for action in commands(sim.scenario):
            result=execute(sim,action)
            self.assertEqual(result["exit_code"],0,(action,result))
        self.assertTrue(grade(sim.scenario,sim.state)["success"],grade(sim.scenario,sim.state))

    def test_all_reference_diagnoses_and_wrong_cause_controls(self):
        for name in NAMES:
            with self.subTest(name=name):
                sim=self.sim(name);self.assertFalse(grade(sim.scenario,sim.state)["success"]);self.solve(sim)
                sim.state["_incident_report"]["diagnosis"]="unconfirmed"
                self.assertFalse(grade(sim.scenario,sim.state)["success"])

    def test_correct_label_without_observed_evidence_fails(self):
        for name in NAMES:
            sim=self.sim(name);self.solve(sim)
            sim.state["_incident_observations"]=[]
            self.assertFalse(grade(sim.scenario,sim.state)["success"])

    def test_missing_source_and_fabricated_quote_fail(self):
        sim=self.sim("gpu-incident-device-memory");self.solve(sim)
        good=copy.deepcopy(sim.state)
        sim.state["_incident_report"]["evidence"][0]["quote"]="invented error message proving everything"
        self.assertFalse(grade(sim.scenario,sim.state)["checks"]["evidence_quotes_authentic"])
        sim.state=good
        sim.state["_incident_observations"]=[e for e in sim.state["_incident_observations"] if "host_memory" not in e["signals"]]
        sim.state["_incident_report"]=report(sim.scenario,sim.state)
        self.assertFalse(grade(sim.scenario,sim.state)["success"])

    def test_current_or_wrong_node_gpu_metrics_cannot_prove_incident(self):
        for change in ("current","peer"):
            sim=self.sim("gpu-incident-device-memory")
            for action in commands(sim.scenario)[:-1]:
                if isinstance(action,dict) and action.get("tool")=="curl":
                    action=copy.deepcopy(action)
                    if change=="current": action["argv"][-1]=action["argv"][-1].replace("query_range","query")
                    else: action["argv"][2]=action["argv"][2].replace(sim.scenario["context"]["pod"],"comparison-pod")
                execute(sim,action)
            sim.state["_incident_report"]=report(sim.scenario,sim.state)
            self.assertFalse(grade(sim.scenario,sim.state)["success"],change)

    def test_snat_needs_usage_allocation_and_failed_connections(self):
        sim=self.sim("egress-incident-snat")
        for action in commands(sim.scenario)[:-1]:
            if isinstance(action,list) and action[:3]==["monitor","metrics","list"]:
                action=list(action);action[action.index("--metric")+1]="UsedSnatPorts"
            execute(sim,action)
        sim.state["_incident_report"]=report(sim.scenario,sim.state)
        self.assertFalse(grade(sim.scenario,sim.state)["success"])

    def test_hints_preserve_stdout_exit_and_do_not_reveal_variant(self):
        messages=[]
        for name in NAMES:
            plain=self.sim(name);help_only=self.sim(name,True);contextual=self.sim(name,True,"contextual")
            x=plain.scenario["context"];argv=["describe","pod",x["pod"],"-n",x["namespace"],"-o","json"]
            a,b,c=[s.call(argv,tool="kubectl") for s in (plain,help_only,contextual)]
            self.assertEqual(a,b);self.assertEqual(a["stdout"],c["stdout"]);self.assertEqual(a["exit_code"],c["exit_code"])
            json.loads(c["stdout"]);self.assertIn("az aks skill show",c["stderr"])
            self.assertEqual(contextual.call(argv,tool="kubectl")["stderr"],"")
            messages.append(c["stderr"])
        self.assertEqual(len(set(messages[:3])),1);self.assertEqual(len(set(messages[3:])),1)

    def test_help_and_usage_hints_remain_tool_only(self):
        s=self.sim(NAMES[0],True,"contextual")
        self.assertNotIn("skill",s.scenario["prompt"].lower())
        response=s.call(["logs","--help"],tool="kubectl")
        self.assertIn("Related diagnostic procedure",response["stderr"])
        self.assertEqual(s.events[-1]["discovery_hint"]["surface"],"help")
        s.call(["aks","show","--help"])
        self.assertTrue(s.events[-1]["skill_help_exposed"])
        self.assertEqual(s.call(["aks","skill","show","--name","aks-investigate-egress"])["exit_code"],0)

    def test_mutation_is_recorded_and_report_cannot_erase_it(self):
        sim=self.sim("gpu-incident-kaito-quota");self.solve(sim)
        before=copy.deepcopy(sim.state["clusters"])
        response=sim.call(["delete","workspace","serving","-n","inference"],tool="kubectl")
        self.assertEqual(response["exit_code"],1);self.assertEqual(before,sim.state["clusters"])
        self.assertFalse(grade(sim.scenario,sim.state)["success"])

    def test_bad_report_shapes_do_not_crash(self):
        sim=self.sim(NAMES[0])
        for bad in ({"evidence":[None]}, {"alternatives":[{}]}, {"recommendation":[]}, {"evidence":"made up"}):
            sim.state["_incident_report"]=bad
            self.assertFalse(grade(sim.scenario,sim.state)["success"])

    def test_three_arm_report_keeps_conditions_and_invalids_distinct(self):
        rows=[]
        for c in ("baseline","help","contextual"):
            rows.append({"scenario":"case","requested_model":"model","provider":"copilot","mode":"live","docs_mode":"off","condition":c,
                "valid_trial":c!="contextual","success":True,"seed":1,"skill_reads":int(c=="contextual"),"elapsed_s":10,"llm_requests":4,"tool_calls":6})
        with tempfile.TemporaryDirectory() as d:
            result=summarize(d,rows)[0]
            self.assertEqual(result["contextual"]["invalid"],1)
            self.assertEqual(result["contextual"]["all_skill_read_trials"],1)
            self.assertEqual(result["contextual"]["skill_read_trials"],0)
            self.assertEqual(result["contextual_minus_help_successful_pairs"],[])

    def test_supplementary_real_reads_are_authentic_without_decisive_credit(self):
        sim=self.sim(NAMES[0]);sim.call(["config","current-context"],tool="kubectl")
        self.solve(sim)
        self.assertTrue(any(e["argv"]==["config","current-context"] for e in sim.state["_incident_observations"]))
        sim.state["_incident_report"]["evidence"].append({"command":"date -u", "quote":"local timestamp conversion"})
        result=grade(sim.scenario,sim.state)
        self.assertTrue(result["success"]);self.assertEqual(result["unverified_local_citations"],["date -u"])

    def test_metric_multivalue_and_case_aliases(self):
        sim=self.sim(NAMES[0]);x=sim.scenario["context"]
        args=["monitor","metrics","list","--resource",x["evidence_sources"]["load_balancer_id"],"--metric","UsedSNATPorts","AllocatedSNATPorts","SnatConnectionCount", "--start-time",x["incident_window"]["start"],"--end-time",x["incident_window"]["end"]]
        result=sim.call(args);self.assertEqual(result["exit_code"],0,result)
        self.assertEqual(len(json.loads(result["stdout"])["value"]),3)

    def test_unscheduled_workloads_do_not_emit_crash_logs_or_memory_series(self):
        for name in ("gpu-incident-plugin","gpu-incident-kaito-quota"):
            sim=self.sim(name);x=sim.scenario["context"]
            r=sim.call(["logs",x["pod"],"-n",x["namespace"],"--previous"],tool="kubectl")
            self.assertEqual(r["exit_code"],1);self.assertNotEqual(sim.events[-1]["category"],"coverage_gap")
            q=next(c for c in commands(sim.scenario) if isinstance(c,dict) and c.get("tool")=="curl")
            r=execute(sim,q);self.assertEqual(json.loads(r["stdout"])["data"]["result"],[])

    def test_compound_and_lossless_metrics_citations_without_execution(self):
        from aks_bench.investigation_citations import verify,projections
        sim=self.sim(NAMES[0]);self.solve(sim)
        observations=sim.state["_incident_observations"]
        import shlex
        first,second=observations[:2]
        citation={"command":shlex.join([first["tool"],*first["argv"]])+" && "+shlex.join([second["tool"],*second["argv"]]),
            "quote":first["stdout"]+second["stdout"]}
        self.assertTrue(verify(citation,observations)[0])
        metrics=next(e for e in observations if "snat_usage" in e["signals"])
        for projection in projections(metrics)[1:]:
            citation={"command":shlex.join([metrics["tool"],*metrics["argv"]])+" | python3 -c 'raise RuntimeError(\"never execute\")'", "quote":projection}
            authentic,tags,_=verify(citation,observations)
            self.assertTrue(authentic);self.assertIn("snat_usage",tags)
            citation["quote"]=projection.replace("420","999999")
            self.assertFalse(verify(citation,observations)[0])

    def test_plugin_historical_uncertainty_is_not_penalized_as_wrong_cause(self):
        sim=self.sim("gpu-incident-plugin");self.solve(sim)
        self.assertEqual(grade(sim.scenario,sim.state)["outcome_kind"],"supported_candidate_with_evidence_gap")
        sim.state["_incident_report"]["confidence"]="confirmed"
        self.assertFalse(grade(sim.scenario,sim.state)["checks"]["confidence_supported"])
