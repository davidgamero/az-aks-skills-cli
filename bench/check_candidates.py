"""Opt-in real-container reference/manifest/docs transport check (not model evidence)."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from aks_bench.candidate_fixtures import NAMES
from aks_bench.candidate_oracles import verified
from aks_bench.candidate_solutions import commands
from aks_bench.mock import Simulator
from aks_bench.runner import container_command, documentation_network
from aks_bench.scenarios import grade, make
from aks_bench.services import Services


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bwrap", required=True)
    parser.add_argument("--copilot", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    for name in NAMES:
        directory = args.output / name
        directory.mkdir()
        artifacts = directory / "agent"; artifacts.mkdir()
        workspace = directory / "workspace"; workspace.mkdir()
        scenario = make(name, 19)
        for filename, content in scenario["workspace_files"].items(): (workspace / filename).write_text(content)
        actions = commands(scenario)
        for action in actions:
            if isinstance(action, dict):
                for filename, content in action.get("files", {}).items():
                    (workspace / Path(filename).relative_to("/work")).write_text(content)
        if name == "gateway-api-publish":
            actions += [{"tool": "curl", "argv": ["-fsSL", url]} for url in (
                "https://learn.microsoft.com/en-us/azure/aks/managed-namespaces",
                "https://kubernetes.io/docs/concepts/services-networking/network-policies/")]
        sim = Simulator(scenario, log_path=directory / "events.jsonl", latency_scale=0, docs_mode="live")
        env = {"PATH": "/opt/client:/usr/bin:/bin", "HOME": "/home/agent"}
        with tempfile.TemporaryDirectory(dir="/tmp/opencode", prefix="candidate-check-") as sockets:
            hosts = documentation_network(sockets, env, set())
            with Services(sockets, sim, hosts, directory / "proxy.jsonl"):
                command = container_command("bwrap", args.bwrap, Path(args.copilot).resolve(), Path(sockets), artifacts,
                    ["--replay", json.dumps(actions)], env, "candidate-check", workspace)
                with (directory / "stdout.txt").open("w") as stdout, (directory / "stderr.txt").open("w") as stderr:
                    result = subprocess.run(command, env=env, stdout=stdout, stderr=stderr, timeout=120)
        checks = grade(scenario, sim.state)
        isolation = json.loads((artifacts / "isolation.json").read_text())
        assert result.returncode == 0 and checks["success"] and verified(scenario, sim.state) and all(isolation.values()), (name, result.returncode, checks)
        print(name + ": isolated reference passed", flush=True)


if __name__ == "__main__": main()
