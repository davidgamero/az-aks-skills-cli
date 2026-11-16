"""Isolated transport-only error ladder check. No agent/model inference."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from aks_bench.error_ladder import metrics
from aks_bench.mock import Simulator
from aks_bench.runner import container_command
from aks_bench.scenarios import make
from aks_bench.services import Services


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bwrap",required=True);parser.add_argument("--copilot",required=True);parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args();root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    for kind in ("arm503","cli_error"):
        for failures in (0,2,3,-1):
            config={"kind":kind,"failures":failures};scenario=make("manual-scale",71);c=scenario["state"]["clusters"][0]
            directory=root/f"{kind}-{failures}";directory.mkdir();artifacts=directory/"agent";artifacts.mkdir();workspace=directory/"workspace";workspace.mkdir()
            sim=Simulator(scenario,skills=True,failure_config=config,latency_scale=0,log_path=directory/"events.jsonl")
            show=["aks","show","-g",c["resourceGroup"],"-n",c["name"]]
            actions=[{"tool":"az","argv":show,"expect_exit":1} for _ in range(failures if failures>=0 else 6)]
            actions.insert(1,{"tool":"az","argv":["aks","show","--help"]})
            if failures>=0:actions.append({"tool":"az","argv":show})
            env={"PATH":"/opt/client:/usr/bin:/bin","HOME":"/home/agent"}
            with tempfile.TemporaryDirectory(dir="/tmp/opencode",prefix="error-check-") as sockets:
                with Services(sockets,sim,set(),directory/"proxy.jsonl"):
                    command=container_command("bwrap",args.bwrap,Path(args.copilot).resolve(),Path(sockets),artifacts,
                        ["--replay",json.dumps(actions)],env,"error-check",workspace)
                    result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=60)
            (directory/"stdout.txt").write_text(result.stdout);(directory/"stderr.txt").write_text(result.stderr)
            isolation=json.loads((artifacts/"isolation.json").read_text())
            summary=metrics(sim.events,config)
            assert result.returncode==0 and all(isolation.values()),(kind,failures,result.stderr)
            assert summary["first_eligible_success_attempt"]==(failures+1 if failures>=0 else None)
            assert not any(e.get("discovery_hint") for e in sim.events)
            (directory/"result.json").write_text(json.dumps({"mode":"transport-check","failure_metrics":summary,"isolation":isolation},indent=2)+"\n")
            print(f"{kind} failures={failures}: isolated gate and help passed",flush=True)


if __name__=="__main__":main()
