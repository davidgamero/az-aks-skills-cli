"""Reference transport validation, not live model evidence."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from aks_bench.procedures import NAMES
from aks_bench.procedure_solutions import commands,backup_assessment
from aks_bench.procedure_oracles import verified
from aks_bench.mock import Simulator
from aks_bench.runner import container_command
from aks_bench.scenarios import make,grade
from aks_bench.services import Services


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bwrap",required=True);parser.add_argument("--copilot",required=True);parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args();root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    for seed in (81,82):
        for name in NAMES:
            directory=root/f"{name}-{seed}";directory.mkdir();workspace=directory/"workspace";workspace.mkdir();artifacts=directory/"agent";artifacts.mkdir()
            sim=Simulator(make(name,seed),skills=True,hint_policy="contextual",latency_scale=0,log_path=directory/"events.jsonl")
            actions=commands(sim.scenario)
            if name==NAMES[3]:actions=actions[:-1]
            for filename,content in sim.scenario["workspace_files"].items():(workspace/filename).write_text(content)
            for action in actions:
                if isinstance(action,dict):
                    for filename,content in action.get("files",{}).items():(workspace/Path(filename).relative_to("/work")).write_text(content)
            env={"PATH":"/opt/client:/usr/bin:/bin","HOME":"/home/agent"}
            with tempfile.TemporaryDirectory(dir="/tmp/opencode",prefix="procedure-check-") as sockets:
                with Services(sockets,sim,set(),directory/"proxy.jsonl"):
                    command=container_command("bwrap",args.bwrap,Path(args.copilot).resolve(),Path(sockets),artifacts,["--replay",json.dumps(actions)],env,"procedure-check",workspace)
                    result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=60)
            (directory/"stdout.txt").write_text(result.stdout);(directory/"stderr.txt").write_text(result.stderr)
            if name==NAMES[3]:sim.state["_procedure_report"]=backup_assessment(sim.scenario)
            checks=grade(sim.scenario,sim.state);isolation=json.loads((artifacts/"isolation.json").read_text())
            assert result.returncode==0 and checks["success"] and verified(sim.scenario,sim.state) and all(isolation.values()),(name,seed,result.stderr,checks)
            print(f"{name} seed {seed}: isolated reference passed",flush=True)


if __name__=="__main__":main()
