# Selective ingress with managed namespace ownership

Inspect all policies selecting the destination pods, the pod labels, and source
namespace labels. Identify whether the resources are standard NetworkPolicy or
another policy kind before reasoning about their semantics.

Standard Kubernetes NetworkPolicy allows the **union** of applicable rules.
An allow-all rule remains permissive when another narrow policy is added. An
ARM-owned policy must be changed through its owner; do not directly patch it.
If the existing managed policy allows same-namespace ingress, an additional
ordinary policy can selectively add the authorized external namespace:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: approved-ingress
  namespace: TARGET_NAMESPACE
spec:
  podSelector:
    matchLabels: {app: TARGET_APP}
  policyTypes: [Ingress]
  ingress:
  - from:
    - namespaceSelector:
        matchLabels: {kubernetes.io/metadata.name: SOURCE_NAMESPACE}
    ports:
    - {protocol: TCP, port: SERVICE_PORT}
```

Substitute observed labels and approved ports. A namespaceSelector and podSelector
in one peer are ANDed; separate peers are ORed. Retain egress behavior and source
egress permissions. Test actual traffic from both the authorized source and an
unrelated namespace, including pods with similar labels. Verify existing traffic
and ARM ownership remain intact.

Sources:
- https://kubernetes.io/docs/concepts/services-networking/network-policies/
- https://learn.microsoft.com/en-us/azure/aks/network-policy-best-practices
- https://learn.microsoft.com/en-us/azure/aks/concepts-managed-namespaces
