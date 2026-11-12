# Configure autoscaler bounds

Inspect the requested pool with
`az aks nodepool show -g RG --cluster-name CLUSTER -n POOL`.
If enableAutoScaling is true, use:

```sh
az aks nodepool update -g RG --cluster-name CLUSTER -n POOL --update-cluster-autoscaler --min-count MIN --max-count MAX
```

If autoscaling is disabled, substitute --enable-cluster-autoscaler. Choose bounds
from the user's request; the minimum must not exceed the maximum. Do not manually
scale a pool whose autoscaler should remain enabled. Do not change the cluster-wide
autoscaler profile or another pool. Verify the target pool's enableAutoScaling,
minCount and maxCount with nodepool show. Count need not immediately equal either
bound; these are autoscaler settings, not a demand to provision MAX nodes now.

Source: https://learn.microsoft.com/en-us/azure/aks/cluster-autoscaler
