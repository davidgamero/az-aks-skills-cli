"""Freeze experimental inputs and compare baseline/original/revised catalogs."""

import hashlib
import json
from pathlib import Path
import shutil
import statistics

from .mock import ROOT  # Also makes the production skill package importable.
from az_aks_skills_cli.catalog import Catalog


def fingerprint(directory):
    catalog = Catalog(Path(directory))
    paths = {"index.json": catalog.root / "index.json"}
    paths.update({str(Path(skill["path"])): catalog.document_path(skill) for skill in catalog.skills})
    digest = hashlib.sha256()
    for relative, path in sorted(paths.items()):
        digest.update(relative.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def freeze(source, destination):
    catalog = Catalog(Path(source))
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    paths = [Path("index.json"), *(Path(skill["path"]) for skill in catalog.skills)]
    for relative in paths:
        if ".." in relative.parts:
            raise ValueError("snapshot catalog paths must not contain '..'")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(catalog.root / relative, target)
    return fingerprint(destination)


METRICS = ("elapsed_s", "time_to_verified_goal_s", "modeled_api_requests", "llm_requests", "skill_calls", "skill_reads")


def comparison_report(directory, results):
    grouped = {}
    for row in results:
        key = (row["scenario"], row["requested_model"], row["provider"], row["discovery"], row["docs_mode"])
        grouped.setdefault(key, []).append(row)
    summaries = []
    for key, rows in grouped.items():
        item = {"scenario": key[0], "model": key[1], "provider": key[2], "discovery": key[3], "docs_mode": key[4]}
        by_seed = {}
        for row in rows:
            condition = row["condition"]
            group = by_seed.setdefault(row["seed"], {})
            if condition in group:
                raise ValueError("duplicate condition/seed in catalog comparison")
            group[condition] = row
        for condition in ("baseline", "original", "revised"):
            trials = [r for r in rows if r["condition"] == condition]
            hashes = {r.get("catalog_sha256") for r in trials}
            if len(hashes) > 1:
                raise ValueError(f"mixed catalog hashes for {condition}")
            valid = [r for r in trials if r["valid_trial"]]
            successful = [r for r in valid if r["success"]]
            item[condition] = {
                "trials": len(trials), "valid_trials": len(valid), "successes": len(successful),
                "failures": len(valid) - len(successful), "invalid_trials": len(trials) - len(valid),
                "skill_adoption": sum(r["skill_reads"] > 0 for r in valid),
                "catalog_sha256": next(iter(hashes), None),
                "successful_medians": {metric: statistics.median(r[metric] for r in successful if r.get(metric) is not None)
                                       for metric in METRICS if any(r.get(metric) is not None for r in successful)},
            }
        for reference in ("original", "baseline"):
            pairs = [(block[reference], block["revised"]) for block in by_seed.values()
                     if reference in block and "revised" in block
                     and all(block[c]["valid_trial"] and block[c]["success"] for c in (reference, "revised"))]
            item[f"revised_minus_{reference}"] = {
                "successful_pairs": len(pairs),
                "both_read_skills": sum(a["skill_reads"] > 0 and b["skill_reads"] > 0 for a, b in pairs),
                "paired_deltas": [{"seed": a["seed"], **{m: b[m] - a[m] for m in METRICS if a.get(m) is not None and b.get(m) is not None}}
                                  for a, b in pairs],
                "median_delta": {m: statistics.median(b[m] - a[m] for a, b in pairs if a.get(m) is not None and b.get(m) is not None)
                                 for m in METRICS if any(a.get(m) is not None and b.get(m) is not None for a, b in pairs)},
            }
        summaries.append(item)
    directory = Path(directory)
    (directory / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")
    lines = ["# Catalog comparison", "", "Each seed uses identical prompts and state. Conditions are interleaved in seeded random order.",
             "Time deltas use successful matched pairs only; failures and invalid runs are retained in JSON.",
             "Medians below are descriptive, not statistical significance. Unread skills cannot explain content benefits.", "",
             "| Scenario | Valid successes B/O/R | Skill adoption O/R | Median seconds B/O/R | Paired Δ revised−original |",
             "|---|---|---|---|---:|"]
    for item in summaries:
        counts = "; ".join(f"{item[c]['successes']}/{item[c]['valid_trials']}" for c in ("baseline", "original", "revised"))
        times = " / ".join(f"{item[c]['successful_medians']['elapsed_s']:.2f}" if "elapsed_s" in item[c]["successful_medians"] else "—"
                           for c in ("baseline", "original", "revised"))
        delta = item["revised_minus_original"]["median_delta"].get("elapsed_s")
        formatted_delta = f"{delta:+.2f}" if delta is not None else "—"
        lines.append(f"| {item['scenario']} | {counts} | {item['original']['skill_adoption']}/{item['revised']['skill_adoption']} | {times} | {formatted_delta} |")
    (directory / "summary.md").write_text("\n".join(lines) + "\n")
    return summaries
