"""Explicit current-rubric audit of unchanged live evidence; preserves original results."""

import argparse
import json
from pathlib import Path
import subprocess

from aks_bench.scenarios import make, grade
from aks_bench.investigation_report import report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    rows=[]
    for path in sorted(args.run.glob("*/result.json")):
        original=json.loads(path.read_text());old=json.loads((path.parent/"scenario.json").read_text())
        state=json.loads((path.parent/"final-state.json").read_text())
        if old.get("suite")!="investigation-v1": raise ValueError("only investigation trials can be audited")
        current=make(old["name"],old["seed"])
        # A scoring-only audit cannot silently change evidence, task or starting state.
        for field in ("prompt","context","initial_state"):
            if old[field]!=current[field]: raise ValueError("fixture changed: "+field)
        for field in ("resources","facts"):
            if old["investigation"][field]!=current["investigation"][field]: raise ValueError("evidence changed: "+field)
        checks=grade(current,state)
        row={**original,"original_success":original["success"],"original_state_grade":original["state_grade"],
             "state_grade":checks,"success":checks["success"] and original["agent_exit_code"]==0 and not original["timed_out"],
             "final_verification_complete":checks["success"],"audit_kind":"current-rubric-no-new-inference"}
        # Keep coverage/isolation validity unchanged, even if a new grader accepts a report.
        target=args.output/path.parent.name;target.mkdir();(target/"result.json").write_text(json.dumps(row,indent=2)+"\n")
        rows.append(row)
    metadata={"original_run":str(args.run),"audit_revision":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
              "audit_git_dirty":bool(subprocess.check_output(["git","status","--porcelain"],text=True)),
              "trials":len(rows),"new_inference_trials":0}
    (args.output/"audit.json").write_text(json.dumps(metadata,indent=2)+"\n")
    report(args.output,rows)
    print(json.dumps(metadata,indent=2))


if __name__=="__main__":main()
