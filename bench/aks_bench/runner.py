"""Fresh rootless/Docker containers, paired trials, and evidence-based reports."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import signal
import shlex
import statistics
import subprocess
import tempfile
import time
from urllib.parse import urlparse

from .mock import ROOT, Simulator, SEMANTIC, COMMANDS
from .scenarios import NAMES, make, grade
from .services import Services
from . import automatic
from . import troubleshooting

COPILOT_HOSTS = {"api.github.com", "api.githubcopilot.com", "api.individual.githubcopilot.com",
                 "api.business.githubcopilot.com", "api.enterprise.githubcopilot.com",
                 "copilot-proxy.githubusercontent.com"}
PROVIDER_VARS = ("COPILOT_PROVIDER_BASE_URL", "COPILOT_PROVIDER_TYPE", "COPILOT_PROVIDER_API_KEY",
                 "COPILOT_PROVIDER_BEARER_TOKEN", "COPILOT_PROVIDER_WIRE_API", "COPILOT_PROVIDER_MODEL_ID",
                 "COPILOT_PROVIDER_WIRE_MODEL", "COPILOT_PROVIDER_AZURE_API_VERSION",
                 "COPILOT_PROVIDER_MAX_PROMPT_TOKENS", "COPILOT_PROVIDER_MAX_OUTPUT_TOKENS")


def json_file(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + "\n")


def timeline(directory, events):
    lines = ["# CLI timeline", "", "Times are seconds since container launch; state and trace are host-owned.", "",
             "| Start | Duration ms | Kind | Exit | Modeled API | Command |", "|---:|---:|---|---:|---:|---|"]
    for event in events:
        command = shlex.join([event.get("tool", "az"), *event["argv"]]).replace("|", "\\|").replace("`", "'")
        lines.append(f"| {event['start_s']:.3f} | {event['duration_ms']:.1f} | {event['category']} | {event['exit_code']} | {event['modeled_api_requests']} | `{command}` |")
    (directory / "timeline.md").write_text("\n".join(lines) + "\n")


def provider_environment(provider, gh_user=None):
    env = {"PATH": "/opt/client:/usr/bin:/bin", "HOME": "/home/agent", "LANG": "C.UTF-8", "TERM": "dumb"}
    if provider == "foundry":
        for key in PROVIDER_VARS:
            if os.environ.get(key):
                env[key] = os.environ[key]
        url = urlparse(env.get("COPILOT_PROVIDER_BASE_URL", ""))
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.port not in (None, 443):
            raise ValueError("Foundry requires a https:// COPILOT_PROVIDER_BASE_URL on port 443")
        if url.hostname in {"management.azure.com", "management.core.windows.net"}:
            raise ValueError("Azure management endpoints cannot be model providers")
        env.setdefault("COPILOT_PROVIDER_TYPE", "azure")
        hosts = {url.hostname}
    else:
        token = next((os.environ[k] for k in ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN") if os.environ.get(k)), None)
        if not token:
            command = ["gh", "auth", "token"] + (["--user", gh_user] if gh_user else [])
            token = subprocess.check_output(command, text=True, stderr=subprocess.PIPE).strip()
        env["COPILOT_GITHUB_TOKEN"] = token
        hosts = COPILOT_HOSTS
    return env, hosts


def container_command(engine, bwrap, copilot, sockets, artifacts, entry_args, env, name):
    client = ROOT / "container"
    if engine == "bwrap":
        command = [bwrap, "--die-with-parent", "--new-session", "--unshare-all", "--cap-drop", "ALL",
                   "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin",
                   "--symlink", "usr/sbin", "/sbin", "--symlink", "usr/lib", "/lib",
                   "--symlink", "usr/lib64", "/lib64", "--proc", "/proc", "--dev", "/dev",
                   "--tmpfs", "/tmp", "--tmpfs", "/home", "--dir", "/home/agent", "--dir", "/work",
                   "--ro-bind", "/etc/ssl/certs", "/etc/ssl/certs",
                   "--ro-bind", str(client), "/opt/client",
                   "--ro-bind", str(client / "client.py"), "/usr/bin/az",
                   "--ro-bind", str(copilot), "/opt/copilot",
                   "--ro-bind", str(sockets), "/run/bench",
                   "--bind", str(artifacts), "/results", "--chdir", "/work",
                   "--", "/usr/bin/python3", "/opt/client/entry.py", *entry_args]
    else:
        command = ["docker", "run", "--rm", "--name", name, "--network", "none", "--read-only",
                   "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "128",
                   "--memory", "2g", "--cpus", "2", "--user", f"{os.getuid()}:{os.getgid()}",
                   "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m", "--tmpfs", "/home:rw,nosuid,nodev,size=256m",
                   "--tmpfs", "/work:rw,nosuid,nodev,size=128m",
                   "--mount", f"type=bind,src={copilot},dst=/opt/copilot,readonly",
                   "--mount", f"type=bind,src={sockets},dst=/run/bench,readonly",
                   "--mount", f"type=bind,src={artifacts},dst=/results"]
        for key in env:
            command.extend(["--env", key])
        command.extend(["az-aks-bench:local", *entry_args])
    return command


def telemetry(path):
    """Count exported model spans once; never infer requests from TCP connections."""
    spans = {}
    if not path.exists():
        return {"llm_requests": None, "models_observed": [], "input_tokens": None, "output_tokens": None}
    def visit(value):
        if isinstance(value, dict):
            span_id = value.get("spanId") or value.get("span_id")
            if span_id and str(value.get("name", "")).startswith("chat "):
                spans[span_id] = value
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    for line in path.read_text().splitlines():
        try:
            visit(json.loads(line))
        except ValueError:
            continue
    models, inputs, outputs = set(), 0, 0
    for span in spans.values():
        attrs = span.get("attributes", {})
        if isinstance(attrs, list):
            attrs = {a["key"]: next(iter(a.get("value", {}).values()), None) for a in attrs}
        models.add(attrs.get("gen_ai.response.model", attrs.get("gen_ai.request.model", span["name"][5:])))
        inputs += int(attrs.get("gen_ai.usage.input_tokens", 0))
        outputs += int(attrs.get("gen_ai.usage.output_tokens", 0))
    return {"llm_requests": len(spans) if spans else None, "models_observed": sorted(m for m in models if m),
            "input_tokens": inputs if spans else None, "output_tokens": outputs if spans else None}


def oracle_commands(scenario):
    if scenario["name"] in troubleshooting.NAMES:
        return troubleshooting.oracle_commands(scenario)
    if scenario["name"] in automatic.NAMES:
        return automatic.oracle_commands(scenario)
    c = scenario["state"]["clusters"][0]
    base = ["-g", c["resourceGroup"], "--cluster-name", c["name"], "-n", "apps"]
    cluster = ["-g", c["resourceGroup"], "-n", c["name"]]
    name = scenario["name"]
    if name in ("manual-scale", "transient-scale"):
        return [["aks", "nodepool", "show", *base],
                ["aks", "nodepool", "update", *base, "--disable-cluster-autoscaler"],
                ["aks", "nodepool", "scale", *base, "--node-count", str(scenario["target_count"])],
                ["aks", "nodepool", "show", *base]]
    if name == "autoscaler":
        return [["aks", "nodepool", "show", *base],
                ["aks", "nodepool", "update", *base, "--update-cluster-autoscaler", "--min-count", "2", "--max-count", str(scenario["target_count"] + 3)],
                ["aks", "nodepool", "show", *base]]
    if name == "stop-dev":
        return [["aks", "show", *cluster], ["aks", "stop", *cluster], ["aks", "show", *cluster]]
    return [["aks", "show", *cluster], ["aks", "get-upgrades", *cluster],
            ["aks", "upgrade", *cluster, "--kubernetes-version", scenario["target_version"], "--control-plane-only", "--yes"],
            ["aks", "show", *cluster]]


def trial(args, scenario_name, seed, skills, directory, mode="live"):
    directory.mkdir(parents=True, exist_ok=False)
    artifacts = directory / "agent"
    artifacts.mkdir()
    scenario = make(scenario_name, seed)
    if args.fixture:
        scenario = json.loads(Path(args.fixture).read_text())
    sim = Simulator(scenario, skills=skills, log_path=directory / "az-events.jsonl", latency_scale=args.latency_scale,
                    docs_mode=getattr(args, "docs_mode", "off"))
    prompt = scenario["prompt"]
    json_file(directory / "scenario.json", scenario)
    (directory / "prompt.txt").write_text(prompt + "\n")
    if mode == "replay":
        start = time.monotonic()
        if skills:
            sim.call(["aks", "skill", "list", "-o", "json"])
        for command in oracle_commands(scenario):
            response = sim.call(command["argv"], tool=command["tool"]) if isinstance(command, dict) else sim.call(command)
            if response["exit_code"] and "TooManyRequests" in response["stderr"]:
                response = sim.call(command)
            if response["exit_code"]:
                raise RuntimeError(response["stderr"])
        elapsed, returncode, timeout = time.monotonic() - start, 0, False
        isolation = None
    else:
        if mode == "check":
            env, hosts = {"PATH": "/opt/client:/usr/bin:/bin", "HOME": "/home/agent"}, set()
            entry = ["--check"]
        else:
            env, hosts = provider_environment(args.provider, args.gh_user)
            entry = [args.model, prompt]
        temp_base = Path("/tmp/opencode") if Path("/tmp/opencode").is_dir() else None
        with tempfile.TemporaryDirectory(prefix="aks-bench-", dir=temp_base) as sockets:
            with Services(sockets, sim, hosts, directory / "proxy-events.jsonl"):
                name = "aks-bench-" + os.urandom(5).hex()
                command = container_command(args.engine, args.bwrap, Path(args.copilot).resolve(), Path(sockets), artifacts.resolve(), entry, env, name)
                start = time.monotonic()
                sim.started = start
                timeout = False
                with (directory / "copilot.stdout.jsonl").open("w") as stdout, (directory / "copilot.stderr.txt").open("w") as stderr:
                    process = subprocess.Popen(command, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
                    try:
                        returncode = process.wait(timeout=args.timeout)
                    except subprocess.TimeoutExpired:
                        timeout = True
                        os.killpg(process.pid, signal.SIGKILL)
                        returncode = process.wait()
                        if args.engine == "docker":
                            subprocess.run(["docker", "rm", "-f", name], capture_output=True)
                elapsed = time.monotonic() - start
        isolation_path = artifacts / "isolation.json"
        isolation = json.loads(isolation_path.read_text()) if isolation_path.exists() else {}
    sim.advance()
    state_grade = grade(scenario, sim.state)
    unsupported = sum(e["category"] == "coverage_gap" for e in sim.events)
    result = {"scenario": scenario["name"], "seed": seed, "skills": skills,
              "discovery": args.discovery, "mode": mode, "engine": args.engine if mode != "replay" else None,
              "requested_model": args.model if mode == "live" else None, "provider": args.provider if mode == "live" else None,
              "elapsed_s": elapsed, "time_to_goal_s": sim.first_goal_s,
              "time_to_verified_goal_s": sim.verified_goal_s, "timed_out": timeout,
              "agent_exit_code": returncode, "state_grade": state_grade,
              "success": state_grade["success"] and sim.verified_goal_s is not None and returncode == 0 and not timeout,
              "coverage_gaps": unsupported, "isolation": isolation,
              "valid_trial": mode == "live" and bool(isolation) and all(isolation.values()) and not unsupported,
              "tool_calls": len(sim.events), "az_calls": sum(e.get("tool", "az") == "az" for e in sim.events),
              "docs_mode": getattr(args, "docs_mode", "off"),
              "documentation_lookups": sum(e["category"] == "documentation" for e in sim.events),
              "documentation_http_requests": sum(e.get("documentation_http_requests", 0) for e in sim.events),
              "kubernetes_calls": sum(e.get("tool") == "kubectl" for e in sim.events),
              "skill_calls": sum(e["category"] == "skill" for e in sim.events),
              "skill_reads": sum(e["command"] == "aks skill show" and e["exit_code"] == 0 and not any(a in ("--help", "-h") for a in e["argv"]) for e in sim.events),
              "azure_cli_calls": sum(e["category"] == "azure" for e in sim.events),
              "modeled_api_requests": sum(e["modeled_api_requests"] for e in sim.events),
              "failed_az_calls": sum(e.get("tool", "az") == "az" and e["exit_code"] != 0 for e in sim.events),
              "failed_tool_calls": sum(e["exit_code"] != 0 for e in sim.events),
              **telemetry(artifacts / "otel.jsonl")}
    if mode == "live" and returncode != 0 and not sim.events:
        result["valid_trial"] = False
        result["harness_error"] = "agent failed before any az invocation; inspect stderr"
    json_file(directory / "final-state.json", sim.state)
    json_file(directory / "result.json", result)
    timeline(directory, sim.events)
    return result


def report(directory):
    results = [json.loads(p.read_text()) for p in sorted(Path(directory).glob("*/result.json"))]
    grouped = {}
    for r in results:
        key = (r["scenario"], r["requested_model"], r["provider"], r["discovery"], r["mode"], r.get("docs_mode", "off"))
        grouped.setdefault(key, []).append(r)
    summary = []
    for key, rows in grouped.items():
        item = {"scenario": key[0], "model": key[1], "provider": key[2], "discovery": key[3], "mode": key[4], "docs_mode": key[5]}
        for arm, flag in (("baseline", False), ("skills", True)):
            trials = [r for r in rows if r["skills"] == flag]
            valid = [r for r in trials if r["valid_trial"]]
            successes = [r for r in valid if r["success"]]
            item[arm] = {"trials": len(trials), "valid_trials": len(valid), "successes": len(successes),
                         "invalid_trials": len(trials) - len(valid), "failures": len(valid) - len(successes),
                         "timeouts": sum(r.get("timed_out", False) for r in valid),
                         "skill_adoption": sum(r.get("skill_reads", 0) > 0 for r in valid),
                         "documentation_lookups": sum(r.get("documentation_lookups", 0) for r in valid),
                         "documentation_http_requests": sum(r.get("documentation_http_requests", 0) for r in valid),
                         "kubernetes_calls": sum(r.get("kubernetes_calls", 0) for r in valid),
                         "success_rate": len(successes) / len(valid) if valid else None}
        pairs = []
        for seed in sorted({r["seed"] for r in rows}):
            paired = {r["skills"]: r for r in rows if r["seed"] == seed and r["valid_trial"] and r["success"]}
            if len(paired) == 2:
                baseline, treatment = paired[False], paired[True]
                pairs.append({metric: treatment[metric] - baseline[metric]
                              for metric in ("elapsed_s", "modeled_api_requests", "azure_cli_calls", "az_calls",
                                              "time_to_verified_goal_s", "llm_requests", "documentation_http_requests", "kubernetes_calls")
                              if treatment.get(metric) is not None and baseline.get(metric) is not None})
        item["successful_pairs"] = len(pairs)
        item["median_paired_delta_skills_minus_baseline"] = {
            metric: statistics.median(p[metric] for p in pairs if metric in p)
            for metric in ("elapsed_s", "modeled_api_requests", "azure_cli_calls", "az_calls",
                            "time_to_verified_goal_s", "llm_requests", "documentation_http_requests", "kubernetes_calls") if any(metric in p for p in pairs)
        } if pairs else None
        summary.append(item)
    json_file(Path(directory) / "summary.json", summary)
    lines = ["# AKS mock benchmark", "", "Negative paired deltas favor skills. API requests are modeled, not measured Azure traffic.",
             "Time deltas include the complete agent run. Failures are retained; deltas use successful matched pairs only.", "",
             "| Scenario | Mode | Baseline success/valid | Skills success/valid | Skill adoption | Successful pairs | Δ seconds | Δ modeled API |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    for r in summary:
        b, s, d = r["baseline"], r["skills"], r["median_paired_delta_skills_minus_baseline"]
        seconds = f"{d['elapsed_s']:.2f}" if d else "—"
        api = str(d["modeled_api_requests"]) if d else "—"
        lines.append(f"| {r['scenario']} | {r['mode']} | {b['successes']}/{b['valid_trials']} | {s['successes']}/{s['valid_trials']} | {s['skill_adoption']} | {r['successful_pairs']} | {seconds} | {api} |")
    lines.extend(["", "Replay rows validate the harness only; they are not agent benchmark results.",
                  "A smoke trial is not enough to establish a reliable improvement. Inspect result.json, traces and failures."])
    (Path(directory) / "summary.md").write_text("\n".join(lines) + "\n")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="Stateful, isolated AKS skill benchmark")
    parser.add_argument("action", choices=("run", "replay", "check", "report", "coverage"))
    parser.add_argument("--output", type=Path, default=Path("benchmark-results") / time.strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--model", default="gpt-6.1-sol")
    parser.add_argument("--provider", choices=("copilot", "foundry"), default="copilot")
    parser.add_argument("--gh-user", help="GitHub CLI account used for the container's Copilot token")
    parser.add_argument("--engine", choices=("bwrap", "docker"), default="bwrap")
    parser.add_argument("--bwrap", default=shutil.which("bwrap") or "bwrap")
    parser.add_argument("--copilot", default=shutil.which("copilot") or "copilot")
    parser.add_argument("--scenarios", nargs="+", choices=NAMES, default=list(NAMES))
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--latency-scale", type=float, default=1)
    parser.add_argument("--discovery", choices=("passive",), default="passive",
                        help="Discovery-only: both arms receive identical task prompts")
    parser.add_argument("--fixture", help="Use a complete custom scenario JSON instead of generated fixtures")
    parser.add_argument("--docs-mode", choices=("live", "off"), default="live",
                        help="Allow logged GET-only Microsoft Learn access through the container curl tool")
    args = parser.parse_args(argv)
    if args.repeats < 1 or args.timeout <= 0 or args.latency_scale < 0:
        parser.error("repeats/timeout must be positive and latency-scale nonnegative")
    if args.fixture and len(args.scenarios) != 1:
        parser.error("--fixture requires exactly one --scenarios entry")
    if args.action == "coverage":
        print(json.dumps({"recognized": len(COMMANDS), "semantic": sorted(SEMANTIC),
                          "fixture_required": sorted(set(COMMANDS) - SEMANTIC)}, indent=2))
        return 0
    if args.action == "report":
        print(json.dumps(report(args.output), indent=2))
        return 0
    args.output = args.output.resolve()
    if args.output.exists():
        parser.error("output directory already exists; choose a fresh directory or use report")
    args.output.mkdir(parents=True)
    metadata = {"model": args.model, "provider": args.provider, "engine": args.engine,
                "discovery": args.discovery, "repeats": args.repeats, "seed": args.seed,
                "latency_scale": args.latency_scale, "docs_mode": args.docs_mode, "created_at": time.time(),
                "command_manifest_sha256": hashlib.sha256((ROOT / "commands.json").read_bytes()).hexdigest()}
    metadata["source_sha256"] = hashlib.sha256(b"".join(
        str(p.relative_to(ROOT)).encode() + p.read_bytes()
        for p in sorted(ROOT.rglob("*")) if p.is_file() and p.suffix in (".py", ".json", ".md")
    )).hexdigest()
    metadata["skill_cli_sha256"] = hashlib.sha256(b"".join(
        p.read_bytes() for p in [ROOT.parent / "bin" / "az", *sorted((ROOT.parent / "src").rglob("*.py"))]
    )).hexdigest()
    if args.fixture:
        metadata["fixture_sha256"] = hashlib.sha256(Path(args.fixture).read_bytes()).hexdigest()
    if args.action != "replay":
        metadata["copilot_version"] = subprocess.check_output([args.copilot, "--version"], text=True).strip()
    try:
        metadata["git_revision"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        metadata["git_dirty"] = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT))
    except subprocess.CalledProcessError:
        metadata["git_revision"] = None
    json_file(args.output / "run.json", metadata)
    if args.action == "check":
        result = trial(args, args.scenarios[0], args.seed, False, args.output / "isolation", mode="check")
        print(json.dumps(result["isolation"], indent=2))
        return 0 if result["isolation"] and all(result["isolation"].values()) else 1
    mode = "replay" if args.action == "replay" else "live"
    invalid = False
    rng = random.Random(args.seed)
    for repeat in range(args.repeats):
        for scenario in args.scenarios:
            arms = [False, True]
            rng.shuffle(arms)
            for skills in arms:
                label = f"{scenario}-{args.seed + repeat}-{'skills' if skills else 'baseline'}"
                print(f"Starting {label} ({mode}, {args.model})", flush=True)
                result = trial(args, scenario, args.seed + repeat, skills, args.output / label, mode=mode)
                invalid = invalid or (mode == "live" and not result["valid_trial"])
                print(json.dumps({k: result[k] for k in ("success", "valid_trial", "elapsed_s", "az_calls", "skill_calls", "modeled_api_requests")}), flush=True)
                report(args.output)
    print(f"Report: {args.output / 'summary.md'}")
    return 1 if invalid else 0
