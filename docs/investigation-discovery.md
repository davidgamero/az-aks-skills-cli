# Symptom-first investigations and tool-surface skill discovery

## Result in brief

**Contextual diagnostic references reached the agent and triggered retrieval.**
In the latest 21 live trials, references were exposed in 7/7 contextual trials and
the relevant skill was read in **4/7**, versus **0/7** with AKS-help-only discovery.
None of the help-only agents opened AKS help. Both conditions had the same catalog.

All three conditions identified all seven intended causes/candidates. After an
explicit scoring-only audit, all 21 reports met the corrected evidence rubric:
six confirmed diagnoses and one appropriately unconfirmed historical candidate
per condition. **This establishes a promising discovery surface, not a demonstrated
diagnostic benefit.** These development fixtures remain tractable for Sol without
skills. No documentation fetches occurred in the latest run.

## Source review

The requested [Azure/AKS-Skills](https://github.com/Azure/AKS-Skills) repository is
deprecated as of its pinned `7fac4bc` revision. Its skill contract explicitly
accepts deep AKS Day-2 workflows and rejects generic Kubernetes recipes. Current
references were inspected in the Microsoft-maintained
[skills mirror](https://github.com/microsoft/skills/tree/f03ec5392f7a0f3aca12af47477e92f1edf7b44c/.github/plugins/aks-skills/skills)
at `f03ec539`, along with Microsoft Learn and Azure SRE Agent guidance.

[The source index](research/investigation-sources.json) records 15 sources.
Full snapshots, fetch timestamps and SHA-256 hashes are local at
`benchmark-results/investigation-sources-20261113/manifest.json`. GitHub sources
are commit-pinned. The two benchmark procedures are independently authored from
these sources, not an assertion that the upstream plugin was evaluated unchanged.

Relevant findings:

- Egress diagnosis needs the actual resolver/outbound path, affected backend and
  incident time. LocalDNS can fail while CoreDNS and later connectivity look healthy.
- Packet-level evidence is a separate workflow; use existing captures before
  assuming permission to deploy new privileged collectors.
- GPU diagnosis must separate host/container memory from device memory and branch
  on the installed profile. Learn specifies `gpuProfile.nvidia.managementMode`
  and `gpuProfile.driver`; the fixture uses those concrete API fields rather than
  flattening shorthand in the skill's table.
- Managed GPU DCGM uses port 19400. A current exporter scrape is not historical
  evidence of an incident peak.
- KAITO readiness, exact-family quota, SKU eligibility and regional capacity are
  distinct. Deleting a Workspace does not automatically clean up its GPU pools.
- Source guidance can differ or age. The fixture deliberately specifies its
  configuration instead of inferring it from a claimed universal default.

## Rebuilt default suite

The default benchmark now runs these seven investigation variants. The previous
27 repair tasks remain selectable by `--scenarios` for historical comparisons.
The catalog contains 27 skills, including `aks-investigate-egress` and
`aks-investigate-gpu`.

| Family | Scenario | Evidence needed to separate plausible causes |
|---|---|---|
| Intermittent egress | `egress-incident-snat` | Application phase timing, affected-backend incident usage/allocation/failed connections, resolver evidence |
| Intermittent egress | `egress-incident-localdns` | Node-local forwarding timeout versus working alternate path, application DNS timing, healthy incident SNAT telemetry |
| Intermittent egress | `egress-incident-upstream` | Fast DNS/connect/TLS, packet/response timing, healthy incident SNAT telemetry |
| GPU initialization | `gpu-incident-container-memory` | Termination reason, container limit/working set, incident GPU used/free memory |
| GPU initialization | `gpu-incident-device-memory` | Previous CUDA error, affected-GPU used/free memory, container-memory evidence |
| GPU scheduling | `gpu-incident-plugin` | Observed ownership profile, node allocatable resources, plugin selector and scheduled status |
| KAITO provisioning | `gpu-incident-kaito-quota` | Workspace conditions/time, failed allocation operation and exact family quota arithmetic; SKU restrictions are available for a separate capacity branch |

Prompts are identical within each family for a given seed. They give a symptom,
target, incident window and a read-only investigation request, not the fault name
or repair. Both arms see the same evidence-source inventory and report schema.
Healthy current snapshots and comparison-node metrics are included to distinguish
them from incident-time evidence. No scenario identity/oracle is mounted inside
the agent container.

### Scoring

The agent writes `/work/diagnosis.json`: cause, target, time window, exact command
citations with excerpts, competing explanations and recommended action.
The host checks these against host-recorded responses and independent fixture
expectations. A correct label with no collected/cited evidence fails. Current-only
or wrong-peer telemetry cannot establish the historical memory incident. Reads
alone do not count as evidence citations. Resource mutation attempts fail this
read-only task even when the simulator rejects them.

The score is **structural**, not an LLM judgment of causal reasoning quality.
Supplementary citations to local transformations (for example `date` converting a
metric timestamp) are reported as unverified and earn no decisive-source credit.
All cited az/kubectl/curl excerpts must match retained responses, including ordinary
nondecisive reads. Alternative labels and the recommendation action are checked; the prose explaining
them still needs trace review. Whitespace-only changes, recorded `&&` command
batches and two lossless Azure-metrics display projections are accepted. Submitted
shell/Python/jq formatter code is never executed by the grader. Unsupported local
transformations receive no source credit. Citation failures must be distinguished from
wrong diagnoses in the report. Diagnosis-file completion is measured at process
exit, not asserted as a precisely observed earlier root-cause timestamp.

This remains a bounded simulation: prepared log/metric/decoded-packet responses,
not real packet capture, a complete PromQL engine, GPU execution, Azure capacity
or a controller implementation. The seven faults are development variants, not
held-out evidence of broad generalization. A missing operation produces a coverage
gap; such trials are retained and excluded from performance claims.

The plugin case deliberately lacks historical proof of when the current selector
mismatch began. Its supported outcome is `supported_candidate_with_evidence_gap`:
identify the current device-plugin problem, cite ownership/node/component evidence,
and retain `unconfirmed` confidence for the historical incident. This is separate
from six confirmed diagnoses; a current mismatch alone does not establish a past cause.

## Discovery experiment

`discover` runs three interleaved conditions per scenario/seed:

| Condition | Skills | Discovery surface |
|---|---|---|
| `baseline` | Unavailable | Ordinary tool output/help |
| `help` | Available | Existing AKS parent/descendant help overlay |
| `contextual` | Same catalog as help | Help overlay plus related-procedure references in diagnostic/help output |

Contextual output looks like:

```text
Related diagnostic procedure: az aks skill show --name aks-investigate-egress (read-only investigation guidance).
```

It is emitted on **stderr**, preserving JSON/data stdout and original exit status,
at most once on each of two surfaces per trial: diagnostic output and help/usage.
Diagnostic surfaces are kubectl describe/logs/exec and Azure nodepool/metrics
inspection. The referenced procedure depends only on the broad egress/GPU family,
never on the hidden fault or winning branch. All three egress variants receive
the same reference; all four GPU variants receive the same reference.

The source implementation is the benchmark's simulated tool layer. The production
PATH shim still forwards ordinary commands with exec and overlays successful AKS
help only. Promoting diagnostic references into a real CLI requires an explicit
integration with the owning diagnostic tool. The experiment measures whether that
surface is worth implementing before changing the passthrough contract.

No prompt hints, automatic skill loading, hidden baseline restrictions or extra
treatment telemetry. All conditions have identical raw evidence. The report
separates hint/help exposure, successful skill reads, first-read time, diagnostic
success, model spans, CLI calls, docs access and modeled service requests.
Discovery availability and content effectiveness are distinct outcomes.

## Run

```sh
PYTHONPATH=bench .venv-bench/bin/python -m aks_bench discover \
  --bwrap /tmp/opencode/bubblewrap/usr/bin/bwrap \
  --copilot /home/david/.local/bin/copilot \
  --model gpt-6.1-sol --seed 41 --timeout 300 \
  --output benchmark-results/investigation-discovery
```

For a normal no-skills/skills pair, use `run`; `discover` compares all three
conditions. Explicit `--scenarios` retains access to the earlier tasks. Other
models and optional Foundry configuration remain supported.

Validation: `python3 -m unittest discover -s tests -v` and
`PYTHONPATH=bench .venv-bench/bin/python -m unittest discover -s bench/tests -v`.
`bench/check_investigations.py --bwrap PATH --copilot PATH --output NEW_DIRECTORY`
also exercises all seven reference investigations through the actual isolated
clients. Reference reports are host-generated for that check and are never live
model evidence.

## First live smoke and corrections

The first 21-trial run at `30ed90f` is preserved under
`benchmark-results/investigation-discovery-20261113`. Contextual references led
to four successful skill reads across seven trials; help-only led to zero. This
is an exposure/retrieval observation, not a valid efficacy comparison: 18 trials
had coverage gaps, and all 21 suffered a citation-retention bug. Ordinary real
responses were not retained unless tagged decisive, so authentic supplementary
citations were incorrectly rejected.

Corrections retain all successful response evidence, give unlogged local
transformations no decisive credit, support multi-value metric syntax and common
read-only diagnostic utilities, and make Pending GPU/KAITO data consistent: no
crash logs or memory telemetry for a container that never started. Those changes
require a new frozen run. The first run remains intact rather than being presented
as model failures or having elapsed times silently rescored.

The second 21-trial run at `4636539` is preserved under
`benchmark-results/investigation-discovery-v2-20261113`. It produced three
contextual skill reads and no help-only reads. All seven baselines named the
intended cause, although the plugin diagnosis appropriately remained unconfirmed.
Two trials had coverage gaps. Several other failures were rubric artifacts:
authentic command batches, lossless metrics formatting and JSON indentation were
rejected. The next scoring revision explicitly handles these representations and
the plugin's historical evidence gap. These failures are not evidence that skills
are needed to diagnose the fixtures; the current evidence primarily tests retrieval.

## Latest live comparison and explicit rubric audit

The third batch ran from clean revision `e1d09c6`, using local Copilot 1.0.98,
requested and observed model `gpt-6.1-sol`, seed 41, one interleaved trial per
condition/scenario and a 300-second timeout. All **21 trials passed isolation and
had zero command-coverage gaps**. Prompts and complete serialized fixtures were
checked byte-for-byte identical across each three-condition group.

The original rubric accepted 8/21 reports. Trace review found the remaining
failures were not wrong diagnoses: it required a metric name to be repeated inside
an excerpt even when bound by the exact source command, rejected a legitimate
short numeric cgroup value, rejected alternative codes followed by explanatory
prose, or required SKU listing despite an explicit failed quota operation and
correct family-quota arithmetic. These are scoring-design defects.

Revision `3a842cd` corrects those rules. The audit utility at `b4c4a5b` checks that
the prompts, public context, starting state and all evidence resources/facts are
unchanged before applying the current rubric. It writes **separate audited results**;
original results, agent reports and measured timings remain intact. No additional
inference occurred during this audit. The 21/21 audited result is post-hoc scoring,
not an independently frozen success-rate estimate or evidence of improved agent ability.

### Latest batch: baseline / help-only / contextual

All rows have three audited accepted reports. The GPU-plugin row is the explicitly
uncertain `supported_candidate_with_evidence_gap` outcome; other rows are confirmed
diagnoses. Elapsed time includes producing the structured report.

| Scenario | Seconds B/H/C | Model spans B/H/C | CLI calls B/H/C | Relevant skill reads H/C |
|---|---:|---:|---:|---:|
| SNAT pressure | 62.2 / 55.8 / 81.5 | 8 / 8 / 10 | 17 / 17 / 27 | 0 / 1 |
| LocalDNS forwarder path | 64.9 / 71.3 / 76.9 | 9 / 9 / 10 | 22 / 19 / 27 | 0 / 0 |
| Upstream response latency | 57.9 / 52.7 / 57.0 | 7 / 8 / 8 | 16 / 18 / 19 | 0 / 0 |
| Container memory | 62.1 / 72.1 / 76.6 | 9 / 10 / 9 | 22 / 23 / 28 | 0 / 1 |
| GPU device memory | 76.3 / 66.5 / 71.2 | 9 / 8 / 10 | 23 / 23 / 22 | 0 / 0 |
| Customer device plugin | 89.5 / 90.8 / 72.9 | 10 / 12 / 10 | 30 / 30 / 29 | 0 / 1 |
| KAITO family quota | 61.5 / 52.3 / 86.1 | 9 / 9 / 11 | 32 / 25 / 44 | 0 / 1 |

| Aggregate | Baseline | Help-only | Contextual |
|---|---:|---:|---:|
| Valid live trials | 7 | 7 | 7 |
| Correct cause/candidate labels | 7 | 7 | 7 |
| Audited accepted evidence reports | 7 | 7 | 7 |
| Trials exposed to a skill reference | 0 | 0 | 7 |
| Trials with a relevant skill read | 0 | 0 | 4 |
| Median elapsed seconds | 62.2 | 66.5 | 76.6 |
| Total measured model spans | 61 | 64 | 68 |
| Total logged CLI calls | 162 | 155 | 196 |
| Documentation fetch attempts | 0 | 0 | 0 |

The median **paired** contextual-minus-help difference was +4.67 seconds,
+1 model span and +5 CLI calls. These descriptive differences from one seed do
not establish statistical significance. Measured model spans and elapsed time
remain distinct from the simulator's modeled Azure/Kubernetes/telemetry requests.

### Which references led to reads?

| Investigation | First reference surface | Time from reference to successful skill read |
|---|---|---:|
| SNAT pressure | `az monitor metrics list` | 6.49 s |
| Container memory | `kubectl describe pod` | 4.32 s |
| Customer device plugin | `kubectl describe node` | 6.04 s |
| KAITO family quota | `kubectl describe pod` | 3.07 s |

The other three contextual agents saw the reference and proceeded without reading
it. No agent in this batch invoked help, so the additional help/usage placement
was implemented and tested but not exercised by the live agents.

## Recommendation

Keep the contextual diagnostic-reference variant for follow-up discovery trials.
The actual diagnostic reads are a better reach point in these traces than AKS
help alone. Use a short, relevant command reference on stderr, cap repetition,
and preserve machine-readable output. Measure exposure and retrieval separately;
do not preload the skill or add a user-prompt hint to manufacture adoption.

**Do not claim these tasks require a skill.** Even with incident-time correlation
and more specialized GPU facts, all baseline agents identified the intended cause.
The supplied evidence inventory, bounded facts and enumerated report vocabulary
make this a controlled discovery experiment. Before claiming content effectiveness,
add held-out incidents with genuinely incomplete/contradictory time series and
multi-resource interactions, then prescreen baseline difficulty. Preserve access
to the same evidence in every condition.

## Artifacts and reproduction

There were **63 live trials** total, three development batches of 21. Earlier
coverage and scoring failures are preserved; they are not pooled into the latest
comparison. The audit is zero additional live trials.

| Artifact | Revision | Local directory |
|---|---|---|
| First live smoke | `30ed90f` | `benchmark-results/investigation-discovery-20261113` |
| Second live smoke | `4636539` | `benchmark-results/investigation-discovery-v2-20261113` |
| Latest live batch | `e1d09c6` | `benchmark-results/investigation-discovery-v3-20261113` |
| Explicit latest-batch audit | `b4c4a5b` | `benchmark-results/investigation-discovery-v3-audit-r2-20261114` |

Latest live source SHA-256:
`39da73b695e2ce345110b43cc91b36e5c194a744dab7d9cd2aab4e1b7ea70785`.
The catalog was unchanged across all three batches:
`5f2ccb768507b99090421700194b933d1fc3ad8d5b10b9d4cccd036c52af3e19`.

```sh
PYTHONPATH=bench .venv-bench/bin/python bench/audit_investigations.py \
  --run benchmark-results/investigation-discovery-v3-20261113 \
  --output benchmark-results/NEW-audit-directory
```

The audit refuses changed fixtures and preserves coverage/isolation validity.
Latest validation: **85 benchmark tests**, **19 shim tests**, and seven successful
isolated reference investigations in each of two transport-check sweeps. Raw
snapshots, telemetry, reports and container evidence remain gitignored.
