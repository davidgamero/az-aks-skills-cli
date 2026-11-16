"""Audit failure schedules without rerunning models or changing original outcomes."""

import argparse
import json
from pathlib import Path
import re
import subprocess

from aks_bench.error_ladder import FailureGate, report


def audit_schedule(events, config):
    gate=FailureGate(**config)
    violations=[]
    for event in events:
        expected=gate.next(event.get("tool","az"),event["argv"])
        recorded=event.get("failure_gate")
        if bool(expected and expected["injected"]) != bool(recorded and recorded["injected"]):
            violations.append({"sequence":event["sequence"],"argv":event["argv"],"expected":expected,"recorded":recorded})
        if recorded and recorded["injected"] and event["state_before"]!=event["state_after"]:
            violations.append({"sequence":event["sequence"],"reason":"injected error changed resource state"})
        if event.get("discovery_hint"):
            violations.append({"sequence":event["sequence"],"reason":"contextual hint in help-only experiment"})
    return violations


def visible_tool_audit(path):
    """Inspect model-requested tools, never private reasoning or authentication."""
    starts=[];exposures=[]
    for line in path.read_text().splitlines() if path.exists() else []:
        try: event=json.loads(line)
        except ValueError: continue
        data=event.get("data",{})
        if event.get("type")=="tool.execution_start":
            arguments=data.get("arguments",{})
            if re.search(r"\bskills?\b",json.dumps(arguments),re.I):
                starts.append({"timestamp":event.get("timestamp"),"name":data.get("toolName"),"arguments":arguments})
        if event.get("type")=="tool.execution_complete":
            content=data.get("result",{}).get("content","")
            if "az aks skill :" in content or "Find and print AKS skills and troubleshooting instructions" in content:
                exposures.append({"timestamp":event.get("timestamp"),"tool_call_id":data.get("toolCallId")})
    return {"skill_related_tool_requests":starts,"completed_results_advertising_skills":exposures}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs",nargs="+",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    rows=[]
    for root in args.runs:
        for path in sorted(root.glob("*/result.json")):
            original=json.loads(path.read_text());config=original["failure_experiment"]["failure_config"]
            events=[json.loads(line) for line in (path.parent/"az-events.jsonl").read_text().splitlines()]
            violations=audit_schedule(events,config)
            row={**original,"original_valid_trial":original["valid_trial"],"valid_trial":original["valid_trial"] and not violations,
                 "schedule_audit":{"violations":violations},"tool_audit":visible_tool_audit(path.parent/"copilot.stdout.jsonl"),
                 "audit_kind":"schedule-and-visible-tool-audit-no-new-inference","original_trial":str(path.parent)}
            target=args.output/path.parent.name
            target.mkdir(exist_ok=False);(target/"result.json").write_text(json.dumps(row,indent=2)+"\n")
            rows.append(row)
    report(args.output,rows)
    metadata={"original_runs":[str(p) for p in args.runs],"audit_revision":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
              "audit_git_dirty":bool(subprocess.check_output(["git","status","--porcelain"],text=True)),"trials":len(rows),"new_inference_trials":0}
    (args.output/"audit.json").write_text(json.dumps(metadata,indent=2)+"\n")
    print(json.dumps({**metadata,"audited_valid":sum(r["valid_trial"] for r in rows),"schedule_invalid":sum(bool(r["schedule_audit"]["violations"]) for r in rows)},indent=2))


if __name__=="__main__": main()
