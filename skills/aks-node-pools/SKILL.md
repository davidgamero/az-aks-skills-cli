# Inspect AKS node pools

1. List pool configuration:
   `az aks nodepool list --resource-group "$RESOURCE_GROUP" --cluster-name "$CLUSTER" -o json`.
2. Summarize each pool's mode, Kubernetes version, VM size, node count,
   availability zones, and autoscaling minimum and maximum counts.
3. With a configured kubectl context, use `kubectl get nodes -o wide` to compare
   actual node readiness with the configured capacity.
4. Check workload scheduling constraints, pool taints, and resource requests
   when investigating unused capacity or pending pods.

Expected output: a pool inventory and any capacity or configuration mismatches
that warrant further investigation.
