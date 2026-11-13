"""Exercise incident reference reads through real isolated clients; no model evidence."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from aks_bench.investigations import NAMES
from aks_bench.investigation_solutions import commands, report
from aks_bench.mock import Simulator
from aks_bench.runner import container_command
from aks_bench.scenarios import make, grade
from aks_bench.services import Services


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bwrap",required=True);parser.add_argument("--copilot",required=True);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    for name in NAMES:
        directory=root/name;directory.mkdir();artifacts=directory/"agent";artifacts.mkdir();workspace=directory/"workspace";workspace.mkdir()
        sim=Simulator(make(name,41),skills=True,hint_policy="contextual",latency_scale=0,log_path=directory/"events.jsonl")
        env={"PATH":"/opt/client:/usr/bin:/bin","HOME":"/home/agent"}
        with tempfile.TemporaryDirectory(dir="/tmp/opencode",prefix="incident-check-") as sockets:
            with Services(sockets,sim,set(),directory/"proxy.jsonl"):
                command=container_command("bwrap",args.bwrap,Path(args.copilot).resolve(),Path(sockets),artifacts,
                    ["--replay",json.dumps(commands(sim.scenario)[:-1])],env,"incident-check",workspace)
                result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=60)
                (directory/"stdout.txt").write_text(result.stdout);(directory/"stderr.txt").write_text(result.stderr)
        sim.state["_incident_report"]=report(sim.scenario,sim.state)
        checks=grade(sim.scenario,sim.state)
        isolation=json.loads((artifacts/"isolation.json").read_text())
        assert result.returncode==0 and checks["success"] and all(isolation.values()),(name,result.stderr,checks)
        print(name+": isolated evidence reference passed",flush=True)


if __name__=="__main__": main()
