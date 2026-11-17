# Specific AKS procedures: master list and measurable comparisons

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

Live results will be added after the frozen run and trace review.
