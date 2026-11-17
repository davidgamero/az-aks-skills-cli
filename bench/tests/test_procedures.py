import copy
import json
from pathlib import Path
import sys
import unittest

from aks_bench.candidate_solutions import execute,patch,kube
from aks_bench.mock import Simulator
from aks_bench.procedures import NAMES
from aks_bench.procedure_oracles import verified,snat_target
from aks_bench.procedure_solutions import commands,backup_assessment
from aks_bench.scenarios import make,grade


class ProcedureTests(unittest.TestCase):
    def sim(self,name,seed=81,skills=False,hint="help"):
        return Simulator(make(name,seed),skills=skills,hint_policy=hint,latency_scale=0)

    def solve(self,sim):
        for action in commands(sim.scenario):
            result=execute(sim,action)
            self.assertEqual(result["exit_code"],0,(action,result))
        self.assertTrue(grade(sim.scenario,sim.state)["success"],grade(sim.scenario,sim.state))
        self.assertTrue(verified(sim.scenario,sim.state))

    def test_both_seed_references_and_independent_negative_controls(self):
        for seed in (81,82):
            for name in NAMES:
                with self.subTest(seed=seed,name=name):
                    sim=self.sim(name,seed);self.assertFalse(grade(sim.scenario,sim.state)["success"]);self.solve(sim)
                    w=sim.state["clusters"][0]["_world"]
                    if name==NAMES[0]:sim.state["clusters"][0]["networkProfile"]["loadBalancerProfile"]["managedOutboundIPs"]["count"]-=1
                    elif name==NAMES[1]:w["dns_loaded"].pop("private.server")
                    elif name==NAMES[2]:w["disk"]["dataHash"]="lost data"
                    else:sim.state["_procedure_report"]["volumes"][0]["eligible"]=not sim.state["_procedure_report"]["volumes"][0]["eligible"]
                    self.assertFalse(grade(sim.scenario,sim.state)["success"])

    def test_snat_must_cover_future_surge_not_current_capacity(self):
        sim=self.sim(NAMES[0]);s=sim.scenario;x=s["context"];ports,ips=snat_target(s)
        args=["aks","update","-g",x["resource_group"],"-n",x["cluster"],"--load-balancer-outbound-ports",str(ports),"--load-balancer-managed-outbound-ip-count",str(ips-1)]
        result=sim.call(args)
        self.assertEqual(result["exit_code"],0,result)
        self.assertFalse(grade(s,sim.state)["success"])
        self.assertEqual(sim.call([*args[:-4],"--load-balancer-outbound-ports",str(ports+1),"--load-balancer-managed-outbound-ip-count",str(ips)])["exit_code"],1)

    def test_dns_apply_requires_reload_and_normal_source_probe(self):
        sim=self.sim(NAMES[1]);actions=commands(sim.scenario);execute(sim,actions[0])
        self.assertFalse(grade(sim.scenario,sim.state)["success"])
        self.assertEqual(execute(sim,actions[2])["exit_code"],1)
        execute(sim,actions[1])
        x=sim.scenario["context"]
        execute(sim,kube("exec","deployment/api","--","nslookup",x["private_query"],x["approved_dns_upstream"]))
        for action in actions[3:]:execute(sim,action)
        self.assertTrue(grade(sim.scenario,sim.state)["success"])
        self.assertFalse(verified(sim.scenario,sim.state))
        execute(sim,actions[2]);self.assertTrue(verified(sim.scenario,sim.state))

    def test_disk_type_branches_and_forged_capacity_do_not_resize(self):
        offline=self.sim(NAMES[2],81)
        action=patch("pvc","data",{"spec":{"resources":{"requests":{"storage":"5120Gi"}}}})
        self.assertEqual(execute(offline,action)["exit_code"],1)
        self.assertEqual(offline.state["clusters"][0]["_world"]["disk"]["diskSizeGb"],3072)
        self.solve(offline)
        online=self.sim(NAMES[2],82)
        self.assertEqual(execute(online,action)["exit_code"],0)
        self.assertFalse(online.state["clusters"][0]["_world"]["downtime_seen"])
        execute(online,kube("scale","deployment/api","--replicas=0"))
        execute(online,kube("scale","deployment/api","--replicas=1"))
        self.assertFalse(grade(online.scenario,online.state)["checks"]["unnecessary_downtime_avoided"])

    def test_backup_schema_empty_missing_extra_and_malformed_fail(self):
        sim=self.sim(NAMES[3]);self.solve(sim)
        good=backup_assessment(sim.scenario)
        for bad in ({}, {"volumes":None}, {"volumes":[{"name":[]} ]}, {**good,"worst_case_rpo_hours":4}, {**good,"volumes":good["volumes"][:-1]}):
            sim.state["_procedure_report"]=bad
            self.assertFalse(grade(sim.scenario,sim.state)["success"])

    def test_contextual_discovery_is_separate_and_stdout_stays_data(self):
        for name in NAMES:
            a=self.sim(name);b=self.sim(name,skills=True,hint="contextual")
            x=a.scenario["context"];args=["aks","show","-g",x["resource_group"],"-n",x["cluster"]]
            plain=a.call(args);hint=b.call(args)
            self.assertEqual(plain["stdout"],hint["stdout"]);json.loads(hint["stdout"])
            self.assertIn("az aks skill show",hint["stderr"])
            self.assertNotIn("skill",a.scenario["prompt"].lower())
            self.assertEqual(b.call(["aks","skill","show","--name",b.scenario["procedure_skill"]])["exit_code"],0)

    def test_master_list_separates_new_designs_from_runnable_history(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from master_scenarios import build
        data=build();names=[s["id"] for s in data["scenarios"]]
        self.assertEqual(len(names),len(set(names)))
        self.assertEqual(data["runnable_scenarios"],38);self.assertEqual(data["designed_only"],20)
        self.assertEqual(len(names),58)
        self.assertFalse(any("comparison" in e for e in data["scenarios"]))

    def test_json_patch_move_and_standard_dns_input_read(self):
        sim=self.sim(NAMES[1])
        result=execute(sim,kube("patch","configmap/coredns-custom","-n","kube-system","--type=json","-p",json.dumps([{"op":"move","from":"/data/private.conf","path":"/data/private.server"}])))
        self.assertEqual(result["exit_code"],0,result)
        result=execute(sim,kube("exec","deployment/api","--","cat","/etc/resolv.conf"))
        self.assertIn("10.100.0.10",result["stdout"])

    def test_routine_health_and_disk_file_probes_are_bounded_and_consistent(self):
        sim=self.sim(NAMES[2]);before=sim.state_hash()
        for args in (("ls","-la","/mnt/data"),("find","/mnt/data","-type","f","-exec","sha256sum","{}",";"),
                     ("sh","-c",r"ls -la /mnt/data; find /mnt/data -type f -exec sha256sum {} \;"),
                     ("curl","-fsS","http://127.0.0.1:8080/ready")):
            result=execute(sim,kube("exec","deployment/api","--",*args))
            self.assertEqual(result["exit_code"],0,(args,result))
        self.assertEqual(before,sim.state_hash())
        self.assertEqual(execute(sim,kube("exec","deployment/api","--","cat","/mnt/data/missing"))["exit_code"],1)

    def test_files_backup_blocker_equivalence_is_not_false_positive(self):
        sim=self.sim(NAMES[3]);self.solve(sim)
        row=next(v for v in sim.state["_procedure_report"]["volumes"] if v["name"].endswith("-4"))
        for blockers in (["driver"],["backupTier"],["driver","backupTier"]):
            row["blockers"]=blockers;self.assertTrue(grade(sim.scenario,sim.state)["success"])
        row["blockers"]=["driver","sizeGiB"]
        self.assertFalse(grade(sim.scenario,sim.state)["success"])

    def test_owner_inventory_reads_have_realistic_bounded_coverage(self):
        sim=self.sim(NAMES[0]);self.solve(sim)
        result=sim.call(["network","public-ip","list","-g",sim.state["clusters"][0]["nodeResourceGroup"]])
        count=sim.state["clusters"][0]["networkProfile"]["loadBalancerProfile"]["managedOutboundIPs"]["count"]
        self.assertEqual(len(json.loads(result["stdout"])),count)
        sim=self.sim(NAMES[2]);result=sim.call(["vmss","list","-g",sim.state["clusters"][0]["nodeResourceGroup"]])
        self.assertEqual(result["exit_code"],0)
        self.assertEqual(len(json.loads(result["stdout"])),2)
