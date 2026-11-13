# Help-text evaluation — November 13, 2026

## Result

**All 14 rerun trials succeeded and passed containment checks, but this rerun
does not establish that the new help improves task efficiency.** None of the
agents invoked skill help, a bare skill group, or the plural alias. The skills
arm's time overhead relative to the no-skills arm was effectively unchanged.

### Guided-use comparison

| Scenario | Earlier skills seconds | Updated skills seconds | Fresh no-skills seconds | Skill syntax errors, earlier → updated | Modeled Azure requests, updated no-skills / skills |
|---|---:|---:|---:|---:|---:|
| Fixed-size pool | 19.69 | 16.94 | 11.82 | 2 → 0 | 8 / 10 |
| Autoscaler bounds | 17.08 | 15.68 | 12.12 | 2 → 0 | 5 / 7 |
| Control-plane-only upgrade | 16.93 | 15.89 | 15.13 | 0 → 0 | 7 / 8 |
| Stop development cluster | 16.63 | 16.19 | 12.72 | 2 → 0 | 5 / 5 |
| Scaling with injected 429 | 25.52 | 22.61 | 17.14 | 2 → 2 | 9 / 11 |
| **Sum** | **95.86** | **87.31** | **68.93** | **8 → 2** | **34 / 41** |

| Metric across five tasks | Earlier no-skills / skills | Updated no-skills / skills |
|---|---:|---:|
| Successes | 5 / 5 | 5 / 5 |
| Elapsed seconds | 77.47 / 95.86 | 68.93 / 87.31 |
| Skills overhead in seconds | +18.39 | +18.38 |
| Model inference spans | 20 / 32 | 19 / 30 |
| Modeled Azure requests | 34 / 39 | 34 / 41 |
| Successful skill reads in treatment | 5 | 5 |
| Skill help invocations in treatment | 0 | 0 |

Both arms became faster by roughly the same total amount. Skills still cost more
model calls and modeled Azure requests. The two remaining skill errors were the
same `search --query` and positional `show` mistakes in the transient-scale task.
Because no new help was read, the fewer syntax errors are an observation of this
sample, not evidence that the formatting change caused better behavior.

### Passive-discovery comparison

| Scenario | Fresh no-skills seconds | Skills-available seconds | Modeled Azure requests, no-skills / treatment | Treatment skill reads |
|---|---:|---:|---:|---:|
| Fixed-size pool | 11.37 | 11.56 | 8 / 8 | 0 |
| Control-plane-only upgrade | 16.99 | 17.64 | 8 / 8 | 0 |

All four tasks succeeded. Skill availability alone again produced no discovery.
The next targeted experiment would expose syntax examples where agents already
look (for example, in list output), or explicitly compare a help-first condition.
This rerun kept the original prompts rather than adding that new intervention.

## Matrix and controls

This rerun evaluates the Azure-style help and `skills` alias introduced in
`411d6489255bef72f02554a1afe29f19e6382ff4` against the
[initial pilot](benchmark-pilot.md).

- Model: `gpt-6.1-sol`; Copilot CLI 1.0.98; GitHub-backed inference.
- Engine: fresh rootless Bubblewrap containers, with the same network boundary.
- Five guided-use scenarios × two arms = **10 runs**.
- Two passive-discovery scenarios × two arms = **4 runs**.
- One matched seed (`1`) per scenario; same seeded arm order as the pilot.
- Same skill documents, task prompts, initial state, 120-second timeout, 30 ms
  service latency and 150 ms synchronous mutation delay.
- The updated command prints help for a bare group and supports the plural alias.
  The existing search/show argument syntax is unchanged.

The before/after comparison is descriptive: the earlier pilot was not rerun
contemporaneously on the old code. Model sampling, caching and service latency
can change outcomes between runs. Fresh no-skills controls help reveal general
timing changes, but one pair per scenario cannot establish a causal or
statistically reliable improvement.

## Scenarios and exact task wording

All seed-1 trials operate on `aks-dev-3201` in `rg-dev-3201`, starting with:

- Control plane and both node pools at Kubernetes **1.33.5**.
- A running cluster with provisioning state `Succeeded`.
- `system`: three nodes, autoscaling disabled.
- `apps`: two nodes, autoscaling enabled, bounds **1–3**.
- An eligible upgrade target of **1.34.2** in the fake service.

Every prompt is constructed as:

> You are operating AKS cluster aks-dev-3201 in resource group rg-dev-3201.
> **[Task below]** Use the available CLI to carry out the task and verify the
> resulting state. Do not just provide instructions. Report what you changed and
> the final state. The CLI is already authenticated. Work autonomously with the
> information provided.

### 1. Fixed-size node pool (`manual-scale`)

> Set the apps node pool to a fixed size of 6 nodes, with autoscaling disabled.
> Leave the system pool unchanged.

Pass condition: `apps.count == 6`, autoscaling off, system pool unchanged, cluster
still running, Kubernetes version unchanged, no unfinished operation, and a
successful verification read. The initial enabled autoscaler rejects a direct
manual scale until it is disabled.

### 2. Autoscaler bounds (`autoscaler`)

> Keep autoscaling enabled on the apps pool and change its bounds to a minimum
> of 2 and a maximum of 9 nodes. Leave the system pool unchanged.

Pass condition: autoscaling enabled, min/max **2–9**, system pool unchanged, and
the common cluster/verification invariants. Provisioning nine nodes immediately
is not required: the task changes bounds, not a fixed node count.

### 3. Control-plane-only upgrade (`control-plane-upgrade`)

> Upgrade only the control plane to Kubernetes 1.34.2. Leave all node pool
> versions unchanged.

Pass condition: control plane **1.34.2**, both pools still **1.33.5**, system pool
unchanged, running cluster, completed operation, and verification. Omitting
`--control-plane-only` upgrades the pools too and fails the state oracle.

### 4. Stop development cluster (`stop-dev`)

> Stop this development cluster to save compute costs. Preserve the cluster and
> its node pool configuration for a later restart.

Pass condition: cluster power state `Stopped`, provisioning complete, original
cluster and pool configuration preserved, and a successful cluster-state read.
Deleting the cluster or scaling pools to zero does not satisfy the task.

### 5. Scaling with a transient failure (`transient-scale`)

> Set the apps node pool to a fixed size of 6 nodes, with autoscaling disabled.
> Leave the system pool unchanged. Handle transient service failures if they occur.

The first `az aks nodepool scale` receives a synthetic HTTP **429
TooManyRequests**, with `Retry-After: 1 second`. Pass condition is the same final
state and verification as fixed-size scaling. The fixture records the injected
failure and subsequent attempts.

All scenarios additionally require the original cluster and both pools to exist
without extra clusters. Success depends on authoritative host-owned state, not
on the agent's final prose. The source workflows are linked in
[the benchmark design](benchmark.md#research-derived-scenarios).

## Guided versus passive prompts

In **guided use**, only the skills arm gets this additional sentence:

> Local AKS runbooks are available through 'az aks skill list', 'az aks skill
> search', and 'az aks skill show'. Consult a relevant runbook before making changes.

The no-skills arm gets the ordinary task prompt. In **passive discovery**, both
arms get the same ordinary prompt; only treatment CLI help advertises skills.
The passive subset is fixed-size scaling and the control-plane-only upgrade,
matching the earlier pilot.

The prompts do not explicitly request `--help` or the new plural alias. Trace
analysis therefore checks whether agents actually encounter the new help before
attributing any observed change to it.

## Evidence locations

New raw artifacts remain local and gitignored:

- `main/benchmark-results/sol-help-guided-20261113/`
- `main/benchmark-results/sol-help-passive-20261113/`

Historical raw artifacts remain under the previous worktree:

- `prototype/benchmark-results/sol-pilot/`
- `prototype/benchmark-results/sol-passive/`

Each trial retains the exact prompt, initial and final state, CLI trace, readable
timeline, isolation checks, model telemetry and scored result. Azure API request
counts are modeled; model inference spans are exported by Copilot. Neither should
be confused with a count of physical network packets or TLS connections.
