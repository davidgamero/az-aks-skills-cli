# Recover a failed node pool upgrade

For `NodePoolMcVersionIncompatible`, compare the current control-plane version
with the requested pool version. A node pool cannot be newer than its control
plane. Inspect the cluster once with `az aks show -g RG -n CLUSTER`, which also
includes agentPoolProfiles, and use `az aks get-upgrades -g RG -n CLUSTER` to
confirm the requested control-plane target is offered.

If the target pool version is newer and the task permits a control-plane upgrade:

```sh
az aks upgrade -g RG -n CLUSTER --kubernetes-version VERSION --control-plane-only --yes
az aks nodepool upgrade -g RG --cluster-name CLUSTER -n POOL --kubernetes-version VERSION
az aks show -g RG -n CLUSTER
```

Preserve unrelated pool versions and counts. An ordinary full-cluster upgrade
would also change other pools. Verify both the target version and the repaired
pool's provisioningState. If the task does not authorize the necessary change,
report the blocker rather than repeatedly retrying an incompatible version.

Source: https://learn.microsoft.com/en-us/troubleshoot/azure/azure-kubernetes/error-codes/nodepoolmcversionincompatible-error
The no-newer-than-control-plane rule is used here; older documentation's maximum
minor-version-skew figures can differ from current AKS policies.
