# Specific AKS procedures: master list and measurable comparisons

## Findings in brief

The new master list now includes **58 scenarios**, with four new procedures tested
in **66 live trials** including coverage-repair reruns and a targeted replication.
The latest explicitly selected matched groups contain **33 trials, 28 valid**.
No invalid run is used for a speed claim; earlier runs remain separately retained.

There are **small descriptive efficiency signals, not a robust general win**:

- **Disk expansion:** three valid matched baseline/contextual pairs, all completed
  correctly. Median paired contextual-minus-baseline time **−5.86 seconds**, model
  spans **−1**, CLI calls **0**, and agent tool requests **−1**. The baseline made
  seven native documentation fetch attempts across those pairs; contextual made
  zero. Two pairs were faster with the skill; the fresh third pair was essentially
  tied (+0.07 s). Two other replication pairs were invalid and stay excluded.
- **SNAT planning:** two valid baseline/contextual pairs. Median paired time
  **−8.77 seconds**, but one seed improved by 22.36 s and the other worsened by
  4.82 s. CLI calls increased by a median one. Native documentation attempts were
  seven versus zero. This is inconsistent timing, not a demonstrated repeatable win.
- **CoreDNS:** both arms completed correctly; contextual was a median **+2.07 s**
  and **+4 CLI calls** versus baseline. No measured efficiency benefit here.
- **Backup:** every arm correctly classified all 14 volume instances. Contextual
  agreed with the pinned support matrix's stated RPO on both seeds; baseline/help
  added a separate tiering delay and reported 40 rather than 36 hours. That is a
  narrow **source-alignment** result, not proof of better end-to-end backup reasoning
  or a universal 36-hour latency bound. No successful-pair speed delta is claimed.

**Discovery remains decisive:** all ten valid contextual trials read their skill;
none of the nine valid help-only trials did, and none entered AKS help. Thus these
efficiency observations concern the command **when reached through a contextual
reference**, not spontaneous use of a hidden/help-only catalog.

## Master list

The [master scenario list](master-scenarios.md) and its
[JSON registry](research/master-scenarios.json) unite **58 scenarios**:

- 34 existing runnable controls/repairs/investigations, with links to their historical evidence.
- **24 newly specified procedures** grounded in current guides and question patterns.
  Four are implemented, bringing the runnable total to **38**; 20 are designed only.

Each new entry names the reusable procedure, motivating question, source URLs,
negative control and holdout ideas. The list is not a frequency survey or a claim
that the model lacks every procedure. Historical studies remain separate rather
than being pooled into one changing benchmark.

The [source index](research/procedure-candidates.json) contains 25 archived pages:
21 product/upstream references and four community questions. Full snapshots,
timestamps and hashes remain local at `benchmark-results/procedure-sources-20261117`.
The manifest SHA-256 is
`b932a3335f1c44926833073af4901d9ee6307150319ad20450a7378bd86acc72`.

### Why these procedures?

Earlier trials showed that adding errors did not make Sol seek skills, and naming
a familiar misconfiguration left little performance headroom. The new candidates
combine a concrete product-specific rule with preservation, sizing, lifecycle or
support-matrix checks. Examples in the designed backlog include CNI dynamic IP
batch reservations, retained-disk CSI migration, same-zone LRS recovery, HPA
sidecar requests, priority-expander matching, PLS PROXY health probes, GitOps
source-of-truth repair and backup restore identity chains.

Community questions identify pain points, not necessarily correct remedies.
Some answers suggest disabling managed components or give blanket online-resize
claims that conflict with the specific current guide. The benchmark procedures
follow the archived product guide/support matrix and expose actual SKU/version
inputs rather than asserting a universal default.

## Implemented first wave

| Scenario | Decisive procedure | Outcome oracle |
|---|---|---|
| `procedure-snat-surge-budget` | Round ports to a multiple of eight, include all pool maxima and approved concurrent percentage surge, size frontend capacity, update AKS rather than its generated LB | Minimal sufficient ports/IPs, effective-rule verification, unchanged pools/timeout/networking |
| `procedure-coredns-import-reload` | Use supported custom-import keys, preserve managed/legacy configuration, reload running DNS and test normal workload resolution | Private zone loaded, legacy/main config preserved, fresh private/cluster/external DNS probes |
| `procedure-disk-expand-boundary` | Inspect actual SKU and branch at expansion beyond 4 TiB; detach only if required; grow existing PVC and verify filesystem | Same PVC/PV/disk/data, correct final size, restored replica count; no unnecessary downtime for v2 |
| `procedure-backup-region-eligibility` | Join PV driver/class with disk size/access/DES; distinguish Operational/Vault tier, paired-region eligibility and RPO | Complete per-volume eligibility/blockers and documented secondary worst-case RPO; no resource changes |

Seeds **81 and 82** change inputs. In particular, seed 81 uses Premium SSD v1
(approved detached resize), and seed 82 uses Premium SSD v2 (online expansion).
SNAT values, pool maxima and backup disk sizes also vary. These are development
variants, **not held-out generalization evidence**.

### Fairness and scope

- Every arm has identical task prompts, public context, starting state and approved
  live documentation access. Prompts never mention skills. Skill text supplies
  general procedures, not seeded resource names, computed answers or scoring rules.
- Skills are fetched through the real `az aks skill show` implementation. Four
  procedures bring the benchmark catalog to **31 skills**; production shim behavior
  and its separate demonstration catalog are unchanged.
- Same three conditions as the discovery study: baseline, ordinary AKS-help-only,
  and contextual tool references. Contextual references appear on stderr, capped
  once per diagnostic/help surface, with stdout and exit status unchanged. They
  refer to the relevant procedure but do not disclose the instance's repair/value.
- The model is explicitly local Copilot `gpt-6.1-sol`; other explicit model choices
  and optional Foundry remain available. No raw Azure resources are touched.
- This is a bounded simulator, not Kubernetes/Azure conformance. DNS process reload
  and CSI detach/expansion reconcile synchronously. A task-authorization guard
  rejects main-DNS edits/deletion; that is not a claim that the real Kubernetes API
  always rejects those writes instead of allowing AKS to reconcile them later.
- SNAT frontends are dedicated outbound capacity; inbound-rule consumption and
  arbitrary upgrade scheduling are not silently assumed. The public planning
  policy states the concurrency envelope being sized.
- Backup cases use small (128–512 GiB) and large (2048 GiB) disks, avoiding ambiguous
  decimal/binary interpretation exactly at a “1 TB” boundary. They assess the
  pinned support matrix, not a real restore or a new RPO SLA. Unknown input support
  and other scenarios remain in the designed backlog.

## Measurement plan

Predeclared first live wave: **24 trials** (four scenarios × two seeds × three
conditions), interleaved by seeded arm order, 240-second timeout. Preserve all
failures, timeouts and simulator coverage gaps. Do not select only runs where
skills happened to help.

Primary checks:

1. Correct completed state or supported assessment, preservation and verification.
2. Actual help/reference exposure and successful skill retrieval.
3. Full elapsed agent/container time, measured model inference spans, and logged
   CLI invocations (az/kubectl/curl). A shell call may batch several CLI invocations.
4. Documentation attempts and modeled Azure/Kubernetes requests, kept separate
   from measured model traffic.

The master generator also derives unique **agent tool requests** from Copilot
`tool.execution_start` IDs. That counter includes shell, file and native web tools;
it is not interchangeable with CLI invocations. These derived measurements do not
rerun inference or alter the frozen state grades.

Paired deltas compare only valid successful trials with the **same scenario/seed**.
Report baseline–help and baseline–contextual separately. A faster failed task is
not a performance improvement. Two seeds provide descriptive smoke results, not
significance. Availability effects and procedural-content effects are distinct:
an unread skill cannot explain a content improvement. A read is not by itself
proof the procedure caused a better outcome.

```sh
PYTHONPATH=bench .venv-bench/bin/python -m aks_bench discover \
  --bwrap /tmp/opencode/bubblewrap/usr/bin/bwrap \
  --copilot /home/david/.local/bin/copilot --model gpt-6.1-sol \
  --seed 81 --repeats 2 --timeout 240 \
  --scenarios procedure-snat-surge-budget procedure-coredns-import-reload \
              procedure-disk-expand-boundary procedure-backup-region-eligibility \
  --output benchmark-results/procedure-comparison-20261117
```

Rebuild the master list with measured data using:

```sh
PYTHONPATH=bench .venv-bench/bin/python bench/master_scenarios.py \
  --runs benchmark-results/procedure-comparison-20261117
```

Validation before live trials: **103 benchmark tests**, **19 shim tests**, and
eight real isolated reference runs (all four procedures on both seeds). Negative
controls include current-count-only SNAT sizing, DNS apply without reload/direct-only
verification, wrong disk-type branching, lost data, incomplete eligibility rows
and falsely equating Operational snapshot cadence with cross-region RPO.

## First live smoke and coverage corrections

The first 24 live trials at `45e3cca` are retained under
`benchmark-results/procedure-comparison-20261117`. Every trial hit a coverage gap:
the agent naturally used routine application HTTP checks, file listing/checksum
probes or JSON Patch move operations not exercised by reference sequences. The
backup assessment also queried prospective policies/instances and the SNAT task
listed load balancers. These runs are **invalid for performance comparisons**,
even though most state oracles passed. They are not baseline failures to attribute
to missing skills.

Corrections add those bounded read operations, real synthetic mount-file/checksum
consistency and RFC-style patch move/copy handling without host shell execution.
Backup blocker grading accepts equivalent identification of Files as a driver/tier
restriction rather than penalizing an extra truthful field. The initial run is not
silently rescored: a full new frozen 24-trial wave follows. The initial contextual
condition read skills in six of eight trials; help-only read none. This is retrieval
evidence from invalid performance trials, not a content-value estimate.

The second 24-trial wave at `7e6e14f` is retained under
`benchmark-results/procedure-comparison-v2-20261117`. Nineteen trials had complete
coverage; five used two further unimplemented read-only inventories (managed public
IPs or VM scale sets). All contextual trials read the relevant skill. All arms
correctly assessed volume eligibility, but baseline/help agents reported a
40-hour cross-region bound by adding the four-hour tiering delay to 24+12 hours,
whereas contextual agents reported the support matrix's stated 36-hour bound.
That distinction must be described as **agreement with a pinned source**, not a
claim that every possible end-to-end backup latency is proven to be 36 hours.

Those missing inventory reads are added for a fresh targeted SNAT/detached-disk
rerun. Invalid results remain excluded; the valid backup failures and DNS/disk
comparisons are retained rather than rerun until they pass.

The targeted SNAT/detached-disk reruns at `d1b8d16` are retained separately. One
SNAT help-only run used a previously unsupported `&&` sequence of read-only HTTP
probes; it remains invalid. A bounded diagnostic-sequence handler is added for
future trials, not used to rewrite that result.

The two completed disk pairs showed a contextual speed reduction, so a separate
**exploratory replication** uses fresh seeds 83–85, three conditions each. It is
post-selection follow-up, not a held-out task or a predeclared significance test.
Results from every replication seed will be retained. The master generator selects
complete scenario/seed groups from explicitly ordered run inputs, never the fastest
arm from different revisions, and includes invalid/failed selected rows.

## Audited live comparison

### Selection and accounting

The ordered master inputs select v2 groups by default, replace both SNAT seed
groups with the targeted SNAT run, replace disk seed 81 with the targeted disk run,
and add disk replication seeds 83–85. The replacement unit is the **complete
three-condition scenario/seed group**, including invalid and failed trials. We do
not fill an invalid help arm with a successful arm from another revision.

| Batch | Revision | Trials | Valid | Invalid | Valid full-rubric passes |
|---|---|---:|---:|---:|---:|
| Initial wave | `45e3cca` | 24 | 0 | 24 | 0 |
| Corrected full wave | `7e6e14f` | 24 | 19 | 5 | 15 |
| Targeted SNAT rerun | `d1b8d16` | 6 | 5 | 1 | 5 |
| Targeted detached-disk rerun | `d1b8d16` | 3 | 3 | 0 | 3 |
| Exploratory disk replication | `7ed1243` | 9 | 5 | 4 | 5 |
| **All retained live trials** | | **66** | **32** | **34** | **28** |

There are **28 valid selected trials out of 33** after superseded groups are
excluded. Four selected backup reports fail only the pinned-RPO criterion, leaving
24 full-rubric passes. This accounting is different from the raw history table
because that table also retains superseded valid trials.

The final four replication gaps were read-only mount/checksum pipelines involving
`mount | grep` or relative paths after `cd` with `sha256sum -c`. Their successful
state outcomes are not used to claim an efficiency gain. These gaps are a concrete
limit of the bounded simulator and a reason to move future artifact-heavy tasks
to real local filesystem/CLI execution rather than continually extending a shell
emulator. A successful reference is necessary but does not establish broad command
coverage; the full raw histories show this limitation.

All 66 trials used Copilot CLI 1.0.98, requested **and observed** `gpt-6.1-sol`,
fresh rootless Bubblewrap containers and live approved documentation access. Every
trial passed isolation. There were no timeouts. Every run launched from a clean
committed tree. Complete prompts and serialized fixtures were checked byte-for-byte
identical across each three-condition group.

### Same-seed successful-pair differences

Values are **contextual minus baseline**; negative values mean fewer/faster.

| Procedure | Valid successful pairs | Median Δ seconds | Median Δ CLI invocations | Median Δ model spans | Median Δ agent tool requests | Native documentation attempts B/C, matched pairs |
|---|---:|---:|---:|---:|---:|---:|
| SNAT growth/surge sizing | 2 | −8.77 | +1 | −1.5 | −3 | 7 / 0 |
| CoreDNS import/reload | 2 | +2.07 | +4 | +1 | +2 | 0 / 0 |
| Disk expansion | 3 | −5.86 | 0 | −1 | −1 | 7 / 0 |
| Backup source-aligned assessment | 0 | — | — | — | — | Not a successful-pair speed comparison |

This table answers different questions from successful medians in the master list.
For example, disk baseline/contextual have different numbers of valid seeds, so
subtracting their unconditional successful medians would overstate the paired effect.
The JSON retains every selected seed, full-rubric criterion counts and paired deltas.

### Replication weakened the initial disk signal

| Seed | Disk SKU/path | Coverage B/H/C | Seconds B/C | Contextual−baseline |
|---|---|---|---:|---:|
| 81 | Premium v1, detached | Valid / Valid / Valid | 46.07 / 36.01 | −10.05 s |
| 82 | Premium v2, online | Valid / Valid / Valid | 33.85 / 27.99 | −5.86 s |
| 83 | Premium v1, detached | Invalid / Invalid / Invalid | Excluded | — |
| 84 | Premium v2, online | Invalid / Valid / Valid | Excluded from B/C pair | — |
| 85 | Premium v1, detached | Valid / Valid / Valid | 42.94 / 43.01 | +0.07 s |

All valid disk trials performed the correct SKU-specific branch, retained identities
and data, restored the replica count and verified mounted capacity. The baseline
did not need a skill to get the procedure right. The observed value is potentially
less lookup/model overhead, and the fresh seed 85 showed no elapsed-time benefit.
The help-only arm also ran faster than baseline on seed 81 despite not reading a
skill, demonstrating why these small timing differences cannot establish causality.

### Backup: a precise but limited source-agreement signal

All six selected backup reports correctly identified which of seven volumes was
eligible and the relevant blockers for the other six: size, restricted access, DES,
Files/Vault incompatibility, in-tree driver and missing static storage class.
That is **14/14 volume classifications per condition**, not 0% baseline understanding.

The only full-rubric difference was the response to `worst_case_rpo_hours`:

| Seed | Baseline | Help-only | Contextual, skill read |
|---|---:|---:|---:|
| 81 | 40 | 40 | 36 |
| 82 | 40 | 40 | 36 |

The archived support matrix states:

> In the secondary region, replication of this recovery point can take up to 12
> another hours, resulting in an effective RPO of up to 36 hours.

The same document separately describes a four-hour tiering delay, explaining the
plausible conservative 24+4+12 calculation. Our task asked for the documented bound;
the skill explicitly preferred the specific matrix and supplied its stated value.
This demonstrates retrieval of a scoped documented fact, but the wording and
latency-scope ambiguity prevent treating it as proof of a generally superior DR
plan. A future benchmark should ask separately for **documented RPO**, **pipeline
latencies**, and **what can safely be promised operationally**. Do not equate any
of these with a guaranteed service SLA.

Contextual backup runs were not faster (about 51–52 s versus 41–47 s for baseline).
They made five native document fetch attempts versus nine baseline and eight
help-only. Those counts are observed tool attempts, not physical HTTP-request counts.

## Which scenarios should be promoted next?

| Candidate | Decision from current evidence |
|---|---|
| Disk expansion | Retain as an exploratory efficiency candidate. Freeze content, add independently authored fault/size variants and improve ordinary command coverage before a larger paired study. |
| SNAT sizing | Retain for lookup-efficiency testing, but do not claim a consistent time or CLI-count improvement from two mixed-seed results. |
| CoreDNS import/reload | Keep as a regression/control task. Baseline already knows it; current skill adds overhead. |
| Backup matrix | Keep as a source-integration candidate, but split the RPO question before a correctness-efficacy claim. Volume eligibility alone showed no gap. |
| CNI dynamic batches | Good next sizing candidate: address reservation/refill and shared-subnet observations, not just active pod counts. Still designed-only. |
| CSI Retain migration and released-PV recovery | Good temporal/data-preservation candidates, provided the model must preserve physical identity and real data rather than only emit a manifest. Still designed-only. |
| GitOps durable repair | Strong procedural candidate when a live fix demonstrably reverts; both arms must have the same repository access and reconciliation evidence. Still designed-only. |
| PLS PROXY health and scoped webhook recovery | Strong multi-component ownership candidates; need real applicability branches and preserved security/traffic behavior. Still designed-only. |

No scenario is promoted to “proven skill benefit” on this evidence. We have measured
candidate time/lookup differences when skills are actually read, and a master list
that prevents confusing designed ideas, implemented controls and tested results.
The content and fixtures were developed together; this is a development screen,
not an independent held-out assessment. Provider caching/backend variability and
short simulated operation delays remain timing confounders. Do not extrapolate
agent seconds here to real Azure upgrades or storage-operation duration.

## Artifacts and regeneration

Raw trial inputs, traces, state, model telemetry and source bodies remain local and
gitignored. No original trial scores or timings were rewritten.

| Batch | Local directory |
|---|---|
| Initial wave | `benchmark-results/procedure-comparison-20261117` |
| Corrected wave | `benchmark-results/procedure-comparison-v2-20261117` |
| SNAT rerun | `benchmark-results/procedure-snat-v3-20261117` |
| Disk seed-81 rerun | `benchmark-results/procedure-disk-v3-20261117` |
| Disk seeds 83–85 | `benchmark-results/procedure-disk-replication-20261117` |

The unchanged 31-skill catalog SHA-256 across all five batches is
`255a1f880e9fe7a40ac4e3addef3e119334e6cddda2ac6be1426a64840387fda`.
Per-run source hashes and revisions are retained in the public JSON registry as
well as the local run manifests.

```sh
PYTHONPATH=bench .venv-bench/bin/python bench/master_scenarios.py --runs \
  benchmark-results/procedure-comparison-20261117 \
  benchmark-results/procedure-comparison-v2-20261117 \
  benchmark-results/procedure-snat-v3-20261117 \
  benchmark-results/procedure-disk-v3-20261117 \
  benchmark-results/procedure-disk-replication-20261117
```

Latest validation: **108 benchmark tests**, **19 shim tests**, and all eight
isolated reference procedures in each of two transport sweeps. These reference
checks are not counted among the 66 live model trials.
