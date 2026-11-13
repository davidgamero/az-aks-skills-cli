# Repair a rollout blocked by a managed namespace quota

First distinguish admission rejection from scheduling capacity. A deployment can
request more replicas while its controller gets `FailedCreate: exceeded quota`;
node auto-provisioning cannot fix this namespace budget.

Inspect `kubectl describe deployment NAME -n NAMESPACE`,
`kubectl get events -n NAMESPACE`, or `kubectl describe resourcequota -n NAMESPACE`.
Check per-pod requests, the number of requested replicas, and the total quota.

For an ARM-managed namespace, edit the management-plane resource:

```sh
az aks namespace show -g RG --cluster-name CLUSTER -n NAMESPACE
az aks namespace update -g RG --cluster-name CLUSTER -n NAMESPACE --cpu-request APPROVED_BUDGET
kubectl rollout status deployment/NAME -n NAMESPACE --timeout=30s
kubectl get deployment NAME -n NAMESPACE -o json
```

`4000m` means four CPU cores; compute the required budget from the user's workload
and approval. Preserve existing CPU limits, memory quotas and ingress/egress
policies unless changes are authorized. Do not patch/delete the managed quota or
namespace through kubectl: the managed-fields reconciler blocks those changes.
Do not lower per-pod requests just to squeeze past a quota when that changes the
workload contract. Verify ready replicas, not only the requested spec.replicas.

Sources:
- https://learn.microsoft.com/en-us/azure/aks/managed-namespaces
- https://learn.microsoft.com/en-us/azure/aks/concepts-managed-namespaces
