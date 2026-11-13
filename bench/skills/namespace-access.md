# Repair namespace read access at the correct authorization plane

Namespace User/Contributor permit management-plane operations; retrieving
connection settings does not imply authorization to read Kubernetes pods.
Confirm the intended principal, authenticated context, failing operation and
approved managed-namespace resource scope. Inspect existing assignments:

```sh
az role assignment list --assignee PRINCIPAL_OBJECT_ID --scope NAMESPACE_RESOURCE_ID --include-inherited
```

For approved read-only data-plane access, assign the namespace-scoped Reader:

```sh
az role assignment create --assignee-object-id PRINCIPAL_OBJECT_ID --assignee-principal-type User --role 'Azure Kubernetes Service RBAC Reader' --scope NAMESPACE_RESOURCE_ID
```

Use the principal's actual type. Preserve other roles; allow propagation before
repeated edits. Verify pod reads in the intended namespace, denied secret reads
and denied reads elsewhere with that principal's context. `kubectl auth can-i`
returns a nonzero status for a denial; that is expected negative evidence.
Admin credentials or cluster-scoped Reader would invalidate the requested boundary.

Sources:
- https://learn.microsoft.com/en-us/azure/aks/concepts-managed-namespaces
- https://learn.microsoft.com/en-us/azure/aks/managed-namespaces
