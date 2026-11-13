# Remove ARM management and retain Kubernetes resources

Read `az aks namespace show -g RG --cluster-name CLUSTER -n NAMESPACE` and record
the namespace, deployment and PVC identities before changing anything.
If the managed resource's `deletePolicy` is already `Keep`, reuse it. Otherwise:

```sh
az aks namespace update -g RG --cluster-name CLUSTER -n NAMESPACE --delete-policy Keep
az aks namespace delete -g RG --cluster-name CLUSTER -n NAMESPACE --yes
```

Delete only the management resource. `Delete` cascades to the Kubernetes namespace
and its contents; deleting and recreating names does not preserve identities/data.
Verify ARM absence with show/list, then retained namespace/workload/PVC UIDs,
storage continuity and workload readiness. Check the management marker is removed.
Do not assume exact cleanup behavior of every generated child policy across versions.

Sources:
- https://learn.microsoft.com/en-us/azure/aks/concepts-managed-namespaces
- https://learn.microsoft.com/en-us/azure/aks/managed-namespaces
