# Configure autoscaler bounds

Use for a requested autoscaler range on an existing managed node pool. Reuse
recent pool data, or call nodepool show once. Select the flag from that state:
enabled → `--update-cluster-autoscaler`; disabled → `--enable-cluster-autoscaler`.
If already correct, finish from that verification read.

With autoscaling enabled, run the write and verification together:

```sh
az aks nodepool update -g RG --cluster-name CLUSTER -n POOL --update-cluster-autoscaler --min-count MIN --max-count MAX -o none &&
az aks nodepool show -g RG --cluster-name CLUSTER -n POOL
```

Verify enableAutoScaling, minCount, maxCount and provisioningState. Preserve other
pools and the cluster-wide profile. Choose the authorized bounds; MIN cannot
exceed MAX. Node count need not immediately equal a bound. Do not force a manual
scale to MAX or repeatedly reread the same configuration. If preserving other
pools must be demonstrated, use one final nodepool list instead of target show.

Source: https://learn.microsoft.com/en-us/azure/aks/cluster-autoscaler
