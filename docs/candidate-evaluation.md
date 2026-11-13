# Research candidate implementation and evaluation

## Result

**All 17 primary scenarios were built and evaluated with local Copilot
`gpt-6.1-sol`, with and without discoverable skills.** Across the latest audited
pair for each scenario, baseline completed **16/17** and skills-available completed
**17/17**. **Neither arm read any skill.** This does not demonstrate a skill-content
benefit; the single success difference and timing variation cannot be attributed
to content the agent never retrieved.

There were **78 live trials** across four frozen batches, including coverage
repair reruns. All trials and failures remain in local artifacts. The final
per-scenario set contains 34 valid trials: 33 completions and one genuine failure.
It uses both arms from the same revision for every pair, never a cross-revision
pair. It is an engineering smoke evaluation, not a held-out efficacy experiment.

## Frozen primary-fixture scope

The [17 researched candidates](research/scenario-candidates.json) are registered
as `suite=candidate-v1`, `variant=primary`. Each has one seeded resource graph,
ordinary CLI/kubectl repair operations, a separate desired-state oracle and a
host-only reference sequence. The benchmark catalog adds 16 procedures (the ACR
procedure serves two cases), for 25 skills total.

Both arms receive identical prompts and identical editable `/work/task-context.json`,
`workload.yaml` and `secret-provider-class.yaml`. The context supplies authorized
identifiers, limits and application probes. It does not disclose desired state or
scoring. Skill discovery remains through AKS help. State, oracles, references and
authoritative event logs remain host-owned outside the fresh containers.

These are **bounded simulations**, not Azure/Kubernetes conformance tests:

- One primary fault per candidate; held-out variants are not implemented or evaluated.
- Synchronous reconciliation; no real scheduler, admission webhook, token issuer,
  RBAC propagation delay, node provisioning or asynchronous controller timing.
- Standard ingress NetworkPolicy matchLabels/port union and same-peer intersection;
  Cilium policy types, IP blocks and matchExpressions are outside this fixture.
- ABAC StringEquals/ActionMatches boolean subset. Repository permissions are checked
  against approved and unapproved equivalence classes, not substring matching.
- NAP capacity uses fixed four-vCPU nodes and an aggregate dynamic pool ceiling.
  Image maintenance intentionally ends in `configured_with_evidenced_blocker`:
  schedule set, image drift observed, unchanged PDB still prohibits replacement.
- Gateway HTTP listeners, hostname/path, same-namespace references, Service ports
  and ready endpoints are modeled. TLS, cross-namespace grants and mesh migrations
  need separate coverage.
- CSI values are synthetic version sentinels. Env refresh is modeled as a rolling
  restart; arbitrary application commands and actual secret values are not executed.
- Unsupported commands/options are retained as coverage gaps and excluded from
  model-performance comparisons. No candidate operation delegates to Azure.

Final success requires state/invariant checks and fresh relevant observation after
the last change. PDB weakening/deletion, availability loss, namespace deletion,
broad repository grants and other prohibited transitions remain in history even
if the agent later restores the final configuration. Manual status fields cannot
forge controller readiness. Each candidate has an independent negative control;
additional tests cover temporal changes, resource deletion, policy union, ABAC
broadening, Gateway failures, uploaded manifests and stale verification.

## Validation and run recipe

```sh
python3 -m unittest discover -s tests -v
PYTHONPATH=bench .venv-bench/bin/python -m unittest discover -s bench/tests -v
PYTHONPATH=bench .venv-bench/bin/python bench/check_candidates.py \
  --bwrap /tmp/opencode/bubblewrap/usr/bin/bwrap \
  --copilot /home/david/.local/bin/copilot \
  --output benchmark-results/candidate-container-check
```

The container check executes reference operations, including manifest uploads and
approved live Learn/Kubernetes documentation GETs. It is replay evidence, not a
model trial. The local raw artifacts remain gitignored.

Live evaluation uses local Copilot `gpt-6.1-sol`, a matched baseline/skills pair per
primary fixture, discovery-only prompts, seed 19, and a 300-second timeout. The
runner freezes the catalog, records source hashes/revision, shuffles arm order,
retains failures and reports invalid trials separately. One pair is a smoke
evaluation, not an efficacy estimate. No content benefit can be attributed to an
unread skill. Other explicit model IDs and the optional Foundry provider remain
available.

## First sweep and coverage corrections

The first 34 trials used revision `5ef986f`, seed 19, and local raw directory
`benchmark-results/candidates-sol-20261113`. Every candidate ran in both arms.
No skill was read. The sweep exposed missing support for a public application
probe, authorization listing and network inventory, plus incomplete CSI source
metadata. These runs are retained; coverage gaps invalidate performance comparisons.

Trace review also found that the simulator accepted a malformed role scope as a
successful broad grant. That ACR baseline result must be treated as simulator-invalid,
even though its original machine classification was valid. Corrections reject
nonexistent scopes transactionally, implement dry-run without mutation and model
template-triggered env refresh. The next revision also supplies CSI's actual
application configuration contract and scopes temporary capacity approval to the
PDB recovery task. Those fixture changes require new matched trials rather than
rescoring old elapsed times.

The second 34-trial sweep used `89de990`. It exposed a cluster-wide authorization
bug: `--all-namespaces` was incorrectly evaluated against the current namespace.
Both RBAC agents detected apparently excessive access and removed their Reader
grants. Those outcomes are simulator-invalid, including the skills trial that the
original machine result classified as valid. Revision `df54caa` fixed that boundary
and added fresh pull-pod reconciliation, private endpoint inspection and bounded
namespace REST reads. Eight targeted trials followed. Revision `bf8df57` corrected
the distinction between an unsupported REST operation and a nonexistent resource
ID, followed by two ingress trials. No skill content changed between the batches.

### Batch accounting

Validity below includes the two manual audit exclusions described above. Original
result files are retained unchanged; their classifications are not silently rewritten.

| Batch | Frozen revision | Live trials | Audited valid | Valid completions | Invalid | Scope |
|---|---|---:|---:|---:|---:|---|
| 1 | `5ef986f` | 34 | 9 | 9 | 25 | All 17; initial coverage smoke |
| 2 | `89de990` | 34 | 27 | 26 | 7 | All 17 after first corrections |
| 3 | `df54caa` | 8 | 7 | 7 | 1 | Namespace RBAC/ingress and both ACR cases |
| 4 | `bf8df57` | 2 | 2 | 2 | 0 | Namespace ingress |
| **Total** | | **78** | **45** | **44** | **33** | Includes superseded valid trials |

The per-scenario table selects batch 2 by default, batch 3 for namespace RBAC and
both ACR cases, and batch 4 for namespace ingress. Selection follows coverage
corrections, not whether the agent succeeded. In particular, the valid NAP image
baseline failure from batch 2 is retained rather than rerun until it passes.

## Per-scenario live results

**B/S = baseline / skills available.** Times are total agent/container seconds.
Model calls are observed Copilot inference spans. CLI calls are host-logged
az/kubectl/curl invocations, not the number of shell-tool calls (a shell can batch
several commands). No trial below used curl for documentation. Native docs counts
are successful `web_fetch` attempts; all listed attempts succeeded.

| Scenario | Batch | Outcome B/S | Seconds B/S | Model calls B/S | CLI calls B/S | Native docs B/S |
|---|---:|---|---:|---:|---:|---:|
| `managed-namespace-adopt-identical` | 2 | Pass / Pass | 52.7 / 49.5 | 12 / 11 | 22 / 26 | 3 / 2 |
| `managed-namespace-detach-keep` | 2 | Pass / Pass | 37.1 / 40.2 | 5 / 7 | 24 / 22 | 0 / 0 |
| `managed-namespace-rbac-plane` | 3 | Pass / Pass | 30.3 / 24.7 | 7 / 6 | 26 / 20 | 0 / 0 |
| `managed-namespace-selective-ingress` | 4 | Pass / Pass | 28.2 / 29.0 | 7 / 7 | 20 / 23 | 0 / 0 |
| `acr-abac-pull-repair` | 3 | Pass / Pass | 45.6 / 42.6 | 9 / 8 | 29 / 27 | 0 / 0 |
| `acr-private-data-endpoint` | 3 | Pass / Pass | 31.9 / 28.6 | 8 / 7 | 24 / 25 | 0 / 0 |
| `workload-federation-versus-rbac` | 2 | Pass / Pass | 23.6 / 23.2 | 6 / 6 | 18 / 17 | 0 / 0 |
| `identity-binding-mixed-audiences` | 2 | Pass / Pass | 28.7 / 25.7 | 7 / 6 | 21 / 20 | 0 / 0 |
| `nap-capacity-control-plane` | 2 | Pass / Pass | 33.4 / 34.1 | 7 / 7 | 25 / 22 | 0 / 0 |
| `nap-image-pickup-versus-disruption` | 2 | **Fail / Blocker evidenced** | 22.8 / 24.2 | 6 / 6 | 22 / 20 | 0 / 0 |
| `automatic-admission-mutation-quota` | 2 | Pass / Pass | 46.4 / 25.7 | 9 / 6 | 32 / 19 | 0 / 0 |
| `pdb-preserving-upgrade` | 2 | Pass / Pass | 29.2 / 33.8 | 8 / 8 | 31 / 29 | 0 / 0 |
| `csi-secret-sync-alias` | 2 | Pass / Pass | 25.8 / 20.0 | 6 / 5 | 14 / 14 | 0 / 0 |
| `csi-rotation-consumption-mode` | 2 | Pass / Pass | 39.5 / 41.3 | 8 / 7 | 25 / 24 | 0 / 0 |
| `overlay-cidr-exhaustion` | 2 | Pass / Pass | 29.5 / 43.4 | 7 / 9 | 23 / 21 | 0 / 0 |
| `api-connectivity-stage-repair` | 2 | Pass / Pass | 23.9 / 28.8 | 6 / 8 | 23 / 25 | 0 / 0 |
| `gateway-api-publish` | 2 | Pass / Pass | 31.1 / 36.0 | 8 / 8 | 24 / 30 | 0 / 0 |

### Outcome and discovery interpretation

- The NAP image baseline created `aksManagedNodeOSUpgrade`, rather than the
  required `aksManagedNodeOSUpgradeSchedule`. It inspected the PDB and drift but
  did not configure the operative schedule. The treatment configured that schedule
  and evidenced the unchanged PDB blocker; it did **not** replace the nodes. This
  is the intentionally supported `configured_with_evidenced_blocker` outcome.
- Successful AKS help was exposed in **4/17 treatment trials**: adoption,
  detachment, NAP image maintenance and CIDR expansion. They all ignored the
  advertised skill entry. The other 13 treatments did not enter AKS help.
- **Skill calls and reads were zero in all 78 live trials.** Availability was
  tested, but the skills' procedural content was not exercised by these agents.
- Only adoption fetched documentation in the selected set: three baseline and
  two treatment native web fetches. This one-fetch difference is not evidence
  that an unread skill saved a lookup. Other tasks were generally completed from
  state, CLI affordances and model knowledge.
- Across the **16 successful matched pairs**, median treatment-minus-baseline
  elapsed time was **+0.17 seconds**, verified-goal time **−0.85 seconds**, model
  spans **−0.5**, CLI calls **−1**, and modeled Azure requests **0**. These are
  descriptive values across heterogeneous tasks with one pair each, not confidence
  intervals, a causal effect, or real Azure latency estimates. Failed completion
  time is excluded from paired deltas.

### Modeled service requests

These are simulator accounting units, separate from measured model inference
spans and documentation traffic. They are **not actual Azure/Kubernetes network
requests**.

| Scenario | Modeled Azure B/S | Modeled Kubernetes B/S |
|---|---:|---:|
| Namespace adoption | 9 / 8 | 11 / 16 |
| Namespace detachment | 11 / 10 | 12 / 12 |
| Namespace RBAC | 7 / 8 | 19 / 13 |
| Selective ingress | 3 / 3 | 16 / 19 |
| ACR ABAC | 12 / 13 | 20 / 17 |
| ACR private data endpoint | 17 / 16 | 8 / 10 |
| Workload federation | 10 / 9 | 9 / 9 |
| Mixed identity audiences | 6 / 6 | 14 / 13 |
| NAP capacity | 3 / 3 | 21 / 18 |
| NAP image schedule/blocker | 7 / 6 | 16 / 14 |
| Automatic admission | 6 / 3 | 25 / 15 |
| PDB-preserving upgrade | 8 / 8 | 24 / 22 |
| CSI sync | 0 / 1 | 13 / 12 |
| CSI rotation | 5 / 5 | 19 / 18 |
| Overlay CIDR | 7 / 7 | 17 / 15 |
| API connectivity | 9 / 9 | 15 / 17 |
| Gateway API | 3 / 5 | 16 / 19 |

## Reproducibility and validation evidence

- Model requested **and observed**: `gpt-6.1-sol` in every live trial; local Copilot
  CLI **1.0.98**, GitHub provider, fresh rootless Bubblewrap containers.
- Seed 19, one pair per batch/scenario, shuffled arm order, 300-second timeout,
  default modeled latency scale 1, live approved documentation access.
- Every selected pair has byte-identical prompts and identical serialized fixtures.
  All selected trials passed all isolation checks and had zero coverage gaps.
- All four batches were launched from clean committed revisions. The unchanged
  catalog SHA-256 is
  `552839a6293c932c874531d429a1cbdffdad6847e4fd6b16cc601ebe280b0937`.
- Latest validation: **67 benchmark tests**, **19 shim tests**, and all **17
  reference sequences** through real isolated containers. The two container-check
  sweeps also exercised live Learn and Kubernetes documentation GETs. These
  reference checks remain separate from the 78 live model trials.

Raw trial directories, state, timelines, prompts, model telemetry and proxy traces
are local and gitignored:

| Batch | Local directory | Recorded source SHA-256 |
|---|---|---|
| 1 | `benchmark-results/candidates-sol-20261113` | `ebbc9f7c8ecf5ab8946c7eb35057058ed8eb9218d6dd0622bd17a04f86ed91b8` |
| 2 | `benchmark-results/candidates-sol-v2-20261113` | `0703603abf64baa229864877c6941dd610afa590847cae472a8963c85d5249e2` |
| 3 | `benchmark-results/candidates-sol-v3-20261113` | `ea0e85c9ca443c1b9acf7bdb4ec5400f4dfb8fcc957598712cac097490b7c40b` |
| 4 | `benchmark-results/candidates-sol-v4-20261113` | `097ce8302436420cc9e3129e9a3609a1be23cbefdbcf7a1888c5690ad130767d` |

The appropriate next experiment is discovery reach/adoption and held-out fault
variants. More repetitions of these easy, mostly lookup-free primary fixtures
would not establish skill-content value while retrieval remains zero.
