"""Build the public master list; summarize explicit live inputs, never raw artifacts."""

import argparse
import json
from pathlib import Path
import statistics
from collections import Counter

from aks_bench.scenarios import NAMES
from aks_bench.procedures import NAMES as PROCEDURES
from aks_bench import candidate_fixtures, investigations

ROOT=Path(__file__).resolve().parents[1]


def metrics(rows):
    result={}
    for arm in ("baseline","help","contextual"):
        trials=[r for r in rows if r["condition"]==arm];valid=[r for r in trials if r["valid_trial"]];ok=[r for r in valid if r["success"]]
        measured=("elapsed_s","tool_calls","llm_requests")+(("agent_tool_calls",) if ok and all("agent_tool_calls" in r for r in ok) else ())
        result[arm]={"trials":len(trials),"valid":len(valid),"successes":len(ok),"invalid":len(trials)-len(valid),
            "read_trials":sum(r["skill_reads"]>0 for r in valid),
            "criterion_successes":{k:sum(r["state_grade"]["checks"].get(k,False) for r in valid) for k in sorted({k for r in valid for k in r["state_grade"]["checks"]})},
            "documentation_attempts":sum(r.get("native_web_tool_attempts",0)+r.get("documentation_lookups",0) for r in valid),
            "median_successful":{k:statistics.median(r[k] for r in ok) for k in measured} if ok else {}}
    for arm in ("help","contextual"):
        pairs=[]
        for seed in sorted({r["seed"] for r in rows}):
            by={r["condition"]:r for r in rows if r["seed"]==seed and r["valid_trial"] and r["success"]}
            if arm in by and "baseline" in by:
                names=("elapsed_s","tool_calls","llm_requests")+(("agent_tool_calls",) if all("agent_tool_calls" in by[c] for c in (arm,"baseline")) else ())
                pairs.append({"seed":seed,**{k:by[arm][k]-by["baseline"][k] for k in names}})
        result[arm+"_minus_baseline"]={"successful_pairs":len(pairs),"deltas":pairs,
            "median":{k:statistics.median(p[k] for p in pairs if k in p) for k in ("elapsed_s","tool_calls","llm_requests","agent_tool_calls") if any(k in p for p in pairs)} if pairs else {}}
    return result


def build(run_paths=()):
    plan=json.loads((ROOT/"docs/research/procedure-candidates.json").read_text())
    definitions={r["id"]:r for r in plan["candidates"]}
    source_index=json.loads((ROOT/"docs/research/aks-source-index.json").read_text())
    legacy_sources={r["id"]:r["url"] for r in source_index["sources"]}
    groups={};run_metadata=[];configuration=None
    for path in run_paths:
        metadata=json.loads((path/"run.json").read_text())
        if metadata.get("action")!="discover":raise ValueError("only explicit discover live runs are supported")
        identity=tuple(metadata.get(k) for k in ("model","provider","engine","docs_mode","catalog_sha256"))
        if configuration is not None and configuration!=identity:raise ValueError("cannot pool different model/provider/engine/docs/catalog configurations")
        configuration=identity
        run_metadata.append({"directory":str(path),"revision":metadata.get("git_revision"),"source_sha256":metadata["source_sha256"],"catalog_sha256":metadata["catalog_sha256"],"model":metadata["model"]})
        local={}
        for result_path in path.glob("*/result.json"):
            row=json.loads(result_path.read_text())
            if row.get("mode")!="live":raise ValueError("replay/audit is not a new live trial")
            output=result_path.parent/"copilot.stdout.jsonl"
            if output.exists():
                tools={}
                for line in output.read_text().splitlines():
                    try:event=json.loads(line)
                    except ValueError:continue
                    if event.get("type")=="tool.execution_start":
                        payload=event.get("data",{});tools[payload.get("toolCallId",event.get("id"))]=payload.get("toolName","unknown")
                row["agent_tool_calls"]=len(tools);row["agent_tool_counts"]=dict(Counter(tools.values()))
            local.setdefault((row["scenario"],row["seed"]),[]).append({**row,"source_run":str(path)})
        for key,rows in local.items():
            if len(rows)!=3 or {r["condition"] for r in rows}!={"baseline","help","contextual"}:raise ValueError("incomplete/duplicate three-arm group")
            # Last explicitly supplied group wins as a whole, including invalid or
            # failed rows. Never select individual winning arms across revisions.
            groups[key]=rows
    trial_rows=[row for rows in groups.values() for row in rows]
    entries=[]
    for name in sorted(set(NAMES)|set(definitions)):
        if name in definitions:
            row=definitions[name]
            entry={**row,"sources":[plan["sources"][k] for k in row["source_ids"]],"runnable":name in NAMES,
                   "evaluation_status":"not_live_evaluated" if name in NAMES else "design_only"}
            rows=[r for r in trial_rows if r["scenario"]==name]
            if rows:entry.update(evaluation_status="live_smoke_evaluated",comparison=metrics(rows),selected_groups=[{"seed":seed,"source_run":group[0]["source_run"]} for (scenario,seed),group in sorted(groups.items()) if scenario==name])
        else:
            candidate=candidate_fixtures.DEFINITIONS.get(name)
            entry={"id":name,"topic":candidate["topic"] if candidate else "investigation" if name in investigations.NAMES else "operational-control",
                "runnable":True,"build_status":"implemented","evaluation_status":"historical_evidence_not_pooled",
                "missing_procedure":candidate["decision_boundary"] if candidate else "Existing bounded task; retain as a control and consult its historical report rather than inferring a new procedural gap.",
                "sources":[legacy_sources[k] for k in candidate["source_ids"] if k in legacy_sources] if candidate else [],
                "historical_reports":["docs/candidate-evaluation.md"] if candidate else ["docs/investigation-discovery.md"] if name in investigations.NAMES else ["docs/benchmark.md"],
                "priority":"control"}
        entries.append(entry)
    return {"schema_version":1,"reviewed_on":"2026-11-17","runnable_scenarios":len(NAMES),"designed_only":sum(not e["runnable"] for e in entries),
        "notes":"One registry, not one pooled statistical study. New comparison rows only summarize explicitly supplied live runs; historical trials remain separate. No positive content claim when skills were unread.",
        "selection_rule":"Last explicitly supplied run replaces the complete scenario/seed group, never individual arms; invalids and failures retained.","new_wave_runs":run_metadata,"scenarios":entries}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs",nargs="*",type=Path,default=[])
    parser.add_argument("--json",type=Path,default=ROOT/"docs/research/master-scenarios.json")
    parser.add_argument("--markdown",type=Path,default=ROOT/"docs/master-scenarios.md")
    args=parser.parse_args();data=build(args.runs)
    args.json.write_text(json.dumps(data,indent=2)+"\n")
    lines=["# Master AKS skill-comparison scenario list","",f"**{len(data['scenarios'])} scenarios: {data['runnable_scenarios']} runnable, {data['designed_only']} designed-only.**",
        "","This is a research/evaluation registry, not a frequency ranking or a claim that every task needs skills.",
        "New guide-derived cases are documented in [procedure comparison](procedure-comparison.md). Historical evidence is not pooled into the new study.",
        "","## Guide-derived procedure candidates","","| Scenario | Topic | Status | Specific procedure to test |","|---|---|---|---|"]
    for entry in data["scenarios"]:
        if entry["id"] in {e["id"] for e in json.loads((ROOT/"docs/research/procedure-candidates.json").read_text())["candidates"]}:
            lines.append(f"| `{entry['id']}` | {entry['topic']} | {entry['evaluation_status']} | {entry['missing_procedure']} |")
    measured=[e for e in data["scenarios"] if "comparison" in e]
    if measured:
        lines += ["","## Explicit new live comparisons","","B/H/C = baseline / help-only / contextual. Medians use successful valid trials only; failures/invalids remain in JSON. Small development/replication samples are descriptive, not statistical significance. Use paired deltas in JSON rather than subtracting medians from different valid-seed sets.",
            "","| Scenario | Rubric pass/valid B/H/C | Reads H/C | Seconds B/H/C | CLI calls B/H/C | Model spans B/H/C |","|---|---|---|---|---|---|"]
        for e in measured:
            c=e["comparison"];arms=("baseline","help","contextual")
            values=[" / ".join(f"{c[a]['successes']}/{c[a]['valid']}" for a in arms),f"{c['help']['read_trials']}/{c['contextual']['read_trials']}"]
            for k in ("elapsed_s","tool_calls","llm_requests"):
                values.append(" / ".join(f"{c[a]['median_successful'][k]:.1f}" if k in c[a]["median_successful"] else "—" for a in arms))
            lines.append(f"| `{e['id']}` | "+" | ".join(values)+" |")
        lines += ["","Backup's full rubric includes agreement with the pinned support matrix's stated RPO. All arms may classify volumes correctly while differing on that bound; consult the criterion counts and the comparison report before treating full-rubric passes as a general correctness improvement.",
            "Multiple run directories are selected in the explicit order supplied, replacing complete scenario/seed groups including failures/invalids. Historical development runs are not silently pooled."]
    lines += ["","## Existing controls and historical scenarios","","| Scenario | Topic | Historical report |","|---|---|---|"]
    for e in data["scenarios"]:
        if "historical_reports" in e:lines.append(f"| `{e['id']}` | {e['topic']} | "+", ".join(f"[{p.rsplit('/',1)[-1]}]({p.removeprefix('docs/')})" for p in e["historical_reports"])+" |")
    lines += ["","The [JSON registry](research/master-scenarios.json) includes source URLs, negative controls, holdout ideas, run revisions and measured deltas when available.",
        "Regenerate with `PYTHONPATH=bench .venv-bench/bin/python bench/master_scenarios.py --runs LIVE_RUN_DIRECTORY`. Do not pass an audit-only directory as a fresh live run."]
    args.markdown.write_text("\n".join(lines)+"\n")
    print(f"Wrote {len(data['scenarios'])} master entries ({data['runnable_scenarios']} runnable).")


if __name__=="__main__":main()
