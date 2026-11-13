# Skill content tuning experiment

## Pilot result

The 30-run comparison completed using `gpt-6.1-sol`, Copilot CLI 1.0.98 and
the frozen harness at `63a7f98`. All 30 runs reached the requested state; **29
were valid**. One no-skills provider-recovery run queried Microsoft.Network,
which the provider fixture did not model. That trial is excluded, not counted as
a model failure or silently treated as a successful performance sample.

All 20 original/revised catalog trials were valid. Prompts and complete scenario
fixtures were verified identical within each of the ten three-condition blocks.
Index metadata was byte-identical between catalogs: only Markdown bodies changed.

| Scenario | Median seconds, no skills | Original | Revised | Skill adoption original / revised |
|---|---:|---:|---:|---:|
| Fixed-size pool | 12.71 | 12.34 | 12.56 | 0/2 / 0/2 |
| Automatic creation | 18.31 | 17.20 | 19.44 | 0/2 / 0/2 |
| Automatic maintenance | 19.39 | 17.25 | 18.33 | 0/2 / 0/2 |
| Provider recovery | 25.06* | 28.12 | 23.86 | 2/2 / 1/2 |
| Managed quota recovery | 17.01 | 19.26 | 18.28 | 0/2 / 0/2 |

\* The no-skills provider value is the sole valid seed-2 run; other cells are
medians of two successful valid runs. Use matched deltas rather than treating
that value as a two-seed control.

Most agents never retrieved a skill. **No performance difference in those runs
can be credited to the revised document bodies.** Adoption was 2/10 with original
content and 1/10 with revised content. Since metadata/help were unchanged, the
different first-read choices are not evidence of improved discovery from body edits.
There were no observed curl or native-web documentation lookups in this pilot.

### The one pair where both agents read skills

Provider recovery, seed 2:

| Metric | No skills | Original | Revised |
|---|---:|---:|---:|
| Full elapsed time | 25.06s | 27.67s | 23.61s |
| Time to verified goal | 22.20s | 23.80s | 19.74s |
| Modeled Azure requests | 11 | 11 | 10 |
| Model inference spans | 6 | 7 | 7 |
| Skill documents read | 0 | 2 | 2 |

The revised run was 4.06 seconds faster than original (about 14.7%) and 1.45
seconds faster than the no-skills run. The trace shows one intended behavior:
after reading, it ran create with `-o none` and final show together using `&&`.
The original used separate tool calls for creation and verification.

This remains a **single promising observation**, not a causal or statistically
reliable speedup. Some timing differences already existed before skill reading.
The original's extra deployment-history request also happened before reading,
so its API-count difference cannot be attributed to the new body text. Both
agents still read two documents: the self-contained recovery recipe did not
eliminate that second read in this run.

### Evidence

Raw artifacts and frozen inputs are local and gitignored at
`benchmark-results/catalog-tuning-20261113/`. The experiment has one revision of
the harness, seeded interleaving, identical prompts/state, and these catalog hashes:

- Original: `a6841e0abe6582457e79d26a70f9635b813a4f290ee00648dc53c165aa3f1bdc`
- Revised: `036eb6a03ef4acf9e67f479efc402b3635a63ace3fd3a90170026f963480eaea`

The summary retains the invalid baseline run and reports successful matched
deltas. The new ACR/workload-identity/PDB recipes were added to the separate
standalone catalog after this experiment started; they are not part of either
frozen experimental catalog. See [their research and scenario designs](typical-aks-task-designs.md).

**Conclusion:** retain the concise operational structure and test it further,
but there is no demonstrated broad success-path speedup yet. Help-based
discovery/adoption remains the main limitation on measuring the content effect.

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
