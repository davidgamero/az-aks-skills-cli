"""Three-condition discovery report; retains invalid trials and matched seeds."""

import json
from pathlib import Path
import statistics


def report(directory, results):
    groups={}
    for r in results:
        key=(r["scenario"],r["requested_model"],r["provider"],r["mode"],r.get("docs_mode"))
        groups.setdefault(key,[]).append(r)
    summary=[]
    for key,rows in sorted(groups.items()):
        item={"scenario":key[0],"model":key[1],"provider":key[2],"mode":key[3],"docs_mode":key[4]}
        for condition in ("baseline","help","contextual"):
            trials=[r for r in rows if r["condition"]==condition];valid=[r for r in trials if r["valid_trial"]]
            item[condition]={"trials":len(trials),"valid":len(valid),"successes":sum(r["success"] for r in valid),
                "invalid":len(trials)-len(valid),"skill_read_trials":sum(r["skill_reads"]>0 for r in valid),
                "exposed_trials":sum(r.get("hint_exposures",0)+r.get("skill_help_exposures",0)>0 for r in valid),
                "all_skill_read_trials":sum(r["skill_reads"]>0 for r in trials),
                "median_elapsed_s":statistics.median(r["elapsed_s"] for r in valid if r["success"]) if any(r["success"] for r in valid) else None}
        pairs=[]
        for seed in sorted({r["seed"] for r in rows}):
            by={r["condition"]:r for r in rows if r["seed"]==seed and r["valid_trial"] and r["success"]}
            if all(c in by for c in ("help","contextual")):
                pairs.append({"seed":seed,**{k:by["contextual"][k]-by["help"][k] for k in ("elapsed_s","llm_requests","tool_calls")}})
        item["contextual_minus_help_successful_pairs"]=pairs
        summary.append(item)
    path=Path(directory);(path/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    lines=["# Investigation discovery comparison","","B = no skills; H = AKS-help discovery; C = contextual diagnostic references plus help.",
        "Prompts and evidence are identical. Invalid trials are excluded from success comparisons and retained below.","",
        "| Scenario | Valid successes B/H/C | Invalid B/H/C | Reads H/C (valid) | Exposure H/C (valid) |",
        "|---|---|---|---|---|"]
    for row in summary:
        counts=" / ".join(f"{row[c]['successes']}/{row[c]['valid']}" for c in ("baseline","help","contextual"))
        invalid=" / ".join(str(row[c]["invalid"]) for c in ("baseline","help","contextual"))
        lines.append(f"| {row['scenario']} | {counts} | {invalid} | {row['help']['skill_read_trials']}/{row['contextual']['skill_read_trials']} | {row['help']['exposed_trials']}/{row['contextual']['exposed_trials']} |")
    lines += ["","One seed is a smoke test. Retrieval does not by itself establish content benefit. Evidence scoring is structural, not a semantic review of causal prose."]
    (path/"summary.md").write_text("\n".join(lines)+"\n")
    return summary
