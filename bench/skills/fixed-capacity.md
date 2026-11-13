# Set fixed node pool capacity

Use for an authorized fixed count on a manually managed pool. Reuse recent pool
output; otherwise read `az aks nodepool show -g RG --cluster-name CLUSTER -n POOL`
once. Check mode, count, enableAutoScaling and provisioningState.

If autoscaling is enabled, run this dependent sequence in one shell call after
substituting the user's values; omit the first command if already disabled:

```sh
az aks nodepool update -g RG --cluster-name CLUSTER -n POOL --disable-cluster-autoscaler -o none &&
az aks nodepool scale -g RG --cluster-name CLUSTER -n POOL --node-count COUNT -o none &&
az aks nodepool show -g RG --cluster-name CLUSTER -n POOL
```

Success: requested count, autoscaling false, provisioning Succeeded. If already
correct, the initial read verifies completion. To compare other pools, substitute
one final nodepool list for show. Default writes wait; don't add polling to them.

System pools require at least two nodes. Preserve unrelated pools. Retain
autoscaling by changing bounds when that is the user's intent; don't apply manual
pool sizing to NAP-managed capacity. For 429, honor Retry-After and retry only the
failed command with bounded backoff; for an in-progress 409, wait before retrying.

Source: https://learn.microsoft.com/en-us/azure/aks/scale-cluster
