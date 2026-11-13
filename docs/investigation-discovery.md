# Symptom-first investigations and tool-surface skill discovery

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
| KAITO provisioning | `gpu-incident-kaito-quota` | Workspace conditions/time, failed allocation operation, exact family quota arithmetic, separate SKU restrictions |

Prompts are identical within each family for a given seed. They give a symptom,
target, incident window and a read-only investigation request, not the fault name
or repair. Both arms see the same evidence-source inventory and report schema.
Healthy current snapshots and comparison-node metrics are included to distinguish
them from incident-time evidence. No scenario identity/oracle is mounted inside
the agent container.

### Scoring

The agent writes `/work/diagnosis.json`: cause, target, time window, exact command
citations with verbatim excerpts, competing explanations and recommended action.
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
them still needs trace review. Exact-citation failures must be distinguished from
wrong diagnoses in the report. Diagnosis-file completion is measured at process
exit, not asserted as a precisely observed earlier root-cause timestamp.

This remains a bounded simulation: prepared log/metric/decoded-packet responses,
not real packet capture, a complete PromQL engine, GPU execution, Azure capacity
or a controller implementation. The seven faults are development variants, not
held-out evidence of broad generalization. A missing operation produces a coverage
gap; such trials are retained and excluded from performance claims.

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
