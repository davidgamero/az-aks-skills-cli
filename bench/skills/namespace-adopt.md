# Adopt an existing namespace without overwriting it

Inspect the existing namespace, ResourceQuota and NetworkPolicy resources and
record workload/PVC UIDs. Read the managed namespace once if it already exists:

```sh
kubectl get namespace NAMESPACE -o yaml
kubectl get resourcequota,networkpolicy,deployment,pvc -n NAMESPACE -o yaml
az aks namespace show -g RG --cluster-name CLUSTER -n NAMESPACE
az aks namespace add --help
```

Translate observed quota quantities, policy behavior and user labels/annotations
into the ARM definition. Preserve equivalent CPU/memory quantities, ignoring
server-generated metadata such as UIDs. Use `--adoption-policy IfIdentical` with
`az aks namespace add`, supplying `--cpu-request`, `--cpu-limit`,
`--memory-request`, `--memory-limit`, `--ingress-policy`, `--egress-policy`,
`--labels` and `--annotations` from those reads. Select the authorized delete
policy independently. `Never` rejects an existing namespace; `Always` can
overwrite it. A mismatch calls for correcting the proposed definition.

Verify the ARM resource, unchanged live policies/quota and retained namespace,
workload and storage identities. Verify workload readiness after adoption.

Sources:
- https://learn.microsoft.com/en-us/azure/aks/concepts-managed-namespaces
- https://learn.microsoft.com/en-us/azure/aks/managed-namespaces
