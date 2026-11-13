# AKS Automatic: research and benchmark scenarios

Research date: November 13, 2026.

## What makes Automatic different

Microsoft's [Automatic overview](https://learn.microsoft.com/en-us/azure/aks/intro-aks-automatic)
describes a distinct cluster SKU, not merely a Standard cluster with the cluster
autoscaler enabled:

- `sku.name = Automatic`, with the **Standard pricing tier**.
- Node auto-provisioning (NAP) creates workload capacity; system infrastructure
  is AKS-managed for newly created Automatic clusters.
- Kubernetes auto-upgrades use **stable**, and node OS upgrades use **NodeImage**.
- Azure CNI Overlay with Cilium, managed networking, workload identity/OIDC and
  other managed defaults are preconfigured.
- Maintenance scheduling is configurable; changing a schedule is different from
  changing or disabling an upgrade channel.

The current [managed-network quickstart](https://learn.microsoft.com/en-us/azure/aks/automatic/quick-automatic-managed-network)
requires Azure CLI **2.86.0+**, creates clusters with `az aks create --sku automatic`,
and describes managed system pools through `hostedSystemProfile.enabled`.
It also shows `--enable-hosted-system`; the benchmark accepts both explicit
selection and the documented new-cluster default. Its multi-line example is
missing a continuation before that flag, so the example below uses valid shell
continuations.

The [planned-maintenance guide](https://learn.microsoft.com/en-us/azure/aks/planned-maintenance)
distinguishes three independent configurations:

| Configuration | Controls |
|---|---|
| `default` | AKS platform/component releases |
| `aksManagedAutoUpgradeSchedule` | Kubernetes version auto-upgrades |
| `aksManagedNodeOSUpgradeSchedule` | Node OS/image auto-upgrades |

Weekly windows use `--schedule-type Weekly`, `--day-of-week`, `--interval-weeks`,
`--duration`, `--start-time` and `--utc-offset`. The guide recommends windows of at
least four hours. These schedules are best-effort, not a guarantee that urgent
maintenance can never occur outside them.

### Documentation discrepancy

The quickstart says Base-to-Automatic migration is unsupported. The newer
[migration guide](https://learn.microsoft.com/en-us/azure/aks/automatic/aks-automatic-sku-migration)
documents that path in **preview**, with an extension, feature registration and
many configuration prerequisites. The initial two scenarios use new-cluster
creation and established maintenance operations, avoiding that version-sensitive
migration path. They do not model Kubernetes workload scheduling or pod readiness
SLA behavior.

## Scenario A — Create an Automatic cluster

**ID:** `automatic-create`

**Task:**

> Create a new AKS Automatic cluster named aks-auto-3201 in the existing resource
> group rg-dev-3201 in eastus. Use AKS-managed networking and managed system node
> pools, retaining the Automatic defaults for node provisioning and upgrade
> channels. The required resource providers are already registered. Verify the
> cluster SKU, managed-system status, provisioning mode and upgrade channels.
> Do not deploy workloads or create manually sized node pools.

The name suffix is seeded; this example is seed 1. The fixture starts with no
cluster, so success requires a real mutation of the fake state.

**Expected command family:**

```sh
az aks create -g RG -n CLUSTER --location eastus \
  --sku automatic --enable-hosted-system
az aks show -g RG -n CLUSTER
```

**State checks:** exactly the requested cluster; provisioning succeeded; SKU
Automatic, tier Standard; hosted system pools enabled; node provisioning Auto;
stable/NodeImage channels; managed-network defaults; no manually sized pools.
A subsequent state read must verify the result.

**Useful negative controls:** `--tier standard` without `--sku automatic` creates
a Base cluster; selecting a Free tier for Automatic fails; specifying fixed
manual capacity does not satisfy the requested Automatic deployment.

**Why it is useful:** distinguishes current Automatic knowledge from ordinary AKS
creation habits, and tests whether one general-purpose skill can avoid redundant
feature configuration and incorrect SKU/tier assumptions.

## Scenario B — Reschedule Automatic maintenance

**ID:** `automatic-maintenance`

**Task:**

> On the existing AKS Automatic cluster aks-auto-3201 in rg-dev-3201, schedule
> Kubernetes auto-upgrades every Sunday from 02:00 to 06:00 UTC and node OS/image
> upgrades every Saturday from 03:00 to 07:00 UTC. Keep the existing upgrade
> channels, Automatic SKU, node provisioning, and unrelated default maintenance
> configuration unchanged. Verify both schedules. Do not start an upgrade now.

The fixture has a running Automatic cluster with three existing windows. The
two relevant windows initially have different days/times; the unrelated
`default` window serves as an invariant.

**Expected command family:**

```sh
az aks maintenanceconfiguration list -g RG --cluster-name CLUSTER
az aks maintenanceconfiguration update -g RG --cluster-name CLUSTER \
  -n aksManagedAutoUpgradeSchedule --schedule-type Weekly \
  --day-of-week Sunday --interval-weeks 1 --duration 4 \
  --start-time 02:00 --utc-offset +00:00
az aks maintenanceconfiguration update -g RG --cluster-name CLUSTER \
  -n aksManagedNodeOSUpgradeSchedule --schedule-type Weekly \
  --day-of-week Saturday --interval-weeks 1 --duration 4 \
  --start-time 03:00 --utc-offset +00:00
az aks maintenanceconfiguration list -g RG --cluster-name CLUSTER
```

**State checks:** the two exact configuration names have the requested weekly
cadence, day, time, duration and UTC offset; `default` is unchanged; the rest of
the cluster is unchanged; both schedules are read in their final target
configuration. Reads can be interleaved with independent updates: a read counts
only while the observed schedule still matches its current version. A generic
cluster `show` alone does not verify maintenance resources.

**Useful negative controls:** editing only `default`; using a single window for
both upgrade types; disabling upgrades instead of scheduling them; using an
undersized window; changing the cluster version immediately.

**Why it is useful:** requires choosing the correct child resources and preserving
Automatic-specific defaults. It tests a more knowledge-sensitive workflow than
the existing simple scaling tasks, with a state-based correctness oracle.

## Experiment setup

Both scenarios use the same skills/no-skills runner, model selection, fresh
containers, host-owned state and timestamps as the existing matrix. Skills contain
general procedures with placeholders, not these fixture names or target times.
New Automatic trials are reported separately from the help-change rerun because
adding scenarios and skills changes the experimental inputs.

The simulator now has stateful maintenanceconfiguration list/show/add/update/delete
handlers, validates weekly windows and Automatic defaults, and keeps child
schedules out of the cluster's public `show` response. Auxiliary resource-group
and provider inspection is fixture-backed. It does not claim complete Automatic
API fidelity; only the modeled fields and command options are graded.

Run the new pair with:

```sh
PYTHONPATH=bench .venv-bench/bin/python -m aks_bench run \
  --bwrap /tmp/opencode/bubblewrap/usr/bin/bwrap --model gpt-6.1-sol \
  --scenarios automatic-create automatic-maintenance --seed 1 \
  --output benchmark-results/automatic-guided
```

Use a fresh output directory and `--discovery passive` for the same prompts
without the runbook hint. The default complete scenario list now includes both
Automatic tasks in addition to the five original Standard-cluster tasks.
