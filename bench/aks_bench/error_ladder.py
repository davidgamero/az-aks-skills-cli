"""Deterministic call-boundary failures and observational skill-fallback metrics."""

from collections import Counter
import json
from pathlib import Path
import statistics
import argparse

KINDS = ("arm503", "cli_error")
DEFAULT_COUNTS = (0, 1, 2, 3, 5, 8, -1)


class FailureGate:
    """One shared prefix budget per trial, not per spelling or output flag.

    First N eligible Azure invocations fail; subsequent ones dispatch normally.
    N=-1 never recovers. No wall-clock recovery or hidden real SDK traffic.
    """

    def __init__(self, kind, failures):
        if kind not in KINDS or not isinstance(failures, int) or failures < -1:
            raise ValueError("invalid error ladder configuration")
        self.kind, self.failures, self.attempts = kind, failures, 0

    def eligible(self, tool, argv):
        if tool != "az" or not argv or any(a in ("--help", "-h", "--version") for a in argv):
            return False
        from .candidate_runtime import parse, WorldError
        try: words, _, _ = parse([a for a in argv if a not in ("--debug","--verbose")], "az")
        except (ValueError, WorldError): return False
        if not words or words[0] in ("account", "version", "configure", "extension"):
            return False
        if words[:2] in (["aks", "skill"], ["aks", "skills"]):
            return False
        # Groups are local usage, not Azure operations. Unknown groups retain the
        # simulator's coverage classification rather than being hidden by injection.
        if words in (["aks"], ["aks", "nodepool"], ["aks", "namespace"]):
            return False
        roots = {"aks", "monitor", "network", "vm", "vmss", "provider", "group", "deployment", "resource", "identity", "role", "acr", "keyvault", "rest"}
        return words[0] in roots and (len(words) > 1 or words[0] == "rest")

    def next(self, tool, argv):
        if not self.eligible(tool, argv): return None
        self.attempts += 1
        return {"kind": self.kind, "configured_failures": self.failures,
                "eligible_attempt": self.attempts,
                "injected": self.failures == -1 or self.attempts <= self.failures}

    def response(self):
        if self.kind == "arm503":
            return {"stdout": "", "stderr": "ERROR: (ServiceUnavailable) The service is temporarily unavailable. HTTP status: 503. Retry-After: 1 second.\n", "exit_code": 1}
        return {"stdout": "", "stderr": "ERROR: The command failed with an unexpected error. Here is the traceback:\nTraceback (most recent call last):\n  File \"azure/cli/core/commands/__init__.py\", line 1, in execute\nKeyError: 'response'\n", "exit_code": 1}


def metrics(events, config):
    """No retrieval => threshold unobserved, never substituted with retry count."""
    count = 0
    all_errors = 0
    first_help = first_seek = first_read = None
    first_recovery = None
    failed_commands = Counter()
    longest = streak = 0
    for event in events:
        fault = event.get("failure_gate")
        if fault and fault["injected"]:
            count += 1
            streak += 1
            longest = max(longest, streak)
            failed_commands[event.get("command", "")] += 1
        elif fault:
            streak = 0
            if first_recovery is None and event["exit_code"] == 0:
                first_recovery = fault["eligible_attempt"]
        if event["exit_code"]: all_errors += 1
        argv = event["argv"]
        item = {"sequence": event["sequence"], "time_s": event["end_s"], "injected_errors_before": count,
                "all_tool_errors_before": all_errors-int(bool(event["exit_code"])), "recovery_already_observed": first_recovery is not None}
        if event.get("tool", "az") == "az" and argv[:1] == ["aks"] and any(a in ("--help", "-h") for a in argv) and event["exit_code"] == 0:
            if first_help is None: first_help = item
        is_skill = event.get("tool", "az") == "az" and argv[:2] in (["aks", "skill"], ["aks", "skills"])
        if is_skill and first_seek is None: first_seek = item
        if is_skill and event["command"] == "aks skill show" and not any(a in ("--help", "-h") for a in argv) and event["exit_code"] == 0:
            if first_read is None: first_read = item
    return {"failure_config": config, "injected_failures_observed": count,
            "eligible_attempts": sum(bool(e.get("failure_gate")) for e in events),
            "first_eligible_success_attempt": first_recovery,
            "longest_failed_eligible_streak": longest,
            "failed_command_families": dict(failed_commands),
            "first_aks_help": first_help, "first_skill_seek": first_seek, "first_skill_read": first_read,
            "skill_fallback_observed": bool(first_read and first_read["injected_errors_before"] > 0),
            "threshold_status": "observed_read" if first_read else "not_observed_before_trial_end",
            "failure_budget_exhausted": config["failures"] >= 0 and count == config["failures"]}


def report(directory, results):
    groups = {}
    for row in results:
        config = row["failure_experiment"]["failure_config"]
        key = (row["scenario"], row["requested_model"], row["provider"], row.get("docs_mode"), config["kind"], config["failures"])
        groups.setdefault(key, []).append(row)
    summary = []
    for key, rows in sorted(groups.items()):
        scenario, model, provider, docs_mode, kind, failures = key
        item = {"scenario": scenario, "model": model, "provider": provider, "docs_mode": docs_mode,
                "kind": kind, "configured_failures": failures, "recovery_eligible_attempt": failures+1 if failures >= 0 else None}
        for condition in ("baseline", "help"):
            trials = [r for r in rows if r["condition"] == condition]
            valid = [r for r in trials if r["valid_trial"]]
            item[condition] = {"trials": len(trials), "valid_trials": len(valid), "invalid_trials": len(trials)-len(valid),
                "successes": sum(r["success"] for r in valid),
                "help_trials": sum(r["failure_experiment"]["first_aks_help"] is not None for r in valid),
                "skill_seek_trials": sum(r["failure_experiment"]["first_skill_seek"] is not None for r in valid),
                "skill_read_trials": sum(r["failure_experiment"]["first_skill_read"] is not None for r in valid),
                "observed_failures": [r["failure_experiment"]["injected_failures_observed"] for r in valid],
                "errors_before_reads": [r["failure_experiment"]["first_skill_read"]["injected_errors_before"] for r in valid if r["failure_experiment"]["first_skill_read"]],
                "median_elapsed_s": statistics.median(r["elapsed_s"] for r in valid) if valid else None}
        item["live_seeds"] = sorted({r["seed"] for r in rows})
        summary.append(item)
    directory = Path(directory)
    (directory/"summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    lines = ["# Consecutive-error skill fallback experiment", "",
        "Only normal AKS help advertises skills. Injected error text never mentions skills. No contextual references or prompt hints.",
        "Attempts are modeled CLI invocations, not SDK HTTP retries or independent model decisions. Missing reads are censored observations, not a threshold.", "",
        "| Task | Error | Fail first | Recovery call | Success/valid B/H | Help B/H | Skill seeks B/H | Skill reads H | Failures observed H |",
        "|---|---|---:|---:|---|---|---|---:|---|"]
    for r in summary:
        b,h = r["baseline"],r["help"]
        lines.append(f"| {r['scenario']} | {r['kind']} | {r['configured_failures']} | {r['recovery_eligible_attempt'] or 'never'} | {b['successes']}/{b['valid_trials']} / {h['successes']}/{h['valid_trials']} | {b['help_trials']}/{h['help_trials']} | {b['skill_seek_trials']}/{h['skill_seek_trials']} | {h['skill_read_trials']} | {h['observed_failures']} |")
    lines += ["", "B = unavailable skills; H = skills available via normal AKS help. Replay is not agent evidence. Invalid runs remain in result files and counts."]
    (directory/"summary.md").write_text("\n".join(lines)+"\n")
    return summary


def run_matrix(args, rng, catalog, trial, render):
    jobs = [(scenario,kind,count,args.seed+repeat) for repeat in range(args.repeats)
            for scenario in args.scenarios for kind in args.failure_kinds for count in args.failure_counts]
    rng.shuffle(jobs)
    invalid = False
    for scenario,kind,count,seed in jobs:
        arms = [("baseline",False),("help",True)]
        rng.shuffle(arms)
        for condition,skills in arms:
            label=f"{scenario}-{seed}-{kind}-f{count if count>=0 else 'persistent'}-{condition}"
            print(f"Starting {label} (live, {args.model})",flush=True)
            trial_args=argparse.Namespace(**vars(args))
            trial_args.skills_dir,trial_args.condition,trial_args.hint_policy=catalog,condition,"help"
            trial_args.failure_config={"kind":kind,"failures":count}
            result=trial(trial_args,scenario,seed,skills,args.output/label,mode="live")
            invalid=invalid or not result["valid_trial"]
            print(json.dumps({k:result[k] for k in ("success","valid_trial","elapsed_s","skill_reads","failure_experiment")}),flush=True)
            render(args.output)
    print(f"Report: {args.output/'summary.md'}")
    return int(invalid)
