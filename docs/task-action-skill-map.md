# Observed task → action → skill-read map

This maps observed actions, not inferred internal reasoning or guaranteed triggers.
Counts below use **valid, skill-enabled, hint-free runs across retained experiments**.
Those experiments used different harness revisions, so the counts are descriptive,
not an adoption-rate estimate. Explicitly hinted runs are excluded.

## Validated path to a read

```text
Task: recover failed AKS Automatic creation
  → inspect cluster existence, failed activity log and provider state
  → az aks create --help
      exposes Related Commands: az aks skill
  → az aks skill --help
  → az aks skill list                    [2 reader sessions]
     OR az aks skill search automatic    [3 reader sessions]
  → az aks skill show --name aks-automatic-create  [5 sessions]
  → az aks skill show --name aks-debug-provider    [4 of those sessions]
```

There were **5 readers among 6 valid provider-recovery runs**. All five received
the advertising help result before requesting the skill command. All five also
completed provider registration before opening the first full skill document;
registration and skill-group exploration happened in the same part of the task.
The documents were therefore consulted while preparing remaining creation and
verification work, rather than as the first diagnostic action.

## Task/action coverage

| Task | Observed action family | Valid hint-free runs | Read a skill | Interpretation |
|---|---|---:|---:|---|
| Failed Automatic creation/provider registration | Activity log/provider diagnosis → create help → optional skill lookup | 6 | 5 | Only validated reader path so far |
| New Automatic creation | Create help → ordinary creation/verification | 5 | 0 | Same command-help entry alone is insufficient |
| Automatic maintenance | Maintenanceconfiguration help/list/update | 5 | 0 | Configuration help exposure did not lead to a read |
| Managed-namespace quota repair | Kubernetes deployment/quota inspection → namespace help/update | 6 | 0 | A failure plus help is not by itself a trigger |
| Fixed-size scaling | Direct nodepool show/update/scale | 6 | 0 | No advertising help entry encountered |
| Control-plane-only upgrade | Cluster/version inspection and upgrade/verification | 2 | 0 | No observed read in the passive runs |
| Failed node-pool version upgrade | Version, operation and node diagnostics | 2 | 0 | No read in valid runs; see exploratory exception below |

Autoscaler-bounds changes, stop/start and transient-scaling recovery were tested
with explicit hints earlier, but the retained data does not establish their
natural-discovery behavior. ACR, workload-identity and PDB-repair recipes have
designs but no corresponding live benchmark scenarios yet.

## Exploratory exception

One earlier version-skew run followed:

```text
failed pool-upgrade task
  → diagnostics and a bundle of aks/nodepool/upgrade help pages
  → az aks skill --help
  → az aks skill search upgrade
  → show aks-debug-version-skew
  → show aks-control-plane-upgrade
```

That run had simulator coverage gaps. It demonstrates a possible discovery route,
but is not a validated performance example. Another invalid provider-recovery run
also followed creation help into skills. Both remain outside the table above.

## Role of each action

| Action | Observed role |
|---|---|
| Failed activity-log/provider reads | Establish the fault; these are not skill advertisements |
| `az aks create --help` | Actual discovery surface in all validated reader sessions |
| `az provider register --wait` | Repair step already completed before document reading; not the advertisement |
| `az aks skill --help` | Learn the custom interface |
| `list` or `search automatic` | Select document IDs |
| `show --name ...` | Actual skill-body read |
| Unix man pages / web docs | No observed source of the skill command in reader sessions |

The most useful association is **failed-creation context + creation-help exposure
→ optional skill lookup**. It is not a deterministic rule: a valid run with that
same context and help entry still skipped skills. The latest controlled study
likewise had 16 help-exposed treatment runs but only three readers.

See [the discovery review](skill-discovery-review.md) for exact trace anchors,
timestamps and the prefetched-two-documents behavior. The local aggregate audit
is `benchmark-results/skill-discovery-review/audit.json`.
