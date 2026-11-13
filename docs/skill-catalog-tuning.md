# Skill content tuning experiment

## What each benchmark skill covers

| Skill ID | Task | Successful endpoint |
|---|---|---|
| `aks-fixed-capacity` | Set a fixed node count; handle autoscaler conflicts and throttling | Requested count, autoscaling off, other pools preserved |
| `aks-autoscaler` | Enable or update pool autoscaler bounds | Correct enabled flag and min/max; no forced scale to MAX |
| `aks-control-plane-upgrade` | Upgrade only the control plane | Requested supported version; pool versions unchanged |
| `aks-stop-start` | Stop or restart a supported cluster | Requested power state and Succeeded provisioning |
| `aks-automatic-create` | Create Automatic with managed defaults | Correct SKU/tier, hosted system, NAP and upgrade channels |
| `aks-automatic-maintenance` | Change Kubernetes and node-image schedules | Correct two child resources, default window preserved |
| `aks-debug-version-skew` | Repair pool/control-plane version incompatibility | Correct upgrade order, repaired pool, other pools preserved |
| `aks-debug-provider` | Repair missing provider registration during Automatic creation | Required provider registered; original creation completed |
| `aks-debug-managed-quota` | Repair a quota-blocked workload in an ARM-managed namespace | Approved quota and ready replicas, other settings preserved |

These are the nine experimental documents under `bench/skills/`. The standalone
shim has a separate catalog under `skills/`, including the original upgrade-plan,
pod-diagnostics and node-pool-inventory examples.

## Content changes being tested

- Start from recent scope-matching observations rather than rereading them.
- After decisions are made, batch dependent writes and a final read with `&&`.
  A failing command stops the sequence for reassessment.
- Use one response to verify multiple fields when it actually contains them.
  For example, aks show includes pool profiles; maintenance resources require
  their own list; deployment readiness requires a Kubernetes observation.
- Make provider/version-skew recovery self-contained so a second skill is not
  needed merely to find the remainder of the same procedure.
- Keep diagnosis conditional: investigate the observed failure, not every possible
  AKS subsystem after the cause has already been established.
- Preserve authorization, prerequisites, readiness checks and unrelated-resource
  invariants. No fixture names, random values or hidden scoring data are embedded.

The goal is fewer unnecessary operations/model round trips, not merely fewer
words. The original nine documents contained 1,415 whitespace-delimited words;
the revised set contains 1,663. Recovery recipes grew to include their complete
success path. Whether that extra content pays for itself must be measured.

## Controlled comparison

Three conditions are interleaved in a seeded random order within each
scenario/seed block:

1. **baseline:** no skill command.
2. **original:** the catalog from Git revision `70bda5e`.
3. **revised:** the edited nine-skill catalog.

The prompts, help overlay, model, simulator, documentation access and scoring are
the same across conditions except for skill availability/content. Metadata IDs,
titles, descriptions and tags are unchanged between the two catalogs, isolating
the document-body revision from search-ranking or help-text changes.

Five representative scenarios, seeds 1 and 2, give **30 fresh live trials**:

- `manual-scale`
- `automatic-create`
- `automatic-maintenance`
- `debug-automatic-provider`
- `debug-managed-namespace-quota`

The other revised documents receive catalog validation but are outside this live
pilot. This is a development-set tuning experiment: the skills were edited with
knowledge of these task types. It is not a held-out generalization evaluation.

`compare` freezes both catalogs under the output directory before running and
records content hashes per trial. Agent containers cannot read those snapshots
directly. Old and revised results have distinct condition labels so neither can
overwrite the other in report pairing. Failed/invalid runs remain visible; time
deltas use successful matched pairs only. The report also records whether both
agents actually read a skill: unread content cannot explain a speedup.

```sh
PYTHONPATH=bench .venv-bench/bin/python -m aks_bench compare \
  --reference-skills-dir benchmark-results/catalog-before-70bda5e \
  --skills-dir bench/skills --bwrap /tmp/opencode/bubblewrap/usr/bin/bwrap \
  --model gpt-6.1-sol --docs-mode live --repeats 2 --seed 1 --timeout 180 \
  --scenarios manual-scale automatic-create automatic-maintenance \
    debug-automatic-provider debug-managed-namespace-quota \
  --output benchmark-results/catalog-tuning-20261113
```

The original snapshot is gitignored experiment data and can be reconstructed
from `70bda5e:bench/skills`. The new `--skills-dir` option also works with ordinary
two-arm runs. All new runs snapshot their selected catalog, so later edits do
not silently change an in-flight trial's skill content.

Two seeds are a pilot, not statistical significance. Report full and verified
completion time, success rates, actual reads, model calls and modeled Azure
requests separately. New research recipes for other tasks require their own
scenario/state coverage before they can be evaluated in this simulator.
