# Recover a failed node pool upgrade

Use for NodePoolMcVersionIncompatible when the requested pool version is newer
than its control plane. Reuse the error and recent cluster data. One aks show
includes pool versions/counts; one get-upgrades confirms the eligible target.
Don't repeat failure-history searches once the version mismatch is established.

With an eligible target and authorization for the control-plane change, execute
the complete sequence in one shell call:

```sh
az aks upgrade -g RG -n CLUSTER --kubernetes-version VERSION --control-plane-only --yes -o none &&
az aks nodepool upgrade -g RG --cluster-name CLUSTER -n POOL --kubernetes-version VERSION -o none &&
az aks show -g RG -n CLUSTER
```

The final response verifies both target versions, pool recovery and unchanged
other pools/counts. This includes the control-plane procedure; no second skill is
needed. Default upgrades wait, so avoid extra waits/polling unless using --no-wait.

Keep --control-plane-only to preserve other pools. Do not bypass auto-upgrade
policy or version support rules. This management-plane validation error is not
evidence of a PDB, node-health or credential problem; investigate those only when
the task requires it or the next error identifies one. If the target/change is
not authorized or supported, report that blocker instead of retrying blindly.

Source: https://learn.microsoft.com/en-us/troubleshoot/azure/azure-kubernetes/error-codes/nodepoolmcversionincompatible-error
The no-newer-than-control-plane rule is used here; older documentation's maximum
minor-version-skew figures can differ from current AKS policies.
