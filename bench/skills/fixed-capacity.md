# Set fixed node pool capacity

Use the cluster, resource group, pool and desired count supplied by the user.

1. Inspect the target pool once with `az aks nodepool show -g RG --cluster-name CLUSTER -n POOL`.
   This returns count, enableAutoScaling, mode, version and provisioningState.
2. If enableAutoScaling is true, disable it before manual scaling:
   `az aks nodepool update -g RG --cluster-name CLUSTER -n POOL --disable-cluster-autoscaler`.
   Manual scaling while autoscaling is enabled is rejected. If the user wants
   autoscaling retained, update bounds instead of forcing a fixed count.
3. Use `az aks nodepool scale -g RG --cluster-name CLUSTER -n POOL --node-count COUNT`.
   This normally waits for completion; avoid extra polling unless using --no-wait.
4. Verify the count and enableAutoScaling with a final nodepool show. Do not change
   unrelated pools. System pools require at least two nodes; user pools may use zero.
5. For a 429, honor Retry-After and retry the failed command with bounded backoff.
   Do not repeat already successful configuration changes. For a 409 indicating an
   ongoing operation, wait for that operation rather than launching more mutations.

Source: https://learn.microsoft.com/en-us/azure/aks/scale-cluster
