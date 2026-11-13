# Discovery-only troubleshooting pilot — November 13, 2026

## Valid matched-pair results

There is now a valid pair for each of the three persistent-fault scenarios. All
six selected runs repaired the fault, preserved the required invariants, verified
the final state, and passed containment checks. Both arms had identical prompts,
with no skills/runbook hint. The observed model was `gpt-6.1-sol` in every run.

| Scenario | No-skills seconds | Skills-available seconds | Modeled Azure requests, baseline / treatment | Model inference spans, baseline / treatment | Treatment skill reads |
|---|---:|---:|---:|---:|---:|
| Repair node-pool version skew | 26.52 | 24.36 | 14 / 15 | 7 / 7 | 0 |
| Repair Automatic provider registration | 22.16 | 29.74 | 14 / 11 | 5 / 8 | 2 |
| Repair managed-namespace quota | 21.50 | 18.74 | 5 / 5 | 5 / 6 | 0 |

**Help-based discovery worked in the registration case.** The treatment agent
followed CLI help, requested `az aks skill --help`, searched for `automatic`, and
read `aks-debug-provider` and `aks-automatic-create`. No task prompt mentioned
those commands. This is a demonstrated discovery/use capability, not a reliable
adoption-rate estimate.

In that pair, skills were associated with three fewer modeled Azure requests,
but three more inference spans and about **7.58 seconds more elapsed time**.
Both agents succeeded, so there was no success-rate improvement.

The other two treatment agents never retrieved a skill. Their lower wall times
cannot be credited to skill content. These are one-pair observations subject to
model sampling, backend timing and cache effects.

## Documentation comparison

Both native Copilot `web_fetch` and the logged curl client were available in the
final configuration. A separate contained Copilot probe successfully fetched
Microsoft Learn using native `web_fetch`.

Across the six selected benchmark runs:

- Logged curl documentation HTTP requests: **0**.
- Native web tool attempts: **0**.

Consequently, these valid pairs **do not demonstrate that skills replace or save
web searches/documentation lookups**. The baseline solved the tasks from its
knowledge, command help and diagnostic output.

## Provenance and exclusions

Each pair uses seed 1 and fresh Bubblewrap containers, Copilot CLI 1.0.98,
GitHub-backed inference, docs mode `live`, 180-second task timeout, and the same
simulated service delays. Complete prompt equality, successful state checks,
zero coverage gaps, zero native-doc transport failures, and observed model IDs
were checked before selecting the valid pairs.

| Selected pair | Source revision | Artifact directory |
|---|---|---|
| Provider registration | `7df02a5` | `benchmark-results/sol-troubleshooting-discovery-v4-20261113/` |
| Version skew and namespace quota | `93e1c3d` | `benchmark-results/sol-troubleshooting-discovery-v5-20261113/` |

The rows come from different debugging revisions, not a single frozen efficacy
matrix. The later revision added node-readiness waits and ReplicaSet inspection;
the provider pair was retained rather than rerun because it already had no
coverage gaps. Each individual pair used the same revision in both arms. These
are descriptive implementation-validation results, not statistically significant
or pooled production-performance results.

Earlier sweeps were kept, not silently replaced:

- The first sweep exposed missing activity logs, deployment history, context,
  node, policy and combined-resource inspection.
- Later version-skew attempts exposed PDB/pod inspection and remote kubectl reads.
- The fourth sweep exposed node readiness waits and ReplicaSet inspection in
  two trials; those pairs were rerun after implementation.
- A native web-fetch DNS failure was found in the second sweep's namespace
  baseline. The derived result was invalidated; raw events are unchanged.
  Native DNS/proxy access was subsequently repaired and independently verified.

Invalid trials are excluded from the table. Raw traces, exact prompts, source
hashes, full state, OTel, tool output and network evidence remain local and
gitignored. No Azure resource operation reached Azure. Azure and Kubernetes
request counts are modeled; native web attempts, curl HTTP requests and proxy
connections are distinct measurements.

## What this establishes

1. The agent can discover and use the CLI skills through ordinary help without
   a prompt hint.
2. The harness can simulate and independently score repairs for persistent AKS,
   Automatic and managed-namespace faults.
3. This pilot still shows no consistent completion-time or success benefit from
   skill content, and no demonstrated documentation-request savings.

For stronger conclusions, freeze the current implementation and run repeated
matched seeds. Keep discovery, skill reading, correct repair, time, Azure costs,
Kubernetes calls and documentation use separate in the analysis.
