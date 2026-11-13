# Repair the capacity constraint owned by NAP

Inspect Pending pod Events/requests/placement, cluster nodeProvisioningProfile,
Karpenter NodePools, AKSNodeClasses and NodeClaims. ARM agent pools and Kubernetes
NodePools are different resources. Scaling an ARM pool does not raise a NAP CRD limit.

Distinguish no matching requirements/taints, exhausted pool limits, failed NodeClaim
provisioning and Azure quota. Query regional quota only when the evidence points
there. For a dynamic pool, CPU/memory limits cap provisioned capacity; account for
whole node sizes, not only the pending pod's request. For example, another node
must fit under the approved aggregate ceiling.

```sh
kubectl get nodepools.karpenter.sh,nodeclaims -o yaml
kubectl patch nodepool POOL --type merge -p '{"spec":{"limits":{"cpu":"APPROVED_CPU"}}}'
```

Substitute the approved value. Preserve requirements, taints, NodeClass, disruption
policy and workload requests. Static NodePools instead use replicas and limits.nodes;
adding/removing replicas cannot switch an existing pool between static and dynamic.
Verify provisioned NodeClaims, Ready nodes and scheduled Ready workloads. If the
approved ceiling cannot fit required node capacity, report that constraint.

Sources:
- https://learn.microsoft.com/en-us/azure/aks/node-auto-provisioning-node-pools
- https://learn.microsoft.com/en-us/troubleshoot/azure/azure-kubernetes/extensions/troubleshoot-node-auto-provision
