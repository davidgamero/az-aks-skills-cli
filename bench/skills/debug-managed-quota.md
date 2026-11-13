# Repair a rollout blocked by a managed namespace quota

Use after FailedCreate/exceeded quota establishes admission rejection. NAP cannot
fix a namespace budget. Reuse deployment/events already read; otherwise inspect
the deployment and quota once. Determine desired replicas, per-pod requests and
other workloads' usage, then compare with the approved budget.

For an ARM-managed namespace, read its ARM configuration once if not already
known: `az aks namespace show -g RG --cluster-name CLUSTER -n NAMESPACE`.
Retain the other quotas and policies. Then run one dependent write/verification:

```sh
az aks namespace update -g RG --cluster-name CLUSTER -n NAMESPACE --cpu-request APPROVED_BUDGET -o none &&
kubectl rollout status deployment/NAME -n NAMESPACE --timeout=120s
```

Use a task-appropriate timeout. Rollout success verifies readiness against the
already-known desired count; another identical deployment read is optional, not
an automatic next step. If rollout fails, inspect the new condition before acting.

Do not rescale when spec.replicas already has the desired value. Do not repeat
network-policy/node-capacity investigations once quota is confirmed. Change only
the approved quota field; preserve per-pod requests, limits, memory and networking.
Managed fields are reconciled by ARM: kubectl patch/delete is not the repair.

Sources:
- https://learn.microsoft.com/en-us/azure/aks/managed-namespaces
- https://learn.microsoft.com/en-us/azure/aks/concepts-managed-namespaces
