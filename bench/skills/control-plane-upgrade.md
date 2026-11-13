# Upgrade only the control plane

Use for an authorized control-plane-only upgrade. Reuse a recent aks show response:
it includes both the control plane and agentPoolProfiles, so another pool inventory
is unnecessary. If needed, obtain that response and eligible targets in one shell
call with `az aks show -g RG -n CLUSTER && az aks get-upgrades -g RG -n CLUSTER`.
Use the requested eligible target, not simply the newest regional version.

Once the target and prerequisites are confirmed, run:

```sh
az aks upgrade -g RG -n CLUSTER --kubernetes-version VERSION --control-plane-only --yes -o none &&
az aks show -g RG -n CLUSTER
```

The final show verifies version, Succeeded state and unchanged pool versions.
Keep --control-plane-only: omitting it also upgrades pools. This operation is
incompatible with cluster autoupgrade; do not disable policy as a shortcut.
Supported non-LTS clusters cannot skip minor versions. Reuse completed preflight
checks; investigate workloads/PDBs when required by the task or a drain failure,
not as a new investigation for an already diagnosed version-only error. Default
upgrade waits; only --no-wait needs separate waiting.

Source: https://learn.microsoft.com/en-us/azure/aks/upgrade-aks-control-plane
