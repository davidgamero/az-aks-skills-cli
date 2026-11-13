# Discovery-only troubleshooting benchmark

See [the valid troubleshooting pilot results](troubleshooting-pilot.md) for
the first matched pairs after diagnostic coverage and native docs access fixes.

## Changes to the experiment

The runner no longer tells either agent that skills exist. Both arms receive
identical task prompts. `--discovery passive` is now the only supported mode;
historical explicit/guided results remain historical evidence, not the current
configuration.

Discovery is through normal help:

```text
az --help → aks
az aks --help → skill / skills subgroups
az aks nodepool upgrade --help → Related Commands: az aks skill
az aks skill → list/search/show syntax and examples
```

The production wrapper overlays successful AKS help from the real CLI and keeps
the original help, stderr and status. The benchmark uses that same overlay on
its mock help. Ordinary production commands still exec the real CLI. The
benchmark never does.

## Audit of earlier failures

The retained live traces had **no unresolved task failures or simulator coverage
gaps**. Observed errors were mainly:

- Skill syntax mistakes: `search --query`, positional `show`, and the early
  debugging run's `show --id`.
- The deliberately injected `TooManyRequests` responses in the scaling scenario.
- A `ResourceNotFound` check for a cluster that had not yet been created.

Those trials primarily tested familiar happy-path workflows and one retryable
fault. They did not establish that skills help diagnose a persistent operational
fault, so the new cases require changing the cause rather than repeating a call.

## Research and scenario selection

Sources were reviewed on November 13, 2026. These are documented failure classes,
not a claim about their frequency in production.

| Area | Source finding | Benchmark treatment |
|---|---|---|
| AKS upgrade FAQ/troubleshooting | A pool cannot be newer than its control plane; inspect available versions and respect upgrade order | Implemented: persistent version-skew failure |
| Automatic prerequisites | Automatic enables Policy; supporting provider namespaces may require registration | Implemented: missing Microsoft.PolicyInsights registration |
| Managed namespaces | ARM owns managed namespace fields/resources; direct Kubernetes edits are blocked; quota can deny new pods/scaling | Implemented: quota-blocked rollout requiring ARM update |
| Upgrade drain failures | PDBs with zero allowed disruptions can block eviction; repair availability/budget before retry | Researched next case; needs a pod/PDB/drain state model |
| Automatic deployment safeguards | Enforcement can reject workloads without required resource/probe settings; disabling enforcement is not a suitable default repair | Researched next case; needs workload manifests and admission-policy simulation |
| Managed namespace access/networking | Control-plane and Kubernetes roles differ; default same-namespace ingress can block cross-namespace traffic | Researched next cases; need authorization and traffic probes |

Sources:

1. [NodePoolMcVersionIncompatible](https://learn.microsoft.com/en-us/troubleshoot/azure/azure-kubernetes/error-codes/nodepoolmcversionincompatible-error).
   This older page's maximum allowed minor-version-skew text differs from newer
   policies; the test uses only the unambiguous node-pool-not-newer rule.
2. [Resource provider registration errors](https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/error-register-resource-provider).
3. [Automatic quickstart prerequisites](https://learn.microsoft.com/en-us/azure/aks/automatic/quick-automatic-managed-network).
4. [Managed namespaces](https://learn.microsoft.com/en-us/azure/aks/managed-namespaces)
   and [concepts, quotas, adoption and roles](https://learn.microsoft.com/en-us/azure/aks/concepts-managed-namespaces).
5. [PDB-related upgrade failures](https://learn.microsoft.com/en-us/troubleshoot/azure/azure-kubernetes/create-upgrade-delete/error-code-poddrainfailure).
6. [Deployment safeguards and FAQ](https://learn.microsoft.com/en-us/azure/aks/deployment-safeguards).

## Three runnable fault scenarios

### First live diagnostic sweep and coverage fixes

The first six discovery-only trials on `f82fca3` all reached their requested final
state, but **all six were excluded from performance analysis** because agents
used legitimate diagnostic commands missing from the initial simulator:

- Azure activity logs and ARM deployment history.
- Kubeconfig/context and node inspection.
- Managed network-policy reads and combined resourcequota/limitrange/pod queries.

These are now modeled. Prior failures are visible in activity logs; direct AKS
SDK operations correctly produce no ARM template deployment history. Credential
retrieval writes a synthetic kubeconfig inside the container only. The installed
CLI's `aks operation show-latest` is also covered. The nonexistent
`aks nodepool operation show-latest` remains a normal CLI error.

Replaying all six recorded command sequences against the fixes produced no
coverage gaps and preserved correct final state. This validates coverage, not
agent performance; fresh live trials are needed for timings.

The invalidated sweep nevertheless recorded a discovery capability: agents in
the version-skew and provider-registration treatment runs found and read skills
through help, without a prompt hint. No agent made a logged documentation HTTP
request. Raw diagnostic artifacts remain in
`benchmark-results/sol-troubleshooting-discovery-20261113/` and are not pooled
into valid benchmark comparisons.

A second sweep exposed a docs-access issue: the quota baseline attempted native
Copilot `web_fetch`, which failed DNS validation in the isolated network before
using the proxy. The zero HTTP count above refers to the logged curl client;
it must not be interpreted as zero attempted browsing. That affected trial is
invalidated in the derived report; raw traces are preserved.

Native web fetching is now enabled through an explicit public-IP hosts mapping
and exact-host proxy allowlist for learn.microsoft.com. A separate live Copilot
probe fetched the managed-namespace page successfully using native `web_fetch`,
with all containment checks passing. Native tool attempts/successes/failures are
tracked separately, and DNS/network transport failures invalidate future trials.
The probe lives at `benchmark-results/native-web-probe-20261113/`.

Additional observed PDB/pod inspection and read-only `az aks command invoke`
queries are modeled. Remote command strings are parsed into a bounded set of
mock Kubernetes reads; they never execute a host shell.

### `debug-version-skew`

**Task:** A previous apps-pool upgrade failed. Finish upgrading it to 1.34.2;
control-plane upgrades are authorized if necessary, but the system pool and node
counts must remain unchanged.

**Initial fault:** The control plane is 1.33.5 and the apps pool is in Failed
state. Retrying the requested pool upgrade repeatedly yields
`NodePoolMcVersionIncompatible` until the control plane is upgraded.

**Expected repair:** Inspect versions/available targets, upgrade the control plane
only, upgrade the target pool, and verify recovery. A full-cluster upgrade changes
the protected system pool and fails the oracle.

### `debug-automatic-provider`

**Task:** Diagnose a failed Automatic cluster creation and finish creating it
with the requested managed defaults. Provider registration is authorized.

**Initial fault:** Microsoft.ContainerService is registered, but
Microsoft.PolicyInsights is not. Automatic create returns
`MissingSubscriptionRegistration` until the named provider is registered.

**Expected repair:** Inspect registration, register the required namespace, retry
creation, and verify Automatic/Standard SKU-tier and managed defaults. Changing
SKU to Base, merely retrying, or registering an unrelated provider cannot pass.

### `debug-managed-namespace-quota`

**Task:** An Automatic cluster's `retail/api` deployment is stuck at two ready
replicas after requesting four. Restore four replicas within the approved
four-core namespace request budget. Preserve per-pod requests, CPU limits,
memory quotas, network policies and cluster settings.

**Initial fault:** Each pod requests one core; the ARM-managed quota permits two.
The deployment spec already requests four, but pod admission produces
`FailedCreate: exceeded quota`. This is not a node-capacity shortage that NAP
can fix. Direct kubectl edits of the managed quota are rejected.

**Expected repair:** Diagnose deployment/events/quota, inspect the managed
namespace, update its `--cpu-request` through `az aks namespace update`, and verify
ready replicas with kubectl. Oversizing beyond the approved budget, weakening
network policy or merely changing desired replicas fails the oracle.

The fake Kubernetes model supports the reads and rollout/scale operations needed
for this case. It does not claim general Kubernetes compatibility or real
scheduler/admission-controller execution. Unknown workload edits are coverage
gaps, not fabricated permission failures.

## Skills versus documentation access

Both arms have the **same documentation access**. The baseline is not forced to
search, and the treatment is not forced to read skills. Error messages and command
help include ordinary Microsoft Learn references; only treatment help lists
skills. No prompt mentions skills or directs the agent toward a particular source.

The container's `curl` is a logged GET-only client. It can fetch:

- `https://learn.microsoft.com/en-us/azure/...`
- `https://learn.microsoft.com/en-us/troubleshoot/azure/...`
- `https://learn.microsoft.com/en-us/cli/azure/...`
- `https://learn.microsoft.com/api/search?...`

The curl host fetcher validates the origin and path before each request and redirect.
It accepts no credentials, uploads or mutation methods. Each response is capped
at 2 MiB and saved outside the container with its content hash. The existing
network namespace and model proxy continue to block ARM and arbitrary internet.
This gives a controlled live documentation/search comparison, not unrestricted
web browsing. A container smoke probe verified both the fake kubectl path and an
actual successful Learn fetch while all isolation checks passed.
Native Copilot web fetching can also use the exact Learn host through the proxy.
Native response content appears in Copilot's tool output; curl body snapshots
and per-HTTP counts belong to the separate host fetcher.

Metrics distinguish:

- Skill retrievals and actual successful skill reads.
- Simulated Azure API costs and Kubernetes requests.
- Actual curl documentation HTTP attempts, including redirects/failures, and
  separately counted native web tool attempts/successes/failures.
- Model inference spans, tokens, full elapsed time and verified completion time.

The legacy `az-events.jsonl` filename contains all three tool types; use its `tool`
field. Body snapshots are in `documents/`. `--docs-mode off` is available for
offline sensitivity runs; do not combine those trials with docs-enabled results.

**Interpretation:** If the baseline solves a case without fetching documentation,
we cannot claim the skill saved a web lookup. If treatment never reads a skill,
we cannot attribute its performance to skill content. Compare correct recovery
and preserved invariants first, then time and network-related metrics. Use repeated
matched seeds before making an efficacy claim.

## Run

```sh
PYTHONPATH=bench .venv-bench/bin/python -m aks_bench run \
  --bwrap /tmp/opencode/bubblewrap/usr/bin/bwrap --model gpt-6.1-sol \
  --scenarios debug-version-skew debug-automatic-provider debug-managed-namespace-quota \
  --docs-mode live --repeats 1 --seed 1 --timeout 180 \
  --output benchmark-results/troubleshooting-discovery
```

The default complete matrix now contains ten scenarios. The new documentation,
help-discovery and failure-model changes should be treated as a new experimental
configuration, not pooled uncritically with the earlier guided-use pilot.
